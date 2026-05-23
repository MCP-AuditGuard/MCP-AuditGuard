from __future__ import annotations

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import (
    contains_suspicious_phrase,
    excerpt,
    iter_metadata_text,
    json_evidence,
    make_finding,
)


ZERO_WIDTH_CHARS = {
    "\u200b": "ZERO WIDTH SPACE",
    "\u200c": "ZERO WIDTH NON-JOINER",
    "\u200d": "ZERO WIDTH JOINER",
    "\ufeff": "ZERO WIDTH NO-BREAK SPACE / BOM",
    "\u2060": "WORD JOINER",
    "\u180e": "MONGOLIAN VOWEL SEPARATOR",
}


class UnicodeObfuscationDetector:
    name = "unicode_obfuscation"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        findings: list[Finding] = []

        for field in iter_metadata_text(tool):
            detected_chars = detect_zero_width_chars(field.value)
            if not detected_chars:
                continue

            normalized = remove_zero_width_chars(field.value)
            reveals_instruction = contains_suspicious_phrase(normalized)
            severity = "high" if reveals_instruction else "medium"
            confidence = "high" if reveals_instruction else "medium"

            evidence = json_evidence(
                {
                    "original_excerpt": excerpt(field.value),
                    "normalized_excerpt": excerpt(normalized),
                    "zero_width_chars": detected_chars,
                    "reveals_instruction_after_normalization": reveals_instruction,
                }
            )

            findings.append(
                make_finding(
                    prefix="mcp03-zero-width",
                    category="obfuscation.zero_width_unicode",
                    severity=severity,
                    confidence=confidence,
                    title="Zero-width Unicode found in tool metadata",
                    tool=tool,
                    location=field.location,
                    evidence=evidence,
                    recommendation=(
                        "Remove zero-width Unicode characters from MCP tool metadata "
                        "and review the normalized text for hidden instructions."
                    ),
                )
            )

        return findings


def detect_zero_width_chars(text: str) -> list[dict[str, str | int]]:
    found: list[dict[str, str | int]] = []
    for index, char in enumerate(text):
        if char not in ZERO_WIDTH_CHARS:
            continue

        found.append(
            {
                "index": index,
                "codepoint": f"U+{ord(char):04X}",
                "name": ZERO_WIDTH_CHARS[char],
            }
        )
    return found


def remove_zero_width_chars(text: str) -> str:
    return "".join(char for char in text if char not in ZERO_WIDTH_CHARS)
