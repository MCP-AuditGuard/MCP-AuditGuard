from __future__ import annotations

import json
from pathlib import Path

from core.models import Finding, ToolMetadata
from core.redaction import redact_text
from detectors.obfuscation.common import stable_fingerprint
from detectors.obfuscation.derived_text import (
    DerivedMetadataText,
    collect_obfuscation_derived_texts,
)
from detectors.rule_engine import RuleMatch, find_rule_matches, load_rules


OWASP_CATEGORY = "MCP03"
CATEGORY = "tool_poisoning.obfuscated_hidden_instruction"
RECOMMENDATION = (
    "Remove obfuscated hidden instructions from MCP tool metadata. Keep metadata "
    "human-readable and review encoded, hidden, or normalized text before publishing."
)

SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
CONFIDENCE_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


class ObfuscatedHiddenInstructionDetector:
    id = "MCP03-OBFUSCATED-HIDDEN-INSTRUCTION"
    category = CATEGORY
    name = "obfuscated_hidden_instruction"

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = rules_path

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        rules = load_rules(self.rules_path, category="hidden_instruction")
        findings: list[Finding] = []

        for derived in collect_obfuscation_derived_texts(tool):
            matches = find_rule_matches(text=derived.value, rules=rules)
            if not matches:
                continue

            findings.append(_build_finding(tool, derived, matches))

        return findings


def _build_finding(
    tool: ToolMetadata,
    derived: DerivedMetadataText,
    matches: list[RuleMatch],
) -> Finding:
    severity = _highest_severity(matches)
    confidence = _combine_confidence(
        derived.decode_confidence,
        _highest_confidence(matches),
    )
    evidence = _evidence(derived, matches, severity, confidence)
    redacted_evidence, redacted = redact_text(evidence)
    fingerprint = stable_fingerprint(
        CATEGORY,
        tool.server_name,
        tool.tool_name,
        derived.source_location,
        _stable_transform_family(derived),
        ",".join(sorted(match.rule_id for match in matches)),
    )

    return Finding(
        id=f"mcp03-obfuscated-hidden-{fingerprint[:12]}",
        category=CATEGORY,
        owasp=OWASP_CATEGORY,
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        title="Hidden instruction revealed after obfuscation decoding",
        target=f"{tool.server_name}.{tool.tool_name}",
        location=derived.derived_location,
        evidence=redacted_evidence,
        redacted=redacted,
        recommendation=RECOMMENDATION,
        fingerprint=fingerprint,
    )


def _evidence(
    derived: DerivedMetadataText,
    matches: list[RuleMatch],
    severity: str,
    confidence: str,
) -> str:
    return json.dumps(
        {
            "matched_on": "canonical",
            "via_obfuscation": True,
            "source_location": derived.source_location,
            "derived_location": derived.derived_location,
            "transform": derived.transform,
            "transformation_chain": list(derived.transformation_chain),
            "decode_confidence": derived.decode_confidence,
            "effective_severity": severity,
            "effective_confidence": confidence,
            "original_excerpt": derived.original_excerpt,
            "canonical_excerpt": derived.value[:240],
            "derived_excerpt": derived.value[:240],
            "matched_rules": [
                {
                    "id": match.rule_id,
                    "matched_rule": match.rule_id,
                    "category": match.category,
                    "severity": match.severity,
                    "confidence": match.confidence,
                    "match_type": match.match_type,
                    "match_method": match.match_type,
                    "pattern": match.pattern,
                    "evidence": match.evidence,
                    "matched_text": match.evidence,
                }
                for match in matches
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _highest_severity(matches: list[RuleMatch]) -> str:
    return max(
        (match.severity for match in matches),
        key=lambda severity: SEVERITY_RANK.get(severity, SEVERITY_RANK["medium"]),
    )


def _highest_confidence(matches: list[RuleMatch]) -> str:
    return max(
        (match.confidence for match in matches),
        key=lambda confidence: CONFIDENCE_RANK.get(confidence, CONFIDENCE_RANK["medium"]),
    )


def _combine_confidence(decode_confidence: str, rule_confidence: str) -> str:
    decode_rank = CONFIDENCE_RANK.get(decode_confidence, CONFIDENCE_RANK["medium"])
    rule_rank = CONFIDENCE_RANK.get(rule_confidence, CONFIDENCE_RANK["medium"])
    final_rank = min(decode_rank, rule_rank)

    for confidence, rank in CONFIDENCE_RANK.items():
        if rank == final_rank:
            return confidence

    return "medium"


def _stable_transform_family(derived: DerivedMetadataText) -> str:
    chain = tuple(part.casefold() for part in derived.transformation_chain)
    transform = derived.transform.casefold()

    if any(_is_encoded_transform(part) for part in chain) or _is_encoded_transform(transform):
        return "encoded_payload"
    if any(part.startswith("hidden:") for part in chain) or transform.startswith("hidden:"):
        return "markup_hidden_text"
    if any("homoglyph" in part for part in chain) or "homoglyph" in transform:
        return "homoglyph"
    if chain or transform:
        return "unicode_obfuscation"

    return "unknown_obfuscation"


def _is_encoded_transform(value: str) -> bool:
    return any(
        marker in value
        for marker in (
            "base64",
            "base64url",
            "url_encoding",
            "hex",
            "octal_escape",
            "html_entity",
            "rot13",
            "decoded:",
        )
    )
