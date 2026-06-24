from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import Finding
from detectors.tool_poisoning.hidden_instruction import (
    find_rule_matches,
    load_rules,
)
from detectors.tool_poisoning.text_chunks import collect_text_chunks


def detect_schema_poisoning(tool: Any, rules_path: str | Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    rules = load_rules(rules_path, category="schema_poisoning") + load_rules(
        rules_path, category="hidden_instruction"
    )

    for chunk in collect_text_chunks(tool, fields=("input_schema",)):
        findings.extend(
            find_rule_matches(
                text=chunk.text,
                tool=tool,
                location=chunk.location,
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
