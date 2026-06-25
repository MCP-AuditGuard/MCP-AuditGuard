from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, ValidationError

from core.mcp_monitoring_models import (
    BaselineComparisonResult,
    BaselineHistoryEventType,
    BaselineLifecycleStatus,
    ComparisonStatus,
    FieldPresence,
    MonitoringScanStatus,
    NormalizedFieldValue,
    NormalizedMetadataFields,
    NormalizedToolMetadata,
    ToolSnapshot,
    ToolSnapshotWarning,
    VerificationStatus,
)


class StatusEnvelope(BaseModel):
    scan_status: MonitoringScanStatus
    lifecycle_status: BaselineLifecycleStatus
    comparison_status: ComparisonStatus
    verification_status: VerificationStatus


def make_fields() -> NormalizedMetadataFields:
    missing = NormalizedFieldValue(presence=FieldPresence.MISSING)
    return NormalizedMetadataFields(
        title=NormalizedFieldValue(
            presence=FieldPresence.VALUE,
            value="Search",
        ),
        description=missing,
        input_schema=missing,
        output_schema=missing,
        annotations=missing,
        meta=missing,
    )


def make_normalized_tool() -> NormalizedToolMetadata:
    return NormalizedToolMetadata(
        normalization_version="mcp-tool-metadata-v1",
        tool_key="search",
        server_name="docs",
        tool_name="search",
        fields=make_fields(),
        tool_hash="a" * 64,
    )


def test_monitoring_status_enum_values_are_stable() -> None:
    assert {status.value for status in MonitoringScanStatus} == {
        "not_scanned",
        "scanning",
        "success",
        "partial_success",
        "failed",
        "timed_out",
    }
    assert {status.value for status in BaselineLifecycleStatus} == {
        "none",
        "candidate_pending",
        "approved",
        "rejected",
    }
    assert {status.value for status in ComparisonStatus} == {
        "not_compared",
        "matched",
        "changed",
        "comparison_failed",
    }
    assert {status.value for status in VerificationStatus} == {
        "unverified",
        "verified",
        "review_required",
        "unavailable",
    }
    assert {event.value for event in BaselineHistoryEventType} == {
        "candidate_created",
        "candidate_approved",
        "candidate_rejected",
        "baseline_superseded",
        "baseline_revoked",
    }


def test_monitoring_statuses_serialize_and_deserialize() -> None:
    envelope = StatusEnvelope(
        scan_status="partial_success",
        lifecycle_status="candidate_pending",
        comparison_status="changed",
        verification_status="review_required",
    )

    serialized = envelope.model_dump(mode="json")
    restored = StatusEnvelope.model_validate(serialized)

    assert serialized == {
        "scan_status": "partial_success",
        "lifecycle_status": "candidate_pending",
        "comparison_status": "changed",
        "verification_status": "review_required",
    }
    assert restored == envelope


def test_monitoring_statuses_reject_unknown_values() -> None:
    with pytest.raises(ValidationError):
        StatusEnvelope(
            scan_status="cancelled",
            lifecycle_status="candidate_pending",
            comparison_status="changed",
            verification_status="review_required",
        )


def test_baseline_comparison_allows_registration_or_configuration_changes() -> None:
    changed = BaselineComparisonResult(
        comparison_status=ComparisonStatus.CHANGED,
        matched=False,
        change_categories=[],
        registration_changed=True,
        configuration_changed=True,
        approved_snapshot_id="snap_" + "1" * 20,
        current_snapshot_id="snap_" + "2" * 20,
        approved_snapshot_hash="1" * 64,
        current_snapshot_hash="2" * 64,
        added_count=0,
        removed_count=0,
        changed_count=0,
        unchanged_count=0,
        tool_changes=[],
    )
    failed = changed.model_copy(
        update={
            "comparison_status": ComparisonStatus.COMPARISON_FAILED,
            "comparison_error_code": "normalization_version_mismatch",
        }
    )

    assert changed.change_categories == []
    assert changed.registration_changed is True
    assert changed.configuration_changed is True
    assert BaselineComparisonResult.model_validate(
        failed.model_dump(mode="python")
    ).registration_changed is True


def test_matched_comparison_rejects_registration_or_configuration_changes() -> None:
    with pytest.raises(ValidationError, match="non-tool changes"):
        BaselineComparisonResult(
            comparison_status=ComparisonStatus.MATCHED,
            matched=True,
            change_categories=[],
            registration_changed=True,
            approved_snapshot_id="snap_" + "1" * 20,
            current_snapshot_id="snap_" + "1" * 20,
            approved_snapshot_hash="1" * 64,
            current_snapshot_hash="1" * 64,
            added_count=0,
            removed_count=0,
            changed_count=0,
            unchanged_count=0,
            tool_changes=[],
        )


def test_normalized_field_value_presence_contract() -> None:
    assert NormalizedFieldValue(
        presence=FieldPresence.MISSING,
    ).to_hash_payload() == {"presence": "missing"}
    assert NormalizedFieldValue(
        presence=FieldPresence.NULL,
    ).to_hash_payload() == {
        "presence": "null",
        "value": None,
    }
    assert NormalizedFieldValue(
        presence=FieldPresence.VALUE,
        value={},
    ).to_hash_payload() == {
        "presence": "value",
        "value": {},
    }

    with pytest.raises(ValidationError):
        NormalizedFieldValue(presence=FieldPresence.MISSING, value="x")

    with pytest.raises(ValidationError):
        NormalizedFieldValue(presence=FieldPresence.VALUE, value=None)

    with pytest.raises(ValidationError):
        NormalizedFieldValue.model_validate({"presence": "unknown"})


def test_normalized_tool_metadata_is_json_serializable() -> None:
    tool = make_normalized_tool()
    serialized = tool.model_dump(mode="json")
    restored = NormalizedToolMetadata.model_validate(serialized)

    assert serialized["normalization_version"] == "mcp-tool-metadata-v1"
    assert serialized["tool_key"] == "search"
    assert serialized["fields"]["title"]["presence"] == "value"
    assert restored == tool


def test_tool_snapshot_validates_counts_versions_and_utc_datetime() -> None:
    tool = make_normalized_tool()
    naive_time = datetime(2026, 6, 24, 12, 0, 0)
    snapshot = ToolSnapshot(
        snapshot_id="snap_" + "1" * 20,
        snapshot_hash="1" * 64,
        normalization_version="mcp-tool-metadata-v1",
        tools=[tool],
        tool_count=1,
        created_at=naive_time,
        warnings=[
            ToolSnapshotWarning(
                code="duplicate_tool_name",
                message="Duplicate MCP tool name.",
                tool_name="search",
                tool_keys=["search#duplicate-1"],
                occurrence_count=2,
            )
        ],
    )

    assert snapshot.created_at.tzinfo is timezone.utc
    assert snapshot.model_dump(mode="json")["created_at"].endswith("Z")

    with pytest.raises(ValidationError, match="tool_count"):
        ToolSnapshot(
            snapshot_id="snap_" + "1" * 20,
            snapshot_hash="1" * 64,
            normalization_version="mcp-tool-metadata-v1",
            tools=[tool],
            tool_count=0,
        )

    with pytest.raises(ValidationError, match="normalization version"):
        ToolSnapshot(
            snapshot_id="snap_" + "1" * 20,
            snapshot_hash="1" * 64,
            normalization_version="other-version",
            tools=[tool],
            tool_count=1,
        )
