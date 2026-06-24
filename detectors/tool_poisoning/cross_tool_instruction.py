from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import Finding
from detectors.tool_poisoning.hidden_instruction import (
    find_rule_matches,
    load_rules,
)
from detectors.tool_poisoning.text_chunks import collect_text_chunks


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
                default_title="도구 간 호출 조작 지시문",
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
    return [
        (chunk.location, chunk.text)
        for chunk in collect_text_chunks(
            tool,
            fields=("title", "description", "annotations", "input_schema"),
        )
    ]
