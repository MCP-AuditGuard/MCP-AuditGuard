from __future__ import annotations

import json

from pathlib import Path

from core.dynamic_scan_models import (
    DiscoveryContext,
    DiscoverySourceStatus,
    McpProduct,
    McpScope,
    McpTransport,
    PermissionEffect,
    PolicySourceCoverage,
    ServerEnabledState,
    ServerSupportState,
    StdioConnectionConfig,
    StreamableHttpConnectionConfig,
)
from core.mcp_discovery import discover_mcp_servers


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False),
        encoding="utf-8",
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_context(
    *,
    user_home: Path,
    project_root: Path,
    current_working_directory: Path | None = None,
    trusted: bool = True,
) -> DiscoveryContext:
    return DiscoveryContext(
        current_working_directory=(
            current_working_directory or project_root
        ),
        project_root=project_root,
        user_home=user_home,
        include_trusted_project_config=trusted,
    )


def test_discovers_codex_user_stdio_and_http_servers_safely(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    write_text(
        user_home / ".codex" / "config.toml",
        """
[mcp_servers.filesystem]
command = "C:/Tools/npx.cmd"
args = ["-y", "secret-package", "--token", "TEST_SECRET"]
env = { TOKEN = "TEST_SECRET" }
env_vars = ["HOST_TOKEN"]
enabled_tools = ["search"]
disabled_tools = ["delete"]

[mcp_servers.remote]
url = "https://user:password@example.com/mcp?token=TEST_SECRET"
http_headers = { Authorization = "Bearer TEST_SECRET" }
env_http_headers = { "X-API-Key" = "HOST_API_KEY" }
bearer_token_env_var = "HOST_BEARER_TOKEN"
enabled = false
""".strip(),
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
            trusted=False,
        )
    )

    servers = {server.server_name: server for server in result.servers}
    filesystem = servers["filesystem"]
    remote = servers["remote"]

    assert filesystem.product == McpProduct.CODEX
    assert filesystem.scope == McpScope.USER
    assert filesystem.transport == McpTransport.STDIO
    assert isinstance(filesystem.connection, StdioConnectionConfig)
    assert filesystem.connection.env_values == {"TOKEN": "TEST_SECRET"}
    assert filesystem.connection.env_references == {
        "HOST_TOKEN": "HOST_TOKEN"
    }
    assert filesystem.command_basename == "npx.cmd"
    assert filesystem.argument_count == 4
    assert filesystem.tool_policy.codex_enabled_tools_configured is True
    assert filesystem.tool_policy.codex_enabled_tools == ["search"]
    assert filesystem.tool_policy.codex_disabled_tools == ["delete"]
    assert (
        filesystem.tool_policy.source_coverage
        == PolicySourceCoverage.INCOMPLETE
    )

    assert remote.transport == McpTransport.STREAMABLE_HTTP
    assert remote.enabled_state == ServerEnabledState.DISABLED
    assert remote.support_state == ServerSupportState.SUPPORTED
    assert remote.support_reason_code == "server_disabled"
    assert remote.connection is None
    assert remote.remote_origin == "https://example.com"

    safe_output = str(result.model_dump())
    for secret in (
        "TEST_SECRET",
        "HOST_TOKEN",
        "HOST_API_KEY",
        "HOST_BEARER_TOKEN",
        "secret-package",
        "password",
    ):
        assert secret not in safe_output


def test_codex_distinguishes_missing_and_explicit_empty_enabled_tools(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    write_text(
        user_home / ".codex" / "config.toml",
        """
[mcp_servers.missing]
command = "python"

[mcp_servers.explicit-empty]
command = "python"
enabled_tools = []
""".strip(),
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
            trusted=False,
        )
    )
    servers = {server.server_name: server for server in result.servers}

    missing_policy = servers["missing"].tool_policy
    empty_policy = servers["explicit-empty"].tool_policy

    assert missing_policy.codex_enabled_tools == []
    assert missing_policy.codex_enabled_tools_configured is False
    assert empty_policy.codex_enabled_tools == []
    assert empty_policy.codex_enabled_tools_configured is True


def test_codex_nearest_project_config_wins_without_field_merge(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    nested = project_root / "packages" / "app"
    current = nested / "src"
    current.mkdir(parents=True)

    write_text(
        user_home / ".codex" / "config.toml",
        """
[mcp_servers.shared]
command = "user-python"
args = ["user.py"]
env = { USER_ONLY = "value" }
""".strip(),
    )
    write_text(
        project_root / ".codex" / "config.toml",
        """
[mcp_servers.shared]
command = "root-python"
args = ["root.py"]
""".strip(),
    )
    write_text(
        nested / ".codex" / "config.toml",
        """
[mcp_servers.shared]
command = "nearest-python"
args = ["nearest.py"]
""".strip(),
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
            current_working_directory=current,
        )
    )

    assert len(result.servers) == 1
    server = result.servers[0]
    assert server.scope == McpScope.PROJECT
    assert server.source_label == "Codex project config (level 1)"
    assert isinstance(server.connection, StdioConnectionConfig)
    assert server.connection.command == "nearest-python"
    assert server.connection.args == ["nearest.py"]
    assert server.connection.env_values == {}
    assert sum(
        issue.code == "shadowed_server_definition"
        for issue in result.issues
    ) == 2


def test_untrusted_project_configs_are_not_read(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    write_text(
        project_root / ".codex" / "config.toml",
        "this is not valid TOML =",
    )
    write_json(
        project_root / ".mcp.json",
        {"mcpServers": {"project-server": {"command": "project"}}},
    )
    write_text(
        user_home / ".codex" / "config.toml",
        '[mcp_servers.user]\ncommand = "python"',
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
            trusted=False,
        )
    )

    assert [server.server_name for server in result.servers] == ["user"]
    assert result.source_statuses["codex:project"] == (
        DiscoverySourceStatus.INACCESSIBLE
    )
    assert result.source_statuses["claude:project"] == (
        DiscoverySourceStatus.INACCESSIBLE
    )
    assert not any(
        issue.code == "source_parse_failed" for issue in result.issues
    )


def test_claude_local_project_user_precedence_uses_whole_entry(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)

    write_json(
        user_home / ".claude.json",
        {
            "mcpServers": {
                "shared": {
                    "type": "stdio",
                    "command": "user-command",
                    "env": {"USER_ONLY": "value"},
                }
            },
            "projects": {
                str(project_root.resolve()): {
                    "mcpServers": {
                        "shared": {
                            "type": "stdio",
                            "command": "local-command",
                            "args": ["local.py"],
                        }
                    }
                }
            },
        },
    )
    write_json(
        project_root / ".mcp.json",
        {
            "mcpServers": {
                "shared": {
                    "type": "stdio",
                    "command": "project-command",
                    "args": ["project.py"],
                }
            }
        },
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
        )
    )

    assert len(result.servers) == 1
    server = result.servers[0]
    assert server.product == McpProduct.CLAUDE
    assert server.scope == McpScope.LOCAL
    assert server.source_label == "Claude local config"
    assert isinstance(server.connection, StdioConnectionConfig)
    assert server.connection.command == "local-command"
    assert server.connection.args == ["local.py"]
    assert server.connection.env_values == {}
    assert sum(
        issue.code == "shadowed_server_definition"
        for issue in result.issues
    ) == 2


def test_claude_project_server_explicit_disabled_is_not_executable(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    server_name = "project-server"
    write_json(
        user_home / ".claude.json",
        {
            "projects": {
                str(project_root.resolve()): {
                    "disabledMcpjsonServers": [server_name],
                    "enabledMcpjsonServers": [server_name],
                    "enableAllProjectMcpServers": True,
                }
            }
        },
    )
    write_json(
        project_root / ".mcp.json",
        {"mcpServers": {server_name: {"command": "python"}}},
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
        )
    )
    server = result.servers[0]

    assert server.scope == McpScope.PROJECT
    assert server.enabled_state == ServerEnabledState.DISABLED
    assert server.support_state == ServerSupportState.SUPPORTED
    assert server.support_reason_code == "server_disabled"
    assert server.connection is None


def test_claude_project_server_explicit_enabled(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    server_name = "project-server"
    write_json(
        user_home / ".claude.json",
        {
            "projects": {
                str(project_root.resolve()): {
                    "enabledMcpjsonServers": [server_name],
                }
            }
        },
    )
    write_json(
        project_root / ".mcp.json",
        {"mcpServers": {server_name: {"command": "python"}}},
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
        )
    )
    server = result.servers[0]

    assert server.enabled_state == ServerEnabledState.ENABLED
    assert isinstance(server.connection, StdioConnectionConfig)


def test_claude_project_enable_all_marks_server_enabled(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    server_name = "project-server"
    write_json(
        user_home / ".claude.json",
        {
            "projects": {
                str(project_root.resolve()): {
                    "enableAllProjectMcpServers": True,
                }
            }
        },
    )
    write_json(
        project_root / ".mcp.json",
        {"mcpServers": {server_name: {"command": "python"}}},
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
        )
    )
    server = result.servers[0]

    assert server.enabled_state == ServerEnabledState.ENABLED
    assert isinstance(server.connection, StdioConnectionConfig)


def test_claude_project_server_state_is_unknown_for_incomplete_source(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    server_name = "project-server"
    write_json(
        user_home / ".claude.json",
        {
            "projects": {
                str(project_root.resolve()): {
                    "disabledMcpjsonServers": server_name,
                    "enableAllProjectMcpServers": True,
                }
            }
        },
    )
    write_json(
        project_root / ".mcp.json",
        {"mcpServers": {server_name: {"command": "python"}}},
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
        )
    )
    server = result.servers[0]

    assert server.enabled_state == ServerEnabledState.UNKNOWN
    assert isinstance(server.connection, StdioConnectionConfig)
    assert any(
        issue.code == "project_activation_state_invalid"
        for issue in result.issues
    )


def test_claude_stdio_and_http_environment_references_are_not_resolved(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    write_json(
        user_home / ".claude.json",
        {
            "mcpServers": {
                "local-tool": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["server.py"],
                    "env": {
                        "STATIC": "value",
                        "TOKEN": "${HOST_TOKEN}",
                    },
                },
                "remote-tool": {
                    "type": "http",
                    "url": "https://example.com/mcp",
                    "headers": {
                        "Authorization": "Bearer ${HOST_BEARER}",
                        "X-API-Key": "${HOST_API_KEY}",
                        "X-Static": "TEST_SECRET",
                    },
                },
            }
        },
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
            trusted=False,
        )
    )
    servers = {server.server_name: server for server in result.servers}

    stdio = servers["local-tool"].connection
    assert isinstance(stdio, StdioConnectionConfig)
    assert stdio.env_values == {"STATIC": "value"}
    assert stdio.env_references == {"TOKEN": "HOST_TOKEN"}

    http = servers["remote-tool"].connection
    assert isinstance(http, StreamableHttpConnectionConfig)
    assert http.static_headers == {"X-Static": "TEST_SECRET"}
    assert http.environment_header_references == {
        "X-API-Key": "HOST_API_KEY"
    }
    assert (
        http.bearer_token_environment_reference == "HOST_BEARER"
    )
    assert "TEST_SECRET" not in str(result.model_dump())
    assert "HOST_BEARER" not in str(result.model_dump())


def test_entry_errors_are_isolated_and_unsupported_servers_remain_visible(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    write_text(
        user_home / ".codex" / "config.toml",
        """
[mcp_servers.valid]
command = "python"

[mcp_servers.invalid]
command = 123
""".strip(),
    )
    write_json(
        user_home / ".claude.json",
        {
            "mcpServers": {
                "websocket": {
                    "type": "ws",
                    "url": "wss://example.com/mcp",
                },
                "headers-helper": {
                    "type": "http",
                    "url": "https://example.com/mcp",
                    "headersHelper": "echo TEST_SECRET",
                },
            }
        },
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
            trusted=False,
        )
    )
    servers = {server.server_name: server for server in result.servers}

    assert servers["valid"].support_state == ServerSupportState.SUPPORTED
    assert servers["invalid"].support_state == ServerSupportState.INVALID
    assert servers["invalid"].connection is None
    assert (
        servers["websocket"].support_state
        == ServerSupportState.UNSUPPORTED
    )
    assert servers["websocket"].connection is None
    assert (
        servers["headers-helper"].support_reason_code
        == "headers_helper_not_supported"
    )
    assert "TEST_SECRET" not in str(result.model_dump())


def test_source_parse_failure_does_not_discard_other_sources(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    write_text(project_root / ".mcp.json", "{ invalid json")
    write_text(
        user_home / ".codex" / "config.toml",
        '[mcp_servers.codex]\ncommand = "python"',
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
        )
    )

    assert [server.server_name for server in result.servers] == ["codex"]
    assert result.source_statuses["claude:project"] == (
        DiscoverySourceStatus.INVALID
    )
    assert any(
        issue.code == "source_parse_failed" for issue in result.issues
    )


def test_same_server_name_in_codex_and_claude_remains_separate(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    write_text(
        user_home / ".codex" / "config.toml",
        '[mcp_servers.shared]\ncommand = "codex-command"',
    )
    write_json(
        user_home / ".claude.json",
        {"mcpServers": {"shared": {"command": "claude-command"}}},
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
            trusted=False,
        )
    )

    assert [
        (server.product, server.server_name)
        for server in result.servers
    ] == [
        (McpProduct.CODEX, "shared"),
        (McpProduct.CLAUDE, "shared"),
    ]
    assert result.servers[0].selection_id != result.servers[1].selection_id


def test_project_root_is_found_from_git_marker(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    current = project_root / "packages" / "app"
    current.mkdir(parents=True)
    (project_root / ".git").mkdir()
    write_json(
        project_root / ".mcp.json",
        {"mcpServers": {"project-server": {"command": "python"}}},
    )

    context = DiscoveryContext(
        current_working_directory=current,
        project_root=None,
        user_home=user_home,
        include_trusted_project_config=True,
    )
    result = discover_mcp_servers(context)

    assert len(result.servers) == 1
    assert result.servers[0].server_name == "project-server"
    assert result.servers[0].scope == McpScope.PROJECT


def test_invalid_claude_local_collection_is_not_reported_as_missing(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    write_json(
        user_home / ".claude.json",
        {
            "projects": {
                str(project_root.resolve()): {
                    "mcpServers": ["not-an-object"],
                }
            }
        },
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
        )
    )

    assert result.source_statuses["claude:local"] == (
        DiscoverySourceStatus.INVALID
    )
    assert any(
        issue.code == "invalid_server_collection"
        for issue in result.issues
    )


def test_collects_claude_permission_sources_without_exposing_rules(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    write_json(
        user_home / ".claude.json",
        {"mcpServers": {"docs": {"command": "python"}}},
    )
    write_json(
        user_home / ".claude" / "settings.json",
        {
            "permissions": {
                "deny": ["mcp__docs__delete", "Read(./secrets/**)"],
            }
        },
    )
    write_json(
        project_root / ".claude" / "settings.json",
        {"permissions": {"allow": ["mcp__docs__search"]}},
    )
    write_json(
        project_root / ".claude" / "settings.local.json",
        {"permissions": {"ask": ["mcp__docs__publish"]}},
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
        )
    )
    policy = result.servers[0].tool_policy

    assert policy.product == McpProduct.CLAUDE
    assert policy.source_coverage == PolicySourceCoverage.INCOMPLETE
    assert [
        (rule.effect, rule.tool_name_pattern)
        for rule in policy.claude_permission_rules
    ] == [
        (PermissionEffect.ASK, "mcp__docs__publish"),
        (PermissionEffect.ALLOW, "mcp__docs__search"),
        (PermissionEffect.DENY, "mcp__docs__delete"),
    ]
    safe_output = str(result.model_dump())
    assert "mcp__docs__publish" not in safe_output
    assert "mcp__docs__delete" not in safe_output
    assert "Read(./secrets/**)" not in safe_output


def test_collects_claude_global_deny_for_mcp_policy_evaluation(
    tmp_path: Path,
) -> None:
    user_home = tmp_path / "home"
    project_root = tmp_path / "project"
    write_json(
        user_home / ".claude.json",
        {"mcpServers": {"docs": {"command": "python"}}},
    )
    write_json(
        user_home / ".claude" / "settings.json",
        {
            "permissions": {
                "deny": ["*", "Read(./secrets/**)"],
            }
        },
    )

    result = discover_mcp_servers(
        make_context(
            user_home=user_home,
            project_root=project_root,
            trusted=False,
        )
    )
    policy = result.servers[0].tool_policy

    assert [
        (rule.effect, rule.tool_name_pattern)
        for rule in policy.claude_permission_rules
    ] == [(PermissionEffect.DENY, "*")]
    assert "Read(./secrets/**)" not in str(result.model_dump())


def test_missing_config_files_return_empty_discovery(
    tmp_path: Path,
) -> None:
    result = discover_mcp_servers(
        make_context(
            user_home=tmp_path / "home",
            project_root=tmp_path / "project",
            trusted=False,
        )
    )

    assert result.servers == []
    assert result.source_statuses["codex:user"] == (
        DiscoverySourceStatus.MISSING
    )
    assert result.source_statuses["claude:home"] == (
        DiscoverySourceStatus.MISSING
    )
    assert result.source_statuses["claude:user"] == (
        DiscoverySourceStatus.MISSING
    )
