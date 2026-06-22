from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.dynamic_scan_models import (
    CleanupResult,
    CollectedTool,
    DiscoveredMcpServer,
    DynamicScanIssue,
    DynamicScanResult,
    DynamicScanStage,
    DynamicScanStageResult,
    DynamicScanStatus,
    DynamicScanTimeouts,
    DynamicStageStatus,
    IssueLevel,
    LocalCleanupResult,
    LocalCleanupStatus,
    McpProtocolMetadata,
    McpServerSummary,
    McpSnapshotResult,
    RemoteSessionTerminationResult,
    RemoteSessionTerminationStatus,
    ServerEnabledState,
    ServerSupportState,
    ToolActivationAssessment,
    ToolActivationStatus,
    build_tool_id,
)
from core.mcp_client import collect_tools_snapshot
from core.mcp_tool_policy import evaluate_tool_activations
from core.models import ToolMetadata
from core.scan_result import ScanResult
from core.scan_service import execute_tool_scan


_STAGE_ORDER = (
    DynamicScanStage.SELECTION,
    DynamicScanStage.CONFIGURATION,
    DynamicScanStage.CONNECT,
    DynamicScanStage.INITIALIZE,
    DynamicScanStage.LIST_TOOLS,
    DynamicScanStage.METADATA_VALIDATION,
    DynamicScanStage.REMOTE_SESSION_TERMINATION,
    DynamicScanStage.LOCAL_CLEANUP,
    DynamicScanStage.TOOL_POLICY,
    DynamicScanStage.SCAN,
)


async def run_dynamic_scan(
    server: DiscoveredMcpServer,
    *,
    timeouts: DynamicScanTimeouts | None = None,
    environment: Mapping[str, str] | None = None,
) -> DynamicScanResult:
    """Run one discovered MCP server through snapshot, policy, and scan."""
    try:
        return await _run_dynamic_scan(
            server,
            timeouts=timeouts,
            environment=environment,
        )
    except Exception:
        return _unexpected_service_failure(server)


async def _run_dynamic_scan(
    server: DiscoveredMcpServer,
    *,
    timeouts: DynamicScanTimeouts | None,
    environment: Mapping[str, str] | None,
) -> DynamicScanResult:
    target = server.to_summary()
    stages = {
        stage: DynamicStageStatus.SKIPPED
        for stage in _STAGE_ORDER
    }
    issues: list[DynamicScanIssue] = []
    collected_tools: list[CollectedTool] = []
    scan_result: ScanResult | None = None
    protocol_metadata: McpProtocolMetadata | None = None
    cleanup = _empty_cleanup()

    preflight_issue = _validate_server(server)
    if preflight_issue is not None:
        issues.append(preflight_issue)
        stages[preflight_issue.stage] = DynamicStageStatus.FAILED
        if preflight_issue.stage != DynamicScanStage.SELECTION:
            stages[DynamicScanStage.SELECTION] = (
                DynamicStageStatus.SUCCEEDED
            )
        if preflight_issue.stage == DynamicScanStage.CONNECT:
            stages[DynamicScanStage.CONFIGURATION] = (
                DynamicStageStatus.SUCCEEDED
            )
        stages[DynamicScanStage.LOCAL_CLEANUP] = (
            DynamicStageStatus.SUCCEEDED
        )
        return _build_result(
            status=DynamicScanStatus.FAILED,
            target=target,
            stages=stages,
            issues=issues,
            cleanup=cleanup,
        )

    stages[DynamicScanStage.SELECTION] = DynamicStageStatus.SUCCEEDED
    stages[DynamicScanStage.CONFIGURATION] = DynamicStageStatus.SUCCEEDED

    try:
        snapshot = await collect_tools_snapshot(
            server.connection,
            server_summary=target,
            timeouts=timeouts,
            environment=environment,
        )
    except Exception:
        unexpected_issue = _issue(
            server,
            stage=DynamicScanStage.CONNECT,
            code="snapshot_collection_failed",
            safe_message=(
                "The MCP snapshot could not be collected because of an "
                "internal error."
            ),
        )
        cleanup_issue = _issue(
            server,
            stage=DynamicScanStage.LOCAL_CLEANUP,
            code="local_cleanup_unconfirmed",
            safe_message=(
                "Local MCP resource cleanup could not be confirmed."
            ),
        )
        issues.extend([unexpected_issue, cleanup_issue])
        cleanup = CleanupResult(
            local_cleanup=LocalCleanupResult(
                status=LocalCleanupStatus.FAILED,
                issues=[cleanup_issue],
            ),
            remote_session_termination=RemoteSessionTerminationResult(
                status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
            ),
        )
        stages[DynamicScanStage.CONNECT] = DynamicStageStatus.FAILED
        stages[DynamicScanStage.LOCAL_CLEANUP] = (
            DynamicStageStatus.FAILED
        )
        return _build_result(
            status=DynamicScanStatus.FAILED,
            target=target,
            stages=stages,
            issues=issues,
            cleanup=cleanup,
        )

    cleanup = snapshot.cleanup
    issues.extend(snapshot.issues)
    protocol_metadata = _protocol_metadata(snapshot)
    _apply_snapshot_stages(
        snapshot=snapshot,
        stages=stages,
        issues=issues,
    )

    if _can_scan_snapshot(snapshot=snapshot, stages=stages):
        try:
            collected_tools = _evaluate_and_collect(
                server=server,
                tools=snapshot.tools,
                stages=stages,
                issues=issues,
            )
        except Exception:
            issues.append(
                _issue(
                    server,
                    stage=DynamicScanStage.TOOL_POLICY,
                    code="collected_tool_assembly_failed",
                    safe_message=(
                        "Collected MCP tools could not be safely assembled."
                    ),
                )
            )
            stages[DynamicScanStage.TOOL_POLICY] = (
                DynamicStageStatus.FAILED
            )
            return _build_result(
                status=DynamicScanStatus.FAILED,
                target=target,
                stages=stages,
                issues=issues,
                protocol_metadata=protocol_metadata,
                cleanup=cleanup,
            )

        tools_for_scan = [
            collected.metadata for collected in collected_tools
        ]
        try:
            candidate_scan_result = execute_tool_scan(
                tools=tools_for_scan,
                scan_type="dynamic",
                source_type="mcp_server",
                source=f"mcp:{server.selection_id}",
            )
            _validate_scan_result(
                scan_result=candidate_scan_result,
                tools=tools_for_scan,
                expected_source=f"mcp:{server.selection_id}",
            )
        except Exception:
            issues.append(
                _issue(
                    server,
                    stage=DynamicScanStage.SCAN,
                    code="scan_failed",
                    safe_message=(
                        "The collected MCP tool metadata could not be "
                        "scanned."
                    ),
                )
            )
            stages[DynamicScanStage.SCAN] = DynamicStageStatus.FAILED
        else:
            scan_result = candidate_scan_result
            stages[DynamicScanStage.SCAN] = DynamicStageStatus.SUCCEEDED
            issues.extend(
                _scanner_warning_issues(
                    server=server,
                    warnings=scan_result.warnings,
                )
            )
    elif (
        not snapshot.tools
        and _snapshot_reached_tool_collection(stages)
    ):
        stages[DynamicScanStage.SCAN] = DynamicStageStatus.FAILED

        issues.append(
            _issue(
                server,
                stage=DynamicScanStage.SCAN,
                code="no_tools_collected",
                safe_message=(
                    "No valid MCP tool metadata was available to scan."
                ),
            )
        )

    status = _final_status(
        stages=stages,
        issues=issues,
        scan_result=scan_result,
        cleanup=cleanup,
    )

    return _build_result(
        status=status,
        target=target,
        stages=stages,
        issues=issues,
        protocol_metadata=protocol_metadata,
        collected_tools=collected_tools,
        cleanup=cleanup,
        scan_result=scan_result,
    )


def _validate_server(
    server: DiscoveredMcpServer,
) -> DynamicScanIssue | None:
    if server.enabled_state == ServerEnabledState.DISABLED:
        return _issue(
            server,
            stage=DynamicScanStage.SELECTION,
            code="server_disabled",
            safe_message="The selected MCP server is disabled.",
        )

    if server.support_state != ServerSupportState.SUPPORTED:
        return _issue(
            server,
            stage=DynamicScanStage.SELECTION,
            code="server_not_supported",
            safe_message="The selected MCP server is not executable.",
        )

    if server.connection is None:
        return _issue(
            server,
            stage=DynamicScanStage.CONFIGURATION,
            code="connection_missing",
            safe_message=(
                "The selected MCP server has no executable connection."
            ),
        )

    return None


def _apply_snapshot_stages(
    *,
    snapshot: McpSnapshotResult,
    stages: dict[DynamicScanStage, DynamicStageStatus],
    issues: list[DynamicScanIssue],
) -> None:
    selection_status = _issue_stage_status(
        issues,
        DynamicScanStage.SELECTION,
    )
    if selection_status is not None:
        stages[DynamicScanStage.SELECTION] = selection_status
        stages[DynamicScanStage.CONFIGURATION] = (
            DynamicStageStatus.SKIPPED
        )

    configuration_status = _issue_stage_status(
        issues,
        DynamicScanStage.CONFIGURATION,
    )
    if (
        stages[DynamicScanStage.SELECTION]
        == DynamicStageStatus.SUCCEEDED
        and configuration_status is not None
    ):
        stages[DynamicScanStage.CONFIGURATION] = configuration_status

    if (
        stages[DynamicScanStage.CONFIGURATION]
        != DynamicStageStatus.SUCCEEDED
    ):
        connect_status = None
    else:
        connect_status = _issue_stage_status(
            issues,
            DynamicScanStage.CONNECT,
        )

    if (
        stages[DynamicScanStage.CONFIGURATION]
        == DynamicStageStatus.SUCCEEDED
    ):
        stages[DynamicScanStage.CONNECT] = (
            connect_status or DynamicStageStatus.SUCCEEDED
        )

    if stages[DynamicScanStage.CONNECT] == DynamicStageStatus.SUCCEEDED:
        initialize_status = _issue_stage_status(
            issues,
            DynamicScanStage.INITIALIZE,
        )
        if initialize_status is not None:
            stages[DynamicScanStage.INITIALIZE] = initialize_status
        elif snapshot.protocol_version is not None:
            stages[DynamicScanStage.INITIALIZE] = (
                DynamicStageStatus.SUCCEEDED
            )
        else:
            stages[DynamicScanStage.INITIALIZE] = DynamicStageStatus.FAILED
            issues.append(
                DynamicScanIssue(
                    stage=DynamicScanStage.INITIALIZE,
                    code="initialize_result_missing",
                    safe_message=(
                        "The MCP initialization result is unavailable."
                    ),
                    level=IssueLevel.WARNING,
                )
            )

    if (
        stages[DynamicScanStage.INITIALIZE]
        == DynamicStageStatus.SUCCEEDED
    ):
        list_status = _issue_stage_status(
            issues,
            DynamicScanStage.LIST_TOOLS,
        )
        stages[DynamicScanStage.LIST_TOOLS] = (
            list_status or DynamicStageStatus.SUCCEEDED
        )

    if (
        stages[DynamicScanStage.LIST_TOOLS]
        == DynamicStageStatus.SUCCEEDED
        or snapshot.tools
    ):
        metadata_status = _metadata_stage_status(
            snapshot=snapshot,
            issues=issues,
        )
        stages[DynamicScanStage.METADATA_VALIDATION] = metadata_status

    remote_status = snapshot.cleanup.remote_session_termination.status
    if remote_status == RemoteSessionTerminationStatus.CONFIRMED:
        stages[DynamicScanStage.REMOTE_SESSION_TERMINATION] = (
            DynamicStageStatus.SUCCEEDED
        )
    elif (
        remote_status
        == RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED
    ):
        remote_stage_status = _issue_stage_status(
            issues,
            DynamicScanStage.REMOTE_SESSION_TERMINATION,
        )
        stages[DynamicScanStage.REMOTE_SESSION_TERMINATION] = (
            remote_stage_status or DynamicStageStatus.FAILED
        )
        if not any(
            issue.stage
            == DynamicScanStage.REMOTE_SESSION_TERMINATION
            for issue in issues
        ):
            issues.append(
                DynamicScanIssue(
                    stage=(
                        DynamicScanStage.REMOTE_SESSION_TERMINATION
                    ),
                    code="remote_session_termination_unconfirmed",
                    level=IssueLevel.WARNING,
                    safe_message=(
                        "Remote MCP session termination could not be "
                        "confirmed."
                    ),
                    server_id=snapshot.server_summary.selection_id,
                )
            )

    cleanup_status = _issue_stage_status(
        issues,
        DynamicScanStage.LOCAL_CLEANUP,
    )
    if cleanup_status is not None:
        stages[DynamicScanStage.LOCAL_CLEANUP] = cleanup_status
    else:
        stages[DynamicScanStage.LOCAL_CLEANUP] = (
            DynamicStageStatus.SUCCEEDED
            if snapshot.cleanup.local_cleanup.status
            == LocalCleanupStatus.SUCCEEDED
            else DynamicStageStatus.FAILED
        )
        if (
            snapshot.cleanup.local_cleanup.status
            == LocalCleanupStatus.FAILED
        ):
            issues.append(
                DynamicScanIssue(
                    stage=DynamicScanStage.LOCAL_CLEANUP,
                    code="local_cleanup_failed",
                    level=IssueLevel.ERROR,
                    safe_message=(
                        "Local MCP resources could not be fully closed."
                    ),
                    server_id=snapshot.server_summary.selection_id,
                )
            )


def _evaluate_and_collect(
    *,
    server: DiscoveredMcpServer,
    tools: list[ToolMetadata],
    stages: dict[DynamicScanStage, DynamicStageStatus],
    issues: list[DynamicScanIssue],
) -> list[CollectedTool]:
    issues.extend(_policy_parse_issues(server))

    try:
        assessments = evaluate_tool_activations(
            tools=tools,
            policy=server.tool_policy,
        )
        if len(assessments) != len(tools):
            raise ValueError("policy assessment count mismatch")
    except Exception:
        assessments = [
            ToolActivationAssessment(
                tool_name=tool.tool_name,
                status=ToolActivationStatus.UNKNOWN,
                product=server.product,
                safe_basis_code="policy_evaluation_failed",
            )
            for tool in tools
        ]
        issues.append(
            _issue(
                server,
                stage=DynamicScanStage.TOOL_POLICY,
                code="tool_policy_evaluation_failed",
                safe_message=(
                    "Tool activation policy could not be evaluated; "
                    "affected tools were marked unknown."
                ),
                level=IssueLevel.WARNING,
            )
        )
        stages[DynamicScanStage.TOOL_POLICY] = DynamicStageStatus.FAILED
    else:
        stages[DynamicScanStage.TOOL_POLICY] = (
            DynamicStageStatus.SUCCEEDED
        )

    collected_tools = [
        CollectedTool(
            tool_id=build_tool_id(
                server_selection_id=server.selection_id,
                tool_name=tool.tool_name,
                snapshot_ordinal=ordinal,
            ),
            metadata=tool,
            activation=assessment,
        )
        for ordinal, (tool, assessment) in enumerate(
            zip(tools, assessments, strict=True)
        )
    ]

    issues.extend(
        _unknown_policy_issues(
            server=server,
            collected_tools=collected_tools,
        )
    )
    return collected_tools


def _policy_parse_issues(
    server: DiscoveredMcpServer,
) -> list[DynamicScanIssue]:
    return [
        _issue(
            server,
            stage=DynamicScanStage.TOOL_POLICY,
            code=issue.code,
            safe_message=issue.safe_message,
            level=IssueLevel.WARNING,
        )
        for issue in server.tool_policy.parse_issues
    ]


def _unknown_policy_issues(
    *,
    server: DiscoveredMcpServer,
    collected_tools: Sequence[CollectedTool],
) -> list[DynamicScanIssue]:
    return [
        DynamicScanIssue(
            stage=DynamicScanStage.TOOL_POLICY,
            code="tool_activation_unknown",
            level=IssueLevel.WARNING,
            safe_message=(
                "Tool activation could not be determined from the "
                "available host policy sources."
            ),
            server_id=server.selection_id,
            tool_id=collected.tool_id,
            tool_name=collected.metadata.tool_name,
        )
        for collected in collected_tools
        if collected.activation.status == ToolActivationStatus.UNKNOWN
    ]


def _scanner_warning_issues(
    *,
    server: DiscoveredMcpServer,
    warnings: Sequence[str],
) -> list[DynamicScanIssue]:
    return [
        _issue(
            server,
            stage=DynamicScanStage.SCAN,
            code="scanner_warning",
            safe_message=warning,
            level=IssueLevel.WARNING,
        )
        for warning in warnings
    ]


def _validate_scan_result(
    *,
    scan_result: ScanResult,
    tools: list[ToolMetadata],
    expected_source: str,
) -> None:
    if scan_result.scan_type != "dynamic":
        raise ValueError("dynamic scan type required")
    if scan_result.source_type != "mcp_server":
        raise ValueError("MCP source type required")
    if scan_result.tools != tools:
        raise ValueError("scan result tools must preserve snapshot order")
    if scan_result.source != expected_source:
        raise ValueError("scan result source must match selected MCP server")


def _metadata_stage_status(
    *,
    snapshot: McpSnapshotResult,
    issues: Sequence[DynamicScanIssue],
) -> DynamicStageStatus:
    metadata_issues = [
        issue
        for issue in issues
        if issue.stage == DynamicScanStage.METADATA_VALIDATION
    ]
    if any(
        issue.code == "all_tool_metadata_invalid"
        for issue in metadata_issues
    ):
        return DynamicStageStatus.FAILED
    if snapshot.tools:
        return DynamicStageStatus.SUCCEEDED
    if any(issue.level == IssueLevel.ERROR for issue in metadata_issues):
        return DynamicStageStatus.FAILED
    return DynamicStageStatus.SUCCEEDED


def _issue_stage_status(
    issues: Sequence[DynamicScanIssue],
    stage: DynamicScanStage,
) -> DynamicStageStatus | None:
    stage_issues = [issue for issue in issues if issue.stage == stage]
    if not stage_issues:
        return None
    if any(_is_timeout_issue(issue) for issue in stage_issues):
        return DynamicStageStatus.TIMED_OUT
    if any(issue.level == IssueLevel.ERROR for issue in stage_issues):
        return DynamicStageStatus.FAILED
    return None


def _snapshot_reached_tool_collection(
    stages: Mapping[DynamicScanStage, DynamicStageStatus],
) -> bool:
    return (
        stages[DynamicScanStage.LIST_TOOLS]
        == DynamicStageStatus.SUCCEEDED
    )


def _can_scan_snapshot(
    *,
    snapshot: McpSnapshotResult,
    stages: Mapping[DynamicScanStage, DynamicStageStatus],
) -> bool:
    return (
        bool(snapshot.tools)
        and stages[DynamicScanStage.LIST_TOOLS]
        != DynamicStageStatus.SKIPPED
        and stages[DynamicScanStage.METADATA_VALIDATION]
        != DynamicStageStatus.FAILED
    )


def _final_status(
    *,
    stages: Mapping[DynamicScanStage, DynamicStageStatus],
    issues: Sequence[DynamicScanIssue],
    scan_result: ScanResult | None,
    cleanup: CleanupResult,
) -> DynamicScanStatus:
    if any(
        status == DynamicStageStatus.TIMED_OUT
        for status in stages.values()
    ) or any(_is_timeout_issue(issue) for issue in issues):
        return DynamicScanStatus.TIMED_OUT

    if scan_result is None:
        return DynamicScanStatus.FAILED

    if (
        issues
        or scan_result.warnings
        or cleanup.local_cleanup.status == LocalCleanupStatus.FAILED
        or cleanup.remote_session_termination.status
        == RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED
    ):
        return DynamicScanStatus.PARTIAL_SUCCESS

    return DynamicScanStatus.SUCCESS


def _is_timeout_issue(issue: DynamicScanIssue) -> bool:
    return issue.code.endswith("_timeout")


def _protocol_metadata(
    snapshot: McpSnapshotResult,
) -> McpProtocolMetadata | None:
    if (
        snapshot.protocol_version is None
        and snapshot.server_implementation is None
    ):
        return None

    return McpProtocolMetadata(
        protocol_version=snapshot.protocol_version,
        server_implementation=snapshot.server_implementation,
    )


def _empty_cleanup() -> CleanupResult:
    return CleanupResult(
        local_cleanup=LocalCleanupResult(
            status=LocalCleanupStatus.SUCCEEDED,
        ),
        remote_session_termination=RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
        ),
    )


def _unexpected_service_failure(
    server: DiscoveredMcpServer,
) -> DynamicScanResult:
    service_issue = _issue(
        server,
        stage=DynamicScanStage.SCAN,
        code="dynamic_scan_internal_error",
        safe_message=(
            "The dynamic MCP scan could not be completed because of an "
            "internal error."
        ),
    )
    cleanup_issue = _issue(
        server,
        stage=DynamicScanStage.LOCAL_CLEANUP,
        code="local_cleanup_unconfirmed",
        safe_message="Local MCP resource cleanup could not be confirmed.",
    )
    stages = {
        stage: DynamicStageStatus.SKIPPED
        for stage in _STAGE_ORDER
    }
    stages[DynamicScanStage.SCAN] = DynamicStageStatus.FAILED
    stages[DynamicScanStage.LOCAL_CLEANUP] = DynamicStageStatus.FAILED

    return _build_result(
        status=DynamicScanStatus.FAILED,
        target=server.to_summary(),
        stages=stages,
        issues=[service_issue, cleanup_issue],
        cleanup=CleanupResult(
            local_cleanup=LocalCleanupResult(
                status=LocalCleanupStatus.FAILED,
                issues=[cleanup_issue],
            ),
            remote_session_termination=RemoteSessionTerminationResult(
                status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
            ),
        ),
    )


def _build_result(
    *,
    status: DynamicScanStatus,
    target: McpServerSummary,
    stages: Mapping[DynamicScanStage, DynamicStageStatus],
    issues: list[DynamicScanIssue],
    cleanup: CleanupResult,
    protocol_metadata: McpProtocolMetadata | None = None,
    collected_tools: list[CollectedTool] | None = None,
    scan_result: ScanResult | None = None,
) -> DynamicScanResult:
    return DynamicScanResult(
        status=status,
        target=target,
        stages=[
            DynamicScanStageResult(
                stage=stage,
                status=stages[stage],
            )
            for stage in _STAGE_ORDER
        ],
        issues=issues,
        protocol_metadata=protocol_metadata,
        collected_tools=collected_tools or [],
        cleanup=cleanup,
        scan_result=scan_result,
    )


def _issue(
    server: DiscoveredMcpServer,
    *,
    stage: DynamicScanStage,
    code: str,
    safe_message: str,
    level: IssueLevel = IssueLevel.ERROR,
) -> DynamicScanIssue:
    return DynamicScanIssue(
        stage=stage,
        code=code,
        level=level,
        safe_message=safe_message,
        server_id=server.selection_id,
    )
