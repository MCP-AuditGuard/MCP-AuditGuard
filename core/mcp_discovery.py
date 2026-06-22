from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from core.config_loader import ConfigLoadError, parse_mcp_server_entry
from core.dynamic_scan_models import (
    ClaudePermissionRule,
    DiscoveryContext,
    DiscoverySourceStatus,
    DiscoveredMcpServer,
    DynamicScanIssue,
    DynamicScanStage,
    HostToolPolicy,
    IssueLevel,
    McpDiscoveryResult,
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


_ENV_REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_BEARER_ENV_REFERENCE = re.compile(
    r"^Bearer\s+\$\{([A-Za-z_][A-Za-z0-9_]*)\}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _ClaudeProjectActivation:
    disabled_servers: frozenset[str] = frozenset()
    enabled_servers: frozenset[str] = frozenset()
    enable_all: bool = False
    source_valid: bool = False


@dataclass(frozen=True)
class _Source:
    product: McpProduct
    scope: McpScope
    source_key: str
    source_label: str
    source_identity: str
    document: Mapping[str, Any]
    claude_project_activation: _ClaudeProjectActivation | None = None


class _EntryProblem(ValueError):
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        support_state: ServerSupportState = ServerSupportState.INVALID,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.support_state = support_state


def discover_mcp_servers(
    context: DiscoveryContext,
) -> McpDiscoveryResult:
    """Discover supported Codex and Claude MCP server configurations."""
    project_root = _resolve_project_root(context)
    issues: list[DynamicScanIssue] = []
    source_statuses: dict[str, DiscoverySourceStatus] = {}

    codex_sources = _load_codex_sources(
        context=context,
        project_root=project_root,
        issues=issues,
        source_statuses=source_statuses,
    )
    claude_sources = _load_claude_sources(
        context=context,
        project_root=project_root,
        issues=issues,
        source_statuses=source_statuses,
    )
    claude_policy = _load_claude_tool_policy(
        context=context,
        project_root=project_root,
        issues=issues,
        source_statuses=source_statuses,
    )

    candidates: list[DiscoveredMcpServer] = []

    for source in codex_sources:
        candidates.extend(_parse_codex_source(source, issues))

    for source in claude_sources:
        candidates.extend(
            _parse_claude_source(
                source,
                policy=claude_policy,
                issues=issues,
            )
        )

    servers = _select_highest_precedence(candidates, issues)

    return McpDiscoveryResult(
        servers=servers,
        issues=issues,
        source_statuses=source_statuses,
    )


def _resolve_project_root(context: DiscoveryContext) -> Path:
    if context.project_root is not None:
        return context.project_root.resolve(strict=False)

    current = context.current_working_directory.resolve(strict=False)

    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate

    return current


def _load_codex_sources(
    *,
    context: DiscoveryContext,
    project_root: Path,
    issues: list[DynamicScanIssue],
    source_statuses: dict[str, DiscoverySourceStatus],
) -> list[_Source]:
    sources: list[_Source] = []

    if context.include_trusted_project_config:
        for level, directory in enumerate(
            _directories_from_current_to_root(
                context.current_working_directory,
                project_root,
            )
        ):
            path = directory / ".codex" / "config.toml"
            source_key = f"codex:project:{level}"
            source = _load_toml_source(
                path=path,
                product=McpProduct.CODEX,
                scope=McpScope.PROJECT,
                source_key=source_key,
                source_label=f"Codex project config (level {level})",
                issues=issues,
                source_statuses=source_statuses,
            )
            if source is not None:
                sources.append(source)
    else:
        source_statuses["codex:project"] = DiscoverySourceStatus.INACCESSIBLE
        issues.append(
            _issue(
                code="project_config_not_trusted",
                safe_message=(
                    "Codex project configuration was not read because the "
                    "caller did not mark the project as trusted."
                ),
            )
        )

    user_path = context.user_home / ".codex" / "config.toml"
    user_source = _load_toml_source(
        path=user_path,
        product=McpProduct.CODEX,
        scope=McpScope.USER,
        source_key="codex:user",
        source_label="Codex user config",
        issues=issues,
        source_statuses=source_statuses,
    )
    if user_source is not None:
        sources.append(user_source)

    return sources


def _load_claude_sources(
    *,
    context: DiscoveryContext,
    project_root: Path,
    issues: list[DynamicScanIssue],
    source_statuses: dict[str, DiscoverySourceStatus],
) -> list[_Source]:
    sources: list[_Source] = []
    project_activation = _ClaudeProjectActivation()
    home_path = context.user_home / ".claude.json"
    home_document = _load_json_document(
        path=home_path,
        source_key="claude:home",
        source_label="Claude home config",
        issues=issues,
        source_statuses=source_statuses,
    )

    if home_document is None:
        home_status = source_statuses["claude:home"]
        source_statuses["claude:local"] = home_status
        source_statuses["claude:user"] = home_status
    else:
        if context.include_trusted_project_config:
            (
                local_status,
                local_entries,
                project_activation,
            ) = _extract_claude_local_entries(
                home_document,
                project_root=project_root,
                current_working_directory=(
                    context.current_working_directory
                ),
                issues=issues,
            )
            source_statuses["claude:local"] = local_status
            if local_entries is not None:
                sources.append(
                    _Source(
                        product=McpProduct.CLAUDE,
                        scope=McpScope.LOCAL,
                        source_key="claude:local",
                        source_label="Claude local config",
                        source_identity=(
                            f"{_path_identity(home_path)}:"
                            f"{_path_identity(project_root)}"
                        ),
                        document={"mcpServers": local_entries},
                    )
                )
        else:
            source_statuses["claude:local"] = (
                DiscoverySourceStatus.INACCESSIBLE
            )
            issues.append(
                _issue(
                    code="project_config_not_trusted",
                    safe_message=(
                        "Claude local MCP configuration was not read because "
                        "the caller did not mark the project as trusted."
                    ),
                )
            )

        user_entries = home_document.get("mcpServers")
        if user_entries is None:
            source_statuses["claude:user"] = DiscoverySourceStatus.MISSING
        elif isinstance(user_entries, Mapping):
            source_statuses["claude:user"] = DiscoverySourceStatus.FOUND
            sources.append(
                _Source(
                    product=McpProduct.CLAUDE,
                    scope=McpScope.USER,
                    source_key="claude:user",
                    source_label="Claude user config",
                    source_identity=_path_identity(home_path),
                    document={"mcpServers": dict(user_entries)},
                )
            )
        else:
            source_statuses["claude:user"] = DiscoverySourceStatus.INVALID
            issues.append(
                _issue(
                    code="invalid_server_collection",
                    safe_message=(
                        "Claude user MCP server collection is not an object."
                    ),
                )
            )

    if context.include_trusted_project_config:
        project_path = project_root / ".mcp.json"
        project_document = _load_json_document(
            path=project_path,
            source_key="claude:project",
            source_label="Claude project config",
            issues=issues,
            source_statuses=source_statuses,
        )
        if project_document is not None:
            sources.insert(
                1 if sources and sources[0].scope == McpScope.LOCAL else 0,
                _Source(
                    product=McpProduct.CLAUDE,
                    scope=McpScope.PROJECT,
                    source_key="claude:project",
                    source_label="Claude project config",
                    source_identity=_path_identity(project_path),
                    document=project_document,
                    claude_project_activation=project_activation,
                ),
            )
    else:
        source_statuses["claude:project"] = (
            DiscoverySourceStatus.INACCESSIBLE
        )

    return sources


def _load_claude_tool_policy(
    *,
    context: DiscoveryContext,
    project_root: Path,
    issues: list[DynamicScanIssue],
    source_statuses: dict[str, DiscoverySourceStatus],
) -> HostToolPolicy:
    rules: list[ClaudePermissionRule] = []
    parse_issues: list[DynamicScanIssue] = []
    policy_sources = [
        (
            "claude:settings:local",
            "Claude local settings",
            project_root / ".claude" / "settings.local.json",
            context.include_trusted_project_config,
        ),
        (
            "claude:settings:project",
            "Claude project settings",
            project_root / ".claude" / "settings.json",
            context.include_trusted_project_config,
        ),
        (
            "claude:settings:user",
            "Claude user settings",
            context.user_home / ".claude" / "settings.json",
            True,
        ),
    ]

    for source_key, source_label, path, allowed in policy_sources:
        if not allowed:
            source_statuses[source_key] = DiscoverySourceStatus.INACCESSIBLE
            continue

        document = _load_json_document(
            path=path,
            source_key=source_key,
            source_label=source_label,
            issues=issues,
            source_statuses=source_statuses,
        )
        if document is None:
            if source_statuses[source_key] == DiscoverySourceStatus.INVALID:
                parse_issues.append(
                    _issue(
                        code="policy_parse_error",
                        safe_message=(
                            f"{source_label} could not be used for MCP tool "
                            "policy evaluation."
                        ),
                    )
                )
            continue

        try:
            rules.extend(
                _parse_claude_permission_rules(
                    document,
                    source_label=source_label,
                )
            )
        except _EntryProblem as error:
            policy_issue = _issue(
                code=error.code,
                safe_message=error.safe_message,
            )
            issues.append(policy_issue)
            parse_issues.append(policy_issue)

    coverage = (
        PolicySourceCoverage.INVALID
        if parse_issues
        else PolicySourceCoverage.INCOMPLETE
    )

    return HostToolPolicy(
        product=McpProduct.CLAUDE,
        source_coverage=coverage,
        claude_permission_rules=rules,
        parse_issues=parse_issues,
    )


def _load_toml_source(
    *,
    path: Path,
    product: McpProduct,
    scope: McpScope,
    source_key: str,
    source_label: str,
    issues: list[DynamicScanIssue],
    source_statuses: dict[str, DiscoverySourceStatus],
) -> _Source | None:
    if not path.exists():
        source_statuses[source_key] = DiscoverySourceStatus.MISSING
        return None

    try:
        document = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except PermissionError:
        source_statuses[source_key] = DiscoverySourceStatus.INACCESSIBLE
        issues.append(
            _issue(
                code="source_inaccessible",
                safe_message=f"{source_label} could not be read.",
            )
        )
        return None
    except (OSError, UnicodeError):
        source_statuses[source_key] = DiscoverySourceStatus.INACCESSIBLE
        issues.append(
            _issue(
                code="source_read_failed",
                safe_message=f"{source_label} could not be read.",
            )
        )
        return None
    except tomllib.TOMLDecodeError:
        source_statuses[source_key] = DiscoverySourceStatus.INVALID
        issues.append(
            _issue(
                code="source_parse_failed",
                safe_message=f"{source_label} contains invalid TOML.",
            )
        )
        return None

    source_statuses[source_key] = DiscoverySourceStatus.FOUND
    return _Source(
        product=product,
        scope=scope,
        source_key=source_key,
        source_label=source_label,
        source_identity=_path_identity(path),
        document=document,
    )


def _load_json_document(
    *,
    path: Path,
    source_key: str,
    source_label: str,
    issues: list[DynamicScanIssue],
    source_statuses: dict[str, DiscoverySourceStatus],
) -> Mapping[str, Any] | None:
    if not path.exists():
        source_statuses[source_key] = DiscoverySourceStatus.MISSING
        return None

    try:
        raw_document = json.loads(path.read_text(encoding="utf-8-sig"))
    except PermissionError:
        source_statuses[source_key] = DiscoverySourceStatus.INACCESSIBLE
        issues.append(
            _issue(
                code="source_inaccessible",
                safe_message=f"{source_label} could not be read.",
            )
        )
        return None
    except (OSError, UnicodeError):
        source_statuses[source_key] = DiscoverySourceStatus.INACCESSIBLE
        issues.append(
            _issue(
                code="source_read_failed",
                safe_message=f"{source_label} could not be read.",
            )
        )
        return None
    except json.JSONDecodeError:
        source_statuses[source_key] = DiscoverySourceStatus.INVALID
        issues.append(
            _issue(
                code="source_parse_failed",
                safe_message=f"{source_label} contains invalid JSON.",
            )
        )
        return None

    if not isinstance(raw_document, Mapping):
        source_statuses[source_key] = DiscoverySourceStatus.INVALID
        issues.append(
            _issue(
                code="source_root_invalid",
                safe_message=f"{source_label} root must be an object.",
            )
        )
        return None

    source_statuses[source_key] = DiscoverySourceStatus.FOUND
    return dict(raw_document)


def _parse_codex_source(
    source: _Source,
    issues: list[DynamicScanIssue],
) -> list[DiscoveredMcpServer]:
    raw_servers = source.document.get("mcp_servers")

    if raw_servers is None:
        return []

    if not isinstance(raw_servers, Mapping):
        issues.append(
            _issue(
                code="invalid_server_collection",
                safe_message=(
                    f"{source.source_label} MCP server collection is not "
                    "an object."
                ),
            )
        )
        return []

    return [
        _build_codex_server(
            server_name=server_name,
            raw_entry=raw_entry,
            source=source,
            issues=issues,
        )
        for server_name, raw_entry in raw_servers.items()
    ]


def _parse_claude_source(
    source: _Source,
    *,
    policy: HostToolPolicy,
    issues: list[DynamicScanIssue],
) -> list[DiscoveredMcpServer]:
    raw_servers = source.document.get("mcpServers")

    if raw_servers is None:
        return []

    if not isinstance(raw_servers, Mapping):
        issues.append(
            _issue(
                code="invalid_server_collection",
                safe_message=(
                    f"{source.source_label} MCP server collection is not "
                    "an object."
                ),
            )
        )
        return []

    return [
        _build_claude_server(
            server_name=server_name,
            raw_entry=raw_entry,
            source=source,
            policy=policy,
            issues=issues,
        )
        for server_name, raw_entry in raw_servers.items()
    ]


def _build_codex_server(
    *,
    server_name: Any,
    raw_entry: Any,
    source: _Source,
    issues: list[DynamicScanIssue],
) -> DiscoveredMcpServer:
    normalized_name = _safe_server_name(server_name)
    selection_id = _selection_id(source, normalized_name)
    entry = raw_entry if isinstance(raw_entry, Mapping) else {}
    transport = _infer_transport(entry)
    enabled_state = _codex_enabled_state(entry)
    policy = _build_codex_policy(
        entry,
        server_id=selection_id,
        source_label=source.source_label,
        issues=issues,
    )

    try:
        if not isinstance(server_name, str):
            raise _EntryProblem(
                "server_name_invalid",
                "Codex MCP server name must be a string.",
            )
        if not isinstance(raw_entry, Mapping):
            raise _EntryProblem(
                "server_entry_invalid",
                f"Codex server '{normalized_name}' entry is not an object.",
            )
        if not isinstance(entry.get("enabled", True), bool):
            raise _EntryProblem(
                "enabled_state_invalid",
                f"Codex server '{normalized_name}' enabled state is invalid.",
            )

        connection, support_state, reason_code = _codex_connection(
            normalized_name,
            entry,
        )
    except (ConfigLoadError, ValidationError, _EntryProblem) as error:
        problem = _as_entry_problem(error, normalized_name, "Codex")
        issues.append(
            _issue(
                code=problem.code,
                safe_message=problem.safe_message,
                server_id=selection_id,
            )
        )
        connection = None
        support_state = problem.support_state
        reason_code = problem.code

    if (
        enabled_state == ServerEnabledState.DISABLED
        and support_state == ServerSupportState.SUPPORTED
    ):
        connection = None
        reason_code = "server_disabled"

    return DiscoveredMcpServer(
        selection_id=selection_id,
        product=McpProduct.CODEX,
        scope=source.scope,
        source_label=source.source_label,
        server_name=normalized_name,
        transport=transport,
        enabled_state=enabled_state,
        support_state=support_state,
        support_reason_code=reason_code,
        command_basename=_command_basename(entry),
        remote_origin=_remote_origin(entry),
        argument_count=_argument_count(entry),
        connection=connection,
        tool_policy=policy,
    )


def _build_claude_server(
    *,
    server_name: Any,
    raw_entry: Any,
    source: _Source,
    policy: HostToolPolicy,
    issues: list[DynamicScanIssue],
) -> DiscoveredMcpServer:
    normalized_name = _safe_server_name(server_name)
    selection_id = _selection_id(source, normalized_name)
    entry = raw_entry if isinstance(raw_entry, Mapping) else {}
    transport = _infer_claude_transport(entry)
    enabled_state = _claude_enabled_state(
        source=source,
        server_name=normalized_name,
    )

    try:
        if not isinstance(server_name, str):
            raise _EntryProblem(
                "server_name_invalid",
                "Claude MCP server name must be a string.",
            )
        if not isinstance(raw_entry, Mapping):
            raise _EntryProblem(
                "server_entry_invalid",
                f"Claude server '{normalized_name}' entry is not an object.",
            )

        connection, support_state, reason_code = _claude_connection(
            normalized_name,
            entry,
        )
    except (ConfigLoadError, ValidationError, _EntryProblem) as error:
        problem = _as_entry_problem(error, normalized_name, "Claude")
        issues.append(
            _issue(
                code=problem.code,
                safe_message=problem.safe_message,
                server_id=selection_id,
            )
        )
        connection = None
        support_state = problem.support_state
        reason_code = problem.code

    if (
        enabled_state == ServerEnabledState.DISABLED
        and support_state == ServerSupportState.SUPPORTED
    ):
        connection = None
        reason_code = "server_disabled"

    return DiscoveredMcpServer(
        selection_id=selection_id,
        product=McpProduct.CLAUDE,
        scope=source.scope,
        source_label=source.source_label,
        server_name=normalized_name,
        transport=transport,
        enabled_state=enabled_state,
        support_state=support_state,
        support_reason_code=reason_code,
        command_basename=_command_basename(entry),
        remote_origin=_remote_origin(entry),
        argument_count=_argument_count(entry),
        connection=connection,
        tool_policy=policy,
    )


def _codex_connection(
    server_name: str,
    entry: Mapping[str, Any],
) -> tuple[
    StdioConnectionConfig | StreamableHttpConnectionConfig,
    ServerSupportState,
    str | None,
]:
    has_command = entry.get("command") is not None
    has_url = entry.get("url") is not None

    if has_command == has_url:
        raise _EntryProblem(
            "transport_ambiguous",
            (
                f"Codex server '{server_name}' must define exactly one of "
                "command or url."
            ),
        )

    if has_command:
        if entry.get("experimental_environment") == "remote":
            raise _EntryProblem(
                "remote_stdio_not_supported",
                f"Codex server '{server_name}' uses unsupported remote stdio.",
                support_state=ServerSupportState.UNSUPPORTED,
            )

        config = parse_mcp_server_entry(server_name, entry)
        if config.command is None:
            raise _EntryProblem(
                "command_missing",
                f"Codex server '{server_name}' has no command.",
            )

        return (
            StdioConnectionConfig(
                server_name=config.server_name,
                command=config.command,
                args=config.args,
                cwd=config.cwd,
                env_values=config.env,
                env_references=_parse_codex_env_references(
                    entry.get("env_vars", [])
                ),
            ),
            ServerSupportState.SUPPORTED,
            None,
        )

    return (
        StreamableHttpConnectionConfig(
            server_name=server_name,
            url=_required_string(entry.get("url"), "url"),
            static_headers=_string_mapping(
                entry.get("http_headers", {}),
                "http_headers",
            ),
            environment_header_references=_string_mapping(
                entry.get("env_http_headers", {}),
                "env_http_headers",
            ),
            bearer_token_environment_reference=_optional_string(
                entry.get("bearer_token_env_var"),
                "bearer_token_env_var",
            ),
        ),
        ServerSupportState.SUPPORTED,
        None,
    )


def _claude_connection(
    server_name: str,
    entry: Mapping[str, Any],
) -> tuple[
    StdioConnectionConfig | StreamableHttpConnectionConfig,
    ServerSupportState,
    str | None,
]:
    transport = _infer_claude_transport(entry)

    if transport == McpTransport.STDIO:
        configured_type = entry.get("type")
        if configured_type not in (None, "stdio"):
            raise _EntryProblem(
                "transport_not_supported",
                (
                    f"Claude server '{server_name}' uses an unsupported "
                    "transport."
                ),
                support_state=ServerSupportState.UNSUPPORTED,
            )

        config = parse_mcp_server_entry(server_name, entry)
        if config.command is None:
            raise _EntryProblem(
                "command_missing",
                f"Claude server '{server_name}' has no command.",
            )
        if _contains_environment_template(config.command):
            raise _EntryProblem(
                "command_environment_reference_not_supported",
                (
                    f"Claude server '{server_name}' uses an environment "
                    "reference in command."
                ),
                support_state=ServerSupportState.UNSUPPORTED,
            )
        if any(_contains_environment_template(item) for item in config.args):
            raise _EntryProblem(
                "argument_environment_reference_not_supported",
                (
                    f"Claude server '{server_name}' uses an environment "
                    "reference in arguments."
                ),
                support_state=ServerSupportState.UNSUPPORTED,
            )
        if config.cwd and _contains_environment_template(config.cwd):
            raise _EntryProblem(
                "cwd_environment_reference_not_supported",
                (
                    f"Claude server '{server_name}' uses an environment "
                    "reference in working directory."
                ),
                support_state=ServerSupportState.UNSUPPORTED,
            )

        env_values, env_references = _split_claude_environment(config.env)
        return (
            StdioConnectionConfig(
                server_name=config.server_name,
                command=config.command,
                args=config.args,
                cwd=config.cwd,
                env_values=env_values,
                env_references=env_references,
            ),
            ServerSupportState.SUPPORTED,
            None,
        )

    configured_type = entry.get("type")
    if configured_type not in (None, "http"):
        raise _EntryProblem(
            "transport_not_supported",
            f"Claude server '{server_name}' uses an unsupported transport.",
            support_state=ServerSupportState.UNSUPPORTED,
        )
    if "headersHelper" in entry:
        raise _EntryProblem(
            "headers_helper_not_supported",
            (
                f"Claude server '{server_name}' uses an executable headers "
                "helper, which discovery will not run."
            ),
            support_state=ServerSupportState.UNSUPPORTED,
        )
    if "oauth" in entry:
        raise _EntryProblem(
            "interactive_oauth_not_supported",
            (
                f"Claude server '{server_name}' requires unsupported OAuth "
                "configuration."
            ),
            support_state=ServerSupportState.UNSUPPORTED,
        )

    url = _required_string(entry.get("url"), "url")
    if _contains_environment_template(url):
        raise _EntryProblem(
            "url_environment_reference_not_supported",
            (
                f"Claude server '{server_name}' uses an environment "
                "reference in URL."
            ),
            support_state=ServerSupportState.UNSUPPORTED,
        )

    static_headers, env_headers, bearer_reference = _split_claude_headers(
        entry.get("headers", {})
    )
    return (
        StreamableHttpConnectionConfig(
            server_name=server_name,
            url=url,
            static_headers=static_headers,
            environment_header_references=env_headers,
            bearer_token_environment_reference=bearer_reference,
        ),
        ServerSupportState.SUPPORTED,
        None,
    )


def _build_codex_policy(
    entry: Mapping[str, Any],
    *,
    server_id: str,
    source_label: str,
    issues: list[DynamicScanIssue],
) -> HostToolPolicy:
    parse_issues: list[DynamicScanIssue] = []
    enabled_tools_configured = "enabled_tools" in entry

    try:
        enabled_tools = _string_list(
            entry.get("enabled_tools", []),
            "enabled_tools",
        )
        disabled_tools = _string_list(
            entry.get("disabled_tools", []),
            "disabled_tools",
        )
    except _EntryProblem:
        policy_issue = _issue(
            code="policy_parse_error",
            safe_message=(
                f"{source_label} contains invalid Codex tool policy fields."
            ),
            server_id=server_id,
        )
        issues.append(policy_issue)
        parse_issues.append(policy_issue)
        enabled_tools = []
        disabled_tools = []

    return HostToolPolicy(
        product=McpProduct.CODEX,
        source_coverage=(
            PolicySourceCoverage.INVALID
            if parse_issues
            else PolicySourceCoverage.INCOMPLETE
        ),
        codex_enabled_tools_configured=enabled_tools_configured,
        codex_enabled_tools=enabled_tools,
        codex_disabled_tools=disabled_tools,
        parse_issues=parse_issues,
    )


def _parse_claude_permission_rules(
    document: Mapping[str, Any],
    *,
    source_label: str,
) -> list[ClaudePermissionRule]:
    permissions = document.get("permissions")
    if permissions is None:
        return []
    if not isinstance(permissions, Mapping):
        raise _EntryProblem(
            "policy_parse_error",
            f"{source_label} permissions must be an object.",
        )

    rules: list[ClaudePermissionRule] = []
    for effect in PermissionEffect:
        raw_rules = permissions.get(effect.value, [])
        if not isinstance(raw_rules, list) or not all(
            isinstance(item, str) for item in raw_rules
        ):
            raise _EntryProblem(
                "policy_parse_error",
                (
                    f"{source_label} permission {effect.value} rules must "
                    "be strings."
                ),
            )

        rules.extend(
            ClaudePermissionRule(
                effect=effect,
                tool_name_pattern=rule,
                source_label=source_label,
            )
            for rule in raw_rules
            if rule == "*" or rule.startswith("mcp__")
        )

    return rules


def _extract_claude_local_entries(
    document: Mapping[str, Any],
    *,
    project_root: Path,
    current_working_directory: Path,
    issues: list[DynamicScanIssue],
) -> tuple[
    DiscoverySourceStatus,
    Mapping[str, Any] | None,
    _ClaudeProjectActivation,
]:
    empty_activation = _ClaudeProjectActivation()
    projects = document.get("projects")
    if projects is None:
        return DiscoverySourceStatus.MISSING, None, empty_activation
    if not isinstance(projects, Mapping):
        issues.append(
            _issue(
                code="local_projects_invalid",
                safe_message="Claude local project collection is invalid.",
            )
        )
        return DiscoverySourceStatus.INVALID, None, empty_activation

    target_identities = {
        _path_identity(project_root),
        _path_identity(current_working_directory),
    }
    for configured_path, project_entry in projects.items():
        if not isinstance(configured_path, str):
            continue
        if _path_identity(Path(configured_path)) not in target_identities:
            continue
        if not isinstance(project_entry, Mapping):
            issues.append(
                _issue(
                    code="local_project_entry_invalid",
                    safe_message="Claude local project entry is invalid.",
                )
            )
            return DiscoverySourceStatus.INVALID, None, empty_activation

        project_activation = _parse_claude_project_activation(
            project_entry,
            issues=issues,
        )

        raw_servers = project_entry.get("mcpServers")
        if raw_servers is None:
            return (
                DiscoverySourceStatus.MISSING,
                None,
                project_activation,
            )
        if not isinstance(raw_servers, Mapping):
            issues.append(
                _issue(
                    code="invalid_server_collection",
                    safe_message=(
                        "Claude local MCP server collection is not an object."
                    ),
                )
            )
            return (
                DiscoverySourceStatus.INVALID,
                None,
                project_activation,
            )
        return (
            DiscoverySourceStatus.FOUND,
            dict(raw_servers),
            project_activation,
        )

    return DiscoverySourceStatus.MISSING, None, empty_activation


def _parse_claude_project_activation(
    project_entry: Mapping[str, Any],
    *,
    issues: list[DynamicScanIssue],
) -> _ClaudeProjectActivation:
    field_names = (
        "disabledMcpjsonServers",
        "enabledMcpjsonServers",
        "enableAllProjectMcpServers",
    )
    if not any(field_name in project_entry for field_name in field_names):
        return _ClaudeProjectActivation()

    try:
        disabled_servers = frozenset(
            _string_list(
                project_entry.get("disabledMcpjsonServers", []),
                "disabledMcpjsonServers",
            )
        )
        enabled_servers = frozenset(
            _string_list(
                project_entry.get("enabledMcpjsonServers", []),
                "enabledMcpjsonServers",
            )
        )
        enable_all = project_entry.get(
            "enableAllProjectMcpServers",
            False,
        )
        if not isinstance(enable_all, bool):
            raise _EntryProblem(
                "enableAllProjectMcpServers_invalid",
                "Claude project MCP enable-all setting must be a boolean.",
            )
    except _EntryProblem:
        issues.append(
            _issue(
                code="project_activation_state_invalid",
                safe_message=(
                    "Claude project MCP activation settings are invalid."
                ),
            )
        )
        return _ClaudeProjectActivation()

    return _ClaudeProjectActivation(
        disabled_servers=disabled_servers,
        enabled_servers=enabled_servers,
        enable_all=enable_all,
        source_valid=True,
    )


def _select_highest_precedence(
    candidates: list[DiscoveredMcpServer],
    issues: list[DynamicScanIssue],
) -> list[DiscoveredMcpServer]:
    selected: list[DiscoveredMcpServer] = []
    selected_by_name: dict[
        tuple[McpProduct, str],
        DiscoveredMcpServer,
    ] = {}

    for candidate in candidates:
        key = (candidate.product, candidate.server_name)
        existing = selected_by_name.get(key)
        if existing is None:
            selected_by_name[key] = candidate
            selected.append(candidate)
            continue

        issues.append(
            _issue(
                code="shadowed_server_definition",
                safe_message=(
                    f"{candidate.source_label} definition for server "
                    f"'{candidate.server_name}' was shadowed by "
                    f"{existing.source_label}."
                ),
                server_id=existing.selection_id,
            )
        )

    return selected


def _directories_from_current_to_root(
    current_working_directory: Path,
    project_root: Path,
) -> list[Path]:
    current = current_working_directory.resolve(strict=False)
    root = project_root.resolve(strict=False)

    try:
        current.relative_to(root)
    except ValueError:
        return [root]

    directories: list[Path] = []
    candidate = current
    while True:
        directories.append(candidate)
        if candidate == root:
            break
        candidate = candidate.parent

    return directories


def _selection_id(source: _Source, server_name: str) -> str:
    payload = (
        f"{source.product.value}\0{source.scope.value}\0"
        f"{source.source_identity}\0{server_name}"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:20]


def _path_identity(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _safe_server_name(server_name: Any) -> str:
    if isinstance(server_name, str) and server_name.strip():
        return server_name.strip()
    return "invalid-server"


def _infer_transport(entry: Mapping[str, Any]) -> McpTransport:
    if entry.get("url") is not None and entry.get("command") is None:
        return McpTransport.STREAMABLE_HTTP
    return McpTransport.STDIO


def _infer_claude_transport(entry: Mapping[str, Any]) -> McpTransport:
    configured_type = entry.get("type")
    if configured_type == "http":
        return McpTransport.STREAMABLE_HTTP
    if configured_type in {"sse", "ws"}:
        return McpTransport.STREAMABLE_HTTP
    return _infer_transport(entry)


def _codex_enabled_state(
    entry: Mapping[str, Any],
) -> ServerEnabledState:
    enabled = entry.get("enabled", True)
    if enabled is True:
        return ServerEnabledState.ENABLED
    if enabled is False:
        return ServerEnabledState.DISABLED
    return ServerEnabledState.UNKNOWN


def _claude_enabled_state(
    *,
    source: _Source,
    server_name: str,
) -> ServerEnabledState:
    if source.scope != McpScope.PROJECT:
        return ServerEnabledState.ENABLED

    activation = source.claude_project_activation
    if activation is None or not activation.source_valid:
        return ServerEnabledState.UNKNOWN
    if server_name in activation.disabled_servers:
        return ServerEnabledState.DISABLED
    if activation.enable_all:
        return ServerEnabledState.ENABLED
    if server_name in activation.enabled_servers:
        return ServerEnabledState.ENABLED
    return ServerEnabledState.UNKNOWN


def _command_basename(entry: Mapping[str, Any]) -> str | None:
    command = entry.get("command")
    if (
        not isinstance(command, str)
        or not command.strip()
        or _contains_environment_template(command)
    ):
        return None
    return command.replace("\\", "/").rsplit("/", 1)[-1]


def _remote_origin(entry: Mapping[str, Any]) -> str | None:
    url = entry.get("url")
    if not isinstance(url, str) or _contains_environment_template(url):
        return None

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return None
    return url


def _argument_count(entry: Mapping[str, Any]) -> int:
    args = entry.get("args")
    return len(args) if isinstance(args, list) else 0


def _parse_codex_env_references(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise _EntryProblem(
            "env_vars_invalid",
            "Codex env_vars must be an array.",
        )

    references: dict[str, str] = {}
    for item in value:
        if isinstance(item, str):
            name = _required_string(item, "env_vars item")
            references[name] = name
            continue
        if isinstance(item, Mapping):
            name = _required_string(item.get("name"), "env_vars name")
            source = item.get("source", "local")
            if source != "local":
                raise _EntryProblem(
                    "remote_environment_reference_not_supported",
                    "Codex remote environment references are not supported.",
                    support_state=ServerSupportState.UNSUPPORTED,
                )
            references[name] = name
            continue
        raise _EntryProblem(
            "env_vars_invalid",
            "Codex env_vars entries are invalid.",
        )

    return references


def _split_claude_environment(
    env: Mapping[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    values: dict[str, str] = {}
    references: dict[str, str] = {}

    for name, value in env.items():
        match = _ENV_REFERENCE.fullmatch(value)
        if match:
            references[name] = match.group(1)
        elif _contains_environment_template(value):
            raise _EntryProblem(
                "environment_template_not_supported",
                "Claude environment defaults or templates are not supported.",
                support_state=ServerSupportState.UNSUPPORTED,
            )
        else:
            values[name] = value

    return values, references


def _split_claude_headers(
    value: Any,
) -> tuple[dict[str, str], dict[str, str], str | None]:
    headers = _string_mapping(value, "headers")
    static_headers: dict[str, str] = {}
    env_headers: dict[str, str] = {}
    bearer_reference: str | None = None

    for name, header_value in headers.items():
        bearer_match = _BEARER_ENV_REFERENCE.fullmatch(header_value)
        if bearer_match and name.lower() == "authorization":
            bearer_reference = bearer_match.group(1)
            continue

        env_match = _ENV_REFERENCE.fullmatch(header_value)
        if env_match:
            env_headers[name] = env_match.group(1)
            continue

        if _contains_environment_template(header_value):
            raise _EntryProblem(
                "header_template_not_supported",
                "Claude header templates are not supported.",
                support_state=ServerSupportState.UNSUPPORTED,
            )

        static_headers[name] = header_value

    return static_headers, env_headers, bearer_reference


def _string_mapping(value: Any, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _EntryProblem(
            f"{field_name}_invalid",
            f"{field_name} must be an object.",
        )

    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise _EntryProblem(
                f"{field_name}_invalid",
                f"{field_name} keys and values must be strings.",
            )
        result[key] = item

    return result


def _string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise _EntryProblem(
            f"{field_name}_invalid",
            f"{field_name} must be an array of strings.",
        )
    return list(value)


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _EntryProblem(
            f"{field_name}_invalid",
            f"{field_name} must be a non-empty string.",
        )
    return value.strip()


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field_name)


def _contains_environment_template(value: str) -> bool:
    return "${" in value


def _as_entry_problem(
    error: Exception,
    server_name: str,
    product: str,
) -> _EntryProblem:
    if isinstance(error, _EntryProblem):
        return error

    return _EntryProblem(
        "server_entry_invalid",
        f"{product} server '{server_name}' entry is invalid.",
    )


def _issue(
    *,
    code: str,
    safe_message: str,
    server_id: str | None = None,
) -> DynamicScanIssue:
    return DynamicScanIssue(
        stage=DynamicScanStage.DISCOVERY,
        code=code,
        level=IssueLevel.WARNING,
        safe_message=safe_message,
        server_id=server_id,
    )
