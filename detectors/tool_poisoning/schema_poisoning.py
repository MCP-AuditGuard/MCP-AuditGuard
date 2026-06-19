from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import Finding
from detectors.tool_poisoning.hidden_instruction import (
    find_rule_matches,
    iter_text_values,
    load_rules,
)


def detect_schema_poisoning(tool: Any, rules_path: str | Path | None = None) -> list[Finding]:
    schema = _get_field(tool, "input_schema")
    if not schema:
        return []

    findings: list[Finding] = []
    rules = load_rules(rules_path, category="schema_poisoning") + load_rules(
        rules_path, category="hidden_instruction"
    )

    for location, text in iter_text_values(schema, "input_schema"):
        if not _is_schema_text_location(location):
            continue
        findings.extend(
            find_rule_matches(
                text=text,
                tool=tool,
                location=location,
                rules=rules,
                default_title="Suspicious instruction in input schema",
            )
        )

    return findings


class SchemaPoisoningDetector:
    id = "MCP03-SCHEMA-POISONING"
    category = "tool_poisoning.schema_poisoning"
    name = "schema_poisoning"

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = rules_path

    def detect(self, tool: Any) -> list[Finding]:
        return detect_schema_poisoning(tool, self.rules_path)


def _is_schema_text_location(location: str) -> bool:
    interesting_keys = ("description", "title", "examples", "default")
    return any(part in location.lower() for part in interesting_keys)


def _get_field(tool: Any, field_name: str) -> Any:
    if isinstance(tool, dict):
        return tool.get(field_name) or tool.get("inputSchema")
    return getattr(tool, field_name, None)
