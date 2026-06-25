from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import Finding
from detectors.tool_poisoning.hidden_instruction import (
    find_rule_matches,
    load_rules,
)
from detectors.tool_poisoning.text_chunks import collect_text_chunks


def detect_metadata_poisoning(tool: Any, rules_path: str | Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    rules = load_rules(rules_path, category="hidden_instruction")

    for chunk in collect_text_chunks(tool, fields=("title", "annotations")):
        findings.extend(
            find_rule_matches(
                text=chunk.text,
                tool=tool,
                location=chunk.location,
                rules=rules,
                default_title="도구 메타데이터의 의심스러운 지시문",
            )
        )

    return findings


class MetadataPoisoningDetector:
    id = "MCP03-METADATA-POISONING"
    category = "tool_poisoning.metadata_poisoning"
    name = "metadata_poisoning"

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = rules_path

    def detect(self, tool: Any) -> list[Finding]:
        return detect_metadata_poisoning(tool, self.rules_path)
