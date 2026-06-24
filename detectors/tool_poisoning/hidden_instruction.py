from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import Finding
from core.redaction import redact_text
from detectors.rule_engine import (
    DEFAULT_RULES_PATH,
    find_rule_matches as find_rule_engine_matches,
    load_rules,
    match_pattern,
)
from detectors.tool_poisoning.text_chunks import iter_text_values

OWASP_CATEGORY = "MCP03"


def detect_hidden_instructions(tool: Any, rules_path: str | Path | None = None) -> list[Finding]:
    text = _get_field(tool, "description")
    if not text:
        return []

    return find_rule_matches(
        text=str(text),
        tool=tool,
        location="description",
        rules=load_rules(rules_path, category="hidden_instruction"),
        default_title="Hidden instruction in tool description",
    )


class HiddenInstructionDetector:
    id = "MCP03-HIDDEN-INSTRUCTION"
    category = "tool_poisoning.hidden_instruction"
    name = "hidden_instruction"

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = rules_path

    def detect(self, tool: Any) -> list[Finding]:
        return detect_hidden_instructions(tool, self.rules_path)


def find_rule_matches(
    text: str,
    tool: Any,
    location: str,
    rules: list[dict[str, Any]],
    default_title: str,
) -> list[Finding]:
    findings: list[Finding] = []

    for match in find_rule_engine_matches(text=text, rules=rules):
        findings.append(
            build_finding(
                rule=match.rule,
                tool=tool,
                location=location,
                evidence=match.evidence,
                title=match.rule.get("title", default_title),
            )
        )

    return findings


def build_finding(
    rule: dict[str, Any],
    tool: Any,
    location: str,
    evidence: str,
    title: str,
) -> Finding:
    redacted_evidence, redacted = redact_text(evidence)
    target = _target_name(tool)
    finding_id = f"{OWASP_CATEGORY}-{rule.get('id', 'tool_poisoning')}"

    return Finding(
        id=finding_id,
        category=rule.get("category", "tool_poisoning"),
        owasp=OWASP_CATEGORY,
        severity=rule.get("severity", "medium"),
        confidence=rule.get("confidence", "medium"),
        title=title,
        target=target,
        location=location,
        evidence=redacted_evidence,
        redacted=redacted,
        recommendation=rule.get(
            "recommendation",
            "Review and remove suspicious instructions from tool metadata.",
        ),
    )


def _match_pattern(text: str, pattern: str, match_type: str) -> str | None:
    return match_pattern(text=text, pattern=pattern, match_type=match_type)


def _get_field(tool: Any, field_name: str) -> Any:
    if isinstance(tool, dict):
        return tool.get(field_name) or tool.get(_to_camel_case(field_name))
    return getattr(tool, field_name, None)


def _target_name(tool: Any) -> str:
    server_name = _get_field(tool, "server_name") or "unknown-server"
    tool_name = _get_field(tool, "tool_name") or _get_field(tool, "name") or "unknown-tool"
    return f"{server_name}.{tool_name}"


def _to_camel_case(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])
