from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from core.models import Finding, ToolMetadata


@dataclass(frozen=True)
class MetadataText:
    location: str
    value: str


TEXT_FIELDS = (
    ("title", "title"),
    ("description", "description"),
    ("input_schema", "inputSchema"),
    ("output_schema", "outputSchema"),
    ("annotations", "annotations"),
    ("meta", "_meta"),
)

SUSPICIOUS_PHRASES = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "system prompt",
    "developer message",
    "exfiltrate",
    "send secrets",
    "steal secrets",
    "read secrets",
    "read environment",
    "send token",
    "bypass",
    "do not reveal",
    "hidden instruction",
)

MAX_RECURSION_DEPTH = 50


def iter_metadata_text(tool: ToolMetadata) -> Iterable[MetadataText]:
    visited_raw_keys: set[str] = set()

    for attr_name, public_name in TEXT_FIELDS:
        value = getattr(tool, attr_name, None)
        if value is None:
            continue

        yield from _walk_text(value, public_name)
        visited_raw_keys.add(public_name)

    if not isinstance(tool.raw, dict):
        yield from _walk_text(tool.raw, "raw")
        return

    for key, child in tool.raw.items():
        key_text = str(key)
        if key_text in visited_raw_keys:
            continue
        yield from _walk_text(child, f"raw.{key_text}")


def _walk_text(value: Any, location: str, depth: int = 0) -> Iterable[MetadataText]:
    if depth > MAX_RECURSION_DEPTH or value is None:
        return

    if isinstance(value, str):
        yield MetadataText(location=location, value=value)
        return

    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_location = f"{location}.{key_text}" if location else key_text
            yield from _walk_text(child, child_location, depth + 1)
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_text(child, f"{location}[{index}]", depth + 1)
        return


def contains_suspicious_phrase(text: str) -> bool:
    normalized = normalize_for_phrase_match(text)
    return any(normalize_for_phrase_match(phrase) in normalized for phrase in SUSPICIOUS_PHRASES)


def normalize_for_phrase_match(text: str) -> str:
    lowered = text.lower()
    return re.sub(r"[^a-z0-9]", "", lowered)


def redact_evidence(text: str) -> tuple[str, bool]:
    try:
        from core.redaction import redact_text

        redacted = redact_text(text)
    except ImportError:
        redacted = _fallback_redact(text)

    return redacted, redacted != text


def _fallback_redact(text: str) -> str:
    patterns = (
        (r"sk-[A-Za-z0-9_\-]{8,}", "[REDACTED_OPENAI_KEY]"),
        (r"ghp_[A-Za-z0-9_]{16,}", "[REDACTED_GITHUB_TOKEN]"),
        (r"github_pat_[A-Za-z0-9_]{16,}", "[REDACTED_GITHUB_PAT]"),
        (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
        (
            r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?)([^'\"\s,\}]+)",
            r"\1[REDACTED_SECRET]",
        ),
    )

    redacted = text
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted


def stable_fingerprint(*parts: str) -> str:
    payload = "\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def finding_id(prefix: str, fingerprint: str) -> str:
    return f"{prefix}-{fingerprint[:12]}"


def json_evidence(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def excerpt(text: str, limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def make_finding(
    *,
    prefix: str,
    category: str,
    severity: str,
    confidence: str,
    title: str,
    tool: ToolMetadata,
    location: str,
    evidence: str,
    recommendation: str,
) -> Finding:
    redacted_evidence, was_redacted = redact_evidence(evidence)
    fingerprint = stable_fingerprint(
        category,
        tool.server_name,
        tool.tool_name,
        location,
        redacted_evidence,
    )

    return Finding(
        id=finding_id(prefix, fingerprint),
        category=category,
        owasp="MCP03",
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        title=title,
        target=f"{tool.server_name}.{tool.tool_name}",
        location=location,
        evidence=redacted_evidence,
        redacted=was_redacted,
        recommendation=recommendation,
        fingerprint=fingerprint,
    )
