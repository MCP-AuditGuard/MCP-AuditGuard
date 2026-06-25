from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class TextChunk:
    location: str
    text: str
    field_type: str
    source: str = "raw"


STRUCTURAL_LOCATION_FRAGMENTS = (
    ".required[",
    ".enum[",
    ".examples[",
    ".const",
    ".default",
)

SPEC_TEXT_FIELDS = (
    "name",
    "title",
    "description",
    "input_schema",
    "output_schema",
    "annotations",
)

SCHEMA_TEXT_KEYS = {"description", "title"}
SCHEMA_FIELD_TYPES = {"input_schema", "output_schema"}

EVALUATION_LOCATION_SUFFIXES = (
    "_meta.expected_signal",
    "meta.expected_signal",
    "_meta.real_world_reference",
    "meta.real_world_reference",
    "_meta.difficulty",
    "meta.difficulty",
    "_meta.scenario_id",
    "meta.scenario_id",
)


def iter_text_values(value: Any, prefix: str) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []

    if isinstance(value, str):
        values.append((prefix, value))
    elif isinstance(value, dict):
        for key, nested_value in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            values.extend(iter_text_values(nested_value, child_prefix))
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            values.extend(iter_text_values(nested_value, child_prefix))

    return values


def collect_text_chunks(
    tool: Any,
    *,
    fields: Iterable[str] | None = None,
    include_structural_values: bool = False,
    include_title: bool = True,
) -> list[TextChunk]:
    requested_fields = tuple(fields or SPEC_TEXT_FIELDS)
    chunks: list[TextChunk] = []

    for field_name in requested_fields:
        if field_name == "title" and not include_title:
            continue

        value = _get_field(tool, field_name)
        if value is None:
            continue

        location_name = _location_name(field_name)
        for location, text in iter_text_values(value, location_name):
            if is_evaluation_location(location):
                continue
            if _is_schema_field(field_name) and not include_structural_values:
                if not is_schema_text_location(location):
                    continue
            if not include_structural_values and is_structural_location(location):
                continue
            stripped_text = text.strip()
            if not stripped_text:
                continue
            chunks.append(
                TextChunk(
                    location=location,
                    text=stripped_text,
                    field_type=field_name,
                )
            )

    return chunks


def is_structural_location(location: str) -> bool:
    return any(fragment in location for fragment in STRUCTURAL_LOCATION_FRAGMENTS)


def is_schema_text_location(location: str) -> bool:
    last_part = location.rsplit(".", maxsplit=1)[-1]
    key = last_part.split("[", maxsplit=1)[0]
    return key in SCHEMA_TEXT_KEYS


def is_evaluation_location(location: str) -> bool:
    return any(
        location.endswith(part) or location == part
        for part in EVALUATION_LOCATION_SUFFIXES
    )


def _get_field(tool: Any, field_name: str) -> Any:
    if isinstance(tool, dict):
        if field_name == "name":
            return tool.get("name") or tool.get("tool_name")
        if field_name == "meta":
            return tool.get("meta") or tool.get("_meta")
        if field_name == "input_schema":
            return tool.get("input_schema") or tool.get("inputSchema")
        if field_name == "output_schema":
            return tool.get("output_schema") or tool.get("outputSchema")
        return tool.get(field_name)
    if field_name == "name":
        return getattr(tool, "name", None) or getattr(tool, "tool_name", None)
    return getattr(tool, field_name, None)


def _location_name(field_name: str) -> str:
    if field_name == "meta":
        return "meta"
    return field_name


def _is_schema_field(field_name: str) -> bool:
    return field_name in SCHEMA_FIELD_TYPES
