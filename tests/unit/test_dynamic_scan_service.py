from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import anyio
import pytest

from core import dynamic_scan_service
from core.dynamic_scan_models import (
    CleanupResult,
    DiscoveredMcpServer,
    DynamicScanIssue,
    DynamicScanStage,
    DynamicScanStatus,
    DynamicStageStatus,
    HostToolPolicy,
    IssueLevel,
    LocalCleanupResult,
    LocalCleanupStatus,
    McpProduct,
    McpScope,
    McpServerImplementation,
    McpSnapshotResult,
    McpTransport,
    PolicySourceCoverage,
    RemoteSessionTerminationResult,
    RemoteSessionTerminationStatus,
    ServerEnabledState,
    ServerSupportState,
    StdioConnectionConfig,
    StreamableHttpConnectionConfig,
    ToolActivationStatus,
    build_tool_id,
)
from core.models import ToolMetadata
from core.scan_result import ScanResult


def make_tool(tool_name: str) -> ToolMetadata:
    return ToolMetadata.from_mcp_tool(
        raw_tool={
            "name": tool_name,
            "description": f"{tool_name} description",
            "inputSchema": {"type": "object"},
        },
        server_name="docs",
        source="mcp:codex:user:docs",
    )


def make_policy(
    *,
    enabled_tools: list[str] | None = None,
) -> HostToolPolicy:
    return HostToolPolicy(
        product=McpProduct.CODEX,
        source_coverage=PolicySourceCoverage.COMPLETE,
        codex_enabled_tools_configured=enabled_tools is not None,
        codex_enabled_tools=enabled_tools or [],
    )


def make_server(
    *,
    enabled_state: ServerEnabledState = ServerEnabledState.ENABLED,
    support_state: ServerSupportState = ServerSupportState.SUPPORTED,
    transport: McpTransport = McpTransport.STDIO,
    policy: HostToolPolicy | None = None,
) -> DiscoveredMcpServer:
    connection: (
        StdioConnectionConfig
        | StreamableHttpConnectionConfig
        | None
    )
    if enabled_state == ServerEnabledState.DISABLED:
        connection = None
    elif support_state != ServerSupportState.SUPPORTED:
        connection = None
    elif transport == McpTransport.STDIO:
        connection = StdioConnectionConfig(
            server_name="docs",
            command="python",
            args=["server.py"],
            env_values={"TOKEN": "TEST_SECRET"},
        )
    else:
        connection = StreamableHttpConnectionConfig(
            server_name="docs",
            url="https://user:password@example.com/mcp?token=TEST_SECRET",
            static_headers={"Authorization": "Bearer TEST_SECRET"},
        )

    return DiscoveredMcpServer(
        selection_id="codex:user:docs",
        product=McpProduct.CODEX,
        scope=McpScope.USER,
        source_label="Codex user config",
        server_name="docs",
        transport=transport,
        enabled_state=enabled_state,
        support_state=support_state,
        support_reason_code=(
            "server_disabled"
            if enabled_state == ServerEnabledState.DISABLED
            else None
        ),
        command_basename="python",
        argument_count=1,
        connection=connection,
        tool_policy=policy or make_policy(),
    )


def make_cleanup(
    *,
    status: LocalCleanupStatus = LocalCleanupStatus.SUCCEEDED,
    issues: list[DynamicScanIssue] | None = None,
    remote_status: RemoteSessionTerminationStatus = (
        RemoteSessionTerminationStatus.NOT_APPLICABLE
    ),
    remote_issues: list[DynamicScanIssue] | None = None,
) -> CleanupResult:
    return CleanupResult(
        local_cleanup=LocalCleanupResult(
            status=status,
            issues=issues or [],
        ),
        remote_session_termination=RemoteSessionTerminationResult(
            status=remote_status,
            issues=remote_issues or [],
        ),
    )


def make_snapshot(
    server: DiscoveredMcpServer,
    *,
    tools: list[ToolMetadata] | None = None,
    issues: list[DynamicScanIssue] | None = None,
    cleanup: CleanupResult | None = None,
    initialized: bool = True,
) -> McpSnapshotResult:
    return McpSnapshotResult(
        server_summary=server.to_summary(),
        protocol_version="2025-11-25" if initialized else None,
        server_implementation=(
            McpServerImplementation(
                name="test-server",
                version="1.0",
            )
            if initialized
            else None
        ),
        tools=tools or [],
        issues=issues or [],
        cleanup=cleanup or make_cleanup(),
    )


def make_scan_result(
    tools: list[ToolMetadata],
    *,
    warnings: list[str] | None = None,
) -> ScanResult:
    now = datetime.now(timezone.utc)
    return ScanResult(
        scan_type="dynamic",
        source_type="mcp_server",
        source="mcp:codex:user:docs",
        started_at=now,
        completed_at=now,
        tools=tools,
        findings=[],
        warnings=warnings or [],
    )


def run_scan(server: DiscoveredMcpServer):
    return anyio.run(dynamic_scan_service.run_dynamic_scan, server)


def stage_statuses(result) -> dict[DynamicScanStage, DynamicStageStatus]:
    return {item.stage: item.status for item in result.stages}


def install_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: McpSnapshotResult,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_collect(
        connection,
        *,
        server_summary,
        timeouts=None,
        environment=None,
    ):
        calls.append(
            {
                "connection": connection,
                "server_summary": server_summary,
                "timeouts": timeouts,
                "environment": environment,
            }
        )
        return snapshot

    monkeypatch.setattr(
        dynamic_scan_service,
        "collect_tools_snapshot",
        fake_collect,
    )
    return calls


def install_scanner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_scan(**kwargs):
        calls.append(kwargs)
        return make_scan_result(
            kwargs["tools"],
            warnings=warnings,
        )

    monkeypatch.setattr(
        dynamic_scan_service,
        "execute_tool_scan",
        fake_scan,
    )
    return calls


def test_normal_snapshot_combines_assessments_and_scans_every_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server(policy=make_policy(enabled_tools=["enabled"]))
    tools = [make_tool("disabled"), make_tool("enabled")]
    snapshot_calls = install_snapshot(
        monkeypatch,
        make_snapshot(server, tools=tools),
    )
    scanner_calls = install_scanner(monkeypatch)

    result = run_scan(server)

    assert result.status == DynamicScanStatus.SUCCESS
    assert len(snapshot_calls) == 1
    assert len(scanner_calls) == 1
    assert scanner_calls[0]["tools"] == tools
    assert scanner_calls[0]["scan_type"] == "dynamic"
    assert scanner_calls[0]["source_type"] == "mcp_server"
    assert [item.metadata for item in result.collected_tools] == tools
    assert [
        item.activation.status for item in result.collected_tools
    ] == [
        ToolActivationStatus.DISABLED,
        ToolActivationStatus.ENABLED,
    ]
    assert [item.tool_id for item in result.collected_tools] == [
        build_tool_id(
            server_selection_id=server.selection_id,
            tool_name="disabled",
            snapshot_ordinal=0,
        ),
        build_tool_id(
            server_selection_id=server.selection_id,
            tool_name="enabled",
            snapshot_ordinal=1,
        ),
    ]
    assert result.scan_result is not None
    assert result.scan_result.tools == tools
    assert stage_statuses(result)[DynamicScanStage.SCAN] == (
        DynamicStageStatus.SUCCEEDED
    )


def test_http_snapshot_reaches_policy_and_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server(transport=McpTransport.STREAMABLE_HTTP)
    tool = make_tool("remote-search")
    snapshot_calls = install_snapshot(
        monkeypatch,
        make_snapshot(
            server,
            tools=[tool],
            cleanup=make_cleanup(
                remote_status=(
                    RemoteSessionTerminationStatus.CONFIRMED
                ),
            ),
        ),
    )
    scanner_calls = install_scanner(monkeypatch)

    result = run_scan(server)
    statuses = stage_statuses(result)

    assert result.status == DynamicScanStatus.SUCCESS
    assert snapshot_calls[0]["connection"] == server.connection
    assert scanner_calls[0]["tools"] == [tool]
    assert [item.metadata for item in result.collected_tools] == [tool]
    assert statuses[DynamicScanStage.REMOTE_SESSION_TERMINATION] == (
        DynamicStageStatus.SUCCEEDED
    )
    assert statuses[DynamicScanStage.SCAN] == DynamicStageStatus.SUCCEEDED


def test_http_remote_termination_failure_preserves_scan_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server(transport=McpTransport.STREAMABLE_HTTP)
    tool = make_tool("remote-search")
    termination_issue = DynamicScanIssue(
        stage=DynamicScanStage.REMOTE_SESSION_TERMINATION,
        code="remote_session_termination_unconfirmed",
        level=IssueLevel.WARNING,
        safe_message=(
            "Remote MCP session termination could not be confirmed."
        ),
        server_id=server.selection_id,
    )
    install_snapshot(
        monkeypatch,
        make_snapshot(
            server,
            tools=[tool],
            issues=[termination_issue],
            cleanup=make_cleanup(
                remote_status=(
                    RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED
                ),
                remote_issues=[termination_issue],
            ),
        ),
    )
    scanner_calls = install_scanner(monkeypatch)

    result = run_scan(server)

    assert result.status == DynamicScanStatus.PARTIAL_SUCCESS
    assert scanner_calls[0]["tools"] == [tool]
    assert result.scan_result is not None
    assert result.scan_result.tools == [tool]
    assert stage_statuses(result)[
        DynamicScanStage.REMOTE_SESSION_TERMINATION
    ] == DynamicStageStatus.FAILED


def test_http_remote_termination_timeout_preserves_scan_and_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server(transport=McpTransport.STREAMABLE_HTTP)
    tool = make_tool("remote-search")
    termination_issue = DynamicScanIssue(
        stage=DynamicScanStage.REMOTE_SESSION_TERMINATION,
        code="remote_session_termination_timeout",
        level=IssueLevel.WARNING,
        safe_message=(
            "Remote MCP session termination could not be confirmed in time."
        ),
        server_id=server.selection_id,
    )
    install_snapshot(
        monkeypatch,
        make_snapshot(
            server,
            tools=[tool],
            issues=[termination_issue],
            cleanup=make_cleanup(
                remote_status=(
                    RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED
                ),
                remote_issues=[termination_issue],
            ),
        ),
    )
    scanner_calls = install_scanner(monkeypatch)

    result = run_scan(server)

    assert result.status == DynamicScanStatus.TIMED_OUT
    assert scanner_calls[0]["tools"] == [tool]
    assert result.scan_result is not None
    assert stage_statuses(result)[
        DynamicScanStage.REMOTE_SESSION_TERMINATION
    ] == DynamicStageStatus.TIMED_OUT


def test_tool_ids_are_stable_for_the_same_snapshot_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    tools = [make_tool("first"), make_tool("second")]
    install_snapshot(monkeypatch, make_snapshot(server, tools=tools))
    install_scanner(monkeypatch)

    first_result = run_scan(server)
    second_result = run_scan(server)

    assert [
        item.tool_id for item in first_result.collected_tools
    ] == [
        item.tool_id for item in second_result.collected_tools
    ]


def test_collection_failure_skips_policy_and_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    list_issue = DynamicScanIssue(
        stage=DynamicScanStage.LIST_TOOLS,
        code="list_tools_failed",
        level=IssueLevel.ERROR,
        safe_message="The tools/list request failed.",
        server_id=server.selection_id,
    )
    install_snapshot(
        monkeypatch,
        make_snapshot(server, issues=[list_issue]),
    )

    def fail_if_scanned(**kwargs):
        raise AssertionError("scanner must not run")

    monkeypatch.setattr(
        dynamic_scan_service,
        "execute_tool_scan",
        fail_if_scanned,
    )

    result = run_scan(server)
    statuses = stage_statuses(result)

    assert result.status == DynamicScanStatus.FAILED
    assert result.scan_result is None
    assert statuses[DynamicScanStage.LIST_TOOLS] == (
        DynamicStageStatus.FAILED
    )
    assert statuses[DynamicScanStage.METADATA_VALIDATION] == (
        DynamicStageStatus.SKIPPED
    )
    assert statuses[DynamicScanStage.TOOL_POLICY] == (
        DynamicStageStatus.SKIPPED
    )
    assert statuses[DynamicScanStage.SCAN] == DynamicStageStatus.SKIPPED


def test_successful_empty_tool_list_is_failed_without_running_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    install_snapshot(monkeypatch, make_snapshot(server))

    def fail_if_scanned(**kwargs):
        raise AssertionError("scanner must not run")

    monkeypatch.setattr(
        dynamic_scan_service,
        "execute_tool_scan",
        fail_if_scanned,
    )

    result = run_scan(server)
    statuses = stage_statuses(result)

    assert result.status == DynamicScanStatus.FAILED
    assert statuses[DynamicScanStage.LIST_TOOLS] == (
        DynamicStageStatus.SUCCEEDED
    )
    assert statuses[DynamicScanStage.METADATA_VALIDATION] == (
        DynamicStageStatus.SUCCEEDED
    )
    assert statuses[DynamicScanStage.SCAN] == DynamicStageStatus.FAILED
    assert [issue.code for issue in result.issues] == [
        "no_tools_collected"
    ]


def test_configuration_failure_skips_connection_and_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    config_issue = DynamicScanIssue(
        stage=DynamicScanStage.CONFIGURATION,
        code="environment_reference_missing",
        level=IssueLevel.ERROR,
        safe_message="A required environment reference is unavailable.",
        server_id=server.selection_id,
    )
    install_snapshot(
        monkeypatch,
        make_snapshot(
            server,
            issues=[config_issue],
            initialized=False,
        ),
    )

    result = run_scan(server)
    statuses = stage_statuses(result)

    assert result.status == DynamicScanStatus.FAILED
    assert statuses[DynamicScanStage.CONFIGURATION] == (
        DynamicStageStatus.FAILED
    )
    assert statuses[DynamicScanStage.CONNECT] == DynamicStageStatus.SKIPPED
    assert statuses[DynamicScanStage.INITIALIZE] == (
        DynamicStageStatus.SKIPPED
    )
    assert statuses[DynamicScanStage.SCAN] == DynamicStageStatus.SKIPPED


def test_partial_metadata_and_detector_warning_keep_scan_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    tool = make_tool("search")
    metadata_issue = DynamicScanIssue(
        stage=DynamicScanStage.METADATA_VALIDATION,
        code="tool_metadata_invalid",
        level=IssueLevel.WARNING,
        safe_message="One metadata item was invalid.",
        server_id=server.selection_id,
        item_index=1,
    )
    install_snapshot(
        monkeypatch,
        make_snapshot(
            server,
            tools=[tool],
            issues=[metadata_issue],
        ),
    )
    install_scanner(
        monkeypatch,
        warnings=["Detector detector-1 failed safely."],
    )

    result = run_scan(server)

    assert result.status == DynamicScanStatus.PARTIAL_SUCCESS
    assert result.scan_result is not None
    assert result.scan_result.tools == [tool]
    assert stage_statuses(result)[
        DynamicScanStage.METADATA_VALIDATION
    ] == DynamicStageStatus.SUCCEEDED
    assert any(
        issue.code == "scanner_warning" for issue in result.issues
    )


def test_timeout_status_skips_later_collection_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    timeout_issue = DynamicScanIssue(
        stage=DynamicScanStage.INITIALIZE,
        code="initialize_timeout",
        level=IssueLevel.ERROR,
        safe_message="Initialization timed out.",
        server_id=server.selection_id,
    )
    install_snapshot(
        monkeypatch,
        make_snapshot(
            server,
            issues=[timeout_issue],
            initialized=False,
        ),
    )

    result = run_scan(server)
    statuses = stage_statuses(result)

    assert result.status == DynamicScanStatus.TIMED_OUT
    assert statuses[DynamicScanStage.INITIALIZE] == (
        DynamicStageStatus.TIMED_OUT
    )
    assert statuses[DynamicScanStage.LIST_TOOLS] == (
        DynamicStageStatus.SKIPPED
    )
    assert statuses[DynamicScanStage.SCAN] == DynamicStageStatus.SKIPPED


@pytest.mark.parametrize(
    ("server", "failed_stage", "expected_code"),
    [
        (
            make_server(enabled_state=ServerEnabledState.DISABLED),
            DynamicScanStage.SELECTION,
            "server_disabled",
        ),
        (
            make_server(
                support_state=ServerSupportState.UNSUPPORTED,
            ),
            DynamicScanStage.SELECTION,
            "server_not_supported",
        ),
        (
            make_server(
                support_state=ServerSupportState.INVALID,
            ),
            DynamicScanStage.SELECTION,
            "server_not_supported",
        ),
    ],
)
def test_non_executable_server_does_not_call_mcp_client(
    monkeypatch: pytest.MonkeyPatch,
    server: DiscoveredMcpServer,
    failed_stage: DynamicScanStage,
    expected_code: str,
) -> None:
    called = False

    async def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("MCP client must not run")

    monkeypatch.setattr(
        dynamic_scan_service,
        "collect_tools_snapshot",
        fail_if_called,
    )

    result = run_scan(server)

    assert called is False
    assert result.status == DynamicScanStatus.FAILED
    assert [issue.code for issue in result.issues] == [expected_code]
    assert stage_statuses(result)[failed_stage] == (
        DynamicStageStatus.FAILED
    )
    assert result.scan_result is None
    safe_result = str(result.model_dump())
    assert "TEST_SECRET" not in safe_result
    assert "password" not in safe_result


def test_cleanup_failure_preserves_collected_tools_and_scan_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    tool = make_tool("search")
    cleanup_issue = DynamicScanIssue(
        stage=DynamicScanStage.LOCAL_CLEANUP,
        code="local_cleanup_failed",
        level=IssueLevel.ERROR,
        safe_message="Local resources could not be fully closed.",
        server_id=server.selection_id,
    )
    install_snapshot(
        monkeypatch,
        make_snapshot(
            server,
            tools=[tool],
            issues=[cleanup_issue],
            cleanup=make_cleanup(
                status=LocalCleanupStatus.FAILED,
                issues=[cleanup_issue],
            ),
        ),
    )
    install_scanner(monkeypatch)

    result = run_scan(server)

    assert result.status == DynamicScanStatus.PARTIAL_SUCCESS
    assert [item.metadata for item in result.collected_tools] == [tool]
    assert result.scan_result is not None
    assert result.scan_result.tools == [tool]
    assert stage_statuses(result)[DynamicScanStage.LOCAL_CLEANUP] == (
        DynamicStageStatus.FAILED
    )


def test_policy_failure_marks_tools_unknown_and_still_scans_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    tools = [make_tool("first"), make_tool("second")]
    install_snapshot(monkeypatch, make_snapshot(server, tools=tools))
    scanner_calls = install_scanner(monkeypatch)

    def fail_policy(**kwargs):
        raise RuntimeError("TEST_SECRET internal detail")

    monkeypatch.setattr(
        dynamic_scan_service,
        "evaluate_tool_activations",
        fail_policy,
    )

    result = run_scan(server)

    assert result.status == DynamicScanStatus.PARTIAL_SUCCESS
    assert scanner_calls[0]["tools"] == tools
    assert all(
        item.activation.status == ToolActivationStatus.UNKNOWN
        for item in result.collected_tools
    )
    assert stage_statuses(result)[DynamicScanStage.TOOL_POLICY] == (
        DynamicStageStatus.FAILED
    )
    assert "TEST_SECRET" not in str(result.model_dump())


def test_unexpected_snapshot_exception_becomes_safe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()

    async def fail_snapshot(*args, **kwargs):
        raise RuntimeError("TEST_SECRET stack detail")

    monkeypatch.setattr(
        dynamic_scan_service,
        "collect_tools_snapshot",
        fail_snapshot,
    )

    result = run_scan(server)

    assert result.status == DynamicScanStatus.FAILED
    assert result.scan_result is None
    assert [issue.code for issue in result.issues] == [
        "snapshot_collection_failed",
        "local_cleanup_unconfirmed",
    ]
    assert result.cleanup.local_cleanup.status == LocalCleanupStatus.FAILED
    assert "TEST_SECRET" not in str(result.model_dump())


def test_unexpected_scanner_exception_keeps_collected_tools_but_fails_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    tool = make_tool("search")
    install_snapshot(
        monkeypatch,
        make_snapshot(server, tools=[tool]),
    )

    def fail_scan(**kwargs):
        raise RuntimeError("TEST_SECRET scanner detail")

    monkeypatch.setattr(
        dynamic_scan_service,
        "execute_tool_scan",
        fail_scan,
    )

    result = run_scan(server)

    assert result.status == DynamicScanStatus.FAILED
    assert [item.metadata for item in result.collected_tools] == [tool]
    assert result.scan_result is None
    assert stage_statuses(result)[DynamicScanStage.SCAN] == (
        DynamicStageStatus.FAILED
    )
    assert [issue.code for issue in result.issues] == ["scan_failed"]
    assert "TEST_SECRET" not in str(result.model_dump())


def test_unexpected_service_exception_is_not_exposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = make_server()
    install_snapshot(
        monkeypatch,
        make_snapshot(server, tools=[make_tool("search")]),
    )

    def fail_result_processing(**kwargs):
        raise RuntimeError("TEST_SECRET orchestration detail")

    monkeypatch.setattr(
        dynamic_scan_service,
        "_apply_snapshot_stages",
        fail_result_processing,
    )

    result = run_scan(server)

    assert result.status == DynamicScanStatus.FAILED
    assert [issue.code for issue in result.issues] == [
        "dynamic_scan_internal_error",
        "local_cleanup_unconfirmed",
    ]
    assert "TEST_SECRET" not in str(result.model_dump())
