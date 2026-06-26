from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.mcp_metadata_normalizer import (
    NORMALIZATION_VERSION,
    MetadataNormalizationError,
    canonical_json_bytes,
    create_tool_snapshot,
    normalize_tool_metadata,
)
from core.mcp_monitoring_models import FieldPresence
from core.models import ToolMetadata


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
    source: str | None = "mcp:test",
    collected_at: datetime | None = None,
    metadata_hash: str | None = None,
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
            output_schema
            if output_schema is not None
            else {"type": "object"}
        )
    if annotations is not _MISSING:
        raw_tool["annotations"] = (
            annotations if annotations is not None else {"readOnlyHint": True}
        )
    if meta is not _MISSING:
        raw_tool["_meta"] = meta if meta is not None else {"version": "1.0"}
    if raw_extra:
        raw_tool.update(raw_extra)

    tool = ToolMetadata.from_mcp_tool(
        raw_tool=raw_tool,
        server_name=server_name,
        source=source,
        collected_at=collected_at,
    )
    if metadata_hash is not None:
        return tool.model_copy(update={"metadata_hash": metadata_hash})

    return tool


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
        collected_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )


class _Missing:
    pass


_MISSING = _Missing()


def test_normalize_tool_metadata_includes_expected_fields() -> None:
    tool = make_tool(
        title="Search",
        description="Search project documents.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        annotations={"readOnlyHint": True},
        meta={"version": "1.0"},
        raw_extra={"secret_extra": "TEST_SECRET"},
        source="C:/private/source/tools.json",
    )

    normalized = normalize_tool_metadata(tool)
    serialized = normalized.model_dump(mode="json")

    assert normalized.normalization_version == NORMALIZATION_VERSION
    assert normalized.tool_key == "search"
    assert normalized.server_name == "docs"
    assert normalized.tool_name == "search"
    assert serialized["fields"]["title"] == {
        "presence": "value",
        "value": "Search",
    }
    assert serialized["fields"]["description"]["presence"] == "value"
    assert serialized["fields"]["input_schema"]["value"] == {"type": "object"}
    assert serialized["fields"]["output_schema"]["value"] == {"type": "object"}
    assert serialized["fields"]["annotations"]["value"] == {"readOnlyHint": True}
    assert serialized["fields"]["meta"]["value"] == {"version": "1.0"}
    assert len(normalized.tool_hash) == 64
    assert "TEST_SECRET" not in str(serialized)
    assert "source" not in normalized.to_hash_payload()
    assert "raw" not in normalized.to_hash_payload()
    assert "metadata_hash" not in normalized.to_hash_payload()


def test_presence_distinguishes_missing_null_empty_values() -> None:
    missing_tool = make_tool(input_schema=_MISSING)
    null_tool = construct_tool_with_raw({"name": "search", "inputSchema": None})
    empty_object_tool = construct_tool_with_raw(
        {"name": "search", "inputSchema": {}}
    )
    empty_array_tool = construct_tool_with_raw(
        {"name": "search", "inputSchema": []}
    )
    empty_string_tool = construct_tool_with_raw(
        {"name": "search", "description": ""}
    )

    missing = normalize_tool_metadata(missing_tool).fields.input_schema
    null = normalize_tool_metadata(null_tool).fields.input_schema
    empty_object = normalize_tool_metadata(empty_object_tool).fields.input_schema
    empty_array = normalize_tool_metadata(empty_array_tool).fields.input_schema
    empty_string = normalize_tool_metadata(empty_string_tool).fields.description

    assert missing.presence == FieldPresence.MISSING
    assert null.presence == FieldPresence.NULL
    assert empty_object.to_hash_payload() == {
        "presence": "value",
        "value": {},
    }
    assert empty_array.to_hash_payload() == {
        "presence": "value",
        "value": [],
    }
    assert empty_string.to_hash_payload() == {
        "presence": "value",
        "value": "",
    }

    hashes = {
        normalize_tool_metadata(tool).tool_hash
        for tool in (
            missing_tool,
            null_tool,
            empty_object_tool,
            empty_array_tool,
            empty_string_tool,
        )
    }
    assert len(hashes) == 5


def test_raw_presence_is_limited_to_standard_metadata_fields() -> None:
    absent_title = make_tool(title=_MISSING)
    null_title = construct_tool_with_raw({"name": "search", "title": None})

    assert (
        normalize_tool_metadata(absent_title).fields.title.presence
        == FieldPresence.MISSING
    )
    assert (
        normalize_tool_metadata(null_title).fields.title.presence
        == FieldPresence.NULL
    )


def test_canonical_json_ignores_object_key_order_but_preserves_array_order() -> None:
    first = make_tool(
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text"},
                "limit": {"type": "integer"},
            },
        }
    )
    second = make_tool(
        input_schema={
            "properties": {
                "limit": {"type": "integer"},
                "query": {"description": "Search text", "type": "string"},
            },
            "type": "object",
        }
    )
    array_first = make_tool(input_schema={"enum": ["a", "b"]})
    array_second = make_tool(input_schema={"enum": ["b", "a"]})

    assert normalize_tool_metadata(first).tool_hash == normalize_tool_metadata(
        second
    ).tool_hash
    assert normalize_tool_metadata(array_first).tool_hash != normalize_tool_metadata(
        array_second
    ).tool_hash


def test_canonical_json_uses_utf8_without_ascii_escaping() -> None:
    encoded = canonical_json_bytes({"text": "검색 도구", "nested": {"b": 1, "a": 2}})
    decoded = encoded.decode("utf-8")

    assert "검색 도구" in decoded
    assert "\\uac80" not in decoded
    assert decoded == '{"nested":{"a":2,"b":1},"text":"검색 도구"}'


@pytest.mark.parametrize(
    ("field_name", "changed_kwargs"),
    [
        ("server_name", {"server_name": "other-server"}),
        ("tool_name", {"tool_name": "read"}),
        ("title", {"title": "Different title"}),
        ("description", {"description": "Different description"}),
        ("input_schema", {"input_schema": {"type": "object", "required": ["q"]}}),
        ("output_schema", {"output_schema": {"type": "object", "required": ["r"]}}),
        ("annotations", {"annotations": {"readOnlyHint": False}}),
        ("meta", {"meta": {"version": "2.0"}}),
    ],
)
def test_each_included_field_changes_tool_hash(
    field_name: str,
    changed_kwargs: dict[str, object],
) -> None:
    original = make_tool()
    changed = make_tool(**changed_kwargs)

    assert normalize_tool_metadata(original).tool_hash != normalize_tool_metadata(
        changed
    ).tool_hash, field_name


def test_excluded_fields_do_not_change_tool_or_snapshot_hash() -> None:
    first = make_tool(
        raw_extra={"debug_only": "first"},
        source="C:/secret/first.json",
        collected_at=datetime(2026, 6, 24, 1, tzinfo=timezone.utc),
        metadata_hash="1" * 64,
    )
    second = make_tool(
        raw_extra={"debug_only": "second"},
        source="C:/secret/second.json",
        collected_at=datetime(2026, 6, 24, 2, tzinfo=timezone.utc),
        metadata_hash="2" * 64,
    )

    assert normalize_tool_metadata(first).tool_hash == normalize_tool_metadata(
        second
    ).tool_hash
    assert create_tool_snapshot([first]).snapshot_hash == create_tool_snapshot(
        [second]
    ).snapshot_hash


def test_snapshot_hash_is_stable_for_input_order_and_excludes_runtime_fields() -> None:
    search = make_tool(tool_name="search")
    read = make_tool(tool_name="read")
    first_time = datetime(2026, 6, 24, 1, tzinfo=timezone.utc)
    second_time = datetime(2026, 6, 24, 2, tzinfo=timezone.utc)

    first = create_tool_snapshot(
        [search, read],
        source_scan_id="scan-one",
        created_at=first_time,
    )
    reordered = create_tool_snapshot(
        [read, search],
        source_scan_id="scan-two",
        created_at=second_time,
    )

    assert first.snapshot_hash == reordered.snapshot_hash
    assert first.source_scan_id == "scan-one"
    assert reordered.source_scan_id == "scan-two"
    assert first.created_at == first_time
    assert reordered.created_at == second_time
    assert [tool.tool_key for tool in first.tools] == ["read", "search"]


def test_snapshot_hash_changes_when_tools_are_added_removed_or_changed() -> None:
    search = make_tool(tool_name="search")
    read = make_tool(tool_name="read")
    changed_search = make_tool(tool_name="search", description="Changed.")

    original = create_tool_snapshot([search, read])
    removed = create_tool_snapshot([search])
    changed = create_tool_snapshot([changed_search, read])

    assert original.snapshot_hash != removed.snapshot_hash
    assert original.snapshot_hash != changed.snapshot_hash


def test_empty_snapshot_is_valid_and_deterministic() -> None:
    first = create_tool_snapshot([])
    second = create_tool_snapshot([])

    assert first.tool_count == 0
    assert first.tools == []
    assert first.snapshot_hash == second.snapshot_hash
    assert first.snapshot_id == second.snapshot_id


def test_duplicate_tool_names_are_preserved_with_order_stable_keys() -> None:
    duplicate_a = make_tool(tool_name="search", description="Search A.")
    duplicate_b = make_tool(tool_name="search", description="Search B.")

    first = create_tool_snapshot([duplicate_a, duplicate_b])
    second = create_tool_snapshot([duplicate_b, duplicate_a])

    assert first.snapshot_hash == second.snapshot_hash
    assert first.tool_count == 2
    assert len(first.tools) == 2
    assert len({tool.tool_key for tool in first.tools}) == 2
    assert all("#duplicate-" in tool.tool_key for tool in first.tools)
    assert [warning.code for warning in first.warnings] == ["duplicate_tool_name"]
    assert first.warnings[0].occurrence_count == 2


def test_identical_duplicate_tool_names_keep_count_without_order_dependency() -> None:
    duplicate = make_tool(tool_name="search", description="Same.")

    first = create_tool_snapshot([duplicate, duplicate])
    second = create_tool_snapshot([duplicate, duplicate])

    assert first.snapshot_hash == second.snapshot_hash
    assert first.tool_count == 2
    assert len({tool.tool_key for tool in first.tools}) == 2
    assert any(tool.tool_key.endswith("-0001") for tool in first.tools)
    assert any(tool.tool_key.endswith("-0002") for tool in first.tools)


def test_invalid_inputs_raise_domain_error() -> None:
    with pytest.raises(MetadataNormalizationError, match="ToolMetadata"):
        normalize_tool_metadata(object())  # type: ignore[arg-type]

    with pytest.raises(MetadataNormalizationError, match="tool_name"):
        normalize_tool_metadata(
            ToolMetadata.model_construct(
                server_name="docs",
                tool_name=" ",
                raw={"name": " "},
                metadata_hash="0" * 64,
                collected_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
            )
        )

    with pytest.raises(MetadataNormalizationError, match="sequence"):
        create_tool_snapshot("not-tools")  # type: ignore[arg-type]


def test_non_json_metadata_values_are_rejected_without_leaking_raw_value() -> None:
    bytes_tool = construct_tool_with_raw(
        {"name": "search", "inputSchema": {"secret": b"TEST_SECRET"}}
    )
    datetime_tool = construct_tool_with_raw(
        {"name": "search", "inputSchema": {"created": datetime.now(timezone.utc)}}
    )
    custom_tool = construct_tool_with_raw(
        {"name": "search", "inputSchema": {"custom": object()}}
    )

    for tool in (bytes_tool, datetime_tool, custom_tool):
        with pytest.raises(MetadataNormalizationError) as error_info:
            normalize_tool_metadata(tool)

        assert "TEST_SECRET" not in str(error_info.value)


def test_nan_and_infinity_are_rejected() -> None:
    nan_tool = construct_tool_with_raw(
        {"name": "search", "inputSchema": {"score": float("nan")}}
    )
    infinity_tool = construct_tool_with_raw(
        {"name": "search", "inputSchema": {"score": float("inf")}}
    )

    with pytest.raises(MetadataNormalizationError, match="finite JSON number"):
        normalize_tool_metadata(nan_tool)

    with pytest.raises(MetadataNormalizationError, match="finite JSON number"):
        normalize_tool_metadata(infinity_tool)
