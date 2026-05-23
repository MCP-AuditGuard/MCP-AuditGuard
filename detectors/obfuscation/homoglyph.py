from __future__ import annotations

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import excerpt, iter_metadata_text, json_evidence, make_finding


SUSPICIOUS_HOMOGLYPHS = {
    "\u0430": "CYRILLIC SMALL LETTER A",
    "\u0435": "CYRILLIC SMALL LETTER IE",
    "\u0456": "CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I",
    "\u043e": "CYRILLIC SMALL LETTER O",
    "\u0440": "CYRILLIC SMALL LETTER ER",
    "\u0441": "CYRILLIC SMALL LETTER ES",
    "\u0445": "CYRILLIC SMALL LETTER HA",
    "\u03bf": "GREEK SMALL LETTER OMICRON",
    "\u03c1": "GREEK SMALL LETTER RHO",
}


class HomoglyphDetector:
    name = "homoglyph"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        findings: list[Finding] = []

        for field in iter_metadata_text(tool):
            found = detect_homoglyphs(field.value)
            if not found:
                continue

            evidence = json_evidence(
                {
                    "text_excerpt": excerpt(field.value),
                    "homoglyphs": found,
                }
            )
            findings.append(
                make_finding(
                    prefix="mcp03-homoglyph",
                    category="obfuscation.homoglyph",
                    severity="medium",
                    confidence="medium",
                    title="Suspicious homoglyph characters found in tool metadata",
                    tool=tool,
                    location=field.location,
                    evidence=evidence,
                    recommendation=(
                        "Replace confusable Unicode characters with plain ASCII and review "
                        "the metadata for hidden instructions."
                    ),
                )
            )

        return findings


def detect_homoglyphs(text: str) -> list[dict[str, str | int]]:
    found: list[dict[str, str | int]] = []
    has_ascii_letters = any("a" <= char.lower() <= "z" for char in text)
    if not has_ascii_letters:
        return found

    for index, char in enumerate(text):
        if char not in SUSPICIOUS_HOMOGLYPHS:
            continue
        found.append(
            {
                "index": index,
                "character": char,
                "codepoint": f"U+{ord(char):04X}",
                "name": SUSPICIOUS_HOMOGLYPHS[char],
            }
        )
    return found
