from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import Finding
from detectors.tool_poisoning.hidden_instruction import (
    find_rule_matches,
    iter_text_values,
    load_rules,
)


def detect_metadata_poisoning(tool: Any, rules_path: str | Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    rules = load_rules(rules_path, category="hidden_instruction")

    for field_name in ("title", "annotations", "meta"):
        value = _get_field(tool, field_name)
        if not value:
            continue

        for location, text in iter_text_values(value, _location_name(field_name)):
            findings.extend(
                find_rule_matches(
                    text=text,
                    tool=tool,
                    location=location,
                    rules=rules,
                    default_title="Suspicious instruction in tool metadata",
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


def _get_field(tool: Any, field_name: str) -> Any:
    if isinstance(tool, dict):
        if field_name == "meta":
            return tool.get("meta") or tool.get("_meta")
        return tool.get(field_name)
    return getattr(tool, field_name, None)


def _location_name(field_name: str) -> str:
    return "_meta" if field_name == "meta" else field_name
