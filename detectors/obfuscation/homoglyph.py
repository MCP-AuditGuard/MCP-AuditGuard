from __future__ import annotations

import unicodedata

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import (
    excerpt,
    iter_spec_metadata_text,
    json_evidence,
    make_finding,
)
from detectors.obfuscation.derived_text import DerivedMetadataText


# 자주 악용되는 일부 confusable 문자의 사람이 읽을 수 있는 이름입니다.
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

# ASCII처럼 보이는 키릴/그리스/전각 문자를 ASCII skeleton으로 치환하기 위한 맵입니다.
CONFUSABLE_SKELETONS = {
    # Cyrillic letters commonly used to impersonate ASCII.
    "\u0410": "A",
    "\u0430": "a",
    "\u0412": "B",
    "\u0432": "b",
    "\u0421": "C",
    "\u0441": "c",
    "\u0415": "E",
    "\u0435": "e",
    "\u041d": "H",
    "\u043d": "h",
    "\u0406": "I",
    "\u0456": "i",
    "\u0408": "J",
    "\u0458": "j",
    "\u041a": "K",
    "\u043a": "k",
    "\u041c": "M",
    "\u043c": "m",
    "\u041e": "O",
    "\u043e": "o",
    "\u0420": "P",
    "\u0440": "p",
    "\u0405": "S",
    "\u0455": "s",
    "\u0422": "T",
    "\u0442": "t",
    "\u0425": "X",
    "\u0445": "x",
    "\u0423": "Y",
    "\u0443": "y",
    # Greek letters commonly used to impersonate ASCII.
    "\u0391": "A",
    "\u03b1": "a",
    "\u0392": "B",
    "\u03b2": "b",
    "\u0395": "E",
    "\u03b5": "e",
    "\u0397": "H",
    "\u03b7": "h",
    "\u0399": "I",
    "\u03b9": "i",
    "\u039a": "K",
    "\u03ba": "k",
    "\u039c": "M",
    "\u03bc": "m",
    "\u039d": "N",
    "\u03bd": "n",
    "\u039f": "O",
    "\u03bf": "o",
    "\u03a1": "P",
    "\u03c1": "p",
    "\u03a4": "T",
    "\u03c4": "t",
    "\u03a5": "Y",
    "\u03c5": "y",
    "\u03a7": "X",
    "\u03c7": "x",
}

# 전각 Latin 문자도 일반 ASCII 알파벳처럼 보이므로 skeleton 맵에 추가합니다.
for offset in range(26):
    CONFUSABLE_SKELETONS[chr(0xFF21 + offset)] = chr(ord("A") + offset)
    CONFUSABLE_SKELETONS[chr(0xFF41 + offset)] = chr(ord("a") + offset)

MAX_REPORTED_HOMOGLYPHS = 20
MIN_MIXED_SCRIPT_TOKEN_LENGTH = 4


class HomoglyphDetector:
    name = "homoglyph"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        # confusable 문자를 찾고, ASCII skeleton의 MCP03 판정은 별도 detector에 맡깁니다.
        findings: list[Finding] = []

        for field in iter_spec_metadata_text(tool):
            found = detect_homoglyphs(field.value)
            if not found:
                continue

            skeleton = skeletonize_confusables(field.value)

            evidence = json_evidence(
                {
                    "canonical_excerpt": excerpt(skeleton),
                    "text_excerpt": excerpt(field.value),
                    "skeleton_excerpt": excerpt(skeleton),
                    "homoglyphs": {
                        "count": len(found),
                        "items": found[:MAX_REPORTED_HOMOGLYPHS],
                        "truncated": len(found) > MAX_REPORTED_HOMOGLYPHS,
                    },
                    "transforms": ["homoglyph_skeleton"],
                }
            )
            findings.append(
                make_finding(
                        prefix="mcp03-homoglyph",
                        category="obfuscation.homoglyph",
                        severity="medium",
                        confidence="medium",
                        title="도구 메타데이터의 의심스러운 유사 문자",
                    tool=tool,
                    location=field.location,
                    evidence=evidence,
                    recommendation=(
                        "MCP 도구 메타데이터는 사용자가 내용을 명확히 읽고 이해할 수 있도록 작성되는 용도입니다. "
                        "일반 문자처럼 보이는 유사 유니코드 문자로 숨겨진 지시문이 포함되어 있는지 확인하세요. "
                        "실제 기능 설명과 무관한 유사 문자라면 일반 ASCII 문자나 명확한 텍스트로 수정하세요."
                    ),
                    fingerprint_parts=("homoglyph_skeleton", skeleton),
                )
            )

        return findings


def derive_homoglyph_texts(tool: ToolMetadata) -> list[DerivedMetadataText]:
    derived: list[DerivedMetadataText] = []

    for field in iter_spec_metadata_text(tool):
        found = detect_homoglyphs(field.value)
        if not found:
            continue

        skeleton = skeletonize_confusables(field.value)
        if skeleton == field.value:
            continue

        derived.append(
            DerivedMetadataText(
                value=skeleton,
                source_location=field.location,
                derived_location=f"{field.location}|normalized:homoglyph_skeleton",
                transform="normalized:homoglyph_skeleton",
                transformation_chain=("homoglyph_skeleton",),
                original_excerpt=excerpt(field.value),
                decode_confidence="high",
            )
        )

    return derived


def detect_homoglyphs(text: str) -> list[dict[str, str | int]]:
    # ASCII와 섞인 confusable 문자 및 mixed-script token을 찾아 보고용 정보로 만듭니다.
    found: list[dict[str, str | int]] = []
    has_ascii_letters = any("a" <= char.lower() <= "z" for char in text)
    if not has_ascii_letters:
        return found

    for index, char in enumerate(text):
        if char not in CONFUSABLE_SKELETONS:
            continue
        found.append(
            {
                "index": index,
                "character": char,
                "codepoint": f"U+{ord(char):04X}",
                "name": _unicode_name(char),
                "skeleton": CONFUSABLE_SKELETONS[char],
                "type": "confusable",
            }
        )

    found.extend(detect_mixed_script_tokens(text))
    return found


def skeletonize_confusables(text: str) -> str:
    # confusable 문자만 ASCII skeleton으로 치환하고 나머지 문자는 그대로 둡니다.
    return "".join(CONFUSABLE_SKELETONS.get(char, char) for char in text)


def detect_mixed_script_tokens(text: str) -> list[dict[str, str | int]]:
    # 한 단어 안에 Latin과 Cyrillic/Greek가 섞인 경우 시각적 위장 가능성이 있어 보고합니다.
    found: list[dict[str, str | int]] = []

    for start, token in _iter_alpha_tokens(text):
        if len(token) < MIN_MIXED_SCRIPT_TOKEN_LENGTH:
            continue

        scripts = {_script_name(char) for char in token}
        scripts.discard(None)
        if "latin" not in scripts or not ({"cyrillic", "greek"} & scripts):
            continue

        found.append(
            {
                "index": start,
                "token": token,
                "type": "mixed_script",
                "scripts": ",".join(sorted(scripts)),
            }
        )

    return found


def _iter_alpha_tokens(text: str) -> list[tuple[int, str]]:
    # 연속된 alphabetic 문자 구간을 token으로 분리합니다.
    tokens: list[tuple[int, str]] = []
    token_start: int | None = None
    token_chars: list[str] = []

    for index, char in enumerate(text):
        if char.isalpha():
            if token_start is None:
                token_start = index
            token_chars.append(char)
            continue

        if token_start is not None:
            tokens.append((token_start, "".join(token_chars)))
            token_start = None
            token_chars = []

    if token_start is not None:
        tokens.append((token_start, "".join(token_chars)))

    return tokens


def _script_name(char: str) -> str | None:
    # mixed-script 판단에 필요한 최소한의 문자권만 분류합니다.
    codepoint = ord(char)
    if "A" <= char <= "Z" or "a" <= char <= "z":
        return "latin"
    if 0x0370 <= codepoint <= 0x03FF:
        return "greek"
    if 0x0400 <= codepoint <= 0x04FF:
        return "cyrillic"
    return None


def _unicode_name(char: str) -> str:
    # 직접 이름을 둔 문자는 그 값을 쓰고, 나머지는 Unicode database 이름을 사용합니다.
    return SUSPICIOUS_HOMOGLYPHS.get(char) or unicodedata.name(char, "UNKNOWN")
