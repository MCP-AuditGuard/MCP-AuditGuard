from __future__ import annotations

from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from cli import main as cli_main
from cli import mcp as cli_mcp
from core.dynamic_scan_models import (
    CleanupResult,
    CollectedTool,
    DiscoveredMcpServer,
    DynamicScanIssue,
    DynamicScanResult,
    DynamicScanStage,
    DynamicScanStageResult,
    DynamicScanStatus,
    DynamicStageStatus,
    HostToolPolicy,
    IssueLevel,
    LocalCleanupResult,
    LocalCleanupStatus,
    McpDiscoveryResult,
    McpProduct,
    McpScope,
    McpTransport,
    PolicySourceCoverage,
    RemoteSessionTerminationResult,
    RemoteSessionTerminationStatus,
    ServerEnabledState,
    ServerSupportState,
    StdioConnectionConfig,
    StreamableHttpConnectionConfig,
    ToolActivationAssessment,
    ToolActivationStatus,
    build_tool_id,
)
from core.models import Finding, ToolMetadata
from core.scan_result import ScanResult


runner = CliRunner()


def make_server(
    *,
    selection_id: str = "codex-user-docs",
    server_name: str = "docs",
    enabled_state: ServerEnabledState = ServerEnabledState.ENABLED,
    support_state: ServerSupportState = ServerSupportState.SUPPORTED,
    transport: McpTransport = McpTransport.STDIO,
    support_reason_code: str | None = None,
) -> DiscoveredMcpServer:
    connection: (
        StdioConnectionConfig
        | StreamableHttpConnectionConfig
        | None
    )
    command_basename: str | None = None
    remote_origin: str | None = None
    argument_count = 0

    if (
        enabled_state == ServerEnabledState.DISABLED
        or support_state != ServerSupportState.SUPPORTED
    ):
        connection = None
    elif transport == McpTransport.STDIO:
        connection = StdioConnectionConfig(
            server_name=server_name,
            command=r"C:\private\bin\python.exe",
            args=["secret-server.py", "--token", "TEST_SECRET"],
            cwd=r"C:\private\workspace",
            env_values={"SECRET_ENV_NAME": "TEST_SECRET"},
            env_references={"TOKEN_ENV_NAME": "TOKEN_SOURCE_NAME"},
        )
        command_basename = "python.exe"
        argument_count = 3
    else:
        connection = StreamableHttpConnectionConfig(
            server_name=server_name,
            url=(
                "https://user:password@example.com:8443/private/mcp"
                "?token=TEST_SECRET"
            ),
            static_headers={"Authorization": "Bearer TEST_SECRET"},
            environment_header_references={
                "X-Secret": "TOKEN_SOURCE_NAME"
            },
            bearer_token_environment_reference="BEARER_TOKEN_NAME",
        )
        remote_origin = "https://example.com:8443"

    return DiscoveredMcpServer(
        selection_id=selection_id,
        product=McpProduct.CODEX,
        scope=McpScope.USER,
        source_label="Codex user config",
        server_name=server_name,
        transport=transport,
        enabled_state=enabled_state,
        support_state=support_state,
        support_reason_code=support_reason_code,
        command_basename=command_basename,
        remote_origin=remote_origin,
        argument_count=argument_count,
        connection=connection,
        tool_policy=HostToolPolicy(
            product=McpProduct.CODEX,
            source_coverage=PolicySourceCoverage.COMPLETE,
        ),
    )


def make_cleanup(
    *,
    local_status: LocalCleanupStatus = LocalCleanupStatus.SUCCEEDED,
    remote_status: RemoteSessionTerminationStatus = (
        RemoteSessionTerminationStatus.NOT_APPLICABLE
    ),
) -> CleanupResult:
    return CleanupResult(
        local_cleanup=LocalCleanupResult(status=local_status),
        remote_session_termination=RemoteSessionTerminationResult(
            status=remote_status,
        ),
    )


def make_tool(
    server: DiscoveredMcpServer,
    tool_name: str,
) -> ToolMetadata:
    return ToolMetadata.from_mcp_tool(
        raw_tool={
            "name": tool_name,
            "description": "token=TEST_SECRET",
            "inputSchema": {"type": "object"},
        },
        server_name=server.server_name,
        source="mcp:test",
    )


def make_collected_tool(
    server: DiscoveredMcpServer,
    *,
    tool_name: str,
    status: ToolActivationStatus,
    ordinal: int,
) -> CollectedTool:
    tool = make_tool(server, tool_name)
    return CollectedTool(
        tool_id=build_tool_id(
            server_selection_id=server.selection_id,
            tool_name=tool_name,
            snapshot_ordinal=ordinal,
        ),
        metadata=tool,
        activation=ToolActivationAssessment(
            tool_name=tool_name,
            status=status,
            product=server.product,
            safe_basis_code=f"test_{status.value}",
        ),
    )


def make_scan_result(
    server: DiscoveredMcpServer,
    collected_tools: list[CollectedTool],
) -> ScanResult:
    now = datetime.now(timezone.utc)
    findings = [
        Finding(
            id="MCP-TEST",
            category="tool_poisoning",
            owasp="MCP03",
            severity="high",
            confidence="high",
            title="Suspicious metadata",
            target=collected_tools[0].metadata.target,
            location="description",
            evidence="token=[REDACTED_SECRET]",
            redacted=True,
            recommendation="Review the tool metadata.",
        )
    ] if collected_tools else []

    return ScanResult(
        scan_type="dynamic",
        source_type="mcp_server",
        source=f"mcp:{server.selection_id}",
        started_at=now,
        completed_at=now,
        tools=[item.metadata for item in collected_tools],
        findings=findings,
    )


def make_dynamic_result(
    server: DiscoveredMcpServer,
    *,
    status: DynamicScanStatus = DynamicScanStatus.SUCCESS,
    collected_tools: list[CollectedTool] | None = None,
    issues: list[DynamicScanIssue] | None = None,
) -> DynamicScanResult:
    tools = collected_tools or []
    scan_result = (
        make_scan_result(server, tools)
        if status
        in {
            DynamicScanStatus.SUCCESS,
            DynamicScanStatus.PARTIAL_SUCCESS,
        }
        else None
    )
    stage_status = {
        DynamicScanStatus.SUCCESS: DynamicStageStatus.SUCCEEDED,
        DynamicScanStatus.PARTIAL_SUCCESS: DynamicStageStatus.SUCCEEDED,
        DynamicScanStatus.FAILED: DynamicStageStatus.FAILED,
        DynamicScanStatus.TIMED_OUT: DynamicStageStatus.TIMED_OUT,
    }[status]

    return DynamicScanResult(
        status=status,
        target=server.to_summary(),
        stages=[
            DynamicScanStageResult(
                stage=DynamicScanStage.SCAN,
                status=stage_status,
            )
        ],
        issues=issues or [],
        collected_tools=tools,
        cleanup=make_cleanup(),
        scan_result=scan_result,
    )


def install_discovery(
    monkeypatch: pytest.MonkeyPatch,
    servers: list[DiscoveredMcpServer],
) -> list:
    contexts = []

    def fake_discovery(context):
        contexts.append(context)
        return McpDiscoveryResult(servers=servers)

    monkeypatch.setattr(
        cli_mcp,
        "discover_mcp_servers",
        fake_discovery,
    )
    return contexts


def install_dynamic_scan(
    monkeypatch: pytest.MonkeyPatch,
    result: DynamicScanResult,
) -> list[DiscoveredMcpServer]:
    calls: list[DiscoveredMcpServer] = []

    async def fake_scan(server):
        calls.append(server)
        return result

    monkeypatch.setattr(cli_mcp, "_run_selected_server", fake_scan)
    return calls


def test_list_outputs_only_safe_server_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdio_server = make_server()
    http_server = make_server(
        selection_id="claude-project-api",
        server_name="remote-api",
        transport=McpTransport.STREAMABLE_HTTP,
    )
    install_discovery(monkeypatch, [stdio_server, http_server])

    result = runner.invoke(cli_main.app, ["mcp", "list"])

    assert result.exit_code == 0
    assert "MCP servers: 2" in result.output
    assert "selection_id: codex-user-docs" in result.output
    assert "command_basename: python.exe" in result.output
    assert "argument_count: 3" in result.output
    assert "http_origin: https://example.com:8443" in result.output
    assert "secret-server.py" not in result.output
    assert "--token" not in result.output
    assert "TEST_SECRET" not in result.output
    assert "SECRET_ENV_NAME" not in result.output
    assert "TOKEN_SOURCE_NAME" not in result.output
    assert "Authorization" not in result.output
    assert "password" not in result.output
    assert "/private/mcp" not in result.output
    assert r"C:\private" not in result.output


def test_project_config_requires_explicit_trust_option(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    contexts = install_discovery(monkeypatch, [])

    default_result = runner.invoke(
        cli_main.app,
        ["mcp", "list", "--project-root", str(tmp_path)],
    )
    trusted_result = runner.invoke(
        cli_main.app,
        [
            "mcp",
            "list",
            "--project-root",
            str(tmp_path),
            "--trust-project-config",
        ],
    )

    assert default_result.exit_code == 0
    assert trusted_result.exit_code == 0
    assert contexts[0].include_trusted_project_config is False
    assert contexts[1].include_trusted_project_config is True
    assert contexts[0].project_root == tmp_path.resolve()
    assert contexts[1].project_root == tmp_path.resolve()
    assert contexts[0].current_working_directory.is_absolute()
    assert contexts[0].user_home.is_absolute()


def test_scan_selects_server_by_stable_selection_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = make_server(selection_id="first-id", server_name="first")
    selected = make_server(
        selection_id="stable-selected-id",
        server_name="selected",
    )
    tools = [
        make_collected_tool(
            selected,
            tool_name="search",
            status=ToolActivationStatus.ENABLED,
            ordinal=0,
        )
    ]
    install_discovery(monkeypatch, [first, selected])
    calls = install_dynamic_scan(
        monkeypatch,
        make_dynamic_result(selected, collected_tools=tools),
    )

    result = runner.invoke(
        cli_main.app,
        [
            "mcp",
            "scan",
            "--server-id",
            "stable-selected-id",
        ],
    )

    assert result.exit_code == 0
    assert calls == [selected]
    assert "name: selected" in result.output
    assert "status: success" in result.output


def test_scan_rejects_missing_selection_id_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    install_discovery(monkeypatch, [server])
    calls = install_dynamic_scan(
        monkeypatch,
        make_dynamic_result(server),
    )

    result = runner.invoke(
        cli_main.app,
        ["mcp", "scan", "--server-id", "missing-id"],
    )

    assert result.exit_code == 1
    assert "No MCP server matches" in result.output
    assert calls == []


def test_scan_rejects_duplicate_selection_id_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = make_server(selection_id="duplicate-id", server_name="first")
    second = make_server(selection_id="duplicate-id", server_name="second")
    install_discovery(monkeypatch, [first, second])
    calls = install_dynamic_scan(
        monkeypatch,
        make_dynamic_result(first),
    )

    result = runner.invoke(
        cli_main.app,
        ["mcp", "scan", "--server-id", "duplicate-id"],
    )

    assert result.exit_code == 1
    assert "selection ID is not unique" in result.output
    assert calls == []


@pytest.mark.parametrize(
    "server",
    [
        make_server(
            selection_id="disabled-id",
            enabled_state=ServerEnabledState.DISABLED,
            support_reason_code="server_disabled",
        ),
        make_server(
            selection_id="unsupported-id",
            support_state=ServerSupportState.UNSUPPORTED,
            support_reason_code="transport_not_supported",
        ),
    ],
)
def test_scan_blocks_disabled_and_unsupported_servers(
    monkeypatch: pytest.MonkeyPatch,
    server: DiscoveredMcpServer,
) -> None:
    install_discovery(monkeypatch, [server])
    calls = install_dynamic_scan(
        monkeypatch,
        make_dynamic_result(server),
    )

    result = runner.invoke(
        cli_main.app,
        ["mcp", "scan", "--server-id", server.selection_id],
    )

    assert result.exit_code == 1
    assert calls == []


def test_http_server_returns_structured_unsupported_scan_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server(
        selection_id="http-id",
        transport=McpTransport.STREAMABLE_HTTP,
    )
    issue = DynamicScanIssue(
        stage=DynamicScanStage.CONNECT,
        code="transport_not_implemented",
        level=IssueLevel.ERROR,
        safe_message="This MCP transport is not implemented.",
        server_id=server.selection_id,
    )
    install_discovery(monkeypatch, [server])
    calls = install_dynamic_scan(
        monkeypatch,
        make_dynamic_result(
            server,
            status=DynamicScanStatus.FAILED,
            issues=[issue],
        ),
    )

    result = runner.invoke(
        cli_main.app,
        ["mcp", "scan", "--server-id", "http-id"],
    )

    assert result.exit_code == 1
    assert calls == [server]
    assert "status: failed" in result.output
    assert "code=transport_not_implemented" in result.output


@pytest.mark.parametrize(
    ("status", "expected_exit_code"),
    [
        (DynamicScanStatus.SUCCESS, 0),
        (DynamicScanStatus.PARTIAL_SUCCESS, 2),
        (DynamicScanStatus.FAILED, 1),
        (DynamicScanStatus.TIMED_OUT, 3),
    ],
)
def test_scan_renders_status_and_uses_stable_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    status: DynamicScanStatus,
    expected_exit_code: int,
) -> None:
    server = make_server()
    tools = [
        make_collected_tool(
            server,
            tool_name="search",
            status=ToolActivationStatus.ENABLED,
            ordinal=0,
        )
    ]
    install_discovery(monkeypatch, [server])
    install_dynamic_scan(
        monkeypatch,
        make_dynamic_result(
            server,
            status=status,
            collected_tools=tools if status in {
                DynamicScanStatus.SUCCESS,
                DynamicScanStatus.PARTIAL_SUCCESS,
            } else [],
        ),
    )

    result = runner.invoke(
        cli_main.app,
        ["mcp", "scan", "--server-id", server.selection_id],
    )

    assert result.exit_code == expected_exit_code
    assert f"status: {status.value}" in result.output
    assert "scan: " in result.output


def test_scan_displays_every_tool_activation_without_exposing_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    tools = [
        make_collected_tool(
            server,
            tool_name="enabled-tool",
            status=ToolActivationStatus.ENABLED,
            ordinal=0,
        ),
        make_collected_tool(
            server,
            tool_name="disabled-tool",
            status=ToolActivationStatus.DISABLED,
            ordinal=1,
        ),
        make_collected_tool(
            server,
            tool_name="unknown-tool",
            status=ToolActivationStatus.UNKNOWN,
            ordinal=2,
        ),
    ]
    issue = DynamicScanIssue(
        stage=DynamicScanStage.SCAN,
        code="scanner_warning",
        level=IssueLevel.WARNING,
        safe_message="token=TEST_SECRET",
        server_id=server.selection_id,
    )
    install_discovery(monkeypatch, [server])
    install_dynamic_scan(
        monkeypatch,
        make_dynamic_result(
            server,
            status=DynamicScanStatus.PARTIAL_SUCCESS,
            collected_tools=tools,
            issues=[issue],
        ),
    )

    result = runner.invoke(
        cli_main.app,
        ["mcp", "scan", "--server-id", server.selection_id],
    )

    assert result.exit_code == 2
    assert "tools_collected: 3" in result.output
    assert "findings: 1" in result.output
    assert "high=1" in result.output
    assert "name=enabled-tool status=enabled" in result.output
    assert "name=disabled-tool status=disabled" in result.output
    assert "name=unknown-tool status=unknown" in result.output
    assert "token=[REDACTED_SECRET]" in result.output
    assert "TEST_SECRET" not in result.output
    assert "SECRET_ENV_NAME" not in result.output
    assert "TOKEN_SOURCE_NAME" not in result.output
    assert "secret-server.py" not in result.output
    assert r"C:\private" not in result.output
