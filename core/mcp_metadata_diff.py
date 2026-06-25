from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.mcp_metadata_normalizer import canonical_json_bytes, calculate_sha256
from core.mcp_monitoring_models import (
    BaselineComparisonResult,
    ComparisonStatus,
    FieldPresence,
    NormalizedFieldValue,
    NormalizedToolMetadata,
    ToolChange,
    ToolChangeType,
    ToolFieldChange,
    ToolSnapshot,
)


CHANGE_CATEGORY_ORDER = ("tool_added", "tool_removed", "tool_changed")
FIELD_ORDER = (
    "server_name",
    "tool_name",
    "title",
    "description",
    "input_schema",
    "output_schema",
    "annotations",
    "meta",
)


class MetadataDiffError(ValueError):
    """Raised when MCP metadata snapshots cannot be compared safely."""


@dataclass(frozen=True)
class _FieldPayload:
    presence: FieldPresence
    value: Any | None
    hash_payload: dict[str, Any]


def compare_tool_snapshots(
    approved: ToolSnapshot,
    current: ToolSnapshot,
) -> BaselineComparisonResult:
    """Compare approved and current MCP ToolSnapshot instances."""
    _validate_snapshot_type(approved, "approved")
    _validate_snapshot_type(current, "current")

    if approved.normalization_version != current.normalization_version:
        return _failed_result(
            approved=approved,
            current=current,
            error_code="normalization_version_mismatch",
        )

    approved_tools = _index_tools_by_key(approved)
    current_tools = _index_tools_by_key(current)
    if approved_tools is None or current_tools is None:
        return _failed_result(
            approved=approved,
            current=current,
            error_code="duplicate_tool_key",
        )

    tool_changes: list[ToolChange] = []
    for tool_key in sorted(set(approved_tools) | set(current_tools)):
        old_tool = approved_tools.get(tool_key)
        new_tool = current_tools.get(tool_key)

        if old_tool is None and new_tool is not None:
            tool_changes.append(
                ToolChange(
                    change_type=ToolChangeType.ADDED,
                    tool_key=tool_key,
                    tool_name=new_tool.tool_name,
                    new_tool_hash=new_tool.tool_hash,
                )
            )
            continue

        if old_tool is not None and new_tool is None:
            tool_changes.append(
                ToolChange(
                    change_type=ToolChangeType.REMOVED,
                    tool_key=tool_key,
                    tool_name=old_tool.tool_name,
                    old_tool_hash=old_tool.tool_hash,
                )
            )
            continue

        if old_tool is None or new_tool is None:
            raise MetadataDiffError("tool snapshot comparison failed")

        compared_change = _compare_tool(tool_key, old_tool, new_tool)
        if compared_change is None:
            return _failed_result(
                approved=approved,
                current=current,
                error_code="tool_hash_mismatch_without_field_change",
            )
        tool_changes.append(compared_change)

    counts = _count_changes(tool_changes)
    comparison_status = (
        ComparisonStatus.MATCHED
        if counts[ToolChangeType.ADDED] == 0
        and counts[ToolChangeType.REMOVED] == 0
        and counts[ToolChangeType.CHANGED] == 0
        else ComparisonStatus.CHANGED
    )

    return BaselineComparisonResult(
        comparison_status=comparison_status,
        matched=comparison_status == ComparisonStatus.MATCHED,
        change_categories=_change_categories(counts),
        approved_snapshot_id=approved.snapshot_id,
        current_snapshot_id=current.snapshot_id,
        approved_snapshot_hash=approved.snapshot_hash,
        current_snapshot_hash=current.snapshot_hash,
        added_count=counts[ToolChangeType.ADDED],
        removed_count=counts[ToolChangeType.REMOVED],
        changed_count=counts[ToolChangeType.CHANGED],
        unchanged_count=counts[ToolChangeType.UNCHANGED],
        tool_changes=tool_changes,
    )


def _validate_snapshot_type(snapshot: object, label: str) -> None:
    if not isinstance(snapshot, ToolSnapshot):
        raise MetadataDiffError(f"{label} snapshot must be a ToolSnapshot instance")


def _index_tools_by_key(
    snapshot: ToolSnapshot,
) -> dict[str, NormalizedToolMetadata] | None:
    indexed: dict[str, NormalizedToolMetadata] = {}
    for tool in snapshot.tools:
        if tool.tool_key in indexed:
            return None
        indexed[tool.tool_key] = tool

    return indexed


def _compare_tool(
    tool_key: str,
    old_tool: NormalizedToolMetadata,
    new_tool: NormalizedToolMetadata,
) -> ToolChange | None:
    if old_tool.tool_hash == new_tool.tool_hash:
        return ToolChange(
            change_type=ToolChangeType.UNCHANGED,
            tool_key=tool_key,
            tool_name=new_tool.tool_name,
            old_tool_hash=old_tool.tool_hash,
            new_tool_hash=new_tool.tool_hash,
        )

    field_changes: list[ToolFieldChange] = []
    for field_name in FIELD_ORDER:
        change = _compare_field(
            field_name=field_name,
            old_payload=_field_payload(old_tool, field_name),
            new_payload=_field_payload(new_tool, field_name),
        )
        if change is not None:
            field_changes.append(change)
    if not field_changes:
        return None

    return ToolChange(
        change_type=ToolChangeType.CHANGED,
        tool_key=tool_key,
        tool_name=new_tool.tool_name,
        old_tool_hash=old_tool.tool_hash,
        new_tool_hash=new_tool.tool_hash,
        field_changes=field_changes,
    )


def _compare_field(
    *,
    field_name: str,
    old_payload: _FieldPayload,
    new_payload: _FieldPayload,
) -> ToolFieldChange | None:
    old_hash = _field_value_hash(old_payload.hash_payload)
    new_hash = _field_value_hash(new_payload.hash_payload)
    if old_hash == new_hash:
        return None

    return ToolFieldChange(
        field_name=field_name,
        old_presence=old_payload.presence,
        new_presence=new_payload.presence,
        old_value=old_payload.value,
        new_value=new_payload.value,
        old_value_hash=old_hash,
        new_value_hash=new_hash,
    )


def _field_payload(
    tool: NormalizedToolMetadata,
    field_name: str,
) -> _FieldPayload:
    if field_name == "server_name":
        return _value_payload(tool.server_name)
    if field_name == "tool_name":
        return _value_payload(tool.tool_name)

    field_value = getattr(tool.fields, field_name)
    if not isinstance(field_value, NormalizedFieldValue):
        raise MetadataDiffError("tool snapshot comparison failed")

    return _normalized_field_payload(field_value)


def _value_payload(value: str) -> _FieldPayload:
    payload = {
        "presence": FieldPresence.VALUE.value,
        "value": value,
    }
    return _FieldPayload(
        presence=FieldPresence.VALUE,
        value=value,
        hash_payload=payload,
    )


def _normalized_field_payload(field_value: NormalizedFieldValue) -> _FieldPayload:
    payload = field_value.to_hash_payload()
    value = (
        field_value.value
        if field_value.presence == FieldPresence.VALUE
        else None
    )
    return _FieldPayload(
        presence=field_value.presence,
        value=value,
        hash_payload=payload,
    )


def _field_value_hash(payload: dict[str, Any]) -> str:
    return calculate_sha256(canonical_json_bytes(payload))


def _count_changes(
    tool_changes: list[ToolChange],
) -> dict[ToolChangeType, int]:
    return {
        change_type: sum(
            1
            for change in tool_changes
            if change.change_type == change_type
        )
        for change_type in ToolChangeType
    }


def _change_categories(
    counts: dict[ToolChangeType, int],
) -> list[str]:
    categories: list[str] = []
    if counts[ToolChangeType.ADDED]:
        categories.append("tool_added")
    if counts[ToolChangeType.REMOVED]:
        categories.append("tool_removed")
    if counts[ToolChangeType.CHANGED]:
        categories.append("tool_changed")

    return categories


def _failed_result(
    *,
    approved: ToolSnapshot,
    current: ToolSnapshot,
    error_code: str,
) -> BaselineComparisonResult:
    return BaselineComparisonResult(
        comparison_status=ComparisonStatus.COMPARISON_FAILED,
        matched=False,
        change_categories=[],
        approved_snapshot_id=approved.snapshot_id,
        current_snapshot_id=current.snapshot_id,
        approved_snapshot_hash=approved.snapshot_hash,
        current_snapshot_hash=current.snapshot_hash,
        added_count=0,
        removed_count=0,
        changed_count=0,
        unchanged_count=0,
        tool_changes=[],
        comparison_error_code=error_code,
    )
