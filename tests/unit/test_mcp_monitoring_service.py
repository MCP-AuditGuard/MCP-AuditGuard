from __future__ import annotations

import asyncio

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.dynamic_scan_models import (
    CleanupResult,
    CollectedTool,
    DiscoveryContext,
    DiscoveredMcpServer,
    DynamicScanResult,
    DynamicScanStatus,
    HostToolPolicy,
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
    ToolActivationAssessment,
    ToolActivationStatus,
)
from core.mcp_baseline_repository import (
    MonitoringConflictError,
    MonitoringNotFoundError,
    StateCommit,
)
from core.mcp_baseline_store import FileMcpBaselineRepository
from core import mcp_monitoring_service as monitoring_service_module
from core.mcp_monitoring_models import (
    BaselineHistoryEventType,
    BaselineLifecycleStatus,
    ComparisonStatus,
    MonitoringScanStatus,
    VerificationStatus,
)
from core.mcp_monitoring_service import (
    McpMonitoringService,
    MonitoringScanError,
    MonitoringServiceError,
)
from core.models import ToolMetadata
from core.scan_result import ScanResult


FIXED_TIME = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def make_context(tmp_path: Path) -> DiscoveryContext:
    project_root = tmp_path / "project"
    user_home = tmp_path / "home"
    project_root.mkdir(parents=True, exist_ok=True)
    user_home.mkdir(parents=True, exist_ok=True)
    return DiscoveryContext(
        current_working_directory=project_root,
        project_root=project_root,
        user_home=user_home,
        include_trusted_project_config=True,
    )


def make_policy(product: McpProduct = McpProduct.CODEX) -> HostToolPolicy:
    return HostToolPolicy(
        product=product,
        source_coverage=PolicySourceCoverage.COMPLETE,
    )


def make_server(
    *,
    selection_id: str = "codex:user:docs",
    server_name: str = "docs",
    scope: McpScope = McpScope.USER,
    command: str = "python",
    args: list[str] | None = None,
    enabled_state: ServerEnabledState = ServerEnabledState.ENABLED,
    support_state: ServerSupportState = ServerSupportState.SUPPORTED,
) -> DiscoveredMcpServer:
    args = args or ["server.py"]
    connection = (
        None
        if enabled_state == ServerEnabledState.DISABLED
        or support_state != ServerSupportState.SUPPORTED
        else StdioConnectionConfig(
            server_name=server_name,
            command=command,
            args=args,
        )
    )
    return DiscoveredMcpServer(
        selection_id=selection_id,
        product=McpProduct.CODEX,
        scope=scope,
        source_label="User config" if scope == McpScope.USER else "Project config",
        server_name=server_name,
        transport=McpTransport.STDIO,
        enabled_state=enabled_state,
        support_state=support_state,
        command_basename=command,
        argument_count=len(args),
        connection=connection,
        tool_policy=make_policy(),
    )


def make_tool(
    *,
    server_name: str = "docs",
    tool_name: str = "search",
    description: str = "Search docs.",
) -> ToolMetadata:
    return ToolMetadata.from_mcp_tool(
        {
            "name": tool_name,
            "title": "Search",
            "description": description,
            "inputSchema": {"type": "object"},
            "annotations": {"readOnlyHint": True},
            "_meta": {"version": "1.0"},
        },
        server_name=server_name,
        source="mcp:test",
        collected_at=FIXED_TIME,
    )


def make_cleanup() -> CleanupResult:
    return CleanupResult(
        local_cleanup=LocalCleanupResult(status=LocalCleanupStatus.SUCCEEDED),
        remote_session_termination=RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
        ),
    )


def make_dynamic_result(
    server: DiscoveredMcpServer,
    *,
    status: DynamicScanStatus = DynamicScanStatus.SUCCESS,
    tools: list[ToolMetadata] | None = None,
    with_scan_result: bool = True,
) -> DynamicScanResult:
    tools = tools if tools is not None else [make_tool(server_name=server.server_name)]
    collected_tools = [
        CollectedTool(
            tool_id=f"{index + 1:020x}",
            metadata=tool,
            activation=ToolActivationAssessment(
                tool_name=tool.tool_name,
                status=ToolActivationStatus.ENABLED,
                product=server.product,
                safe_basis_code="enabled_by_host",
            ),
        )
        for index, tool in enumerate(tools)
    ]
    scan_result = (
        ScanResult(
            scan_type="dynamic",
            source_type="mcp_server",
            source="mcp:test",
            started_at=FIXED_TIME,
            completed_at=FIXED_TIME,
            tools=tools,
            findings=[],
        )
        if with_scan_result
        else None
    )
    return DynamicScanResult(
        status=status,
        target=server.to_summary(),
        collected_tools=collected_tools,
        cleanup=make_cleanup(),
        scan_result=scan_result,
    )


class FakeDiscovery:
    def __init__(self, servers: list[DiscoveredMcpServer]) -> None:
        self.servers = servers
        self.calls = 0

    def __call__(self, context: DiscoveryContext) -> McpDiscoveryResult:
        self.calls += 1
        return McpDiscoveryResult(servers=list(self.servers))


class FakeRunner:
    def __init__(self, result: DynamicScanResult) -> None:
        self.result = result
        self.calls = 0

    async def __call__(self, server: DiscoveredMcpServer) -> DynamicScanResult:
        self.calls += 1
        return self.result


class IndexWarningRepository(FileMcpBaselineRepository):
    def _rebuild_indexes_best_effort(self, monitoring_group_key: str) -> list[str]:
        return ["index_rebuild_pending", "index_rebuild_pending"]


def make_service(
    tmp_path: Path,
    servers: list[DiscoveredMcpServer],
    runner_result: DynamicScanResult,
) -> tuple[McpMonitoringService, FileMcpBaselineRepository, FakeDiscovery, FakeRunner]:
    repo = FileMcpBaselineRepository(tmp_path)
    discovery = FakeDiscovery(servers)
    runner = FakeRunner(runner_result)
    service = McpMonitoringService(
        repo,
        discover_servers=discovery,
        dynamic_scan_runner=runner,
        clock=lambda: FIXED_TIME,
    )
    return service, repo, discovery, runner


def test_list_monitored_servers_does_not_create_target_state(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    result = make_dynamic_result(server)
    service, repo, discovery, _runner = make_service(tmp_path, [server], result)

    listed = service.list_monitored_servers(context)
    item = listed.servers[0]

    assert discovery.calls == 1
    assert item.server_summary == server.to_summary()
    assert item.can_scan is True
    assert item.safe_action_reason is None
    assert item.monitoring_state.state_version == 0
    assert item.related_target_count == 1
    assert repo.load_target_state(
        item.monitoring_identity.monitoring_target_key
    ) is None
    assert not (repo.root / "index.json").exists()
    assert not (
        repo.root
        / "groups"
        / item.monitoring_identity.monitoring_group_key
        / "index.json"
    ).exists()


def test_scan_creates_initial_candidate_from_successful_scan(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    dynamic_result = make_dynamic_result(server)
    service, repo, _discovery, runner = make_service(
        tmp_path,
        [server],
        dynamic_result,
    )

    result = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert runner.calls == 1
    assert result.candidate_created is True
    assert result.candidate is not None
    assert result.candidate.comparison_result is None
    assert result.monitoring_state.state_version == 1
    assert result.monitoring_state.pending_candidate_ids == [
        result.candidate.candidate_id
    ]
    assert result.monitoring_state.baseline_lifecycle == (
        BaselineLifecycleStatus.CANDIDATE_PENDING
    )
    assert repo.load_candidate(
        result.candidate.candidate_id,
        result.monitoring_identity.monitoring_target_key,
    ) == result.candidate


def test_scan_failure_updates_state_without_candidate(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    failed = make_dynamic_result(
        server,
        status=DynamicScanStatus.FAILED,
        with_scan_result=False,
    )
    service, _repo, _discovery, _runner = make_service(tmp_path, [server], failed)

    result = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert result.candidate is None
    assert result.candidate_created is False
    assert result.monitoring_state.last_scan_status == MonitoringScanStatus.FAILED
    assert result.monitoring_state.comparison_status == (
        ComparisonStatus.COMPARISON_FAILED
    )
    assert result.monitoring_state.verification_status == VerificationStatus.UNAVAILABLE
    assert result.monitoring_state.pending_candidate_ids == []


def test_snapshot_value_error_updates_state_without_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    dynamic_result = make_dynamic_result(server)
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        dynamic_result,
    )

    def fail_snapshot(*args: object, **kwargs: object) -> object:
        raise ValueError("SECRET_TOKEN C:/private/path")

    monkeypatch.setattr(
        monitoring_service_module,
        "create_tool_snapshot",
        fail_snapshot,
    )

    result = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert result.dynamic_scan_result == dynamic_result
    assert result.candidate is None
    assert result.comparison_result is None
    assert result.monitoring_state.last_scan_status == MonitoringScanStatus.SUCCESS
    assert result.monitoring_state.comparison_status == (
        ComparisonStatus.COMPARISON_FAILED
    )
    assert result.monitoring_state.verification_status == VerificationStatus.UNAVAILABLE
    assert result.monitoring_state.pending_candidate_ids == []
    assert result.warnings == ["candidate_snapshot_unavailable"]
    assert "SECRET_TOKEN" not in result.model_dump_json()


def test_partial_snapshot_validation_error_preserves_dynamic_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    partial_result = make_dynamic_result(
        server,
        status=DynamicScanStatus.PARTIAL_SUCCESS,
    )
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        partial_result,
    )

    def fail_snapshot(*args: object, **kwargs: object) -> object:
        try:
            ToolMetadata.model_validate({"invalid": "tool"})
        except ValidationError as exc:
            raise exc
        raise AssertionError("validation should fail")

    monkeypatch.setattr(
        monitoring_service_module,
        "create_tool_snapshot",
        fail_snapshot,
    )

    result = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert result.candidate is None
    assert result.monitoring_state.last_scan_status == (
        MonitoringScanStatus.PARTIAL_SUCCESS
    )
    assert result.monitoring_state.comparison_status == (
        ComparisonStatus.COMPARISON_FAILED
    )
    assert result.monitoring_state.verification_status == VerificationStatus.UNAVAILABLE
    assert result.warnings == [
        "partial_scan",
        "candidate_snapshot_unavailable",
    ]


def test_snapshot_failure_preserves_existing_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None
    approved = service.approve_candidate(
        scan.candidate.candidate_id,
        expected_state_version=scan.monitoring_state.state_version,
        monitoring_target_key=scan.monitoring_identity.monitoring_target_key,
    )

    def fail_snapshot(*args: object, **kwargs: object) -> object:
        raise TypeError("SECRET_TOKEN")

    monkeypatch.setattr(
        monitoring_service_module,
        "create_tool_snapshot",
        fail_snapshot,
    )
    failed = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert failed.candidate is None
    assert failed.monitoring_state.current_approved_id == approved.baseline_id
    assert failed.monitoring_state.pending_candidate_ids == []
    assert failed.monitoring_state.rejected_candidate_ids == []
    assert failed.monitoring_state.history_ids == approved.committed_state.history_ids
    assert failed.monitoring_state.baseline_lifecycle == (
        BaselineLifecycleStatus.APPROVED
    )
    assert failed.monitoring_state.verification_status == VerificationStatus.UNAVAILABLE
    assert failed.warnings == ["candidate_snapshot_unavailable"]
    assert repo.load_approved_baseline(
        approved.baseline_id,
        scan.monitoring_identity.monitoring_target_key,
    ).baseline_id == approved.baseline_id


def test_scan_reuses_existing_pending_candidate(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    first = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    second = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert first.candidate is not None
    assert second.candidate_reused is True
    assert second.candidate is not None
    assert second.candidate.candidate_id == first.candidate.candidate_id
    assert second.monitoring_state.pending_candidate_ids == [
        first.candidate.candidate_id
    ]
    assert second.monitoring_state.state_version == 2


def test_rejected_same_snapshot_requires_reconsider_flag(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    first = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert first.candidate is not None
    rejected = service.reject_candidate(
        first.candidate.candidate_id,
        expected_state_version=first.monitoring_state.state_version,
        monitoring_target_key=first.monitoring_identity.monitoring_target_key,
    )

    blocked = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    reconsidered = asyncio.run(
        service.scan_monitored_server(
            context,
            server.selection_id,
            reconsider_rejected=True,
        )
    )

    assert rejected.decision == "rejected"
    assert rejected.committed_state.baseline_lifecycle == BaselineLifecycleStatus.REJECTED
    assert blocked.rejected_same_snapshot is True
    assert blocked.can_reconsider_rejected is True
    assert blocked.candidate is None
    assert blocked.monitoring_state.current_approved_id is None
    assert blocked.monitoring_state.baseline_lifecycle == BaselineLifecycleStatus.REJECTED
    assert blocked.monitoring_state.verification_status == (
        VerificationStatus.REVIEW_REQUIRED
    )
    assert reconsidered.candidate_created is True
    assert reconsidered.candidate is not None
    assert reconsidered.candidate.candidate_revision == 2
    assert reconsidered.candidate.supersedes_rejected_candidate_id == (
        first.candidate.candidate_id
    )


def test_reconsider_rejected_uses_highest_revision_regardless_of_order(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    first = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert first.candidate is not None
    first_rejected = service.reject_candidate(
        first.candidate.candidate_id,
        expected_state_version=first.monitoring_state.state_version,
        monitoring_target_key=first.monitoring_identity.monitoring_target_key,
    )
    second = asyncio.run(
        service.scan_monitored_server(
            context,
            server.selection_id,
            reconsider_rejected=True,
        )
    )
    assert second.candidate is not None
    second_rejected = service.reject_candidate(
        second.candidate.candidate_id,
        expected_state_version=second.monitoring_state.state_version,
        monitoring_target_key=second.monitoring_identity.monitoring_target_key,
    )
    state = second_rejected.committed_state
    reversed_state = state.model_copy(
        update={
            "state_version": state.state_version + 1,
            "rejected_candidate_ids": list(reversed(state.rejected_candidate_ids)),
        }
    )
    repo.commit_state(StateCommit(state.state_version, reversed_state))

    third = asyncio.run(
        service.scan_monitored_server(
            context,
            server.selection_id,
            reconsider_rejected=True,
        )
    )

    assert first_rejected.committed_state.rejected_candidate_ids == [
        first.candidate.candidate_id
    ]
    assert third.candidate is not None
    assert third.candidate.candidate_revision == 3
    assert third.candidate.supersedes_rejected_candidate_id == (
        second.candidate.candidate_id
    )
    assert third.monitoring_state.rejected_candidate_ids == list(
        reversed(state.rejected_candidate_ids)
    )
    assert third.monitoring_state.pending_candidate_ids == [
        third.candidate.candidate_id
    ]


def test_rejected_highest_revision_collision_is_conflict(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    first = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert first.candidate is not None
    service.reject_candidate(
        first.candidate.candidate_id,
        expected_state_version=first.monitoring_state.state_version,
        monitoring_target_key=first.monitoring_identity.monitoring_target_key,
    )
    second = asyncio.run(
        service.scan_monitored_server(
            context,
            server.selection_id,
            reconsider_rejected=True,
        )
    )
    assert second.candidate is not None
    second_rejected = service.reject_candidate(
        second.candidate.candidate_id,
        expected_state_version=second.monitoring_state.state_version,
        monitoring_target_key=second.monitoring_identity.monitoring_target_key,
    )
    duplicate = second.candidate.model_copy(
        update={"candidate_id": "cand_duplicate_max"}
    )
    repo._save_immutable_document(repo._candidate_path(duplicate), duplicate)
    bad_state = second_rejected.committed_state.model_copy(
        update={
            "state_version": second_rejected.committed_state.state_version + 1,
            "rejected_candidate_ids": [
                *second_rejected.committed_state.rejected_candidate_ids,
                duplicate.candidate_id,
            ],
        }
    )
    repo.commit_state(
        StateCommit(second_rejected.committed_state.state_version, bad_state)
    )

    with pytest.raises(MonitoringConflictError):
        asyncio.run(
            service.scan_monitored_server(
                context,
                server.selection_id,
                reconsider_rejected=True,
            )
        )


def test_pending_duplicate_matching_candidate_is_conflict(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    first = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert first.candidate is not None
    duplicate = first.candidate.model_copy(
        update={"candidate_id": "cand_duplicate_pending"}
    )
    repo._save_immutable_document(repo._candidate_path(duplicate), duplicate)
    bad_state = first.monitoring_state.model_copy(
        update={
            "state_version": first.monitoring_state.state_version + 1,
            "pending_candidate_ids": [
                first.candidate.candidate_id,
                duplicate.candidate_id,
            ],
        }
    )
    repo.commit_state(StateCommit(first.monitoring_state.state_version, bad_state))

    with pytest.raises(MonitoringConflictError):
        asyncio.run(service.scan_monitored_server(context, server.selection_id))


def test_approve_candidate_and_matched_rescan(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None

    approved = service.approve_candidate(
        scan.candidate.candidate_id,
        expected_state_version=scan.monitoring_state.state_version,
        monitoring_target_key=scan.monitoring_identity.monitoring_target_key,
    )
    matched = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert approved.decision == "approved"
    assert approved.baseline_id is not None
    assert approved.committed_state.current_approved_id == approved.baseline_id
    assert approved.committed_state.pending_candidate_ids == []
    assert matched.candidate is None
    assert matched.comparison_result is not None
    assert matched.comparison_result.comparison_status == ComparisonStatus.MATCHED
    assert matched.registration_changed is False
    assert matched.monitoring_state.verification_status == VerificationStatus.VERIFIED


def test_revoke_current_baseline_preserves_documents_and_resets_state(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None
    approved = service.approve_candidate(
        scan.candidate.candidate_id,
        monitoring_target_key=scan.monitoring_state.monitoring_target_key,
        expected_state_version=scan.monitoring_state.state_version,
        safe_reason_code="user_approved",
    )
    assert approved.baseline_id is not None
    approved_baseline = repo.load_approved_baseline(
        approved.baseline_id,
        scan.monitoring_state.monitoring_target_key,
    )

    revoked = service.revoke_current_baseline(
        scan.monitoring_state.monitoring_target_key,
        expected_state_version=approved.committed_state.state_version,
        expected_current_approved_id=approved.baseline_id,
        safe_reason_code="user_revoked",
    )

    state = revoked.committed_state
    assert revoked.decision == "baseline_revoked"
    assert revoked.removed_baseline_id == approved.baseline_id
    assert state.current_approved_id is None
    assert state.state_version == approved.committed_state.state_version + 1
    assert state.comparison_status == ComparisonStatus.NOT_COMPARED
    assert state.verification_status == VerificationStatus.UNVERIFIED
    assert state.last_comparison is None
    assert approved.baseline_id in state.superseded_baseline_ids
    assert state.pending_candidate_ids == []
    assert state.rejected_candidate_ids == []
    assert state.baseline_lifecycle == BaselineLifecycleStatus.NONE
    assert repo.load_approved_baseline(
        approved.baseline_id,
        scan.monitoring_state.monitoring_target_key,
    ) == approved_baseline

    history = repo.load_history_record(
        revoked.history_id,
        scan.monitoring_state.monitoring_target_key,
    )
    assert history.event_type == BaselineHistoryEventType.BASELINE_REVOKED
    assert history.baseline_id == approved.baseline_id
    assert history.previous_approved_id == approved.baseline_id
    assert history.new_approved_id is None
    assert history.candidate_id is None
    assert history.safe_reason_code == "user_revoked"


def test_delete_target_history_clears_history_and_current_baseline(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None
    approved = service.approve_candidate(
        scan.candidate.candidate_id,
        monitoring_target_key=scan.monitoring_state.monitoring_target_key,
        expected_state_version=scan.monitoring_state.state_version,
        safe_reason_code="user_approved",
    )
    assert approved.baseline_id is not None

    deleted = service.delete_target_history(
        scan.monitoring_state.monitoring_target_key,
        expected_state_version=approved.committed_state.state_version,
    )

    assert deleted.decision == "baseline_history_deleted"
    assert deleted.deleted_history_count == 1
    assert deleted.committed_state.state_version == (
        approved.committed_state.state_version + 1
    )
    assert deleted.committed_state.history_ids == []
    assert deleted.committed_state.current_approved_id is None
    assert deleted.committed_state.pending_candidate_ids == []
    assert deleted.committed_state.rejected_candidate_ids == []
    assert deleted.committed_state.superseded_baseline_ids == []
    assert deleted.committed_state.baseline_lifecycle == BaselineLifecycleStatus.NONE
    assert deleted.committed_state.comparison_status == ComparisonStatus.NOT_COMPARED
    assert deleted.committed_state.verification_status == VerificationStatus.UNVERIFIED
    assert deleted.committed_state.last_comparison is None
    assert repo.list_target_history(scan.monitoring_state.monitoring_target_key) == []
    with pytest.raises(MonitoringNotFoundError):
        repo.load_history_record(
            approved.history_id,
            scan.monitoring_state.monitoring_target_key,
        )


def test_revoke_current_baseline_conflicts_without_current_baseline(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    with pytest.raises(MonitoringConflictError):
        service.revoke_current_baseline(
            scan.monitoring_state.monitoring_target_key,
            expected_state_version=scan.monitoring_state.state_version,
            expected_current_approved_id="base_missing",
        )


def test_revoke_current_baseline_rejects_stale_or_mismatched_request(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None
    approved = service.approve_candidate(
        scan.candidate.candidate_id,
        monitoring_target_key=scan.monitoring_state.monitoring_target_key,
        expected_state_version=scan.monitoring_state.state_version,
    )
    assert approved.baseline_id is not None

    with pytest.raises(MonitoringConflictError):
        service.revoke_current_baseline(
            scan.monitoring_state.monitoring_target_key,
            expected_state_version=approved.committed_state.state_version - 1,
            expected_current_approved_id=approved.baseline_id,
        )

    with pytest.raises(MonitoringConflictError):
        service.revoke_current_baseline(
            scan.monitoring_state.monitoring_target_key,
            expected_state_version=approved.committed_state.state_version,
            expected_current_approved_id="base_other",
        )


def test_scan_after_revoke_creates_initial_candidate_instead_of_matched(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None
    approved = service.approve_candidate(
        scan.candidate.candidate_id,
        monitoring_target_key=scan.monitoring_state.monitoring_target_key,
        expected_state_version=scan.monitoring_state.state_version,
    )
    assert approved.baseline_id is not None
    revoked = service.revoke_current_baseline(
        scan.monitoring_state.monitoring_target_key,
        expected_state_version=approved.committed_state.state_version,
        expected_current_approved_id=approved.baseline_id,
    )

    rescanned = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert rescanned.candidate_created is True
    assert rescanned.comparison_result is None
    assert rescanned.monitoring_state.current_approved_id is None
    assert rescanned.monitoring_state.state_version == (
        revoked.committed_state.state_version + 1
    )
    assert rescanned.monitoring_state.baseline_lifecycle == (
        BaselineLifecycleStatus.CANDIDATE_PENDING
    )


def test_matched_rescan_with_pending_candidate_requires_review(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    original_result = make_dynamic_result(server)
    service, _repo, _discovery, runner = make_service(
        tmp_path,
        [server],
        original_result,
    )
    initial = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert initial.candidate is not None
    approved = service.approve_candidate(
        initial.candidate.candidate_id,
        expected_state_version=initial.monitoring_state.state_version,
        monitoring_target_key=initial.monitoring_identity.monitoring_target_key,
    )
    runner.result = make_dynamic_result(
        server,
        tools=[make_tool(description="Changed docs.")],
    )
    pending = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert pending.candidate is not None
    assert pending.monitoring_state.pending_candidate_ids == [
        pending.candidate.candidate_id
    ]

    runner.result = original_result
    matched = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert matched.candidate is None
    assert matched.candidate_created is False
    assert matched.monitoring_state.current_approved_id == approved.baseline_id
    assert matched.monitoring_state.pending_candidate_ids == [
        pending.candidate.candidate_id
    ]
    assert matched.monitoring_state.comparison_status == ComparisonStatus.MATCHED
    assert matched.monitoring_state.baseline_lifecycle == (
        BaselineLifecycleStatus.CANDIDATE_PENDING
    )
    assert matched.monitoring_state.verification_status == (
        VerificationStatus.REVIEW_REQUIRED
    )


def test_reject_changed_candidate_after_approval_marks_lifecycle_rejected(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    initial = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert initial.candidate is not None
    approved = service.approve_candidate(
        initial.candidate.candidate_id,
        expected_state_version=initial.monitoring_state.state_version,
        monitoring_target_key=initial.monitoring_identity.monitoring_target_key,
    )
    runner.result = make_dynamic_result(
        server,
        tools=[make_tool(description="Changed docs.")],
    )
    changed = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert changed.candidate is not None

    rejected = service.reject_candidate(
        changed.candidate.candidate_id,
        expected_state_version=changed.monitoring_state.state_version,
        monitoring_target_key=changed.monitoring_identity.monitoring_target_key,
    )

    assert rejected.committed_state.current_approved_id == approved.baseline_id
    assert rejected.committed_state.pending_candidate_ids == []
    assert rejected.committed_state.rejected_candidate_ids == [
        changed.candidate.candidate_id
    ]
    assert rejected.committed_state.baseline_lifecycle == (
        BaselineLifecycleStatus.REJECTED
    )
    assert rejected.committed_state.verification_status == (
        VerificationStatus.REVIEW_REQUIRED
    )


def test_rejected_same_snapshot_after_approval_keeps_lifecycle_rejected(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    initial = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert initial.candidate is not None
    approved = service.approve_candidate(
        initial.candidate.candidate_id,
        expected_state_version=initial.monitoring_state.state_version,
        monitoring_target_key=initial.monitoring_identity.monitoring_target_key,
    )
    changed_result = make_dynamic_result(
        server,
        tools=[make_tool(description="Changed docs.")],
    )
    runner.result = changed_result
    changed = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert changed.candidate is not None
    rejected = service.reject_candidate(
        changed.candidate.candidate_id,
        expected_state_version=changed.monitoring_state.state_version,
        monitoring_target_key=changed.monitoring_identity.monitoring_target_key,
    )

    same_rejected = asyncio.run(
        service.scan_monitored_server(context, server.selection_id)
    )

    assert rejected.committed_state.baseline_lifecycle == (
        BaselineLifecycleStatus.REJECTED
    )
    assert same_rejected.candidate is None
    assert same_rejected.rejected_same_snapshot is True
    assert same_rejected.can_reconsider_rejected is True
    assert same_rejected.monitoring_state.current_approved_id == approved.baseline_id
    assert same_rejected.monitoring_state.rejected_candidate_ids == [
        changed.candidate.candidate_id
    ]
    assert same_rejected.monitoring_state.pending_candidate_ids == []
    assert same_rejected.monitoring_state.baseline_lifecycle == (
        BaselineLifecycleStatus.REJECTED
    )
    assert same_rejected.monitoring_state.verification_status == (
        VerificationStatus.REVIEW_REQUIRED
    )


def test_reject_one_candidate_keeps_lifecycle_pending_when_another_pending(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    first = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert first.candidate is not None
    runner.result = make_dynamic_result(
        server,
        tools=[make_tool(description="Changed docs.")],
    )
    second = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert second.candidate is not None
    assert second.candidate.candidate_id != first.candidate.candidate_id

    rejected = service.reject_candidate(
        first.candidate.candidate_id,
        expected_state_version=second.monitoring_state.state_version,
        monitoring_target_key=first.monitoring_identity.monitoring_target_key,
    )

    assert rejected.committed_state.pending_candidate_ids == [
        second.candidate.candidate_id
    ]
    assert rejected.committed_state.baseline_lifecycle == (
        BaselineLifecycleStatus.CANDIDATE_PENDING
    )


def test_rejected_same_snapshot_keeps_lifecycle_pending_with_other_pending(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    initial = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert initial.candidate is not None
    service.approve_candidate(
        initial.candidate.candidate_id,
        expected_state_version=initial.monitoring_state.state_version,
        monitoring_target_key=initial.monitoring_identity.monitoring_target_key,
    )
    candidate_a_result = make_dynamic_result(
        server,
        tools=[make_tool(description="Candidate A.")],
    )
    runner.result = candidate_a_result
    candidate_a = asyncio.run(
        service.scan_monitored_server(context, server.selection_id)
    )
    assert candidate_a.candidate is not None
    candidate_b_result = make_dynamic_result(
        server,
        tools=[make_tool(description="Candidate B.")],
    )
    runner.result = candidate_b_result
    candidate_b = asyncio.run(
        service.scan_monitored_server(context, server.selection_id)
    )
    assert candidate_b.candidate is not None
    rejected_a = service.reject_candidate(
        candidate_a.candidate.candidate_id,
        expected_state_version=candidate_b.monitoring_state.state_version,
        monitoring_target_key=candidate_a.monitoring_identity.monitoring_target_key,
    )

    runner.result = candidate_a_result
    same_rejected = asyncio.run(
        service.scan_monitored_server(context, server.selection_id)
    )

    assert rejected_a.committed_state.pending_candidate_ids == [
        candidate_b.candidate.candidate_id
    ]
    assert same_rejected.rejected_same_snapshot is True
    assert same_rejected.monitoring_state.pending_candidate_ids == [
        candidate_b.candidate.candidate_id
    ]
    assert same_rejected.monitoring_state.rejected_candidate_ids == [
        candidate_a.candidate.candidate_id
    ]
    assert same_rejected.monitoring_state.baseline_lifecycle == (
        BaselineLifecycleStatus.CANDIDATE_PENDING
    )
    assert same_rejected.monitoring_state.verification_status == (
        VerificationStatus.REVIEW_REQUIRED
    )


def test_registration_change_creates_candidate_without_tool_change(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server(selection_id="codex:user:docs")
    service, _repo, discovery, runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None
    service.approve_candidate(
        scan.candidate.candidate_id,
        expected_state_version=scan.monitoring_state.state_version,
        monitoring_target_key=scan.monitoring_identity.monitoring_target_key,
    )

    moved_server = make_server(selection_id="codex:user:docs-renamed")
    discovery.servers = [moved_server]
    runner.result = make_dynamic_result(moved_server)
    changed = asyncio.run(
        service.scan_monitored_server(context, moved_server.selection_id)
    )

    assert changed.candidate_created is True
    assert changed.registration_changed is True
    assert changed.configuration_changed is False
    assert changed.comparison_result is not None
    assert changed.comparison_result.change_categories == []
    assert changed.comparison_result.comparison_status == ComparisonStatus.CHANGED


def test_other_target_approved_marks_shadowing_without_copying_baseline(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    user_server = make_server(scope=McpScope.USER, selection_id="codex:user:docs")
    project_server = make_server(
        scope=McpScope.PROJECT,
        selection_id="codex:project:docs",
    )
    service, _repo, _discovery, runner = make_service(
        tmp_path,
        [user_server, project_server],
        make_dynamic_result(user_server),
    )
    user_scan = asyncio.run(
        service.scan_monitored_server(context, user_server.selection_id)
    )
    assert user_scan.candidate is not None
    approved = service.approve_candidate(
        user_scan.candidate.candidate_id,
        expected_state_version=user_scan.monitoring_state.state_version,
        monitoring_target_key=user_scan.monitoring_identity.monitoring_target_key,
    )

    runner.result = make_dynamic_result(project_server)
    project_scan = asyncio.run(
        service.scan_monitored_server(context, project_server.selection_id)
    )

    assert project_scan.candidate_created is True
    assert project_scan.candidate is not None
    assert project_scan.candidate.comparison_result is None
    assert project_scan.comparison_result is None
    assert project_scan.monitoring_state.current_approved_id is None
    assert project_scan.monitoring_state.comparison_status == (
        ComparisonStatus.NOT_COMPARED
    )
    assert project_scan.monitoring_state.verification_status == (
        VerificationStatus.REVIEW_REQUIRED
    )
    assert project_scan.registration_changed is True
    assert project_scan.related_approved_target_keys == [
        user_scan.monitoring_identity.monitoring_target_key
    ]
    assert approved.baseline_id not in project_scan.monitoring_state.history_ids


def test_project_targets_keep_independent_candidates_and_approvals(
    tmp_path: Path,
) -> None:
    context_a = make_context(tmp_path / "a")
    context_b = make_context(tmp_path / "b")
    server = make_server(scope=McpScope.PROJECT, selection_id="codex:project:docs")
    repo = FileMcpBaselineRepository(tmp_path)
    runner = FakeRunner(make_dynamic_result(server))
    service = McpMonitoringService(
        repo,
        discover_servers=FakeDiscovery([server]),
        dynamic_scan_runner=runner,
        clock=lambda: FIXED_TIME,
    )
    scan_a = asyncio.run(service.scan_monitored_server(context_a, server.selection_id))
    assert scan_a.candidate is not None
    approved_a = service.approve_candidate(
        scan_a.candidate.candidate_id,
        expected_state_version=scan_a.monitoring_state.state_version,
        monitoring_target_key=scan_a.monitoring_identity.monitoring_target_key,
    )

    scan_b = asyncio.run(service.scan_monitored_server(context_b, server.selection_id))

    assert scan_b.candidate_created is True
    assert scan_b.candidate is not None
    assert scan_b.monitoring_identity.monitoring_group_key == (
        scan_a.monitoring_identity.monitoring_group_key
    )
    assert scan_b.monitoring_identity.monitoring_target_key != (
        scan_a.monitoring_identity.monitoring_target_key
    )
    assert scan_b.monitoring_state.current_approved_id is None
    assert scan_b.registration_changed is True
    assert scan_b.related_approved_target_keys == [
        scan_a.monitoring_identity.monitoring_target_key
    ]
    assert approved_a.baseline_id == service.get_monitoring_target_state(
        scan_a.monitoring_identity.monitoring_target_key
    ).current_approved_id


def test_configuration_change_creates_candidate_without_tool_change(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server(command="python")
    service, _repo, discovery, runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None
    service.approve_candidate(
        scan.candidate.candidate_id,
        expected_state_version=scan.monitoring_state.state_version,
        monitoring_target_key=scan.monitoring_identity.monitoring_target_key,
    )

    reconfigured = make_server(command="node")
    discovery.servers = [reconfigured]
    runner.result = make_dynamic_result(reconfigured)
    changed = asyncio.run(
        service.scan_monitored_server(context, reconfigured.selection_id)
    )

    assert changed.candidate_created is True
    assert changed.registration_changed is False
    assert changed.configuration_changed is True
    assert changed.comparison_result is not None
    assert changed.comparison_result.change_categories == []


def test_partial_success_match_requires_review(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None
    service.approve_candidate(
        scan.candidate.candidate_id,
        expected_state_version=scan.monitoring_state.state_version,
        monitoring_target_key=scan.monitoring_identity.monitoring_target_key,
    )

    runner.result = make_dynamic_result(
        server,
        status=DynamicScanStatus.PARTIAL_SUCCESS,
    )
    partial = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert partial.candidate is None
    assert partial.monitoring_state.last_scan_status == (
        MonitoringScanStatus.PARTIAL_SUCCESS
    )
    assert partial.monitoring_state.comparison_status == ComparisonStatus.MATCHED
    assert partial.monitoring_state.verification_status == (
        VerificationStatus.REVIEW_REQUIRED
    )
    assert partial.warnings == ["partial_scan"]


def test_partial_success_candidate_includes_partial_scan_warning(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server, status=DynamicScanStatus.PARTIAL_SUCCESS),
    )

    result = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert result.candidate_created is True
    assert result.monitoring_state.last_scan_status == (
        MonitoringScanStatus.PARTIAL_SUCCESS
    )
    assert result.warnings == ["partial_scan"]


def test_warning_codes_are_ordered_and_deduplicated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(tmp_path)
    server = make_server()
    repo = IndexWarningRepository(tmp_path)
    discovery = FakeDiscovery([server])
    runner = FakeRunner(
        make_dynamic_result(server, status=DynamicScanStatus.PARTIAL_SUCCESS)
    )
    service = McpMonitoringService(
        repo,
        discover_servers=discovery,
        dynamic_scan_runner=runner,
        clock=lambda: FIXED_TIME,
    )

    def fail_snapshot(*args: object, **kwargs: object) -> object:
        raise ValueError("SECRET_TOKEN")

    monkeypatch.setattr(
        monitoring_service_module,
        "create_tool_snapshot",
        fail_snapshot,
    )

    result = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert result.warnings == [
        "partial_scan",
        "candidate_snapshot_unavailable",
        "index_rebuild_pending",
    ]


def test_empty_successful_tool_list_is_valid_snapshot(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server, tools=[]),
    )

    result = asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert result.candidate_created is True
    assert result.candidate is not None
    assert result.candidate.snapshot.tool_count == 0


def test_selection_errors_are_mapped_to_repository_errors(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server_a = make_server(selection_id="duplicate")
    server_b = make_server(selection_id="duplicate")
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server_a, server_b],
        make_dynamic_result(server_a),
    )

    with pytest.raises(MonitoringConflictError):
        asyncio.run(service.scan_monitored_server(context, "duplicate"))

    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server_a],
        make_dynamic_result(server_a),
    )
    with pytest.raises(MonitoringNotFoundError):
        asyncio.run(service.scan_monitored_server(context, "missing"))


def test_disabled_server_is_listed_but_not_scanned(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server(enabled_state=ServerEnabledState.DISABLED)
    service, repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(make_server()),
    )

    listed = service.list_monitored_servers(context)

    assert listed.servers[0].can_scan is False
    assert listed.servers[0].safe_action_reason == "server_disabled"
    with pytest.raises(MonitoringScanError, match="server_disabled"):
        asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert repo.load_target_state(
        listed.servers[0].monitoring_identity.monitoring_target_key
    ) is None


def test_same_target_concurrent_scan_is_rejected(tmp_path: Path) -> None:
    async def run_case() -> None:
        context = make_context(tmp_path)
        server = make_server()
        repo = FileMcpBaselineRepository(tmp_path)
        discovery = FakeDiscovery([server])
        started = asyncio.Event()
        release = asyncio.Event()

        async def runner(_server: DiscoveredMcpServer) -> DynamicScanResult:
            started.set()
            await release.wait()
            return make_dynamic_result(server)

        service = McpMonitoringService(
            repo,
            discover_servers=discovery,
            dynamic_scan_runner=runner,
            clock=lambda: FIXED_TIME,
        )
        first = asyncio.create_task(
            service.scan_monitored_server(context, server.selection_id)
        )
        await started.wait()
        with pytest.raises(MonitoringConflictError):
            await service.scan_monitored_server(context, server.selection_id)
        release.set()
        completed = await first
        assert completed.candidate_created is True

    asyncio.run(run_case())


def test_dynamic_scan_exception_is_sanitized(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()

    async def runner(_server: DiscoveredMcpServer) -> DynamicScanResult:
        raise RuntimeError("SECRET_TOKEN C:/private/path")

    service = McpMonitoringService(
        FileMcpBaselineRepository(tmp_path),
        discover_servers=FakeDiscovery([server]),
        dynamic_scan_runner=runner,
        clock=lambda: FIXED_TIME,
    )

    with pytest.raises(MonitoringScanError) as error_info:
        asyncio.run(service.scan_monitored_server(context, server.selection_id))

    assert str(error_info.value) == "could not scan MCP server"
    assert "SECRET_TOKEN" not in str(error_info.value)


def test_safe_reason_code_rejects_unsafe_text(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    server = make_server()
    service, _repo, _discovery, _runner = make_service(
        tmp_path,
        [server],
        make_dynamic_result(server),
    )
    scan = asyncio.run(service.scan_monitored_server(context, server.selection_id))
    assert scan.candidate is not None

    with pytest.raises(MonitoringServiceError):
        service.approve_candidate(
            scan.candidate.candidate_id,
            expected_state_version=scan.monitoring_state.state_version,
            monitoring_target_key=scan.monitoring_identity.monitoring_target_key,
            safe_reason_code="bad reason",
        )


def test_group_state_collects_related_approved_targets(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    user_server = make_server(scope=McpScope.USER, selection_id="codex:user:docs")
    project_server = make_server(
        scope=McpScope.PROJECT,
        selection_id="codex:project:docs",
    )
    service, _repo, discovery, runner = make_service(
        tmp_path,
        [user_server, project_server],
        make_dynamic_result(user_server),
    )
    user_scan = asyncio.run(
        service.scan_monitored_server(context, user_server.selection_id)
    )
    assert user_scan.candidate is not None
    service.approve_candidate(
        user_scan.candidate.candidate_id,
        expected_state_version=user_scan.monitoring_state.state_version,
        monitoring_target_key=user_scan.monitoring_identity.monitoring_target_key,
    )

    runner.result = make_dynamic_result(project_server)
    project_scan = asyncio.run(
        service.scan_monitored_server(context, project_server.selection_id)
    )
    group = service.get_monitoring_group(
        user_scan.monitoring_identity.monitoring_group_key
    )
    listed = service.list_monitored_servers(context)

    assert project_scan.candidate_created is True
    assert sorted(group.target_keys) == sorted(
        [
            user_scan.monitoring_identity.monitoring_target_key,
            project_scan.monitoring_identity.monitoring_target_key,
        ]
    )
    assert group.related_approved_target_keys == [
        user_scan.monitoring_identity.monitoring_target_key
    ]
    assert {item.related_target_count for item in listed.servers} == {2}
    assert {item.related_approved_target_count for item in listed.servers} == {1}
    assert discovery.calls >= 3
