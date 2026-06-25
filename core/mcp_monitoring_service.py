from __future__ import annotations

import asyncio
import inspect
import re

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.dynamic_scan_models import (
    DiscoveryContext,
    DiscoveredMcpServer,
    DynamicScanResult,
    DynamicScanStatus,
    McpDiscoveryResult,
    McpServerSummary,
    ServerEnabledState,
    ServerSupportState,
)
from core.dynamic_scan_service import run_dynamic_scan
from core.mcp_baseline_repository import (
    ApprovalCommit,
    BaselineHistoryDeletionCommit,
    BaselineRevocationCommit,
    CandidateCommit,
    McpBaselineRepository,
    MonitoringConflictError,
    MonitoringNotFoundError,
    RejectionCommit,
    StateCommit,
)
from core.mcp_discovery import discover_mcp_servers
from core.mcp_metadata_diff import compare_tool_snapshots
from core.mcp_metadata_normalizer import (
    MetadataNormalizationError,
    calculate_sha256,
    canonical_json_bytes,
    create_tool_snapshot,
)
from core.mcp_monitoring_models import (
    ApprovedBaseline,
    BaselineComparisonResult,
    BaselineHistoryEventType,
    BaselineHistoryRecord,
    BaselineLifecycleStatus,
    ComparisonStatus,
    ConfigurationFingerprint,
    MonitoringCandidate,
    MonitoringIdentity,
    MonitoringScanStatus,
    MonitoredServerState,
    RepositoryCommitResult,
    ToolSnapshot,
    VerificationStatus,
)
from core.mcp_server_identity import (
    create_configuration_fingerprint,
    create_monitoring_identity,
)
from core.models import ToolMetadata


_SAFE_REASON_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_CANDIDATE_ID_VERSION = "mcp-monitoring-candidate-id-v1"
_BASELINE_ID_VERSION = "mcp-monitoring-baseline-id-v1"
_HISTORY_ID_VERSION = "mcp-monitoring-history-id-v1"
_PARTIAL_SCAN_WARNING = "partial_scan"
_SNAPSHOT_UNAVAILABLE_WARNING = "candidate_snapshot_unavailable"
_WARNING_ORDER = (
    _PARTIAL_SCAN_WARNING,
    _SNAPSHOT_UNAVAILABLE_WARNING,
    "index_rebuild_pending",
)


class MonitoringServiceError(Exception):
    """Base error for MCP monitoring service orchestration failures."""


class MonitoringDiscoveryError(MonitoringServiceError):
    """Raised when MCP discovery cannot be completed safely."""


class MonitoringScanError(MonitoringServiceError):
    """Raised when MCP dynamic scanning cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class _SnapshotBuildResult:
    snapshot: ToolSnapshot | None
    warning_codes: tuple[str, ...] = ()


class _ServiceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
        validate_assignment=True,
    )


class MonitoredServerListItem(_ServiceModel):
    server_summary: McpServerSummary
    monitoring_identity: MonitoringIdentity
    monitoring_state: MonitoredServerState
    related_target_count: int = Field(ge=0)
    related_approved_target_count: int = Field(ge=0)
    can_scan: bool
    safe_action_reason: str | None = None


class MonitoredServerListResult(_ServiceModel):
    servers: list[MonitoredServerListItem] = Field(default_factory=list)
    discovery_result: McpDiscoveryResult


class MonitoredScanResult(_ServiceModel):
    server_summary: McpServerSummary
    monitoring_identity: MonitoringIdentity
    dynamic_scan_result: DynamicScanResult
    monitoring_state: MonitoredServerState
    candidate: MonitoringCandidate | None = None
    comparison_result: BaselineComparisonResult | None = None
    registration_changed: bool = False
    configuration_changed: bool = False
    related_target_keys: list[str] = Field(default_factory=list)
    related_approved_target_keys: list[str] = Field(default_factory=list)
    candidate_created: bool = False
    candidate_reused: bool = False
    rejected_same_snapshot: bool = False
    can_reconsider_rejected: bool = False
    warnings: list[str] = Field(default_factory=list)


class CandidateDecisionResult(_ServiceModel):
    decision: Literal["approved", "rejected"]
    candidate_id: str
    monitoring_group_key: str
    monitoring_target_key: str
    baseline_id: str | None = None
    history_id: str
    committed_state: MonitoredServerState
    warnings: list[str] = Field(default_factory=list)


class BaselineRevocationResult(_ServiceModel):
    decision: Literal["baseline_revoked"] = "baseline_revoked"
    monitoring_group_key: str
    monitoring_target_key: str
    removed_baseline_id: str
    history_id: str
    committed_state: MonitoredServerState
    warnings: list[str] = Field(default_factory=list)


class BaselineHistoryDeletionResult(_ServiceModel):
    decision: Literal["baseline_history_deleted"] = "baseline_history_deleted"
    monitoring_group_key: str
    monitoring_target_key: str
    deleted_history_count: int
    committed_state: MonitoredServerState
    warnings: list[str] = Field(default_factory=list)


class MonitoringGroupState(_ServiceModel):
    monitoring_group_key: str
    target_keys: list[str] = Field(default_factory=list)
    target_states: list[MonitoredServerState] = Field(default_factory=list)
    related_approved_target_keys: list[str] = Field(default_factory=list)


class McpMonitoringService:
    def __init__(
        self,
        repository: McpBaselineRepository,
        *,
        discover_servers: Callable[[DiscoveryContext], McpDiscoveryResult] = (
            discover_mcp_servers
        ),
        dynamic_scan_runner: Callable[[DiscoveredMcpServer], object] = (
            run_dynamic_scan
        ),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._repository = repository
        self._discover_servers = discover_servers
        self._dynamic_scan_runner = dynamic_scan_runner
        self._clock = clock
        self._scan_registry_lock = asyncio.Lock()
        self._active_scan_targets: set[str] = set()

    def list_monitored_servers(
        self,
        context: DiscoveryContext,
    ) -> MonitoredServerListResult:
        discovery = self._discover(context)
        identities = [
            create_monitoring_identity(server, context)
            for server in discovery.servers
        ]
        discovered_by_group: dict[str, set[str]] = {}
        for identity in identities:
            discovered_by_group.setdefault(
                identity.monitoring_group_key,
                set(),
            ).add(identity.monitoring_target_key)

        items: list[MonitoredServerListItem] = []
        now = self._now()
        for server, identity in zip(discovery.servers, identities, strict=True):
            stored_state = self._repository.load_target_state(
                identity.monitoring_target_key
            )
            state = stored_state or self._initial_state(identity, now)
            related_keys = self._related_target_keys(
                identity.monitoring_group_key,
                discovered_target_keys=discovered_by_group.get(
                    identity.monitoring_group_key,
                    set(),
                ),
            )
            related_approved_keys = self._approved_target_keys(related_keys)
            can_scan, reason = self._scan_capability(server)
            items.append(
                MonitoredServerListItem(
                    server_summary=server.to_summary(),
                    monitoring_identity=identity,
                    monitoring_state=state,
                    related_target_count=len(related_keys),
                    related_approved_target_count=len(related_approved_keys),
                    can_scan=can_scan,
                    safe_action_reason=reason,
                )
            )

        return MonitoredServerListResult(
            servers=items,
            discovery_result=discovery,
        )

    async def scan_monitored_server(
        self,
        context: DiscoveryContext,
        selection_id: str,
        *,
        reconsider_rejected: bool = False,
    ) -> MonitoredScanResult:
        discovery = self._discover(context)
        server = self._select_server(discovery, selection_id)
        can_scan, reason = self._scan_capability(server)
        if not can_scan:
            raise MonitoringScanError(reason or "server cannot be scanned")

        identity = create_monitoring_identity(server, context)
        fingerprint = create_configuration_fingerprint(server)
        await self._enter_target_scan(identity.monitoring_target_key)
        try:
            state = self._load_or_create_state(identity)
            dynamic_result = await self._run_dynamic_scan(server)
            return self._commit_scan_result(
                server=server,
                identity=identity,
                fingerprint=fingerprint,
                state=state,
                dynamic_result=dynamic_result,
                reconsider_rejected=reconsider_rejected,
            )
        finally:
            await self._exit_target_scan(identity.monitoring_target_key)

    def get_monitoring_target_state(
        self,
        monitoring_target_key: str,
    ) -> MonitoredServerState:
        state = self._repository.load_target_state(monitoring_target_key)
        if state is None:
            raise MonitoringNotFoundError("target state was not found")
        return state

    def get_monitoring_group(
        self,
        monitoring_group_key: str,
    ) -> MonitoringGroupState:
        target_keys = self._repository.list_group_targets(monitoring_group_key)
        target_states = [
            state
            for key in target_keys
            if (state := self._repository.load_target_state(key)) is not None
        ]
        return MonitoringGroupState(
            monitoring_group_key=monitoring_group_key,
            target_keys=target_keys,
            target_states=target_states,
            related_approved_target_keys=[
                state.monitoring_target_key
                for state in target_states
                if state.current_approved_id is not None
            ],
        )

    def get_candidate(
        self,
        candidate_id: str,
        *,
        monitoring_target_key: str | None = None,
    ) -> MonitoringCandidate:
        return self._repository.load_candidate(
            candidate_id,
            monitoring_target_key,
        )

    def list_target_history(
        self,
        monitoring_target_key: str,
    ) -> list[BaselineHistoryRecord]:
        return self._repository.list_target_history(monitoring_target_key)

    def delete_target_history(
        self,
        monitoring_target_key: str,
        *,
        expected_state_version: int,
    ) -> BaselineHistoryDeletionResult:
        state = self.get_monitoring_target_state(monitoring_target_key)
        if state.state_version != expected_state_version:
            raise MonitoringConflictError("state version conflict")

        if not state.history_ids:
            return BaselineHistoryDeletionResult(
                monitoring_group_key=state.monitoring_group_key,
                monitoring_target_key=state.monitoring_target_key,
                deleted_history_count=0,
                committed_state=state,
            )

        new_state = self._state_with(
            state,
            state_version=state.state_version + 1,
            current_approved_id=None,
            pending_candidate_ids=[],
            rejected_candidate_ids=[],
            superseded_baseline_ids=[],
            history_ids=[],
            baseline_lifecycle=BaselineLifecycleStatus.NONE,
            comparison_status=ComparisonStatus.NOT_COMPARED,
            verification_status=VerificationStatus.UNVERIFIED,
            last_comparison=None,
            updated_at=self._now(),
        )
        result = self._repository.commit_history_deletion(
            BaselineHistoryDeletionCommit(
                expected_state_version,
                new_state,
            )
        )
        return BaselineHistoryDeletionResult(
            monitoring_group_key=state.monitoring_group_key,
            monitoring_target_key=state.monitoring_target_key,
            deleted_history_count=len(state.history_ids),
            committed_state=result.committed_state,
            warnings=result.warnings,
        )

    def approve_candidate(
        self,
        candidate_id: str,
        *,
        expected_state_version: int,
        monitoring_target_key: str | None = None,
        safe_reason_code: str | None = None,
    ) -> CandidateDecisionResult:
        reason = self._reason_code(safe_reason_code, default="user_approved")
        candidate = self._repository.load_candidate(
            candidate_id,
            monitoring_target_key,
        )
        state = self.get_monitoring_target_state(candidate.monitoring_target_key)
        if monitoring_target_key is not None and (
            state.monitoring_target_key != monitoring_target_key
        ):
            raise MonitoringNotFoundError("candidate was not found")
        if candidate.candidate_id not in state.pending_candidate_ids:
            raise MonitoringConflictError("candidate is not pending")

        now = self._now()
        baseline_id = self._baseline_id(candidate, now)
        history_id = self._history_id(
            event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
            candidate_id=candidate.candidate_id,
            baseline_id=baseline_id,
            created_at=now,
        )
        previous_approved_id = state.current_approved_id
        approved = ApprovedBaseline(
            baseline_id=baseline_id,
            monitoring_group_key=candidate.monitoring_group_key,
            monitoring_target_key=candidate.monitoring_target_key,
            approved_at=now,
            approved_from_candidate_id=candidate.candidate_id,
            selection_id_at_approval=candidate.selection_id,
            configuration_fingerprint=candidate.configuration_fingerprint,
            snapshot=candidate.snapshot,
        )
        history = BaselineHistoryRecord(
            history_id=history_id,
            monitoring_group_key=candidate.monitoring_group_key,
            monitoring_target_key=candidate.monitoring_target_key,
            event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
            candidate_id=candidate.candidate_id,
            baseline_id=baseline_id,
            previous_approved_id=previous_approved_id,
            new_approved_id=baseline_id,
            created_at=now,
            safe_reason_code=reason,
        )
        pending_ids = [
            item
            for item in state.pending_candidate_ids
            if item != candidate.candidate_id
        ]
        superseded_ids = list(state.superseded_baseline_ids)
        if previous_approved_id is not None:
            superseded_ids.append(previous_approved_id)

        comparison = compare_tool_snapshots(candidate.snapshot, candidate.snapshot)
        verification_status = (
            VerificationStatus.VERIFIED
            if not pending_ids
            and candidate.dynamic_scan_status == MonitoringScanStatus.SUCCESS
            else VerificationStatus.REVIEW_REQUIRED
        )
        new_state = self._state_with(
            state,
            identity=state.identity,
            state_version=state.state_version + 1,
            current_approved_id=baseline_id,
            pending_candidate_ids=pending_ids,
            superseded_baseline_ids=superseded_ids,
            history_ids=[*state.history_ids, history_id],
            last_scan_status=candidate.dynamic_scan_status,
            last_scan_at=now,
            last_seen_selection_id=candidate.selection_id,
            baseline_lifecycle=self._lifecycle(
                current_approved_id=baseline_id,
                pending_candidate_ids=pending_ids,
                rejected_candidate_ids=state.rejected_candidate_ids,
            ),
            comparison_status=comparison.comparison_status,
            verification_status=verification_status,
            last_comparison=comparison,
            updated_at=now,
        )
        result = self._repository.commit_approval(
            ApprovalCommit(
                expected_state_version,
                approved,
                history,
                new_state,
            )
        )
        return CandidateDecisionResult(
            decision="approved",
            candidate_id=candidate.candidate_id,
            monitoring_group_key=candidate.monitoring_group_key,
            monitoring_target_key=candidate.monitoring_target_key,
            baseline_id=baseline_id,
            history_id=history_id,
            committed_state=result.committed_state,
            warnings=result.warnings,
        )

    def reject_candidate(
        self,
        candidate_id: str,
        *,
        expected_state_version: int,
        monitoring_target_key: str | None = None,
        safe_reason_code: str | None = None,
    ) -> CandidateDecisionResult:
        reason = self._reason_code(safe_reason_code, default="user_rejected")
        candidate = self._repository.load_candidate(
            candidate_id,
            monitoring_target_key,
        )
        state = self.get_monitoring_target_state(candidate.monitoring_target_key)
        if monitoring_target_key is not None and (
            state.monitoring_target_key != monitoring_target_key
        ):
            raise MonitoringNotFoundError("candidate was not found")
        if candidate.candidate_id not in state.pending_candidate_ids:
            raise MonitoringConflictError("candidate is not pending")

        now = self._now()
        history_id = self._history_id(
            event_type=BaselineHistoryEventType.CANDIDATE_REJECTED,
            candidate_id=candidate.candidate_id,
            baseline_id=None,
            created_at=now,
        )
        history = BaselineHistoryRecord(
            history_id=history_id,
            monitoring_group_key=candidate.monitoring_group_key,
            monitoring_target_key=candidate.monitoring_target_key,
            event_type=BaselineHistoryEventType.CANDIDATE_REJECTED,
            candidate_id=candidate.candidate_id,
            previous_approved_id=state.current_approved_id,
            new_approved_id=state.current_approved_id,
            created_at=now,
            safe_reason_code=reason,
        )
        pending_ids = [
            item
            for item in state.pending_candidate_ids
            if item != candidate.candidate_id
        ]
        rejected_ids = [*state.rejected_candidate_ids, candidate.candidate_id]
        new_state = self._state_with(
            state,
            identity=state.identity,
            state_version=state.state_version + 1,
            pending_candidate_ids=pending_ids,
            rejected_candidate_ids=rejected_ids,
            history_ids=[*state.history_ids, history_id],
            baseline_lifecycle=(
                BaselineLifecycleStatus.CANDIDATE_PENDING
                if pending_ids
                else BaselineLifecycleStatus.REJECTED
            ),
            verification_status=VerificationStatus.REVIEW_REQUIRED,
            updated_at=now,
        )
        result = self._repository.commit_rejection(
            RejectionCommit(expected_state_version, history, new_state)
        )
        return CandidateDecisionResult(
            decision="rejected",
            candidate_id=candidate.candidate_id,
            monitoring_group_key=candidate.monitoring_group_key,
            monitoring_target_key=candidate.monitoring_target_key,
            history_id=history_id,
            committed_state=result.committed_state,
            warnings=result.warnings,
        )

    def revoke_current_baseline(
        self,
        monitoring_target_key: str,
        *,
        expected_state_version: int,
        expected_current_approved_id: str,
        safe_reason_code: str | None = None,
    ) -> BaselineRevocationResult:
        reason = self._reason_code(
            safe_reason_code,
            default="user_revoked_baseline",
        )
        state = self.get_monitoring_target_state(monitoring_target_key)
        current_approved_id = state.current_approved_id
        if current_approved_id is None:
            raise MonitoringConflictError("current approved baseline is missing")
        if current_approved_id != expected_current_approved_id:
            raise MonitoringConflictError("current approved baseline conflict")

        approved = self._repository.load_approved_baseline(
            current_approved_id,
            monitoring_target_key=state.monitoring_target_key,
        )
        now = self._now()
        history_id = self._history_id(
            event_type=BaselineHistoryEventType.BASELINE_REVOKED,
            candidate_id=None,
            baseline_id=approved.baseline_id,
            created_at=now,
        )
        history = BaselineHistoryRecord(
            history_id=history_id,
            monitoring_group_key=state.monitoring_group_key,
            monitoring_target_key=state.monitoring_target_key,
            event_type=BaselineHistoryEventType.BASELINE_REVOKED,
            candidate_id=None,
            baseline_id=approved.baseline_id,
            previous_approved_id=approved.baseline_id,
            new_approved_id=None,
            created_at=now,
            safe_reason_code=reason,
        )
        superseded_ids = list(state.superseded_baseline_ids)
        if approved.baseline_id not in superseded_ids:
            superseded_ids.append(approved.baseline_id)

        new_state = self._state_with(
            state,
            identity=state.identity,
            state_version=state.state_version + 1,
            current_approved_id=None,
            superseded_baseline_ids=superseded_ids,
            history_ids=[*state.history_ids, history_id],
            baseline_lifecycle=(
                BaselineLifecycleStatus.CANDIDATE_PENDING
                if state.pending_candidate_ids
                else BaselineLifecycleStatus.NONE
            ),
            comparison_status=ComparisonStatus.NOT_COMPARED,
            verification_status=VerificationStatus.UNVERIFIED,
            last_comparison=None,
            updated_at=now,
        )
        result = self._repository.commit_baseline_revocation(
            BaselineRevocationCommit(
                expected_state_version,
                approved.baseline_id,
                history,
                new_state,
            )
        )
        return BaselineRevocationResult(
            monitoring_group_key=state.monitoring_group_key,
            monitoring_target_key=state.monitoring_target_key,
            removed_baseline_id=approved.baseline_id,
            history_id=history_id,
            committed_state=result.committed_state,
            warnings=result.warnings,
        )

    def _discover(self, context: DiscoveryContext) -> McpDiscoveryResult:
        try:
            return self._discover_servers(context)
        except Exception as exc:
            raise MonitoringDiscoveryError(
                "could not discover MCP servers"
            ) from exc

    def _select_server(
        self,
        discovery: McpDiscoveryResult,
        selection_id: str,
    ) -> DiscoveredMcpServer:
        matches = [
            server
            for server in discovery.servers
            if server.selection_id == selection_id
        ]
        if not matches:
            raise MonitoringNotFoundError("selected server was not found")
        if len(matches) > 1:
            raise MonitoringConflictError("selected server is ambiguous")
        return matches[0]

    async def _run_dynamic_scan(
        self,
        server: DiscoveredMcpServer,
    ) -> DynamicScanResult:
        try:
            result = self._dynamic_scan_runner(server)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            raise MonitoringScanError("could not scan MCP server") from exc

        if not isinstance(result, DynamicScanResult):
            raise MonitoringScanError("dynamic scan result was invalid")
        return result

    async def _enter_target_scan(self, monitoring_target_key: str) -> None:
        async with self._scan_registry_lock:
            if monitoring_target_key in self._active_scan_targets:
                raise MonitoringConflictError("target scan is already running")
            self._active_scan_targets.add(monitoring_target_key)

    async def _exit_target_scan(self, monitoring_target_key: str) -> None:
        async with self._scan_registry_lock:
            self._active_scan_targets.discard(monitoring_target_key)

    def _load_or_create_state(
        self,
        identity: MonitoringIdentity,
    ) -> MonitoredServerState:
        state = self._repository.load_target_state(identity.monitoring_target_key)
        if state is not None:
            return state

        initial_state = self._initial_state(identity, self._now())
        try:
            return self._repository.save_initial_target_state(initial_state)
        except MonitoringConflictError:
            existing = self._repository.load_target_state(
                identity.monitoring_target_key
            )
            if existing is not None:
                return existing
            raise

    def _commit_scan_result(
        self,
        *,
        server: DiscoveredMcpServer,
        identity: MonitoringIdentity,
        fingerprint: ConfigurationFingerprint,
        state: MonitoredServerState,
        dynamic_result: DynamicScanResult,
        reconsider_rejected: bool,
    ) -> MonitoredScanResult:
        now = self._now()
        scan_status = self._monitoring_scan_status(dynamic_result.status)
        snapshot_result = self._snapshot_from_dynamic_result(dynamic_result, now)
        snapshot = snapshot_result.snapshot
        related_keys = self._related_target_keys(identity.monitoring_group_key)
        related_approved_keys = self._approved_target_keys(related_keys)
        warnings = self._warning_codes(
            [_PARTIAL_SCAN_WARNING]
            if scan_status == MonitoringScanStatus.PARTIAL_SUCCESS
            else [],
            snapshot_result.warning_codes,
        )
        shadowing_registration_changed = (
            state.current_approved_id is None
            and any(
                target_key != identity.monitoring_target_key
                for target_key in related_approved_keys
            )
        )

        if snapshot is None:
            new_state = self._scan_state(
                state,
                identity=identity,
                scan_status=scan_status,
                selection_id=server.selection_id,
                comparison_result=None,
                comparison_status=ComparisonStatus.COMPARISON_FAILED,
                verification_status=VerificationStatus.UNAVAILABLE,
                now=now,
            )
            result = self._repository.commit_state(
                StateCommit(state.state_version, new_state)
            )
            warnings = self._warning_codes(warnings, result.warnings)
            return self._scan_result(
                server=server,
                identity=identity,
                dynamic_result=dynamic_result,
                committed=result,
                candidate=None,
                comparison_result=None,
                related_target_keys=related_keys,
                related_approved_target_keys=related_approved_keys,
                registration_changed=shadowing_registration_changed,
                warnings=warnings,
            )

        comparison_result = self._comparison_result(
            state=state,
            snapshot=snapshot,
            selection_id=server.selection_id,
            fingerprint=fingerprint,
        )
        registration_changed = (
            comparison_result.registration_changed
            if comparison_result is not None
            else False
        )
        configuration_changed = (
            comparison_result.configuration_changed
            if comparison_result is not None
            else False
        )
        matched = (
            comparison_result is not None
            and comparison_result.comparison_status == ComparisonStatus.MATCHED
        )

        if matched:
            verification_status = (
                VerificationStatus.REVIEW_REQUIRED
                if (
                    scan_status == MonitoringScanStatus.PARTIAL_SUCCESS
                    or bool(state.pending_candidate_ids)
                )
                else VerificationStatus.VERIFIED
            )
            new_state = self._scan_state(
                state,
                identity=identity,
                scan_status=scan_status,
                selection_id=server.selection_id,
                comparison_result=comparison_result,
                comparison_status=comparison_result.comparison_status,
                verification_status=verification_status,
                now=now,
            )
            result = self._repository.commit_state(
                StateCommit(state.state_version, new_state)
            )
            warnings = self._warning_codes(warnings, result.warnings)
            return self._scan_result(
                server=server,
                identity=identity,
                dynamic_result=dynamic_result,
                committed=result,
                candidate=None,
                comparison_result=comparison_result,
                registration_changed=registration_changed,
                configuration_changed=configuration_changed,
                related_target_keys=related_keys,
                related_approved_target_keys=related_approved_keys,
                warnings=warnings,
            )

        pending_match = self._matching_pending_candidate(
            candidate_ids=state.pending_candidate_ids,
            monitoring_target_key=state.monitoring_target_key,
            selection_id=server.selection_id,
            fingerprint=fingerprint,
            snapshot=snapshot,
        )
        if pending_match is not None:
            new_state = self._scan_state(
                state,
                identity=identity,
                scan_status=scan_status,
                selection_id=server.selection_id,
                comparison_result=comparison_result,
                comparison_status=self._comparison_status(comparison_result),
                verification_status=VerificationStatus.REVIEW_REQUIRED,
                now=now,
            )
            result = self._repository.commit_state(
                StateCommit(state.state_version, new_state)
            )
            warnings = self._warning_codes(warnings, result.warnings)
            return self._scan_result(
                server=server,
                identity=identity,
                dynamic_result=dynamic_result,
                committed=result,
                candidate=pending_match,
                comparison_result=comparison_result,
                registration_changed=(
                    registration_changed or shadowing_registration_changed
                ),
                configuration_changed=configuration_changed,
                related_target_keys=related_keys,
                related_approved_target_keys=related_approved_keys,
                candidate_reused=True,
                warnings=warnings,
            )

        rejected_match = self._matching_rejected_candidate(
            candidate_ids=state.rejected_candidate_ids,
            monitoring_target_key=state.monitoring_target_key,
            selection_id=server.selection_id,
            fingerprint=fingerprint,
            snapshot=snapshot,
        )
        if rejected_match is not None and not reconsider_rejected:
            rejected_lifecycle = (
                BaselineLifecycleStatus.CANDIDATE_PENDING
                if state.pending_candidate_ids
                else BaselineLifecycleStatus.REJECTED
            )
            new_state = self._scan_state(
                state,
                identity=identity,
                scan_status=scan_status,
                selection_id=server.selection_id,
                comparison_result=comparison_result,
                comparison_status=self._comparison_status(comparison_result),
                verification_status=VerificationStatus.REVIEW_REQUIRED,
                now=now,
                baseline_lifecycle_override=rejected_lifecycle,
            )
            result = self._repository.commit_state(
                StateCommit(state.state_version, new_state)
            )
            warnings = self._warning_codes(warnings, result.warnings)
            return self._scan_result(
                server=server,
                identity=identity,
                dynamic_result=dynamic_result,
                committed=result,
                candidate=None,
                comparison_result=comparison_result,
                registration_changed=(
                    registration_changed or shadowing_registration_changed
                ),
                configuration_changed=configuration_changed,
                related_target_keys=related_keys,
                related_approved_target_keys=related_approved_keys,
                rejected_same_snapshot=True,
                can_reconsider_rejected=True,
                warnings=warnings,
            )

        candidate_revision = 1
        supersedes_rejected_id = None
        if rejected_match is not None:
            candidate_revision = rejected_match.candidate_revision + 1
            supersedes_rejected_id = rejected_match.candidate_id
        candidate_revision = self._available_candidate_revision(
            identity=identity,
            selection_id=server.selection_id,
            fingerprint=fingerprint,
            snapshot=snapshot,
            start_revision=candidate_revision,
            supersedes_rejected_candidate_id=supersedes_rejected_id,
        )

        candidate = self._candidate(
            identity=identity,
            selection_id=server.selection_id,
            fingerprint=fingerprint,
            snapshot=snapshot,
            comparison_result=comparison_result,
            scan_status=scan_status,
            scan_id=self._scan_id(dynamic_result),
            state_version=state.state_version,
            created_at=now,
            candidate_revision=candidate_revision,
            supersedes_rejected_candidate_id=supersedes_rejected_id,
        )
        result_registration_changed = (
            registration_changed or shadowing_registration_changed
        )
        new_state = self._scan_state(
            state,
            identity=identity,
            scan_status=scan_status,
            selection_id=server.selection_id,
            comparison_result=comparison_result,
            comparison_status=self._comparison_status(comparison_result),
            verification_status=VerificationStatus.REVIEW_REQUIRED,
            now=now,
            pending_candidate_ids=[*state.pending_candidate_ids, candidate.candidate_id],
        )
        result = self._repository.commit_candidate(
            CandidateCommit(state.state_version, candidate, new_state)
        )
        warnings = self._warning_codes(warnings, result.warnings)
        return self._scan_result(
            server=server,
            identity=identity,
            dynamic_result=dynamic_result,
            committed=result,
            candidate=candidate,
            comparison_result=comparison_result,
            registration_changed=result_registration_changed,
            configuration_changed=configuration_changed,
            related_target_keys=related_keys,
            related_approved_target_keys=related_approved_keys,
            candidate_created=True,
            warnings=warnings,
        )

    def _scan_result(
        self,
        *,
        server: DiscoveredMcpServer,
        identity: MonitoringIdentity,
        dynamic_result: DynamicScanResult,
        committed: RepositoryCommitResult,
        candidate: MonitoringCandidate | None,
        comparison_result: BaselineComparisonResult | None,
        related_target_keys: list[str],
        related_approved_target_keys: list[str] | None = None,
        registration_changed: bool = False,
        configuration_changed: bool = False,
        candidate_created: bool = False,
        candidate_reused: bool = False,
        rejected_same_snapshot: bool = False,
        can_reconsider_rejected: bool = False,
        warnings: list[str] | None = None,
    ) -> MonitoredScanResult:
        related_approved_keys = (
            related_approved_target_keys
            if related_approved_target_keys is not None
            else self._approved_target_keys(related_target_keys)
        )
        return MonitoredScanResult(
            server_summary=server.to_summary(),
            monitoring_identity=identity,
            dynamic_scan_result=dynamic_result,
            monitoring_state=committed.committed_state,
            candidate=candidate,
            comparison_result=comparison_result,
            registration_changed=registration_changed,
            configuration_changed=configuration_changed,
            related_target_keys=related_target_keys,
            related_approved_target_keys=related_approved_keys,
            candidate_created=candidate_created,
            candidate_reused=candidate_reused,
            rejected_same_snapshot=rejected_same_snapshot,
            can_reconsider_rejected=can_reconsider_rejected,
            warnings=list(warnings or []),
        )

    def _comparison_result(
        self,
        *,
        state: MonitoredServerState,
        snapshot: ToolSnapshot,
        selection_id: str,
        fingerprint: ConfigurationFingerprint,
    ) -> BaselineComparisonResult | None:
        if state.current_approved_id is None:
            return None

        approved = self._repository.load_approved_baseline(
            state.current_approved_id,
            state.monitoring_target_key,
        )
        result = compare_tool_snapshots(approved.snapshot, snapshot)
        registration_changed = approved.selection_id_at_approval != selection_id
        configuration_changed = (
            approved.configuration_fingerprint.fingerprint
            != fingerprint.fingerprint
            or approved.configuration_fingerprint.transport
            != fingerprint.transport
        )
        return self._with_comparison_flags(
            result,
            registration_changed=registration_changed,
            configuration_changed=configuration_changed,
        )

    def _with_comparison_flags(
        self,
        result: BaselineComparisonResult,
        *,
        registration_changed: bool,
        configuration_changed: bool,
    ) -> BaselineComparisonResult:
        if result.comparison_status == ComparisonStatus.COMPARISON_FAILED:
            return self._comparison_with(
                result,
                registration_changed=registration_changed,
                configuration_changed=configuration_changed,
            )

        material_count = (
            result.added_count + result.removed_count + result.changed_count
        )
        changed = material_count > 0 or registration_changed or configuration_changed
        return self._comparison_with(
            result,
            comparison_status=(
                ComparisonStatus.CHANGED
                if changed
                else ComparisonStatus.MATCHED
            ),
            matched=not changed,
            registration_changed=registration_changed,
            configuration_changed=configuration_changed,
        )

    def _matching_pending_candidate(
        self,
        *,
        candidate_ids: list[str],
        monitoring_target_key: str,
        selection_id: str,
        fingerprint: ConfigurationFingerprint,
        snapshot: ToolSnapshot,
    ) -> MonitoringCandidate | None:
        matches = self._matching_candidates(
            candidate_ids=candidate_ids,
            monitoring_target_key=monitoring_target_key,
            selection_id=selection_id,
            fingerprint=fingerprint,
            snapshot=snapshot,
        )
        if len(matches) > 1:
            raise MonitoringConflictError("matching pending candidate is ambiguous")
        return matches[0] if matches else None

    def _matching_rejected_candidate(
        self,
        *,
        candidate_ids: list[str],
        monitoring_target_key: str,
        selection_id: str,
        fingerprint: ConfigurationFingerprint,
        snapshot: ToolSnapshot,
    ) -> MonitoringCandidate | None:
        matches = self._matching_candidates(
            candidate_ids=candidate_ids,
            monitoring_target_key=monitoring_target_key,
            selection_id=selection_id,
            fingerprint=fingerprint,
            snapshot=snapshot,
        )
        if not matches:
            return None

        max_revision = max(candidate.candidate_revision for candidate in matches)
        highest = [
            candidate
            for candidate in matches
            if candidate.candidate_revision == max_revision
        ]
        if len(highest) > 1:
            raise MonitoringConflictError("matching rejected candidate is ambiguous")
        return highest[0]

    def _matching_candidates(
        self,
        *,
        candidate_ids: list[str],
        monitoring_target_key: str,
        selection_id: str,
        fingerprint: ConfigurationFingerprint,
        snapshot: ToolSnapshot,
    ) -> list[MonitoringCandidate]:
        matches: list[MonitoringCandidate] = []
        for candidate_id in candidate_ids:
            candidate = self._repository.load_candidate(
                candidate_id,
                monitoring_target_key,
            )
            if (
                candidate.monitoring_target_key == monitoring_target_key
                and candidate.selection_id == selection_id
                and candidate.configuration_fingerprint.fingerprint
                == fingerprint.fingerprint
                and candidate.configuration_fingerprint.transport
                == fingerprint.transport
                and candidate.snapshot.snapshot_hash == snapshot.snapshot_hash
                and candidate.snapshot.normalization_version
                == snapshot.normalization_version
            ):
                matches.append(candidate)
        return matches

    def _candidate(
        self,
        *,
        identity: MonitoringIdentity,
        selection_id: str,
        fingerprint: ConfigurationFingerprint,
        snapshot: ToolSnapshot,
        comparison_result: BaselineComparisonResult | None,
        scan_status: MonitoringScanStatus,
        scan_id: str | None,
        state_version: int,
        created_at: datetime,
        candidate_revision: int,
        supersedes_rejected_candidate_id: str | None,
    ) -> MonitoringCandidate:
        candidate_id = self._candidate_id(
            identity=identity,
            selection_id=selection_id,
            fingerprint=fingerprint,
            snapshot=snapshot,
            candidate_revision=candidate_revision,
            supersedes_rejected_candidate_id=supersedes_rejected_candidate_id,
        )
        return MonitoringCandidate(
            candidate_id=candidate_id,
            monitoring_group_key=identity.monitoring_group_key,
            monitoring_target_key=identity.monitoring_target_key,
            selection_id=selection_id,
            configuration_fingerprint=fingerprint,
            snapshot=snapshot,
            comparison_result=comparison_result,
            dynamic_scan_status=scan_status,
            scan_id=scan_id,
            created_at=created_at,
            candidate_revision=candidate_revision,
            supersedes_rejected_candidate_id=supersedes_rejected_candidate_id,
            state_version_at_creation=state_version,
        )

    def _candidate_id(
        self,
        *,
        identity: MonitoringIdentity,
        selection_id: str,
        fingerprint: ConfigurationFingerprint,
        snapshot: ToolSnapshot,
        candidate_revision: int,
        supersedes_rejected_candidate_id: str | None,
    ) -> str:
        return "cand_" + self._digest(
            {
                "version": _CANDIDATE_ID_VERSION,
                "monitoring_target_key": identity.monitoring_target_key,
                "selection_id": selection_id,
                "configuration_fingerprint": fingerprint.fingerprint,
                "snapshot_hash": snapshot.snapshot_hash,
                "normalization_version": snapshot.normalization_version,
                "candidate_revision": candidate_revision,
                "supersedes_rejected_candidate_id": (
                    supersedes_rejected_candidate_id
                ),
            }
        )

    def _available_candidate_revision(
        self,
        *,
        identity: MonitoringIdentity,
        selection_id: str,
        fingerprint: ConfigurationFingerprint,
        snapshot: ToolSnapshot,
        start_revision: int,
        supersedes_rejected_candidate_id: str | None,
    ) -> int:
        candidate_revision = start_revision
        while True:
            candidate_id = self._candidate_id(
                identity=identity,
                selection_id=selection_id,
                fingerprint=fingerprint,
                snapshot=snapshot,
                candidate_revision=candidate_revision,
                supersedes_rejected_candidate_id=supersedes_rejected_candidate_id,
            )
            try:
                self._repository.load_candidate(
                    candidate_id,
                    monitoring_target_key=identity.monitoring_target_key,
                )
            except MonitoringNotFoundError:
                return candidate_revision
            candidate_revision += 1

    def _baseline_id(
        self,
        candidate: MonitoringCandidate,
        approved_at: datetime,
    ) -> str:
        return "base_" + self._digest(
            {
                "version": _BASELINE_ID_VERSION,
                "monitoring_target_key": candidate.monitoring_target_key,
                "candidate_id": candidate.candidate_id,
                "snapshot_hash": candidate.snapshot.snapshot_hash,
                "approved_at": self._datetime_payload(approved_at),
            }
        )

    def _history_id(
        self,
        *,
        event_type: BaselineHistoryEventType,
        candidate_id: str | None,
        baseline_id: str | None,
        created_at: datetime,
    ) -> str:
        return "hist_" + self._digest(
            {
                "version": _HISTORY_ID_VERSION,
                "event_type": event_type.value,
                "candidate_id": candidate_id,
                "baseline_id": baseline_id,
                "created_at": self._datetime_payload(created_at),
            }
        )

    def _snapshot_from_dynamic_result(
        self,
        dynamic_result: DynamicScanResult,
        created_at: datetime,
    ) -> _SnapshotBuildResult:
        if dynamic_result.status not in {
            DynamicScanStatus.SUCCESS,
            DynamicScanStatus.PARTIAL_SUCCESS,
        }:
            return _SnapshotBuildResult(snapshot=None)
        if dynamic_result.scan_result is None:
            return _SnapshotBuildResult(
                snapshot=None,
                warning_codes=(_SNAPSHOT_UNAVAILABLE_WARNING,),
            )

        tools: list[ToolMetadata] = [
            collected.metadata for collected in dynamic_result.collected_tools
        ]
        if not tools:
            tools = list(dynamic_result.scan_result.tools)

        try:
            snapshot = create_tool_snapshot(
                tools,
                source_scan_id=self._scan_id(dynamic_result),
                created_at=created_at,
            )
        except (
            MetadataNormalizationError,
            ValidationError,
            TypeError,
            ValueError,
        ):
            return _SnapshotBuildResult(
                snapshot=None,
                warning_codes=(_SNAPSHOT_UNAVAILABLE_WARNING,),
            )

        return _SnapshotBuildResult(snapshot=snapshot)

    def _scan_state(
        self,
        state: MonitoredServerState,
        *,
        identity: MonitoringIdentity,
        scan_status: MonitoringScanStatus,
        selection_id: str,
        comparison_result: BaselineComparisonResult | None,
        comparison_status: ComparisonStatus,
        verification_status: VerificationStatus,
        now: datetime,
        pending_candidate_ids: list[str] | None = None,
        baseline_lifecycle_override: BaselineLifecycleStatus | None = None,
    ) -> MonitoredServerState:
        pending_ids = (
            pending_candidate_ids
            if pending_candidate_ids is not None
            else state.pending_candidate_ids
        )
        return self._state_with(
            state,
            identity=identity,
            state_version=state.state_version + 1,
            pending_candidate_ids=pending_ids,
            last_scan_status=scan_status,
            last_scan_at=now,
            last_seen_selection_id=selection_id,
            baseline_lifecycle=(
                baseline_lifecycle_override
                if baseline_lifecycle_override is not None
                else self._lifecycle(
                    current_approved_id=state.current_approved_id,
                    pending_candidate_ids=pending_ids,
                    rejected_candidate_ids=state.rejected_candidate_ids,
                )
            ),
            comparison_status=comparison_status,
            verification_status=verification_status,
            last_comparison=comparison_result,
            updated_at=now,
        )

    def _state_with(
        self,
        state: MonitoredServerState,
        **updates: object,
    ) -> MonitoredServerState:
        data = state.model_dump(mode="python")
        data.update(updates)
        return MonitoredServerState.model_validate(data)

    def _comparison_with(
        self,
        result: BaselineComparisonResult,
        **updates: object,
    ) -> BaselineComparisonResult:
        data = result.model_dump(mode="python")
        data.update(updates)
        return BaselineComparisonResult.model_validate(data)

    def _initial_state(
        self,
        identity: MonitoringIdentity,
        now: datetime,
    ) -> MonitoredServerState:
        return MonitoredServerState(
            monitoring_group_key=identity.monitoring_group_key,
            monitoring_target_key=identity.monitoring_target_key,
            identity=identity,
            updated_at=now,
        )

    def _related_target_keys(
        self,
        monitoring_group_key: str,
        *,
        discovered_target_keys: set[str] | None = None,
    ) -> list[str]:
        target_keys = set(self._repository.list_group_targets(monitoring_group_key))
        if discovered_target_keys:
            target_keys.update(discovered_target_keys)
        return sorted(target_keys)

    def _approved_target_keys(self, target_keys: list[str]) -> list[str]:
        approved: list[str] = []
        for target_key in target_keys:
            state = self._repository.load_target_state(target_key)
            if state is not None and state.current_approved_id is not None:
                approved.append(state.monitoring_target_key)
        return approved

    def _scan_capability(
        self,
        server: DiscoveredMcpServer,
    ) -> tuple[bool, str | None]:
        if server.enabled_state == ServerEnabledState.DISABLED:
            return False, "server_disabled"
        if server.support_state != ServerSupportState.SUPPORTED:
            return False, "server_not_supported"
        if server.connection is None:
            return False, "connection_unavailable"
        return True, None

    def _monitoring_scan_status(
        self,
        status: DynamicScanStatus,
    ) -> MonitoringScanStatus:
        if status == DynamicScanStatus.SUCCESS:
            return MonitoringScanStatus.SUCCESS
        if status == DynamicScanStatus.PARTIAL_SUCCESS:
            return MonitoringScanStatus.PARTIAL_SUCCESS
        if status == DynamicScanStatus.FAILED:
            return MonitoringScanStatus.FAILED
        if status == DynamicScanStatus.TIMED_OUT:
            return MonitoringScanStatus.TIMED_OUT
        raise MonitoringScanError("dynamic scan status was invalid")

    def _comparison_status(
        self,
        comparison_result: BaselineComparisonResult | None,
    ) -> ComparisonStatus:
        if comparison_result is None:
            return ComparisonStatus.NOT_COMPARED
        return comparison_result.comparison_status

    def _lifecycle(
        self,
        *,
        current_approved_id: str | None,
        pending_candidate_ids: list[str],
        rejected_candidate_ids: list[str],
    ) -> BaselineLifecycleStatus:
        if pending_candidate_ids:
            return BaselineLifecycleStatus.CANDIDATE_PENDING
        if current_approved_id is not None:
            return BaselineLifecycleStatus.APPROVED
        if rejected_candidate_ids:
            return BaselineLifecycleStatus.REJECTED
        return BaselineLifecycleStatus.NONE

    def _scan_id(self, dynamic_result: DynamicScanResult) -> str | None:
        if dynamic_result.scan_result is None:
            return None
        return str(dynamic_result.scan_result.scan_id)

    def _reason_code(self, value: str | None, *, default: str) -> str:
        if value is None:
            reason = default
        else:
            reason = value.strip()
            if reason != value:
                raise MonitoringServiceError("invalid safe reason code")
        if not _SAFE_REASON_RE.fullmatch(reason):
            raise MonitoringServiceError("invalid safe reason code")
        return reason

    def _warning_codes(self, *groups: object) -> list[str]:
        seen: set[str] = set()
        for group in groups:
            if group is None:
                continue
            if isinstance(group, str):
                candidates = [group]
            else:
                candidates = list(group)  # type: ignore[arg-type]
            for candidate in candidates:
                if not isinstance(candidate, str):
                    continue
                if not _SAFE_REASON_RE.fullmatch(candidate):
                    continue
                seen.add(candidate)

        ordered = [code for code in _WARNING_ORDER if code in seen]
        ordered.extend(sorted(seen - set(_WARNING_ORDER)))
        return ordered

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _datetime_payload(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    def _digest(self, payload: object) -> str:
        return calculate_sha256(canonical_json_bytes(payload))[:32]
