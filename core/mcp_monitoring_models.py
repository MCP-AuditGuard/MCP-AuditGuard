from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.dynamic_scan_models import McpProduct, McpScope, McpTransport


MONITORING_STORAGE_SCHEMA_VERSION = "mcp-monitoring-storage-v1"


class MonitoringScanStatus(StrEnum):
    NOT_SCANNED = "not_scanned"
    SCANNING = "scanning"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class BaselineLifecycleStatus(StrEnum):
    NONE = "none"
    CANDIDATE_PENDING = "candidate_pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ComparisonStatus(StrEnum):
    NOT_COMPARED = "not_compared"
    MATCHED = "matched"
    CHANGED = "changed"
    COMPARISON_FAILED = "comparison_failed"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REVIEW_REQUIRED = "review_required"
    UNAVAILABLE = "unavailable"


class ToolChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


class BaselineHistoryEventType(StrEnum):
    CANDIDATE_CREATED = "candidate_created"
    CANDIDATE_APPROVED = "candidate_approved"
    CANDIDATE_REJECTED = "candidate_rejected"
    BASELINE_SUPERSEDED = "baseline_superseded"
    BASELINE_REVOKED = "baseline_revoked"


class FieldPresence(StrEnum):
    MISSING = "missing"
    NULL = "null"
    VALUE = "value"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        validate_assignment=True,
    )


class NormalizedFieldValue(_FrozenModel):
    presence: FieldPresence
    value: Any | None = None

    @model_validator(mode="after")
    def validate_presence_payload(self) -> Self:
        if self.presence in {FieldPresence.MISSING, FieldPresence.NULL}:
            if self.value is not None:
                raise ValueError("missing and null fields cannot have a value")
        elif self.value is None:
            raise ValueError("value fields must not use None")

        return self

    def to_hash_payload(self) -> dict[str, Any]:
        if self.presence == FieldPresence.MISSING:
            return {"presence": self.presence.value}

        return {
            "presence": self.presence.value,
            "value": self.value,
        }


class NormalizedMetadataFields(_FrozenModel):
    title: NormalizedFieldValue
    description: NormalizedFieldValue
    input_schema: NormalizedFieldValue
    output_schema: NormalizedFieldValue
    annotations: NormalizedFieldValue
    meta: NormalizedFieldValue

    def to_hash_payload(self) -> dict[str, Any]:
        return {
            "title": self.title.to_hash_payload(),
            "description": self.description.to_hash_payload(),
            "input_schema": self.input_schema.to_hash_payload(),
            "output_schema": self.output_schema.to_hash_payload(),
            "annotations": self.annotations.to_hash_payload(),
            "meta": self.meta.to_hash_payload(),
        }


class ToolSnapshotWarning(_FrozenModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    tool_name: str | None = None
    tool_keys: list[str] = Field(default_factory=list)
    occurrence_count: int | None = Field(default=None, ge=1)

    @field_validator("code", "message")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")

        return normalized

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if not value.strip():
            raise ValueError("tool_name must not be empty")

        return value


class NormalizedToolMetadata(_FrozenModel):
    normalization_version: str = Field(min_length=1)
    tool_key: str = Field(min_length=1)
    server_name: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    fields: NormalizedMetadataFields
    tool_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "normalization_version",
        "tool_key",
        "server_name",
        "tool_name",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required text fields must not be empty")

        return value

    def to_hash_payload(self) -> dict[str, Any]:
        return {
            "normalization_version": self.normalization_version,
            "tool_key": self.tool_key,
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "fields": self.fields.to_hash_payload(),
        }


class ToolSnapshot(_FrozenModel):
    snapshot_id: str = Field(pattern=r"^snap_[0-9a-f]{20}$")
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_version: str = Field(min_length=1)
    tools: list[NormalizedToolMetadata] = Field(default_factory=list)
    tool_count: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_scan_id: str | None = None
    warnings: list[ToolSnapshotWarning] = Field(default_factory=list)

    @field_validator("normalization_version", "source_scan_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")

        return normalized

    @field_validator("created_at")
    @classmethod
    def ensure_utc_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.tool_count != len(self.tools):
            raise ValueError("tool_count must match the number of tools")

        if any(
            tool.normalization_version != self.normalization_version
            for tool in self.tools
        ):
            raise ValueError("all tools must use the snapshot normalization version")

        return self


class RegistrationIdentity(_FrozenModel):
    selection_id: str = Field(min_length=1)
    scope: McpScope
    safe_source_label: str = Field(min_length=1)
    context_identity: str = Field(pattern=r"^mcpctx_[0-9a-f]{32}$")

    @field_validator("selection_id", "safe_source_label")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required text fields must not be empty")

        return normalized


class MonitoringIdentity(_FrozenModel):
    monitoring_group_key: str = Field(pattern=r"^mcpgrp_[0-9a-f]{32}$")
    monitoring_target_key: str = Field(pattern=r"^mcptgt_[0-9a-f]{32}$")
    product: McpProduct
    normalized_server_name: str = Field(min_length=1)
    display_server_name: str = Field(min_length=1)
    context_identity: str = Field(pattern=r"^mcpctx_[0-9a-f]{32}$")
    context_label: str = Field(min_length=1)
    registration_identity: RegistrationIdentity

    @field_validator(
        "normalized_server_name",
        "display_server_name",
        "context_label",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required text fields must not be empty")

        return value

    @model_validator(mode="after")
    def validate_registration_context(self) -> Self:
        if self.registration_identity.context_identity != self.context_identity:
            raise ValueError(
                "registration context_identity must match monitoring identity"
            )

        return self


SafeSummaryValue = str | int | bool | None


class ConfigurationFingerprint(_FrozenModel):
    algorithm: Literal["sha256"] = "sha256"
    version: Literal["mcp-config-fingerprint-v1"] = "mcp-config-fingerprint-v1"
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    transport: McpTransport
    safe_summary: dict[str, SafeSummaryValue]
    secret_value_included: Literal[False] = False


class ToolFieldChange(_FrozenModel):
    field_name: str = Field(min_length=1)
    old_presence: FieldPresence
    new_presence: FieldPresence
    old_value: Any | None = None
    new_value: Any | None = None
    old_value_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_value_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("field_name")
    @classmethod
    def strip_field_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field_name must not be empty")

        return normalized

    @model_validator(mode="after")
    def validate_presence_values(self) -> Self:
        if self.old_presence != FieldPresence.VALUE and self.old_value is not None:
            raise ValueError("old_value must be empty unless old_presence is value")
        if self.new_presence != FieldPresence.VALUE and self.new_value is not None:
            raise ValueError("new_value must be empty unless new_presence is value")
        if self.old_presence == FieldPresence.VALUE and self.old_value is None:
            raise ValueError("old_value is required when old_presence is value")
        if self.new_presence == FieldPresence.VALUE and self.new_value is None:
            raise ValueError("new_value is required when new_presence is value")

        return self


class ToolChange(_FrozenModel):
    change_type: ToolChangeType
    tool_key: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    old_tool_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    new_tool_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    field_changes: list[ToolFieldChange] = Field(default_factory=list)

    @field_validator("tool_key", "tool_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required text fields must not be empty")

        return normalized

    @model_validator(mode="after")
    def validate_change_contract(self) -> Self:
        if self.change_type == ToolChangeType.ADDED:
            if self.old_tool_hash is not None or self.new_tool_hash is None:
                raise ValueError("added tool changes require only new_tool_hash")
            if self.field_changes:
                raise ValueError("added tool changes must not include field_changes")
        elif self.change_type == ToolChangeType.REMOVED:
            if self.old_tool_hash is None or self.new_tool_hash is not None:
                raise ValueError("removed tool changes require only old_tool_hash")
            if self.field_changes:
                raise ValueError("removed tool changes must not include field_changes")
        elif self.change_type == ToolChangeType.CHANGED:
            if self.old_tool_hash is None or self.new_tool_hash is None:
                raise ValueError("changed tool changes require both tool hashes")
            if self.old_tool_hash == self.new_tool_hash:
                raise ValueError("changed tool changes require different tool hashes")
            if not self.field_changes:
                raise ValueError("changed tool changes require field_changes")
        elif self.change_type == ToolChangeType.UNCHANGED:
            if self.old_tool_hash is None or self.new_tool_hash is None:
                raise ValueError("unchanged tool changes require both tool hashes")
            if self.old_tool_hash != self.new_tool_hash:
                raise ValueError("unchanged tool changes require matching hashes")
            if self.field_changes:
                raise ValueError("unchanged tool changes must not include field_changes")

        return self


class BaselineComparisonResult(_FrozenModel):
    comparison_status: ComparisonStatus
    matched: bool
    change_categories: list[str] = Field(default_factory=list)
    registration_changed: bool = False
    configuration_changed: bool = False
    approved_snapshot_id: str = Field(pattern=r"^snap_[0-9a-f]{20}$")
    current_snapshot_id: str = Field(pattern=r"^snap_[0-9a-f]{20}$")
    approved_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    added_count: int = Field(ge=0)
    removed_count: int = Field(ge=0)
    changed_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    tool_changes: list[ToolChange] = Field(default_factory=list)
    comparison_error_code: str | None = None

    @field_validator("change_categories")
    @classmethod
    def validate_change_categories(cls, value: list[str]) -> list[str]:
        allowed = ("tool_added", "tool_removed", "tool_changed")
        if any(category not in allowed for category in value):
            raise ValueError("change_categories contains an unsupported category")
        if value != [category for category in allowed if category in value]:
            raise ValueError("change_categories must use the canonical order")
        if len(value) != len(set(value)):
            raise ValueError("change_categories must not contain duplicates")

        return value

    @field_validator("comparison_error_code")
    @classmethod
    def strip_error_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("comparison_error_code must not be empty")

        return normalized

    @model_validator(mode="after")
    def validate_comparison_result(self) -> Self:
        counts = {
            ToolChangeType.ADDED: self.added_count,
            ToolChangeType.REMOVED: self.removed_count,
            ToolChangeType.CHANGED: self.changed_count,
            ToolChangeType.UNCHANGED: self.unchanged_count,
        }
        for change_type, expected_count in counts.items():
            actual_count = sum(
                1
                for change in self.tool_changes
                if change.change_type == change_type
            )
            if actual_count != expected_count:
                raise ValueError("tool change counts must match tool_changes")

        expected_categories = []
        if self.added_count:
            expected_categories.append("tool_added")
        if self.removed_count:
            expected_categories.append("tool_removed")
        if self.changed_count:
            expected_categories.append("tool_changed")
        if self.change_categories != expected_categories:
            raise ValueError("change_categories must match material tool changes")

        material_count = self.added_count + self.removed_count + self.changed_count
        non_tool_changed = self.registration_changed or self.configuration_changed
        if self.comparison_status == ComparisonStatus.MATCHED:
            if not self.matched:
                raise ValueError("matched comparison must set matched=true")
            if material_count != 0:
                raise ValueError("matched comparison cannot include material changes")
            if non_tool_changed:
                raise ValueError("matched comparison cannot include non-tool changes")
            if self.comparison_error_code is not None:
                raise ValueError("matched comparison cannot include an error code")
        elif self.comparison_status == ComparisonStatus.CHANGED:
            if self.matched:
                raise ValueError("changed comparison must set matched=false")
            if material_count == 0 and not non_tool_changed:
                raise ValueError("changed comparison requires material changes")
            if self.comparison_error_code is not None:
                raise ValueError("changed comparison cannot include an error code")
        elif self.comparison_status == ComparisonStatus.COMPARISON_FAILED:
            if self.matched:
                raise ValueError("failed comparison must set matched=false")
            if self.comparison_error_code is None:
                raise ValueError("failed comparison requires an error code")

        return self


CandidateId = str
BaselineId = str
HistoryId = str


class MonitoringCandidate(_FrozenModel):
    schema_version: Literal["mcp-monitoring-storage-v1"] = (
        MONITORING_STORAGE_SCHEMA_VERSION
    )
    document_type: Literal["monitoring_candidate"] = "monitoring_candidate"
    candidate_id: CandidateId = Field(pattern=r"^cand_[A-Za-z0-9_-]{1,128}$")
    monitoring_group_key: str = Field(pattern=r"^mcpgrp_[0-9a-f]{32}$")
    monitoring_target_key: str = Field(pattern=r"^mcptgt_[0-9a-f]{32}$")
    selection_id: str = Field(min_length=1)
    configuration_fingerprint: ConfigurationFingerprint
    snapshot: ToolSnapshot
    comparison_result: BaselineComparisonResult | None = None
    dynamic_scan_status: MonitoringScanStatus
    scan_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    candidate_revision: int = Field(default=1, ge=1)
    supersedes_rejected_candidate_id: CandidateId | None = Field(
        default=None,
        pattern=r"^cand_[A-Za-z0-9_-]{1,128}$",
    )
    state_version_at_creation: int = Field(ge=0)
    secret_value_included: Literal[False] = False

    @field_validator("selection_id", "scan_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")

        return normalized

    @field_validator("created_at")
    @classmethod
    def ensure_created_at_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)

    @model_validator(mode="after")
    def validate_comparison_snapshot_reference(self) -> Self:
        if self.comparison_result is None:
            return self

        if self.comparison_result.current_snapshot_id != self.snapshot.snapshot_id:
            raise ValueError("comparison_result current snapshot id must match candidate snapshot")
        if self.comparison_result.current_snapshot_hash != self.snapshot.snapshot_hash:
            raise ValueError("comparison_result current snapshot hash must match candidate snapshot")

        return self


class ApprovedBaseline(_FrozenModel):
    schema_version: Literal["mcp-monitoring-storage-v1"] = (
        MONITORING_STORAGE_SCHEMA_VERSION
    )
    document_type: Literal["approved_baseline"] = "approved_baseline"
    baseline_id: BaselineId = Field(pattern=r"^base_[A-Za-z0-9_-]{1,128}$")
    monitoring_group_key: str = Field(pattern=r"^mcpgrp_[0-9a-f]{32}$")
    monitoring_target_key: str = Field(pattern=r"^mcptgt_[0-9a-f]{32}$")
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_from_candidate_id: CandidateId | None = Field(
        default=None,
        pattern=r"^cand_[A-Za-z0-9_-]{1,128}$",
    )
    selection_id_at_approval: str = Field(min_length=1)
    configuration_fingerprint: ConfigurationFingerprint
    snapshot: ToolSnapshot
    approved_by: Literal["local_user"] = "local_user"
    secret_value_included: Literal[False] = False

    @field_validator("selection_id_at_approval")
    @classmethod
    def strip_selection_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("selection_id_at_approval must not be empty")

        return normalized

    @field_validator("approved_at")
    @classmethod
    def ensure_approved_at_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class BaselineHistoryRecord(_FrozenModel):
    schema_version: Literal["mcp-monitoring-storage-v1"] = (
        MONITORING_STORAGE_SCHEMA_VERSION
    )
    document_type: Literal["baseline_history"] = "baseline_history"
    history_id: HistoryId = Field(pattern=r"^hist_[A-Za-z0-9_-]{1,128}$")
    monitoring_group_key: str = Field(pattern=r"^mcpgrp_[0-9a-f]{32}$")
    monitoring_target_key: str = Field(pattern=r"^mcptgt_[0-9a-f]{32}$")
    event_type: BaselineHistoryEventType
    candidate_id: CandidateId | None = Field(
        default=None,
        pattern=r"^cand_[A-Za-z0-9_-]{1,128}$",
    )
    baseline_id: BaselineId | None = Field(
        default=None,
        pattern=r"^base_[A-Za-z0-9_-]{1,128}$",
    )
    previous_approved_id: BaselineId | None = Field(
        default=None,
        pattern=r"^base_[A-Za-z0-9_-]{1,128}$",
    )
    new_approved_id: BaselineId | None = Field(
        default=None,
        pattern=r"^base_[A-Za-z0-9_-]{1,128}$",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    safe_reason_code: str | None = None

    @field_validator("safe_reason_code")
    @classmethod
    def strip_reason_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("safe_reason_code must not be empty")

        return normalized

    @field_validator("created_at")
    @classmethod
    def ensure_history_created_at_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class MonitoringFindingSummary(_FrozenModel):
    """Persisted Finding severity counts for the latest scan result."""

    critical: int = Field(default=0, ge=0)
    high: int = Field(default=0, ge=0)
    medium: int = Field(default=0, ge=0)
    low: int = Field(default=0, ge=0)
    info: int = Field(default=0, ge=0)


class MonitoredServerState(_FrozenModel):
    schema_version: Literal["mcp-monitoring-storage-v1"] = (
        MONITORING_STORAGE_SCHEMA_VERSION
    )
    document_type: Literal["monitored_server_state"] = "monitored_server_state"
    monitoring_group_key: str = Field(pattern=r"^mcpgrp_[0-9a-f]{32}$")
    monitoring_target_key: str = Field(pattern=r"^mcptgt_[0-9a-f]{32}$")
    identity: MonitoringIdentity
    state_version: int = Field(default=0, ge=0)
    current_approved_id: BaselineId | None = Field(
        default=None,
        pattern=r"^base_[A-Za-z0-9_-]{1,128}$",
    )
    pending_candidate_ids: list[CandidateId] = Field(default_factory=list)
    rejected_candidate_ids: list[CandidateId] = Field(default_factory=list)
    superseded_baseline_ids: list[BaselineId] = Field(default_factory=list)
    history_ids: list[HistoryId] = Field(default_factory=list)
    last_scan_status: MonitoringScanStatus = MonitoringScanStatus.NOT_SCANNED
    last_scan_at: datetime | None = None
    last_finding_summary: MonitoringFindingSummary | None = None
    last_seen_selection_id: str | None = None
    baseline_lifecycle: BaselineLifecycleStatus = BaselineLifecycleStatus.NONE
    comparison_status: ComparisonStatus = ComparisonStatus.NOT_COMPARED
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    last_comparison: BaselineComparisonResult | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    secret_value_included: Literal[False] = False

    @field_validator(
        "pending_candidate_ids",
        "rejected_candidate_ids",
        mode="before",
    )
    @classmethod
    def validate_candidate_ids(cls, value: list[str]) -> list[str]:
        return _validate_id_list(value, "candidate")

    @field_validator("superseded_baseline_ids", mode="before")
    @classmethod
    def validate_baseline_ids(cls, value: list[str]) -> list[str]:
        return _validate_id_list(value, "baseline")

    @field_validator("history_ids", mode="before")
    @classmethod
    def validate_history_ids(cls, value: list[str]) -> list[str]:
        return _validate_id_list(value, "history")

    @field_validator("last_scan_at")
    @classmethod
    def ensure_last_scan_at_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None

        return _ensure_utc(value)

    @field_validator("updated_at")
    @classmethod
    def ensure_updated_at_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)

    @field_validator("last_seen_selection_id")
    @classmethod
    def strip_seen_selection_id(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("last_seen_selection_id must not be empty")

        return normalized

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.identity.monitoring_group_key != self.monitoring_group_key:
            raise ValueError("identity monitoring_group_key must match state")
        if self.identity.monitoring_target_key != self.monitoring_target_key:
            raise ValueError("identity monitoring_target_key must match state")
        if (
            self.current_approved_id is not None
            and self.current_approved_id in self.superseded_baseline_ids
        ):
            raise ValueError("current approved baseline cannot be superseded")
        if set(self.pending_candidate_ids) & set(self.rejected_candidate_ids):
            raise ValueError("candidate cannot be both pending and rejected")

        return self


class MonitoringTargetIndexEntry(_FrozenModel):
    monitoring_target_key: str = Field(pattern=r"^mcptgt_[0-9a-f]{32}$")
    context_label: str = Field(min_length=1)
    last_scan_status: MonitoringScanStatus = MonitoringScanStatus.NOT_SCANNED
    baseline_lifecycle: BaselineLifecycleStatus = BaselineLifecycleStatus.NONE
    comparison_status: ComparisonStatus = ComparisonStatus.NOT_COMPARED
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    last_seen_at: datetime | None = None

    @field_validator("context_label")
    @classmethod
    def strip_context_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("context_label must not be empty")

        return normalized

    @field_validator("last_seen_at")
    @classmethod
    def ensure_last_seen_at_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None

        return _ensure_utc(value)


class MonitoringGroupIndex(_FrozenModel):
    # Non-authoritative cache. Target state documents are the source of truth.
    schema_version: Literal["mcp-monitoring-storage-v1"] = (
        MONITORING_STORAGE_SCHEMA_VERSION
    )
    document_type: Literal["monitoring_group_index"] = "monitoring_group_index"
    monitoring_group_key: str = Field(pattern=r"^mcpgrp_[0-9a-f]{32}$")
    product: McpProduct
    display_server_name: str = Field(min_length=1)
    targets: list[MonitoringTargetIndexEntry] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("display_server_name")
    @classmethod
    def strip_display_server_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_server_name must not be empty")

        return normalized

    @field_validator("updated_at")
    @classmethod
    def ensure_group_index_updated_at_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class MonitoringRootIndex(_FrozenModel):
    # Non-authoritative cache. It can be rebuilt from group/target state.
    schema_version: Literal["mcp-monitoring-storage-v1"] = (
        MONITORING_STORAGE_SCHEMA_VERSION
    )
    document_type: Literal["monitoring_root_index"] = "monitoring_root_index"
    groups: list[MonitoringGroupIndex] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("updated_at")
    @classmethod
    def ensure_root_index_updated_at_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class OrphanDocument(_FrozenModel):
    document_type: Literal[
        "monitoring_candidate",
        "approved_baseline",
        "baseline_history",
    ]
    document_id: str = Field(min_length=1)
    monitoring_target_key: str = Field(pattern=r"^mcptgt_[0-9a-f]{32}$")
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("document_id")
    @classmethod
    def strip_document_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("document_id must not be empty")

        return normalized

    @field_validator("discovered_at")
    @classmethod
    def ensure_orphan_discovered_at_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class RepositoryCommitResult(_FrozenModel):
    committed_state: MonitoredServerState
    document_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _validate_id_list(value: list[str], label: str) -> list[str]:
    if len(value) != len(set(value)):
        raise ValueError(f"{label} IDs must not contain duplicates")

    return value
