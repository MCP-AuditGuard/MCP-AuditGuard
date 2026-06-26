from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from core.mcp_monitoring_models import (
    FieldPresence,
    NormalizedFieldValue,
    NormalizedMetadataFields,
    NormalizedToolMetadata,
    ToolSnapshot,
    ToolSnapshotWarning,
)
from core.models import ToolMetadata


NORMALIZATION_VERSION = "mcp-tool-metadata-v1"
SNAPSHOT_ID_HASH_PREFIX_LENGTH = 20


class MetadataNormalizationError(ValueError):
    """Raised when MCP tool metadata cannot be normalized deterministically."""


@dataclass(frozen=True)
class _FieldSpec:
    name: str
    attribute: str
    raw_keys: tuple[str, ...]


@dataclass(frozen=True)
class _PreparedTool:
    server_name: str
    tool_name: str
    fields: NormalizedMetadataFields
    content_payload: dict[str, Any]
    content_hash: str
    content_bytes: bytes


_FIELD_SPECS = (
    _FieldSpec("title", "title", ("title",)),
    _FieldSpec("description", "description", ("description",)),
    _FieldSpec("input_schema", "input_schema", ("inputSchema", "input_schema")),
    _FieldSpec("output_schema", "output_schema", ("outputSchema", "output_schema")),
    _FieldSpec("annotations", "annotations", ("annotations",)),
    _FieldSpec("meta", "meta", ("_meta", "meta")),
)


def normalize_tool_metadata(tool: ToolMetadata) -> NormalizedToolMetadata:
    """Normalize one ToolMetadata using the MCP Monitoring v1 contract."""
    prepared = _prepare_tool(tool)
    return _build_normalized_tool(
        prepared,
        tool_key=prepared.tool_name,
    )


def create_tool_snapshot(
    tools: Sequence[ToolMetadata],
    *,
    source_scan_id: str | None = None,
    created_at: datetime | None = None,
) -> ToolSnapshot:
    """Create a deterministic ToolSnapshot from collected MCP ToolMetadata."""
    if isinstance(tools, (str, bytes, bytearray)):
        raise MetadataNormalizationError("tools must be a sequence of ToolMetadata")

    try:
        tool_list = list(tools)
    except TypeError as exc:
        raise MetadataNormalizationError(
            "tools must be a sequence of ToolMetadata"
        ) from exc

    prepared_tools = [_prepare_tool(tool) for tool in tool_list]
    keyed_tools = _assign_tool_keys(prepared_tools)
    normalized_tools = [
        _build_normalized_tool(prepared, tool_key=tool_key)
        for prepared, tool_key in keyed_tools
    ]
    sorted_tools = sorted(normalized_tools, key=lambda tool: tool.tool_key)
    warnings = _duplicate_tool_warnings(
        keyed_tools=keyed_tools,
        prepared_tools=prepared_tools,
    )
    snapshot_hash = _calculate_snapshot_hash(sorted_tools)

    return ToolSnapshot(
        snapshot_id=f"snap_{snapshot_hash[:SNAPSHOT_ID_HASH_PREFIX_LENGTH]}",
        snapshot_hash=snapshot_hash,
        normalization_version=NORMALIZATION_VERSION,
        tools=sorted_tools,
        tool_count=len(sorted_tools),
        created_at=_normalize_datetime(created_at),
        source_scan_id=source_scan_id,
        warnings=warnings,
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical UTF-8 JSON bytes for deterministic hashing."""
    compatible_value = _to_json_compatible(value, path="$")
    try:
        text = json.dumps(
            compatible_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise MetadataNormalizationError(
            "value cannot be encoded as canonical JSON"
        ) from exc

    return text.encode("utf-8")


def calculate_sha256(payload: bytes) -> str:
    """Return a lower-case SHA-256 hexadecimal digest."""
    if not isinstance(payload, bytes):
        raise MetadataNormalizationError("sha256 payload must be bytes")

    return hashlib.sha256(payload).hexdigest()


def _prepare_tool(tool: ToolMetadata) -> _PreparedTool:
    if not isinstance(tool, ToolMetadata):
        raise MetadataNormalizationError("tool must be a ToolMetadata instance")

    server_name = _required_text(tool.server_name, "server_name")
    tool_name = _required_text(tool.tool_name, "tool_name")

    fields_by_name = {
        spec.name: _normalize_field(tool, spec)
        for spec in _FIELD_SPECS
    }
    fields = NormalizedMetadataFields(**fields_by_name)
    content_payload = {
        "normalization_version": NORMALIZATION_VERSION,
        "server_name": server_name,
        "tool_name": tool_name,
        "fields": fields.to_hash_payload(),
    }
    content_bytes = canonical_json_bytes(content_payload)

    return _PreparedTool(
        server_name=server_name,
        tool_name=tool_name,
        fields=fields,
        content_payload=content_payload,
        content_hash=calculate_sha256(content_bytes),
        content_bytes=content_bytes,
    )


def _build_normalized_tool(
    prepared: _PreparedTool,
    *,
    tool_key: str,
) -> NormalizedToolMetadata:
    payload = {
        **prepared.content_payload,
        "tool_key": tool_key,
    }
    tool_hash = calculate_sha256(canonical_json_bytes(payload))

    return NormalizedToolMetadata(
        normalization_version=NORMALIZATION_VERSION,
        tool_key=tool_key,
        server_name=prepared.server_name,
        tool_name=prepared.tool_name,
        fields=prepared.fields,
        tool_hash=tool_hash,
    )


def _normalize_field(
    tool: ToolMetadata,
    spec: _FieldSpec,
) -> NormalizedFieldValue:
    if not isinstance(tool.raw, dict):
        raise MetadataNormalizationError("tool raw metadata must be a JSON object")

    for raw_key in spec.raw_keys:
        if raw_key in tool.raw:
            return _field_value(tool.raw[raw_key], spec.name)

    fallback_value = getattr(tool, spec.attribute)
    if fallback_value is None:
        # ToolMetadata collapses absent and null to None unless raw preserves
        # the key. Without raw presence, this contract can only mark missing.
        return NormalizedFieldValue(presence=FieldPresence.MISSING)

    return _field_value(fallback_value, spec.name)


def _field_value(value: Any, field_name: str) -> NormalizedFieldValue:
    if value is None:
        return NormalizedFieldValue(presence=FieldPresence.NULL)

    return NormalizedFieldValue(
        presence=FieldPresence.VALUE,
        value=_to_json_compatible(value, path=field_name),
    )


def _assign_tool_keys(
    prepared_tools: Sequence[_PreparedTool],
) -> list[tuple[_PreparedTool, str]]:
    grouped: dict[str, list[_PreparedTool]] = defaultdict(list)
    for prepared in prepared_tools:
        grouped[prepared.tool_name].append(prepared)

    keyed: list[tuple[_PreparedTool, str]] = []
    for tool_name in sorted(grouped):
        group = grouped[tool_name]
        if len(group) == 1:
            keyed.append((group[0], tool_name))
            continue

        sorted_group = sorted(
            group,
            key=lambda prepared: (
                prepared.content_hash,
                prepared.content_bytes,
            ),
        )
        hash_counts = Counter(prepared.content_hash for prepared in sorted_group)
        hash_ordinals: dict[str, int] = defaultdict(int)

        for prepared in sorted_group:
            hash_ordinals[prepared.content_hash] += 1
            suffix = prepared.content_hash
            if hash_counts[prepared.content_hash] > 1:
                suffix = (
                    f"{suffix}-{hash_ordinals[prepared.content_hash]:04d}"
                )
            keyed.append((prepared, f"{tool_name}#duplicate-{suffix}"))

    return _resolve_tool_key_collisions(keyed)


def _resolve_tool_key_collisions(
    keyed_tools: Sequence[tuple[_PreparedTool, str]],
) -> list[tuple[_PreparedTool, str]]:
    key_counts = Counter(tool_key for _, tool_key in keyed_tools)
    if all(count == 1 for count in key_counts.values()):
        return list(keyed_tools)

    collision_ordinals: dict[str, int] = defaultdict(int)
    resolved: list[tuple[_PreparedTool, str]] = []
    for prepared, tool_key in sorted(
        keyed_tools,
        key=lambda item: (
            item[1],
            item[0].content_hash,
            item[0].content_bytes,
        ),
    ):
        if key_counts[tool_key] == 1:
            resolved.append((prepared, tool_key))
            continue

        collision_ordinals[tool_key] += 1
        resolved.append(
            (
                prepared,
                (
                    f"{tool_key}#key-{prepared.content_hash}"
                    f"-{collision_ordinals[tool_key]:04d}"
                ),
            )
        )

    return resolved


def _duplicate_tool_warnings(
    *,
    keyed_tools: Sequence[tuple[_PreparedTool, str]],
    prepared_tools: Sequence[_PreparedTool],
) -> list[ToolSnapshotWarning]:
    counts = Counter(prepared.tool_name for prepared in prepared_tools)
    if not counts:
        return []

    keys_by_name: dict[str, list[str]] = defaultdict(list)
    for prepared, tool_key in keyed_tools:
        keys_by_name[prepared.tool_name].append(tool_key)

    warnings: list[ToolSnapshotWarning] = []
    for tool_name in sorted(name for name, count in counts.items() if count > 1):
        warnings.append(
            ToolSnapshotWarning(
                code="duplicate_tool_name",
                message=(
                    "Duplicate MCP tool names were isolated with "
                    "content-hash tool keys."
                ),
                tool_name=tool_name,
                tool_keys=sorted(keys_by_name[tool_name]),
                occurrence_count=counts[tool_name],
            )
        )

    return warnings


def _calculate_snapshot_hash(
    tools: Sequence[NormalizedToolMetadata],
) -> str:
    payload = {
        "version": NORMALIZATION_VERSION,
        "tools": [
            {
                "tool_key": tool.tool_key,
                "tool_hash": tool.tool_hash,
            }
            for tool in tools
        ],
    }

    return calculate_sha256(canonical_json_bytes(payload))


def _to_json_compatible(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    if isinstance(value, float):
        if not isfinite(value):
            raise MetadataNormalizationError(
                f"metadata value at {path} must be a finite JSON number"
            )
        return value

    if isinstance(value, list):
        return [
            _to_json_compatible(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise MetadataNormalizationError(
                    f"metadata object key at {path} must be a string"
                )
            normalized[key] = _to_json_compatible(
                item,
                path=f"{path}.{key}",
            )
        return normalized

    raise MetadataNormalizationError(
        f"metadata value at {path} is not JSON-serializable "
        f"({type(value).__name__})"
    )


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MetadataNormalizationError(f"{field_name} must not be empty")

    return value


def _normalize_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)
