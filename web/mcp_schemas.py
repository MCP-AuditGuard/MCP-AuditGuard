from __future__ import annotations

import json

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.dynamic_scan_models import (
    CleanupResult,
    DynamicScanIssue,
    DynamicScanResult,
    DynamicScanStageResult,
    McpProtocolMetadata,
    McpServerSummary,
)
from core.mcp_monitoring_models import (
    BaselineComparisonResult,
    BaselineHistoryRecord,
    ConfigurationFingerprint,
    MonitoringCandidate,
    MonitoringIdentity,
    MonitoredServerState,
    ToolChange,
    ToolFieldChange,
    ToolSnapshot,
    ToolSnapshotWarning,
)
from core.mcp_monitoring_service import (
    BaselineHistoryDeletionResult,
    BaselineRevocationResult,
    CandidateDecisionResult,
    MonitoredScanResult,
    MonitoredServerListItem,
    MonitoredServerListResult,
    MonitoringGroupState,
)
from core.models import Finding
from core.scan_result import ScanResult, SeveritySummary


HASH_PREFIX_LENGTH = 16
TEXT_VALUE_LIMIT = 4000
JSON_VALUE_LIMIT = 12000

_SAFE_CONFIG_SUMMARY_KEYS = frozenset(
    {
        "transport",
        "command_basename",
        "argument_count",
        "cwd_present",
        "env_key_count",
        "env_literal_key_count",
        "env_reference_key_count",
        "env_reference_count",
        "origin",
        "header_name_count",
        "token_reference_present",
        "verify_tls",
        "follow_redirects",
        "trust_env",
    }
)


class _WebModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorResponse(_WebModel):
    error_code: str
    message: str
    details: dict[str, str | int | bool | None] | None = None


class McpServerScanRequest(_WebModel):
    include_trusted_project_config: bool = False
    reconsider_rejected: bool = False


class CandidateDecisionRequest(_WebModel):
    monitoring_target_key: str = Field(pattern=r"^mcptgt_[0-9a-f]{32}$")
    expected_state_version: int = Field(ge=0)
    safe_reason_code: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]{1,64}$",
    )


class BaselineRevocationRequest(_WebModel):
    expected_state_version: int = Field(ge=0)
    expected_current_approved_id: str = Field(
        pattern=r"^base_[A-Za-z0-9_-]{1,128}$"
    )
    safe_reason_code: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]{1,64}$",
    )


class BaselineHistoryDeletionRequest(_WebModel):
    expected_state_version: int = Field(ge=0)


class McpServerSummaryResponse(_WebModel):
    selection_id: str
    product: str
    scope: str
    source_label: str
    server_name: str
    transport: str
    enabled_state: str
    support_state: str
    support_reason_code: str | None = None
    command_basename: str | None = None
    remote_origin: str | None = None
    argument_count: int

    @classmethod
    def from_core(cls, summary: McpServerSummary) -> McpServerSummaryResponse:
        return cls(
            selection_id=summary.selection_id,
            product=_enum_value(summary.product),
            scope=_enum_value(summary.scope),
            source_label=summary.source_label,
            server_name=summary.server_name,
            transport=_enum_value(summary.transport),
            enabled_state=_enum_value(summary.enabled_state),
            support_state=_enum_value(summary.support_state),
            support_reason_code=summary.support_reason_code,
            command_basename=summary.command_basename,
            remote_origin=summary.remote_origin,
            argument_count=summary.argument_count,
        )


class MonitoringIdentityResponse(_WebModel):
    monitoring_group_key: str
    monitoring_target_key: str
    product: str
    display_server_name: str
    context_label: str
    selection_id: str
    scope: str
    source_label: str

    @classmethod
    def from_core(cls, identity: MonitoringIdentity) -> MonitoringIdentityResponse:
        return cls(
            monitoring_group_key=identity.monitoring_group_key,
            monitoring_target_key=identity.monitoring_target_key,
            product=_enum_value(identity.product),
            display_server_name=identity.display_server_name,
            context_label=identity.context_label,
            selection_id=identity.registration_identity.selection_id,
            scope=_enum_value(identity.registration_identity.scope),
            source_label=identity.registration_identity.safe_source_label,
        )


class ToolFieldChangeResponse(_WebModel):
    field_name: str
    old_presence: str
    new_presence: str
    old_value_text: str | None
    new_value_text: str | None
    old_value_hash_prefix: str
    new_value_hash_prefix: str
    old_value_truncated: bool
    new_value_truncated: bool

    @classmethod
    def from_core(cls, change: ToolFieldChange) -> ToolFieldChangeResponse:
        old_value_text, old_truncated = _value_text(
            change.old_value,
            has_value=_enum_value(change.old_presence) == "value",
        )
        new_value_text, new_truncated = _value_text(
            change.new_value,
            has_value=_enum_value(change.new_presence) == "value",
        )
        return cls(
            field_name=change.field_name,
            old_presence=_enum_value(change.old_presence),
            new_presence=_enum_value(change.new_presence),
            old_value_text=old_value_text,
            new_value_text=new_value_text,
            old_value_hash_prefix=_hash_prefix(change.old_value_hash),
            new_value_hash_prefix=_hash_prefix(change.new_value_hash),
            old_value_truncated=old_truncated,
            new_value_truncated=new_truncated,
        )


class ToolChangeResponse(_WebModel):
    change_type: str
    tool_key: str
    tool_name: str
    old_tool_hash_prefix: str | None = None
    new_tool_hash_prefix: str | None = None
    field_changes: list[ToolFieldChangeResponse] = Field(default_factory=list)

    @classmethod
    def from_core(cls, change: ToolChange) -> ToolChangeResponse:
        return cls(
            change_type=_enum_value(change.change_type),
            tool_key=change.tool_key,
            tool_name=change.tool_name,
            old_tool_hash_prefix=_optional_hash_prefix(change.old_tool_hash),
            new_tool_hash_prefix=_optional_hash_prefix(change.new_tool_hash),
            field_changes=[
                ToolFieldChangeResponse.from_core(field_change)
                for field_change in change.field_changes
            ],
        )


class BaselineComparisonResponse(_WebModel):
    comparison_status: str
    matched: bool
    change_categories: list[str] = Field(default_factory=list)
    registration_changed: bool
    configuration_changed: bool
    approved_snapshot_id: str
    current_snapshot_id: str
    approved_snapshot_hash_prefix: str
    current_snapshot_hash_prefix: str
    added_count: int
    removed_count: int
    changed_count: int
    unchanged_count: int
    tool_changes: list[ToolChangeResponse] = Field(default_factory=list)
    comparison_error_code: str | None = None

    @classmethod
    def from_core(
        cls,
        comparison: BaselineComparisonResult,
    ) -> BaselineComparisonResponse:
        return cls(
            comparison_status=_enum_value(comparison.comparison_status),
            matched=comparison.matched,
            change_categories=list(comparison.change_categories),
            registration_changed=comparison.registration_changed,
            configuration_changed=comparison.configuration_changed,
            approved_snapshot_id=comparison.approved_snapshot_id,
            current_snapshot_id=comparison.current_snapshot_id,
            approved_snapshot_hash_prefix=_hash_prefix(
                comparison.approved_snapshot_hash
            ),
            current_snapshot_hash_prefix=_hash_prefix(
                comparison.current_snapshot_hash
            ),
            added_count=comparison.added_count,
            removed_count=comparison.removed_count,
            changed_count=comparison.changed_count,
            unchanged_count=comparison.unchanged_count,
            tool_changes=[
                ToolChangeResponse.from_core(change)
                for change in comparison.tool_changes
            ],
            comparison_error_code=comparison.comparison_error_code,
        )


class MonitoringStateResponse(_WebModel):
    monitoring_group_key: str
    monitoring_target_key: str
    identity: MonitoringIdentityResponse
    state_version: int
    current_approved_id: str | None = None
    pending_candidate_ids: list[str] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)
    superseded_baseline_ids: list[str] = Field(default_factory=list)
    history_ids: list[str] = Field(default_factory=list)
    last_scan_status: str
    last_scan_at: datetime | None = None
    last_seen_selection_id: str | None = None
    baseline_lifecycle: str
    comparison_status: str
    verification_status: str
    last_comparison: BaselineComparisonResponse | None = None
    updated_at: datetime

    @classmethod
    def from_core(cls, state: MonitoredServerState) -> MonitoringStateResponse:
        return cls(
            monitoring_group_key=state.monitoring_group_key,
            monitoring_target_key=state.monitoring_target_key,
            identity=MonitoringIdentityResponse.from_core(state.identity),
            state_version=state.state_version,
            current_approved_id=state.current_approved_id,
            pending_candidate_ids=list(state.pending_candidate_ids),
            rejected_candidate_ids=list(state.rejected_candidate_ids),
            superseded_baseline_ids=list(state.superseded_baseline_ids),
            history_ids=list(state.history_ids),
            last_scan_status=_enum_value(state.last_scan_status),
            last_scan_at=state.last_scan_at,
            last_seen_selection_id=state.last_seen_selection_id,
            baseline_lifecycle=_enum_value(state.baseline_lifecycle),
            comparison_status=_enum_value(state.comparison_status),
            verification_status=_enum_value(state.verification_status),
            last_comparison=(
                BaselineComparisonResponse.from_core(state.last_comparison)
                if state.last_comparison is not None
                else None
            ),
            updated_at=state.updated_at,
        )


class ConfigurationFingerprintResponse(_WebModel):
    algorithm: str
    version: str
    fingerprint_hash_prefix: str
    transport: str
    safe_summary: dict[str, str | int | bool | None]

    @classmethod
    def from_core(
        cls,
        fingerprint: ConfigurationFingerprint,
    ) -> ConfigurationFingerprintResponse:
        return cls(
            algorithm=fingerprint.algorithm,
            version=fingerprint.version,
            fingerprint_hash_prefix=_hash_prefix(fingerprint.fingerprint),
            transport=_enum_value(fingerprint.transport),
            safe_summary=_filtered_safe_summary(fingerprint.safe_summary),
        )


class ToolSnapshotWarningResponse(_WebModel):
    code: str
    message: str
    tool_name: str | None = None
    occurrence_count: int | None = None

    @classmethod
    def from_core(
        cls,
        warning: ToolSnapshotWarning,
    ) -> ToolSnapshotWarningResponse:
        return cls(
            code=warning.code,
            message=warning.message,
            tool_name=warning.tool_name,
            occurrence_count=warning.occurrence_count,
        )


class ToolSnapshotSummaryResponse(_WebModel):
    snapshot_id: str
    snapshot_hash_prefix: str
    normalization_version: str
    tool_count: int
    created_at: datetime
    source_scan_id: str | None = None
    warnings: list[ToolSnapshotWarningResponse] = Field(default_factory=list)

    @classmethod
    def from_core(cls, snapshot: ToolSnapshot) -> ToolSnapshotSummaryResponse:
        return cls(
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash_prefix=_hash_prefix(snapshot.snapshot_hash),
            normalization_version=snapshot.normalization_version,
            tool_count=snapshot.tool_count,
            created_at=snapshot.created_at,
            source_scan_id=snapshot.source_scan_id,
            warnings=[
                ToolSnapshotWarningResponse.from_core(warning)
                for warning in snapshot.warnings
            ],
        )


class BaselineCandidateResponse(_WebModel):
    candidate_id: str
    monitoring_group_key: str
    monitoring_target_key: str
    selection_id: str
    configuration_fingerprint: ConfigurationFingerprintResponse
    snapshot: ToolSnapshotSummaryResponse
    comparison_result: BaselineComparisonResponse | None = None
    dynamic_scan_status: str
    scan_id: str | None = None
    created_at: datetime
    candidate_revision: int
    supersedes_rejected_candidate_id: str | None = None
    state_version_at_creation: int

    @classmethod
    def from_core(
        cls,
        candidate: MonitoringCandidate,
    ) -> BaselineCandidateResponse:
        return cls(
            candidate_id=candidate.candidate_id,
            monitoring_group_key=candidate.monitoring_group_key,
            monitoring_target_key=candidate.monitoring_target_key,
            selection_id=candidate.selection_id,
            configuration_fingerprint=ConfigurationFingerprintResponse.from_core(
                candidate.configuration_fingerprint
            ),
            snapshot=ToolSnapshotSummaryResponse.from_core(candidate.snapshot),
            comparison_result=(
                BaselineComparisonResponse.from_core(candidate.comparison_result)
                if candidate.comparison_result is not None
                else None
            ),
            dynamic_scan_status=_enum_value(candidate.dynamic_scan_status),
            scan_id=candidate.scan_id,
            created_at=candidate.created_at,
            candidate_revision=candidate.candidate_revision,
            supersedes_rejected_candidate_id=(
                candidate.supersedes_rejected_candidate_id
            ),
            state_version_at_creation=candidate.state_version_at_creation,
        )


class DynamicScanIssueResponse(_WebModel):
    stage: str
    code: str
    level: str
    safe_message: str
    server_id: str | None = None
    tool_id: str | None = None
    item_index: int | None = None
    tool_name: str | None = None

    @classmethod
    def from_core(cls, issue: DynamicScanIssue) -> DynamicScanIssueResponse:
        return cls(
            stage=_enum_value(issue.stage),
            code=issue.code,
            level=_enum_value(issue.level),
            safe_message=issue.safe_message,
            server_id=issue.server_id,
            tool_id=issue.tool_id,
            item_index=issue.item_index,
            tool_name=issue.tool_name,
        )


class DynamicScanStageResponse(_WebModel):
    stage: str
    status: str

    @classmethod
    def from_core(
        cls,
        stage: DynamicScanStageResult,
    ) -> DynamicScanStageResponse:
        return cls(
            stage=_enum_value(stage.stage),
            status=_enum_value(stage.status),
        )


class CleanupResultResponse(_WebModel):
    local_cleanup_status: str
    remote_session_termination_status: str
    remote_session_safe_basis_code: str | None = None
    issues: list[DynamicScanIssueResponse] = Field(default_factory=list)

    @classmethod
    def from_core(cls, cleanup: CleanupResult) -> CleanupResultResponse:
        issues = [
            *cleanup.local_cleanup.issues,
            *cleanup.remote_session_termination.issues,
        ]
        return cls(
            local_cleanup_status=_enum_value(cleanup.local_cleanup.status),
            remote_session_termination_status=_enum_value(
                cleanup.remote_session_termination.status
            ),
            remote_session_safe_basis_code=(
                cleanup.remote_session_termination.safe_basis_code
            ),
            issues=[
                DynamicScanIssueResponse.from_core(issue)
                for issue in issues
            ],
        )


class ProtocolMetadataResponse(_WebModel):
    protocol_version: str | None = None
    server_implementation_name: str | None = None
    server_implementation_version: str | None = None

    @classmethod
    def from_core(
        cls,
        metadata: McpProtocolMetadata,
    ) -> ProtocolMetadataResponse:
        implementation = metadata.server_implementation
        return cls(
            protocol_version=metadata.protocol_version,
            server_implementation_name=(
                implementation.name if implementation is not None else None
            ),
            server_implementation_version=(
                implementation.version if implementation is not None else None
            ),
        )


class SeveritySummaryResponse(_WebModel):
    critical: int
    high: int
    medium: int
    low: int
    info: int
    total: int

    @classmethod
    def from_core(cls, summary: SeveritySummary) -> SeveritySummaryResponse:
        return cls(
            critical=summary.critical,
            high=summary.high,
            medium=summary.medium,
            low=summary.low,
            info=summary.info,
            total=summary.total,
        )


class ScanSummaryResponse(_WebModel):
    tool_count: int
    finding_count: int
    affected_target_count: int
    by_severity: SeveritySummaryResponse
    by_confidence: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)

    @classmethod
    def from_core(cls, scan: ScanResult) -> ScanSummaryResponse:
        summary = scan.summary
        return cls(
            tool_count=summary.tool_count,
            finding_count=summary.finding_count,
            affected_target_count=summary.affected_target_count,
            by_severity=SeveritySummaryResponse.from_core(summary.by_severity),
            by_confidence={
                _enum_value(key): count
                for key, count in summary.by_confidence.items()
            },
            by_category=dict(summary.by_category),
        )


class FindingResponse(_WebModel):
    id: str
    category: str
    owasp: str
    severity: str
    confidence: str
    title: str
    target: str
    location: str
    evidence: str
    redacted: bool
    recommendation: str
    fingerprint_hash_prefix: str

    @classmethod
    def from_core(cls, finding: Finding) -> FindingResponse:
        return cls(
            id=finding.id,
            category=finding.category,
            owasp=finding.owasp,
            severity=_enum_value(finding.severity),
            confidence=_enum_value(finding.confidence),
            title=finding.title,
            target=finding.target,
            location=finding.location,
            evidence=finding.evidence,
            redacted=finding.redacted,
            recommendation=finding.recommendation,
            fingerprint_hash_prefix=_optional_hash_prefix(finding.fingerprint) or "",
        )


class ScanResultSummaryResponse(_WebModel):
    scan_id: str
    scan_type: str
    source_type: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    baseline_compared: bool
    warnings: list[str] = Field(default_factory=list)
    summary: ScanSummaryResponse
    findings: list[FindingResponse] = Field(default_factory=list)

    @classmethod
    def from_core(cls, scan: ScanResult) -> ScanResultSummaryResponse:
        return cls(
            scan_id=str(scan.scan_id),
            scan_type=scan.scan_type,
            source_type=scan.source_type,
            started_at=scan.started_at,
            completed_at=scan.completed_at,
            duration_ms=scan.duration_ms,
            baseline_compared=scan.baseline_compared,
            warnings=list(scan.warnings),
            summary=ScanSummaryResponse.from_core(scan),
            findings=[
                FindingResponse.from_core(finding)
                for finding in scan.findings
            ],
        )


class DynamicScanSummaryResponse(_WebModel):
    status: str
    target: McpServerSummaryResponse
    stages: list[DynamicScanStageResponse] = Field(default_factory=list)
    issues: list[DynamicScanIssueResponse] = Field(default_factory=list)
    protocol_metadata: ProtocolMetadataResponse | None = None
    cleanup: CleanupResultResponse
    scan_result: ScanResultSummaryResponse | None = None

    @classmethod
    def from_core(
        cls,
        result: DynamicScanResult,
    ) -> DynamicScanSummaryResponse:
        return cls(
            status=_enum_value(result.status),
            target=McpServerSummaryResponse.from_core(result.target),
            stages=[
                DynamicScanStageResponse.from_core(stage)
                for stage in result.stages
            ],
            issues=[
                DynamicScanIssueResponse.from_core(issue)
                for issue in result.issues
            ],
            protocol_metadata=(
                ProtocolMetadataResponse.from_core(result.protocol_metadata)
                if result.protocol_metadata is not None
                else None
            ),
            cleanup=CleanupResultResponse.from_core(result.cleanup),
            scan_result=(
                ScanResultSummaryResponse.from_core(result.scan_result)
                if result.scan_result is not None
                else None
            ),
        )


class McpServerListItemResponse(_WebModel):
    server: McpServerSummaryResponse
    identity: MonitoringIdentityResponse
    monitoring_state: MonitoringStateResponse
    related_target_count: int
    related_approved_target_count: int
    can_scan: bool
    safe_action_reason: str | None = None

    @classmethod
    def from_core(
        cls,
        item: MonitoredServerListItem,
    ) -> McpServerListItemResponse:
        return cls(
            server=McpServerSummaryResponse.from_core(item.server_summary),
            identity=MonitoringIdentityResponse.from_core(
                item.monitoring_identity
            ),
            monitoring_state=MonitoringStateResponse.from_core(
                item.monitoring_state
            ),
            related_target_count=item.related_target_count,
            related_approved_target_count=item.related_approved_target_count,
            can_scan=item.can_scan,
            safe_action_reason=item.safe_action_reason,
        )


class McpServerListResponse(_WebModel):
    servers: list[McpServerListItemResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    include_trusted_project_config: bool
    discovery_issue_count: int
    discovery_warning_count: int
    discovery_error_count: int
    discovery_issue_codes: list[str] = Field(default_factory=list)

    @classmethod
    def from_core(
        cls,
        result: MonitoredServerListResult,
        *,
        include_trusted_project_config: bool = False,
    ) -> McpServerListResponse:
        server_items = [
            McpServerListItemResponse.from_core(item)
            for item in result.servers
        ]
        return cls(
            servers=server_items,
            total=len(server_items),
            include_trusted_project_config=include_trusted_project_config,
            discovery_issue_count=len(result.discovery_result.issues),
            discovery_warning_count=sum(
                1
                for issue in result.discovery_result.issues
                if _enum_value(issue.level) == "warning"
            ),
            discovery_error_count=sum(
                1
                for issue in result.discovery_result.issues
                if _enum_value(issue.level) == "error"
            ),
            discovery_issue_codes=sorted(
                {issue.code for issue in result.discovery_result.issues}
            ),
        )


class MonitoredScanResponse(_WebModel):
    server: McpServerSummaryResponse
    identity: MonitoringIdentityResponse
    dynamic_scan_result: DynamicScanSummaryResponse
    monitoring_state: MonitoringStateResponse
    candidate: BaselineCandidateResponse | None = None
    comparison_result: BaselineComparisonResponse | None = None
    registration_changed: bool
    configuration_changed: bool
    related_target_keys: list[str] = Field(default_factory=list)
    related_approved_target_keys: list[str] = Field(default_factory=list)
    candidate_created: bool
    candidate_reused: bool
    rejected_same_snapshot: bool
    can_reconsider_rejected: bool
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_core(cls, result: MonitoredScanResult) -> MonitoredScanResponse:
        return cls(
            server=McpServerSummaryResponse.from_core(result.server_summary),
            identity=MonitoringIdentityResponse.from_core(
                result.monitoring_identity
            ),
            dynamic_scan_result=DynamicScanSummaryResponse.from_core(
                result.dynamic_scan_result
            ),
            monitoring_state=MonitoringStateResponse.from_core(
                result.monitoring_state
            ),
            candidate=(
                BaselineCandidateResponse.from_core(result.candidate)
                if result.candidate is not None
                else None
            ),
            comparison_result=(
                BaselineComparisonResponse.from_core(result.comparison_result)
                if result.comparison_result is not None
                else None
            ),
            registration_changed=result.registration_changed,
            configuration_changed=result.configuration_changed,
            related_target_keys=list(result.related_target_keys),
            related_approved_target_keys=list(result.related_approved_target_keys),
            candidate_created=result.candidate_created,
            candidate_reused=result.candidate_reused,
            rejected_same_snapshot=result.rejected_same_snapshot,
            can_reconsider_rejected=result.can_reconsider_rejected,
            warnings=list(result.warnings),
        )


class MonitoringGroupResponse(_WebModel):
    monitoring_group_key: str
    target_keys: list[str] = Field(default_factory=list)
    target_states: list[MonitoringStateResponse] = Field(default_factory=list)
    related_approved_target_keys: list[str] = Field(default_factory=list)

    @classmethod
    def from_core(cls, group: MonitoringGroupState) -> MonitoringGroupResponse:
        return cls(
            monitoring_group_key=group.monitoring_group_key,
            target_keys=list(group.target_keys),
            target_states=[
                MonitoringStateResponse.from_core(state)
                for state in group.target_states
            ],
            related_approved_target_keys=list(group.related_approved_target_keys),
        )


class BaselineHistoryResponse(_WebModel):
    history_id: str
    monitoring_group_key: str
    monitoring_target_key: str
    event_type: str
    candidate_id: str | None = None
    baseline_id: str | None = None
    previous_approved_id: str | None = None
    new_approved_id: str | None = None
    created_at: datetime
    safe_reason_code: str | None = None

    @classmethod
    def from_core(
        cls,
        record: BaselineHistoryRecord,
    ) -> BaselineHistoryResponse:
        return cls(
            history_id=record.history_id,
            monitoring_group_key=record.monitoring_group_key,
            monitoring_target_key=record.monitoring_target_key,
            event_type=_enum_value(record.event_type),
            candidate_id=record.candidate_id,
            baseline_id=record.baseline_id,
            previous_approved_id=record.previous_approved_id,
            new_approved_id=record.new_approved_id,
            created_at=record.created_at,
            safe_reason_code=record.safe_reason_code,
        )


class BaselineHistoryListResponse(_WebModel):
    monitoring_target_key: str
    records: list[BaselineHistoryResponse] = Field(default_factory=list)
    total: int = Field(ge=0)

    @classmethod
    def from_core(
        cls,
        monitoring_target_key: str,
        records: list[BaselineHistoryRecord],
    ) -> BaselineHistoryListResponse:
        history_records = [
            BaselineHistoryResponse.from_core(record)
            for record in records
        ]
        return cls(
            monitoring_target_key=monitoring_target_key,
            records=history_records,
            total=len(history_records),
        )


class BaselineHistoryDeletionResponse(_WebModel):
    decision: str
    monitoring_group_key: str
    monitoring_target_key: str
    deleted_history_count: int = Field(ge=0)
    state_version: int
    history_ids: list[str] = Field(default_factory=list)
    current_approved_id: str | None = None
    baseline_lifecycle: str
    comparison_status: str
    verification_status: str
    last_scan_status: str
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_core(
        cls,
        result: BaselineHistoryDeletionResult,
    ) -> BaselineHistoryDeletionResponse:
        state = result.committed_state
        return cls(
            decision=result.decision,
            monitoring_group_key=result.monitoring_group_key,
            monitoring_target_key=result.monitoring_target_key,
            deleted_history_count=result.deleted_history_count,
            state_version=state.state_version,
            history_ids=list(state.history_ids),
            current_approved_id=state.current_approved_id,
            baseline_lifecycle=_enum_value(state.baseline_lifecycle),
            comparison_status=_enum_value(state.comparison_status),
            verification_status=_enum_value(state.verification_status),
            last_scan_status=_enum_value(state.last_scan_status),
            warnings=list(result.warnings),
        )


class CandidateDecisionResponse(_WebModel):
    decision: str
    candidate_id: str
    monitoring_group_key: str
    monitoring_target_key: str
    baseline_id: str | None = None
    history_id: str
    state_version: int
    current_approved_id: str | None = None
    baseline_lifecycle: str
    comparison_status: str
    verification_status: str
    last_scan_status: str
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_core(
        cls,
        result: CandidateDecisionResult,
    ) -> CandidateDecisionResponse:
        state = result.committed_state
        return cls(
            decision=result.decision,
            candidate_id=result.candidate_id,
            monitoring_group_key=result.monitoring_group_key,
            monitoring_target_key=result.monitoring_target_key,
            baseline_id=result.baseline_id,
            history_id=result.history_id,
            state_version=state.state_version,
            current_approved_id=state.current_approved_id,
            baseline_lifecycle=_enum_value(state.baseline_lifecycle),
            comparison_status=_enum_value(state.comparison_status),
            verification_status=_enum_value(state.verification_status),
            last_scan_status=_enum_value(state.last_scan_status),
            warnings=list(result.warnings),
        )


class BaselineRevocationResponse(_WebModel):
    decision: str
    monitoring_group_key: str
    monitoring_target_key: str
    removed_baseline_id: str
    history_id: str
    state_version: int
    current_approved_id: str | None = None
    baseline_lifecycle: str
    comparison_status: str
    verification_status: str
    last_scan_status: str
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_core(
        cls,
        result: BaselineRevocationResult,
    ) -> BaselineRevocationResponse:
        state = result.committed_state
        return cls(
            decision=result.decision,
            monitoring_group_key=result.monitoring_group_key,
            monitoring_target_key=result.monitoring_target_key,
            removed_baseline_id=result.removed_baseline_id,
            history_id=result.history_id,
            state_version=state.state_version,
            current_approved_id=state.current_approved_id,
            baseline_lifecycle=_enum_value(state.baseline_lifecycle),
            comparison_status=_enum_value(state.comparison_status),
            verification_status=_enum_value(state.verification_status),
            last_scan_status=_enum_value(state.last_scan_status),
            warnings=list(result.warnings),
        )


def _enum_value(value: object) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _hash_prefix(value: str) -> str:
    return value[:HASH_PREFIX_LENGTH]


def _optional_hash_prefix(value: str | None) -> str | None:
    if value is None:
        return None
    return _hash_prefix(value)


def _value_text(value: Any, *, has_value: bool) -> tuple[str | None, bool]:
    if not has_value:
        return None, False

    if isinstance(value, str):
        return _truncate(value, TEXT_VALUE_LIMIT)

    limit = JSON_VALUE_LIMIT if isinstance(value, (dict, list)) else TEXT_VALUE_LIMIT
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        text = "[unavailable]"

    return _truncate(text, limit)


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit], True


def _filtered_safe_summary(
    summary: dict[str, str | int | bool | None],
) -> dict[str, str | int | bool | None]:
    return {
        key: value
        for key, value in summary.items()
        if key in _SAFE_CONFIG_SUMMARY_KEYS
    }
