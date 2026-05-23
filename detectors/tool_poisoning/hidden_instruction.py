from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml


DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "tool_poisoning.yaml"
OWASP_CATEGORY = "MCP03"


def load_rules(path: str | Path | None = None, category: str | None = None) -> list[dict[str, Any]]:
    rules_path = Path(path) if path else DEFAULT_RULES_PATH
    with rules_path.open("r", encoding="utf-8") as rule_file:
        data = yaml.safe_load(rule_file) or {}

    rules = data.get("rules", [])
    if category is None:
        return rules
    return [rule for rule in rules if rule.get("category") == category]


def detect_hidden_instructions(tool: Any, rules_path: str | Path | None = None) -> list[dict[str, Any]]:
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
    name = "hidden_instruction"

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = rules_path

    def detect(self, tool: Any) -> list[dict[str, Any]]:
        return detect_hidden_instructions(tool, self.rules_path)


def find_rule_matches(
    text: str,
    tool: Any,
    location: str,
    rules: list[dict[str, Any]],
    default_title: str,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for rule in rules:
        for pattern in rule.get("patterns", []):
            evidence = _match_pattern(text, pattern, rule.get("type", "keyword"))
            if evidence is None:
                continue

            findings.append(
                build_finding(
                    rule=rule,
                    tool=tool,
                    location=location,
                    evidence=evidence,
                    title=rule.get("title", default_title),
                )
            )
            break

    return findings


def build_finding(
    rule: dict[str, Any],
    tool: Any,
    location: str,
    evidence: str,
    title: str,
) -> dict[str, Any]:
    redacted_evidence = _redact_secret_like(evidence)
    target = _target_name(tool)
    finding_id = f"{OWASP_CATEGORY}-{rule.get('id', 'tool_poisoning')}"
    fingerprint = _fingerprint(finding_id, target, location, redacted_evidence)

    return {
        "id": finding_id,
        "category": rule.get("category", "tool_poisoning"),
        "owasp": OWASP_CATEGORY,
        "severity": rule.get("severity", "medium"),
        "confidence": rule.get("confidence", "medium"),
        "title": title,
        "target": target,
        "location": location,
        "evidence": redacted_evidence,
        "redacted": redacted_evidence != evidence,
        "recommendation": rule.get(
            "recommendation",
            "Review and remove suspicious instructions from tool metadata.",
        ),
        "fingerprint": fingerprint,
    }


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


def _match_pattern(text: str, pattern: str, match_type: str) -> str | None:
    if match_type == "regex":
        match = re.search(pattern, text, flags=re.IGNORECASE)
        return match.group(0) if match else None

    lowered_text = text.lower()
    lowered_pattern = pattern.lower()
    if lowered_pattern not in lowered_text:
        return None
    return pattern


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


def _redact_secret_like(text: str) -> str:
    patterns = [
        r"(?i)(api[_-]?key|token|password|secret|credential)\s*[:=]\s*[A-Za-z0-9_\-./+=]{6,}",
        r"(?i)(FAKE|TEST|DUMMY)_[A-Z0-9_\-]{6,}",
    ]

    redacted = text
    for pattern in patterns:
        redacted = re.sub(pattern, "[REDACTED]", redacted)
    return redacted


def _fingerprint(*parts: str) -> str:
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()

