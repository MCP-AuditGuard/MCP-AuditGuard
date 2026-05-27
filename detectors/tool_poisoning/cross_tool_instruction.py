from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import Finding
from detectors.tool_poisoning.hidden_instruction import (
    find_rule_matches,
    iter_text_values,
    load_rules,
)


def detect_cross_tool_instructions(tool: Any, rules_path: str | Path | None = None) -> list[Finding]:
    rules = load_rules(rules_path, category="cross_tool_instruction")
    findings: list[Finding] = []

    for location, text in _candidate_texts(tool):
        findings.extend(
            find_rule_matches(
                text=text,
                tool=tool,
                location=location,
                rules=rules,
                default_title="Cross-tool instruction in tool metadata",
            )
        )

    return findings


class CrossToolInstructionDetector:
    id = "MCP03-CROSS-TOOL-INSTRUCTION"
    category = "tool_poisoning.cross_tool_instruction"
    name = "cross_tool_instruction"

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = rules_path

    def detect(self, tool: Any) -> list[Finding]:
        return detect_cross_tool_instructions(tool, self.rules_path)


def _candidate_texts(tool: Any) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    for field_name in ("title", "description", "annotations", "meta", "input_schema"):
        value = _get_field(tool, field_name)
        if value:
            candidates.extend(iter_text_values(value, _location_name(field_name)))

    return candidates


def _get_field(tool: Any, field_name: str) -> Any:
    if isinstance(tool, dict):
        if field_name == "meta":
            return tool.get("meta") or tool.get("_meta")
        if field_name == "input_schema":
            return tool.get("input_schema") or tool.get("inputSchema")
        return tool.get(field_name)
    return getattr(tool, field_name, None)


def _location_name(field_name: str) -> str:
    if field_name == "meta":
        return "_meta"
    return field_name
