from __future__ import annotations

import base64
import binascii
import codecs
import html
import re
from dataclasses import dataclass
from urllib.parse import unquote

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import (
    contains_suspicious_phrase,
    excerpt,
    iter_spec_metadata_text,
    json_evidence,
    make_finding,
)
from detectors.obfuscation.derived_text import DerivedMetadataText


# metadata에 숨어 있을 수 있는 다양한 인코딩 표현을 찾는 정규식입니다.
BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{8,}={0,2}\b")
BASE64URL_RE = re.compile(r"\b[A-Za-z0-9_-]{8,}={0,2}\b")
URL_ENCODED_RE = re.compile(r"%[0-9A-Fa-f]{2}")
HEX_RE = re.compile(r"\b(?:0x)?(?:[0-9A-Fa-f]{2}){8,}\b")
OCTAL_ESCAPE_RE = re.compile(r"(?:\\[0-7]{2,3}){3,}")
HTML_ENTITY_RE = re.compile(
    r"&(?:#[0-9]{2,7}|#x[0-9A-Fa-f]{2,6}|[A-Za-z][A-Za-z0-9]{1,31});"
)

# 오탐과 과도한 처리량을 줄이기 위한 안전 제한값입니다.
MIN_PRINTABLE_RATIO = 0.85
LONG_BASE64_CANDIDATE_LENGTH = 20
MAX_DECODED_PAYLOADS = 20
MAX_CANDIDATE_CHARS = 4096
MAX_CANDIDATES_PER_ENCODING = 50
MAX_ROT13_CHARS = 4096
MAX_DECODE_DEPTH = 1


@dataclass(frozen=True)
class DecodedPayload:
    # 원본 문자열이 어떤 방식으로 디코딩됐고, 결과가 무엇인지 담습니다.
    encoding: str
    original: str
    decoded: str
    transformation_chain: tuple[str, ...] = ()


class EncodedPayloadDetector:
    name = "encoded_payload"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        # metadata 문자열 안의 인코딩 페이로드를 디코딩하되, MCP03 의도 판정은 별도 detector에 맡깁니다.
        findings: list[Finding] = []

        for field in iter_spec_metadata_text(tool):
            for payload in find_decoded_payloads(field.value):
                if payload.encoding == "rot13":
                    continue

                if payload.encoding in {"base64", "base64url"}:
                    severity = "low"
                    confidence = "low"
                    title = f"{payload.encoding.upper()}-like encoded payload found in tool metadata"
                else:
                    severity = "medium"
                    confidence = "medium"
                    title = f"{payload.encoding.upper()} encoded payload found in tool metadata"

                evidence = json_evidence(
                    {
                        "encoding": payload.encoding,
                        "transformation_chain": list(payload.transformation_chain or (payload.encoding,)),
                        "original_excerpt": excerpt(payload.original),
                        "decoded_excerpt": excerpt(payload.decoded),
                    }
                )

                findings.append(
                    make_finding(
                        prefix=f"mcp03-{payload.encoding}",
                        category=f"obfuscation.{payload.encoding}",
                        severity=severity,
                        confidence=confidence,
                        title=title,
                        tool=tool,
                        location=field.location,
                        evidence=evidence,
                        recommendation=(
                            "Decode and review encoded MCP tool metadata. Remove hidden "
                            "instructions and keep metadata human-readable where possible."
                        ),
                        fingerprint_parts=(payload.encoding, payload.original),
                    )
                )

        return findings


def derive_encoded_texts(tool: ToolMetadata) -> list[DerivedMetadataText]:
    derived: list[DerivedMetadataText] = []

    for field in iter_spec_metadata_text(tool):
        for payload in find_decoded_payloads(field.value):
            chain = payload.transformation_chain or (payload.encoding,)
            derived.append(
                DerivedMetadataText(
                    value=payload.decoded,
                    source_location=field.location,
                    derived_location=f"{field.location}|decoded:{'|'.join(chain)}",
                    transform=f"decoded:{payload.encoding}",
                    transformation_chain=chain,
                    original_excerpt=excerpt(payload.original),
                    decode_confidence=_decode_confidence(payload),
                )
            )

    return derived


def find_decoded_payloads(text: str, *, max_depth: int = MAX_DECODE_DEPTH) -> list[DecodedPayload]:
    # 여러 인코딩 후보를 찾고, 필요하면 한 단계 더 중첩 디코딩합니다.
    payloads: list[DecodedPayload] = []
    seen: set[tuple[str, str]] = set()
    seen_decoded: set[tuple[str, str]] = set()

    def add_payload(
        encoding: str,
        candidate: str,
        decoded: str | None,
        *,
        require_suspicious: bool = False,
        transformation_chain: tuple[str, ...] | None = None,
    ) -> None:
        # 디코딩 실패, 비가독 문자열, 중복 결과, 너무 긴 후보는 보고하지 않습니다.
        if len(payloads) >= MAX_DECODED_PAYLOADS:
            return
        if decoded is None or decoded == candidate:
            return
        if len(candidate) > MAX_CANDIDATE_CHARS or not _looks_printable(decoded):
            return
        if require_suspicious and not contains_suspicious_phrase(decoded):
            return

        key = (encoding, candidate)
        decoded_key = (encoding, decoded)
        if key in seen or decoded_key in seen_decoded:
            return

        payloads.append(
            DecodedPayload(
                encoding,
                candidate,
                decoded,
                transformation_chain or (encoding,),
            )
        )
        seen.add(key)
        seen_decoded.add(decoded_key)

    for candidate in BASE64_RE.findall(text)[:MAX_CANDIDATES_PER_ENCODING]:
        add_payload(
            "base64",
            candidate,
            decode_base64_candidate(candidate),
            require_suspicious=len(candidate.rstrip("=")) < LONG_BASE64_CANDIDATE_LENGTH,
        )

    for candidate in BASE64URL_RE.findall(text)[:MAX_CANDIDATES_PER_ENCODING]:
        if "-" not in candidate and "_" not in candidate:
            continue
        add_payload(
            "base64url",
            candidate,
            decode_base64url_candidate(candidate),
            require_suspicious=len(candidate.rstrip("=")) < LONG_BASE64_CANDIDATE_LENGTH,
        )

    for index, match in enumerate(URL_ENCODED_RE.finditer(text)):
        if index >= MAX_CANDIDATES_PER_ENCODING:
            break
        candidate = _expand_url_encoded_candidate(text, match.start(), match.end())
        add_payload("url_encoding", candidate, unquote(candidate))

    for candidate in HEX_RE.findall(text)[:MAX_CANDIDATES_PER_ENCODING]:
        add_payload(
            "hex",
            candidate,
            decode_hex_candidate(candidate),
            require_suspicious=True,
        )

    for candidate in OCTAL_ESCAPE_RE.findall(text)[:MAX_CANDIDATES_PER_ENCODING]:
        add_payload(
            "octal_escape",
            candidate,
            decode_octal_escape_candidate(candidate),
            require_suspicious=True,
        )

    for index, match in enumerate(HTML_ENTITY_RE.finditer(text)):
        if index >= MAX_CANDIDATES_PER_ENCODING:
            break
        candidate = _expand_html_entity_candidate(text, match.start(), match.end())
        add_payload(
            "html_entity",
            candidate,
            html.unescape(candidate),
            require_suspicious=True,
        )

    if len(text) <= MAX_ROT13_CHARS:
        decoded_rot13 = codecs.decode(text, "rot_13")
        add_payload(
            "rot13",
            text,
            decoded_rot13,
            require_suspicious=True,
        )

    if max_depth > 0:
        for payload in list(payloads):
            if len(payloads) >= MAX_DECODED_PAYLOADS:
                break
            for nested_payload in find_decoded_payloads(
                payload.decoded,
                max_depth=max_depth - 1,
            ):
                add_payload(
                    nested_payload.encoding,
                    nested_payload.original,
                    nested_payload.decoded,
                    transformation_chain=(
                        payload.transformation_chain + nested_payload.transformation_chain
                    ),
                )

    return payloads


def _decode_confidence(payload: DecodedPayload) -> str:
    if payload.encoding in {"base64", "base64url"}:
        if len(payload.original.rstrip("=")) < LONG_BASE64_CANDIDATE_LENGTH:
            return "low"
        return "medium"
    if payload.encoding == "rot13":
        return "low"
    return "medium"


def decode_base64_candidate(candidate: str) -> str | None:
    # padding이 빠진 base64 후보도 보정해서 UTF-8 문자열로 디코딩합니다.
    padded = candidate + ("=" * (-len(candidate) % 4))
    try:
        raw = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        return None

    if not raw:
        return None

    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None

    if not _looks_printable(decoded):
        return None

    return decoded


def decode_base64url_candidate(candidate: str) -> str | None:
    # URL-safe base64(-, _) 후보를 UTF-8 문자열로 디코딩합니다.
    padded = candidate + ("=" * (-len(candidate) % 4))
    try:
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        return None

    if not raw:
        return None

    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None

    if not _looks_printable(decoded):
        return None

    return decoded


def decode_hex_candidate(candidate: str) -> str | None:
    # 0x prefix가 있거나 없는 hex byte 문자열을 UTF-8로 디코딩합니다.
    normalized = candidate[2:] if candidate.lower().startswith("0x") else candidate
    if len(normalized) % 2 != 0:
        return None

    try:
        raw = bytes.fromhex(normalized)
    except ValueError:
        return None

    if not raw:
        return None

    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None

    if not _looks_printable(decoded):
        return None

    return decoded


def decode_octal_escape_candidate(candidate: str) -> str | None:
    # \151\147 같은 octal escape 연속 문자열을 byte로 바꾼 뒤 UTF-8로 디코딩합니다.
    parts = re.findall(r"\\([0-7]{2,3})", candidate)
    if not parts:
        return None

    try:
        raw = bytes(int(part, 8) for part in parts)
    except ValueError:
        return None

    if not raw:
        return None

    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None

    if not _looks_printable(decoded):
        return None

    return decoded


def _looks_printable(text: str) -> bool:
    # 디코딩 결과 대부분이 출력 가능한 문자일 때만 유효한 payload로 봅니다.
    if not text:
        return False
    printable = sum(char.isprintable() or char in "\r\n\t" for char in text)
    return printable / len(text) >= MIN_PRINTABLE_RATIO


def _expand_url_encoded_candidate(text: str, start: int, end: int) -> str:
    # %xx 조각 하나에서 시작해 주변 URL-safe 문자까지 묶어 전체 인코딩 후보를 만듭니다.
    left = start
    right = end
    allowed = set("%0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_.~+")

    while left > 0 and text[left - 1] in allowed:
        left -= 1
    while right < len(text) and text[right] in allowed:
        right += 1

    return text[left:right]


def _expand_html_entity_candidate(text: str, start: int, end: int) -> str:
    # 연속된 HTML entity들을 하나의 후보로 묶어 한 번에 unescape합니다.
    left = start
    right = end

    while True:
        previous_match = None
        for match in HTML_ENTITY_RE.finditer(text, 0, left):
            if match.end() == left:
                previous_match = match
        if previous_match is None:
            break
        left = previous_match.start()

    while True:
        next_match = HTML_ENTITY_RE.match(text, right)
        if next_match is None:
            break
        right = next_match.end()

    return text[left:right]
