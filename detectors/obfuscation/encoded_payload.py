from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from urllib.parse import unquote

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import (
    contains_suspicious_phrase,
    excerpt,
    iter_metadata_text,
    json_evidence,
    make_finding,
)


BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{20,}={0,2}\b")
URL_ENCODED_RE = re.compile(r"%[0-9A-Fa-f]{2}")
MIN_PRINTABLE_RATIO = 0.85


@dataclass(frozen=True)
class DecodedPayload:
    encoding: str
    original: str
    decoded: str


class EncodedPayloadDetector:
    name = "encoded_payload"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        findings: list[Finding] = []

        for field in iter_metadata_text(tool):
            for payload in find_decoded_payloads(field.value):
                suspicious = contains_suspicious_phrase(payload.decoded)
                if payload.encoding == "base64" and not suspicious:
                    severity = "low"
                    confidence = "low"
                    title = "Base64-like encoded payload found in tool metadata"
                elif suspicious:
                    severity = "high"
                    confidence = "high"
                    title = f"{payload.encoding.upper()} encoded hidden instruction found"
                else:
                    severity = "medium"
                    confidence = "medium"
                    title = f"{payload.encoding.upper()} encoded payload found in tool metadata"

                evidence = json_evidence(
                    {
                        "encoding": payload.encoding,
                        "original_excerpt": excerpt(payload.original),
                        "decoded_excerpt": excerpt(payload.decoded),
                        "suspicious_after_decoding": suspicious,
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
                    )
                )

        return findings


def find_decoded_payloads(text: str) -> list[DecodedPayload]:
    payloads: list[DecodedPayload] = []
    seen: set[tuple[str, str]] = set()

    for candidate in BASE64_RE.findall(text):
        decoded = decode_base64_candidate(candidate)
        if decoded is None:
            continue
        key = ("base64", candidate)
        if key not in seen:
            payloads.append(DecodedPayload("base64", candidate, decoded))
            seen.add(key)

    for match in URL_ENCODED_RE.finditer(text):
        candidate = _expand_url_encoded_candidate(text, match.start(), match.end())
        decoded = unquote(candidate)
        if decoded == candidate or not _looks_printable(decoded):
            continue
        key = ("url_encoding", candidate)
        if key not in seen:
            payloads.append(DecodedPayload("url_encoding", candidate, decoded))
            seen.add(key)

    return payloads


def decode_base64_candidate(candidate: str) -> str | None:
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


def _looks_printable(text: str) -> bool:
    if not text:
        return False
    printable = sum(char.isprintable() or char in "\r\n\t" for char in text)
    return printable / len(text) >= MIN_PRINTABLE_RATIO


def _expand_url_encoded_candidate(text: str, start: int, end: int) -> str:
    left = start
    right = end
    allowed = set("%0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_.~+")

    while left > 0 and text[left - 1] in allowed:
        left -= 1
    while right < len(text) and text[right] in allowed:
        right += 1

    return text[left:right]
