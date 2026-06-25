from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.mcp_metadata_diff import (
    MetadataDiffError,
    compare_tool_snapshots,
)
from core.mcp_metadata_normalizer import (
    NORMALIZATION_VERSION,
    calculate_sha256,
    canonical_json_bytes,
    create_tool_snapshot,
    normalize_tool_metadata,
)
from core.mcp_monitoring_models import (
    BaselineComparisonResult,
    ComparisonStatus,
    FieldPresence,
    NormalizedFieldValue,
    NormalizedMetadataFields,
    NormalizedToolMetadata,
    ToolChange,
    ToolChangeType,
    ToolFieldChange,
    ToolSnapshot,
)
from core.models import ToolMetadata


FIXED_TIME = datetime(2026, 6, 24, tzinfo=timezone.utc)


class _Missing:
    pass


_MISSING = _Missing()


def make_tool(
    *,
    server_name: str = "docs",
    tool_name: str = "search",
    title: object = "Search",
    description: object = "Search project documents.",
    input_schema: object = None,
    output_schema: object = None,
    annotations: object = None,
    meta: object = None,
    raw_extra: dict[str, object] | None = None,
) -> ToolMetadata:
    raw_tool: dict[str, object] = {"name": tool_name}
    if title is not _MISSING:
        raw_tool["title"] = title
    if description is not _MISSING:
        raw_tool["description"] = description
    if input_schema is not _MISSING:
        raw_tool["inputSchema"] = (
            input_schema
            if input_schema is not None
            else {"type": "object", "properties": {"query": {"type": "string"}}}
        )
    if output_schema is not _MISSING:
        raw_tool["outputSchema"] = (
            output_schema if output_schema is not None else {"type": "object"}
        )
    if annotations is not _MISSING:
        raw_tool["annotations"] = (
            annotations if annotations is not None else {"readOnlyHint": True}
        )
    if meta is not _MISSING:
        raw_tool["_meta"] = meta if meta is not None else {"version": "1.0"}
    if raw_extra:
        raw_tool.update(raw_extra)

    return ToolMetadata.from_mcp_tool(
        raw_tool=raw_tool,
        server_name=server_name,
        source="mcp:test",
        collected_at=FIXED_TIME,
    )


def construct_tool_with_raw(raw: dict[str, object]) -> ToolMetadata:
    return ToolMetadata.model_construct(
        server_name="docs",
        tool_name=str(raw.get("name", "search")),
        title=None,
        description=None,
        input_schema=None,
        output_schema=None,
        annotations=None,
        meta=None,
        raw=raw,
        source=None,
        metadata_hash="0" * 64,
        collected_at=FIXED_TIME,
    )


def construct_tool_with_input_schema(
    value: object = _MISSING,
) -> ToolMetadata:
    raw: dict[str, object] = {
        "name": "search",
        "title": "Search",
        "description": "Search project documents.",
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True},
        "_meta": {"version": "1.0"},
    }
    if value is not _MISSING:
        raw["inputSchema"] = value

    return construct_tool_with_raw(raw)


def snapshot_of(*tools: ToolMetadata) -> ToolSnapshot:
    return create_tool_snapshot(
        list(tools),
        created_at=FIXED_TIME,
        source_scan_id="scan-test",
    )


def snapshot_from_normalized(
    tools: list[NormalizedToolMetadata],
    *,
    normalization_version: str = NORMALIZATION_VERSION,
) -> ToolSnapshot:
    snapshot_hash = calculate_sha256(
        canonical_json_bytes(
            {
                "version": normalization_version,
                "tools": [
                    {
                        "tool_key": tool.tool_key,
                        "tool_hash": tool.tool_hash,
                    }
                    for tool in tools
                ],
            }
        )
    )
    return ToolSnapshot(
        snapshot_id=f"snap_{snapshot_hash[:20]}",
        snapshot_hash=snapshot_hash,
        normalization_version=normalization_version,
        tools=tools,
        tool_count=len(tools),
        created_at=FIXED_TIME,
    )


def missing_field() -> NormalizedFieldValue:
    return NormalizedFieldValue(presence=FieldPresence.MISSING)


def make_fields(
    *,
    title: NormalizedFieldValue | None = None,
    description: NormalizedFieldValue | None = None,
    input_schema: NormalizedFieldValue | None = None,
    output_schema: NormalizedFieldValue | None = None,
    annotations: NormalizedFieldValue | None = None,
    meta: NormalizedFieldValue | None = None,
) -> NormalizedMetadataFields:
    return NormalizedMetadataFields(
        title=title or missing_field(),
        description=description or missing_field(),
        input_schema=input_schema or missing_field(),
        output_schema=output_schema or missing_field(),
        annotations=annotations or missing_field(),
        meta=meta or missing_field(),
    )


def normalized_tool(
    *,
    tool_key: str = "search",
    server_name: str = "docs",
    tool_name: str = "search",
    fields: NormalizedMetadataFields | None = None,
    normalization_version: str = NORMALIZATION_VERSION,
) -> NormalizedToolMetadata:
    fields = fields or make_fields(
        title=NormalizedFieldValue(
            presence=FieldPresence.VALUE,
            value="Search",
        )
    )
    payload = {
        "normalization_version": normalization_version,
        "tool_key": tool_key,
        "server_name": server_name,
        "tool_name": tool_name,
        "fields": fields.to_hash_payload(),
    }
    return NormalizedToolMetadata(
        normalization_version=normalization_version,
        tool_key=tool_key,
        server_name=server_name,
        tool_name=tool_name,
        fields=fields,
        tool_hash=calculate_sha256(canonical_json_bytes(payload)),
    )


def change_by_key(
    result: BaselineComparisonResult,
    tool_key: str,
) -> ToolChange:
    return next(change for change in result.tool_changes if change.tool_key == tool_key)


def field_change_names(change: ToolChange) -> list[str]:
    return [field_change.field_name for field_change in change.field_changes]


def test_identical_snapshot_is_matched_with_unchanged_tools() -> None:
    snapshot = snapshot_of(
        make_tool(tool_name="search"),
        make_tool(tool_name="read"),
    )

    result = compare_tool_snapshots(snapshot, snapshot)

    assert result.comparison_status == ComparisonStatus.MATCHED
    assert result.matched is True
    assert result.added_count == 0
    assert result.removed_count == 0
    assert result.changed_count == 0
    assert result.unchanged_count == snapshot.tool_count
    assert all(
        change.change_type == ToolChangeType.UNCHANGED
        for change in result.tool_changes
    )


def test_empty_snapshots_are_matched() -> None:
    approved = snapshot_of()
    current = snapshot_of()

    result = compare_tool_snapshots(approved, current)

    assert result.comparison_status == ComparisonStatus.MATCHED
    assert result.matched is True
    assert result.added_count == 0
    assert result.removed_count == 0
    assert result.changed_count == 0
    assert result.unchanged_count == 0
    assert result.tool_changes == []


def test_input_tool_order_does_not_affect_comparison() -> None:
    search = make_tool(tool_name="search")
    read = make_tool(tool_name="read")

    approved = snapshot_of(search, read)
    current = snapshot_of(read, search)

    result = compare_tool_snapshots(approved, current)

    assert result.comparison_status == ComparisonStatus.MATCHED
    assert result.unchanged_count == 2


def test_tool_added_is_reported_with_category() -> None:
    approved = snapshot_of(make_tool(tool_name="search"))
    current = snapshot_of(
        make_tool(tool_name="search"),
        make_tool(tool_name="read"),
    )

    result = compare_tool_snapshots(approved, current)

    assert result.comparison_status == ComparisonStatus.CHANGED
    assert result.change_categories == ["tool_added"]
    assert result.added_count == 1
    assert change_by_key(result, "read").change_type == ToolChangeType.ADDED


def test_tool_removed_is_reported_with_category() -> None:
    approved = snapshot_of(
        make_tool(tool_name="search"),
        make_tool(tool_name="read"),
    )
    current = snapshot_of(make_tool(tool_name="search"))

    result = compare_tool_snapshots(approved, current)

    assert result.comparison_status == ComparisonStatus.CHANGED
    assert result.change_categories == ["tool_removed"]
    assert result.removed_count == 1
    assert change_by_key(result, "read").change_type == ToolChangeType.REMOVED


def test_tool_changed_reports_field_changes_and_category() -> None:
    approved = snapshot_of(make_tool(description="Old description."))
    current = snapshot_of(make_tool(description="New description."))

    result = compare_tool_snapshots(approved, current)
    change = change_by_key(result, "search")

    assert result.comparison_status == ComparisonStatus.CHANGED
    assert result.change_categories == ["tool_changed"]
    assert result.changed_count == 1
    assert change.change_type == ToolChangeType.CHANGED
    assert field_change_names(change) == ["description"]


@pytest.mark.parametrize(
    ("field_name", "approved_tool", "current_tool"),
    [
        (
            "server_name",
            make_tool(server_name="docs"),
            make_tool(server_name="other-docs"),
        ),
        (
            "tool_name",
            normalized_tool(tool_key="stable-key", tool_name="search"),
            normalized_tool(tool_key="stable-key", tool_name="read"),
        ),
        (
            "title",
            make_tool(title="Search"),
            make_tool(title="Find"),
        ),
        (
            "description",
            make_tool(description="Old"),
            make_tool(description="New"),
        ),
        (
            "input_schema",
            make_tool(input_schema={"type": "object"}),
            make_tool(input_schema={"type": "object", "required": ["q"]}),
        ),
        (
            "output_schema",
            make_tool(output_schema={"type": "object"}),
            make_tool(output_schema={"type": "array"}),
        ),
        (
            "annotations",
            make_tool(annotations={"readOnlyHint": True}),
            make_tool(annotations={"readOnlyHint": False}),
        ),
        (
            "meta",
            make_tool(meta={"version": "1.0"}),
            make_tool(meta={"version": "2.0"}),
        ),
    ],
)
def test_each_field_single_change_reports_only_that_field(
    field_name: str,
    approved_tool: ToolMetadata | NormalizedToolMetadata,
    current_tool: ToolMetadata | NormalizedToolMetadata,
) -> None:
    if isinstance(approved_tool, NormalizedToolMetadata):
        approved = snapshot_from_normalized([approved_tool])
        current = snapshot_from_normalized([current_tool])  # type: ignore[list-item]
    else:
        approved = snapshot_of(approved_tool)
        current = snapshot_of(current_tool)  # type: ignore[arg-type]

    result = compare_tool_snapshots(approved, current)
    change = result.tool_changes[0]

    assert change.change_type == ToolChangeType.CHANGED
    assert field_change_names(change) == [field_name]


@pytest.mark.parametrize(
    ("approved_tool", "current_tool", "old_presence", "new_presence"),
    [
        (
            construct_tool_with_input_schema(_MISSING),
            construct_tool_with_input_schema(None),
            FieldPresence.MISSING,
            FieldPresence.NULL,
        ),
        (
            construct_tool_with_input_schema(None),
            make_tool(input_schema={"type": "object"}),
            FieldPresence.NULL,
            FieldPresence.VALUE,
        ),
        (
            make_tool(input_schema={"type": "object"}),
            make_tool(input_schema=_MISSING),
            FieldPresence.VALUE,
            FieldPresence.MISSING,
        ),
        (
            construct_tool_with_input_schema(None),
            construct_tool_with_input_schema({}),
            FieldPresence.NULL,
            FieldPresence.VALUE,
        ),
        (
            construct_tool_with_input_schema({}),
            construct_tool_with_input_schema([]),
            FieldPresence.VALUE,
            FieldPresence.VALUE,
        ),
        (
            construct_tool_with_input_schema([]),
            construct_tool_with_input_schema(""),
            FieldPresence.VALUE,
            FieldPresence.VALUE,
        ),
    ],
)
def test_presence_and_empty_value_changes_are_reported(
    approved_tool: ToolMetadata,
    current_tool: ToolMetadata,
    old_presence: FieldPresence,
    new_presence: FieldPresence,
) -> None:
    result = compare_tool_snapshots(
        snapshot_of(approved_tool),
        snapshot_of(current_tool),
    )
    change = result.tool_changes[0].field_changes[0]

    assert change.field_name == "input_schema"
    assert change.old_presence == old_presence
    assert change.new_presence == new_presence
    assert len(change.old_value_hash) == 64
    assert len(change.new_value_hash) == 64


def test_canonical_json_object_order_is_ignored_but_array_order_is_not() -> None:
    object_first = snapshot_of(
        make_tool(input_schema={"b": 2, "a": {"d": 4, "c": 3}})
    )
    object_second = snapshot_of(
        make_tool(input_schema={"a": {"c": 3, "d": 4}, "b": 2})
    )
    array_first = snapshot_of(make_tool(input_schema={"enum": ["a", "b"]}))
    array_second = snapshot_of(make_tool(input_schema={"enum": ["b", "a"]}))

    assert compare_tool_snapshots(
        object_first,
        object_second,
    ).comparison_status == ComparisonStatus.MATCHED

    array_result = compare_tool_snapshots(array_first, array_second)
    assert array_result.comparison_status == ComparisonStatus.CHANGED
    assert field_change_names(array_result.tool_changes[0]) == ["input_schema"]


def test_complex_comparison_counts_categories_and_order_are_deterministic() -> None:
    approved = snapshot_of(
        make_tool(tool_name="same"),
        make_tool(tool_name="removed"),
        make_tool(tool_name="changed", description="Old"),
    )
    current = snapshot_of(
        make_tool(tool_name="same"),
        make_tool(tool_name="added"),
        make_tool(tool_name="changed", description="New"),
    )

    result = compare_tool_snapshots(approved, current)

    assert result.added_count == 1
    assert result.removed_count == 1
    assert result.changed_count == 1
    assert result.unchanged_count == 1
    assert result.change_categories == [
        "tool_added",
        "tool_removed",
        "tool_changed",
    ]
    assert [change.tool_key for change in result.tool_changes] == [
        "added",
        "changed",
        "removed",
        "same",
    ]


def test_normalization_version_mismatch_returns_comparison_failed() -> None:
    approved = snapshot_of(make_tool())
    current = snapshot_of(make_tool()).model_copy(
        update={"normalization_version": "other-version"}
    )

    result = compare_tool_snapshots(approved, current)

    assert result.comparison_status == ComparisonStatus.COMPARISON_FAILED
    assert result.matched is False
    assert result.comparison_error_code == "normalization_version_mismatch"
    assert result.tool_changes == []


def test_duplicate_tool_key_returns_comparison_failed_without_overwrite() -> None:
    tool = normalize_tool_metadata(make_tool())
    duplicated = snapshot_from_normalized([tool, tool])
    current = snapshot_of(make_tool())

    result = compare_tool_snapshots(duplicated, current)

    assert result.comparison_status == ComparisonStatus.COMPARISON_FAILED
    assert result.comparison_error_code == "duplicate_tool_key"
    assert result.tool_changes == []


def test_tool_hash_mismatch_without_field_change_returns_failed_result() -> None:
    tool = normalize_tool_metadata(make_tool())
    tampered = tool.model_copy(update={"tool_hash": "b" * 64})

    result = compare_tool_snapshots(
        snapshot_from_normalized([tool]),
        snapshot_from_normalized([tampered]),
    )

    assert result.comparison_status == ComparisonStatus.COMPARISON_FAILED
    assert (
        result.comparison_error_code
        == "tool_hash_mismatch_without_field_change"
    )


def test_duplicate_tool_names_reorder_matches_and_content_change_adds_removes() -> None:
    duplicate_a = make_tool(tool_name="search", description="A")
    duplicate_b = make_tool(tool_name="search", description="B")
    duplicate_c = make_tool(tool_name="search", description="C")

    first = snapshot_of(duplicate_a, duplicate_b)
    reordered = snapshot_of(duplicate_b, duplicate_a)
    changed = snapshot_of(duplicate_a, duplicate_c)

    assert compare_tool_snapshots(
        first,
        reordered,
    ).comparison_status == ComparisonStatus.MATCHED

    result = compare_tool_snapshots(first, changed)
    assert result.added_count == 1
    assert result.removed_count == 1
    assert result.changed_count == 0
    assert result.unchanged_count == 1
    assert result.change_categories == ["tool_added", "tool_removed"]


def test_comparison_models_validate_contracts_and_are_frozen() -> None:
    field_change = ToolFieldChange(
        field_name="description",
        old_presence=FieldPresence.VALUE,
        new_presence=FieldPresence.VALUE,
        old_value="old",
        new_value="new",
        old_value_hash="1" * 64,
        new_value_hash="2" * 64,
    )

    with pytest.raises(ValidationError, match="field_changes"):
        ToolChange(
            change_type=ToolChangeType.CHANGED,
            tool_key="search",
            tool_name="search",
            old_tool_hash="1" * 64,
            new_tool_hash="2" * 64,
            field_changes=[],
        )

    with pytest.raises(ValidationError, match="matching hashes"):
        ToolChange(
            change_type=ToolChangeType.UNCHANGED,
            tool_key="search",
            tool_name="search",
            old_tool_hash="1" * 64,
            new_tool_hash="2" * 64,
        )

    snapshot = snapshot_of(make_tool())
    valid_change = ToolChange(
        change_type=ToolChangeType.CHANGED,
        tool_key="search",
        tool_name="search",
        old_tool_hash="1" * 64,
        new_tool_hash="2" * 64,
        field_changes=[field_change],
    )

    with pytest.raises(ValidationError, match="material changes"):
        BaselineComparisonResult(
            comparison_status=ComparisonStatus.MATCHED,
            matched=True,
            approved_snapshot_id=snapshot.snapshot_id,
            current_snapshot_id=snapshot.snapshot_id,
            approved_snapshot_hash=snapshot.snapshot_hash,
            current_snapshot_hash=snapshot.snapshot_hash,
            added_count=0,
            removed_count=0,
            changed_count=1,
            unchanged_count=0,
            change_categories=["tool_changed"],
            tool_changes=[valid_change],
        )

    with pytest.raises(ValidationError, match="error code"):
        BaselineComparisonResult(
            comparison_status=ComparisonStatus.COMPARISON_FAILED,
            matched=False,
            approved_snapshot_id=snapshot.snapshot_id,
            current_snapshot_id=snapshot.snapshot_id,
            approved_snapshot_hash=snapshot.snapshot_hash,
            current_snapshot_hash=snapshot.snapshot_hash,
            added_count=0,
            removed_count=0,
            changed_count=0,
            unchanged_count=0,
        )

    valid = compare_tool_snapshots(snapshot, snapshot)
    with pytest.raises(ValidationError):
        BaselineComparisonResult.model_validate(
            {**valid.model_dump(mode="json"), "extra": "x"}
        )
    with pytest.raises(ValidationError):
        valid.matched = False  # type: ignore[misc]


def test_diff_errors_and_failed_results_do_not_leak_raw_metadata() -> None:
    secret_tool = make_tool(
        input_schema={"secret": "VERY_SECRET_SCHEMA"},
        raw_extra={"raw_secret": "VERY_SECRET_RAW"},
    )
    secret_snapshot = snapshot_of(secret_tool)

    with pytest.raises(MetadataDiffError) as error_info:
        compare_tool_snapshots(object(), secret_snapshot)  # type: ignore[arg-type]

    assert "VERY_SECRET_SCHEMA" not in str(error_info.value)
    assert "VERY_SECRET_RAW" not in str(error_info.value)
    assert "object at" not in str(error_info.value)

    normalized = normalize_tool_metadata(secret_tool)
    tampered = normalized.model_copy(update={"tool_hash": "c" * 64})
    result = compare_tool_snapshots(
        snapshot_from_normalized([normalized]),
        snapshot_from_normalized([tampered]),
    )
    serialized = result.model_dump_json()

    assert "VERY_SECRET_SCHEMA" not in serialized
    assert "VERY_SECRET_RAW" not in serialized
    assert "raw_secret" not in serialized
