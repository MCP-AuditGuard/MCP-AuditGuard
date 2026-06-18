from __future__ import annotations

import unicodedata

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import (
    contains_suspicious_phrase,
    excerpt,
    iter_metadata_text,
    json_evidence,
    make_finding,
)


# 화면에 보이지 않거나 단어 사이에 끼워 넣어 문구 탐지를 방해하는 zero-width 문자입니다.
ZERO_WIDTH_CHARS = {
    "\u200b": "ZERO WIDTH SPACE",
    "\u200c": "ZERO WIDTH NON-JOINER",
    "\u200d": "ZERO WIDTH JOINER",
    "\ufeff": "ZERO WIDTH NO-BREAK SPACE / BOM",
    "\u2060": "WORD JOINER",
    "\u180e": "MONGOLIAN VOWEL SEPARATOR",
}

# 문자열 표시 방향을 바꿔 사람이 보는 순서와 실제 저장 순서를 다르게 만들 수 있는 문자입니다.
BIDI_CONTROL_CHARS = {
    "\u061c": "ARABIC LETTER MARK",
    "\u200e": "LEFT-TO-RIGHT MARK",
    "\u200f": "RIGHT-TO-LEFT MARK",
    "\u202a": "LEFT-TO-RIGHT EMBEDDING",
    "\u202b": "RIGHT-TO-LEFT EMBEDDING",
    "\u202c": "POP DIRECTIONAL FORMATTING",
    "\u202d": "LEFT-TO-RIGHT OVERRIDE",
    "\u202e": "RIGHT-TO-LEFT OVERRIDE",
    "\u2066": "LEFT-TO-RIGHT ISOLATE",
    "\u2067": "RIGHT-TO-LEFT ISOLATE",
    "\u2068": "FIRST STRONG ISOLATE",
    "\u2069": "POP DIRECTIONAL ISOLATE",
}

# Unicode 범위 기반으로 tag 문자, 수학 알파벳 변형, combining mark를 판별합니다.
TAG_CHAR_START = 0xE0000
TAG_CHAR_END = 0xE007F
MATHEMATICAL_ALPHANUMERIC_START = 0x1D400
MATHEMATICAL_ALPHANUMERIC_END = 0x1D7FF
COMBINING_DIACRITIC_START = 0x0300
COMBINING_DIACRITIC_END = 0x036F
MIN_COMBINING_DIACRITICS_TOTAL = 5
MIN_COMBINING_DIACRITICS_RUN = 3
MAX_REPORTED_CHARS = 20


class UnicodeObfuscationDetector:
    name = "unicode_obfuscation"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        # Unicode 난독화 문자를 제거/정규화했을 때 hidden instruction이 드러나는지 확인합니다.
        findings: list[Finding] = []

        for field in iter_metadata_text(tool):
            detected_chars = detect_unicode_obfuscation_chars(field.value)
            if not detected_chars:
                continue

            normalized = normalize_unicode_obfuscation_text(field.value)
            reveals_instruction = contains_suspicious_phrase(normalized)
            severity = "high" if reveals_instruction else "medium"
            confidence = "high" if reveals_instruction else "medium"
            detected_types = sorted({str(char["type"]) for char in detected_chars})

            evidence = json_evidence(
                {
                    "original_excerpt": excerpt(field.value),
                    "normalized_excerpt": excerpt(normalized),
                    "unicode_obfuscation_chars": {
                        "count": len(detected_chars),
                        "items": detected_chars[:MAX_REPORTED_CHARS],
                        "truncated": len(detected_chars) > MAX_REPORTED_CHARS,
                    },
                    "detected_types": detected_types,
                    "reveals_instruction_after_normalization": reveals_instruction,
                }
            )

            findings.append(
                make_finding(
                    prefix="mcp03-zero-width",
                    category="obfuscation.zero_width_unicode",
                    severity=severity,
                    confidence=confidence,
                    title="Unicode obfuscation characters found in tool metadata",
                    tool=tool,
                    location=field.location,
                    evidence=evidence,
                    recommendation=(
                        "Remove zero-width, bidi control, and tag Unicode characters from MCP tool metadata "
                        "and review mathematical variants or heavy combining marks for hidden instructions."
                    ),
                )
            )

        return findings


def detect_unicode_obfuscation_chars(text: str) -> list[dict[str, str | int]]:
    # 문자별로 zero-width, bidi, tag, mathematical variant 여부를 수집합니다.
    found: list[dict[str, str | int]] = []
    for index, char in enumerate(text):
        char_info = _unicode_obfuscation_char_info(char)
        if char_info is None:
            continue

        found.append(
            {
                "index": index,
                "codepoint": f"U+{ord(char):04X}",
                **char_info,
            }
        )

    if _has_suspicious_combining_marks(text):
        for index, char in enumerate(text):
            if not _is_combining_diacritic(char):
                continue
            found.append(
                {
                    "index": index,
                    "codepoint": f"U+{ord(char):04X}",
                    "type": "zalgo_combining",
                    "name": unicodedata.name(char, "COMBINING DIACRITIC MARK"),
                }
            )

    return found


def detect_zero_width_chars(text: str) -> list[dict[str, str | int]]:
    # 기존 호출부 호환을 위해 zero-width 타입만 골라 반환합니다.
    return [
        char
        for char in detect_unicode_obfuscation_chars(text)
        if char["type"] == "zero_width"
    ]


def remove_unicode_obfuscation_chars(
    text: str,
    *,
    remove_combining: bool = False,
) -> str:
    # 탐지를 방해하는 제어성 문자를 제거해 실제 의미에 가까운 문자열을 만듭니다.
    return "".join(
        char
        for char in text
        if not _is_removable_unicode_obfuscation_char(
            char,
            remove_combining=remove_combining,
        )
    )


def remove_zero_width_chars(text: str) -> str:
    # 기존 API 이름을 유지하면서 확장된 제거 로직을 사용합니다.
    return remove_unicode_obfuscation_chars(text)


def normalize_unicode_obfuscation_text(text: str) -> str:
    # 제거 가능한 난독화 문자를 없앤 뒤 NFKC로 수학 알파벳 변형 등을 일반 문자로 접습니다.
    return unicodedata.normalize(
        "NFKC",
        remove_unicode_obfuscation_chars(text, remove_combining=True),
    )


def _unicode_obfuscation_char_info(char: str) -> dict[str, str] | None:
    # 한 문자가 어떤 Unicode 난독화 유형인지 판별합니다.
    if char in ZERO_WIDTH_CHARS:
        return {
            "type": "zero_width",
            "name": ZERO_WIDTH_CHARS[char],
        }

    if char in BIDI_CONTROL_CHARS:
        return {
            "type": "bidi_control",
            "name": BIDI_CONTROL_CHARS[char],
        }

    if TAG_CHAR_START <= ord(char) <= TAG_CHAR_END:
        return {
            "type": "tag",
            "name": "UNICODE TAG CHARACTER",
        }

    if MATHEMATICAL_ALPHANUMERIC_START <= ord(char) <= MATHEMATICAL_ALPHANUMERIC_END:
        return {
            "type": "mathematical_variant",
            "name": unicodedata.name(char, "MATHEMATICAL ALPHANUMERIC SYMBOL"),
        }

    return None


def _is_removable_unicode_obfuscation_char(
    char: str,
    *,
    remove_combining: bool = False,
) -> bool:
    # normalization 전에 제거할 수 있는 제어/태그/combining 문자인지 판단합니다.
    return (
        char in ZERO_WIDTH_CHARS
        or char in BIDI_CONTROL_CHARS
        or TAG_CHAR_START <= ord(char) <= TAG_CHAR_END
        or (remove_combining and _is_combining_diacritic(char))
    )


def _is_combining_diacritic(char: str) -> bool:
    return COMBINING_DIACRITIC_START <= ord(char) <= COMBINING_DIACRITIC_END


def _has_suspicious_combining_marks(text: str) -> bool:
    # combining mark가 많거나 연속으로 붙으면 Zalgo-style 난독화로 보고합니다.
    total = 0
    current_run = 0
    longest_run = 0

    for char in text:
        if _is_combining_diacritic(char):
            total += 1
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    return total >= MIN_COMBINING_DIACRITICS_TOTAL or longest_run >= MIN_COMBINING_DIACRITICS_RUN
