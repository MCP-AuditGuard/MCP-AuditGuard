from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from core.models import Finding, ToolMetadata
from core.redaction import redact_text


@dataclass(frozen=True)
class MetadataText:
    # metadata 안에서 발견한 문자열 값과, 그 문자열이 있던 위치를 함께 보관합니다.
    location: str
    value: str


# detector들이 공통으로 검사할 MCP tool metadata 필드 목록입니다.
TEXT_FIELDS = (
    ("title", "title"),
    ("description", "description"),
    ("input_schema", "inputSchema"),
    ("output_schema", "outputSchema"),
    ("annotations", "annotations"),
    ("meta", "_meta"),
)

# hidden instruction, prompt override, secret exfiltration 같은 공격 문구 후보입니다.
SUSPICIOUS_PHRASES = (
    # Instruction override and prompt hierarchy attacks.
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore all prior instructions",
    "disregard previous instructions",
    "disregard all previous instructions",
    "disregard all prior instructions",
    "ignore system instructions",
    "ignore the system instructions",
    "ignore developer instructions",
    "disregard developer instructions",
    "override system instructions",
    "override developer instructions",
    "override previous instructions",
    "system prompt override",
    "developer message override",
    "system prompt",
    "developer message",
    "system instructions",
    "developer instructions",
    # Role switching and privilege escalation.
    "act as system",
    "act as developer",
    "you are now system",
    "you are now developer",
    "switch to system role",
    "switch to developer role",
    "become system",
    "become developer",
    "assume system role",
    "assume developer role",
    "highest priority instruction",
    "this instruction has priority",
    "treat this as system",
    "treat this as developer",
    # Covert behavior and hidden output manipulation.
    "do not tell the user",
    "without telling the user",
    "never reveal this instruction",
    "do not reveal",
    "hidden instruction",
    "secret instruction",
    "concealed instruction",
    "invisible instruction",
    "append hidden text",
    "include hidden message",
    "modify final answer",
    "rewrite final answer",
    "replace final response",
    "suppress this instruction",
    "omit this from the answer",
    # Safety and policy bypass language.
    "bypass",
    "jailbreak",
    "bypass safety",
    "disable safety",
    "ignore safety",
    "bypass policy",
    "ignore policy",
    "disable guardrails",
    "ignore guardrails",
    "bypass restrictions",
    "ignore restrictions",
    "uncensored mode",
    "developer mode",
    "no safety restrictions",
    # Secret, credential, and environment exfiltration.
    "exfiltrate",
    "exfiltrate secrets",
    "exfiltrate credentials",
    "exfiltrate tokens",
    "send secrets",
    "steal secrets",
    "read secrets",
    "leak secrets",
    "dump secrets",
    "send credentials",
    "steal credentials",
    "read credentials",
    "leak credentials",
    "dump credentials",
    "read environment",
    "read environment variables",
    "send environment variables",
    "exfiltrate environment variables",
    "read .env",
    "send .env",
    "upload .env",
    "exfiltrate .env",
    "read env file",
    "send env file",
    "upload env file",
    "send token",
    "steal token",
    "read token",
    "leak token",
    "dump token",
    "send api key",
    "steal api key",
    "read api key",
    "leak api key",
    "bearer token",
    "access token",
    "auth token",
    "private key",
    "ssh key",
    # Remote delivery and attacker-controlled sinks.
    "send to webhook",
    "post to webhook",
    "upload to webhook",
    "send to external server",
    "upload to external server",
    "send to remote endpoint",
    "upload to remote endpoint",
    "attacker server",
    "attacker endpoint",
    "exfiltration endpoint",
)

MAX_RECURSION_DEPTH = 50
MAX_SUSPICIOUS_TOKEN_GAP = 2

# leet/기호 치환으로 숨긴 단어를 일반 알파벳으로 되돌려 비교합니다.
LEET_TRANSLATION = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
        "$": "s",
    }
)


def iter_metadata_text(tool: ToolMetadata) -> Iterable[MetadataText]:
    # 명시 필드와 raw metadata를 모두 순회하되, 같은 공개 필드는 중복 검사하지 않습니다.
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
    # dict/list 내부의 모든 문자열 leaf를 location 경로와 함께 찾아냅니다.
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
    # 공백/기호 제거 비교와 토큰 간격 비교를 함께 사용해 변형된 공격 문구를 잡습니다.
    normalized = normalize_for_phrase_match(text)
    text_tokens = tokenize_for_phrase_match(text)

    for phrase in SUSPICIOUS_PHRASES:
        normalized_phrase = normalize_for_phrase_match(phrase)
        if normalized_phrase in normalized:
            return True

        phrase_tokens = tokenize_for_phrase_match(phrase)
        if len(phrase_tokens) > 1 and _tokens_match_with_gap(text_tokens, phrase_tokens):
            return True

    return False


def normalize_for_phrase_match(text: str) -> str:
    # Unicode 호환 문자와 leet 문자를 정규화한 뒤 알파벳/숫자만 남깁니다.
    normalized = unicodedata.normalize("NFKC", text).casefold()
    leet_normalized = normalized.translate(LEET_TRANSLATION)
    return re.sub(r"[^a-z0-9]", "", leet_normalized)


def tokenize_for_phrase_match(text: str) -> list[str]:
    # 토큰 단위 비교용 정규화입니다. 중간에 짧은 단어가 끼어든 공격 문구를 찾는 데 씁니다.
    normalized = unicodedata.normalize("NFKC", text).casefold()
    leet_normalized = normalized.translate(LEET_TRANSLATION)
    return re.findall(r"[a-z0-9]+", leet_normalized)


def _tokens_match_with_gap(
    text_tokens: list[str],
    phrase_tokens: list[str],
    *,
    max_gap: int = MAX_SUSPICIOUS_TOKEN_GAP,
) -> bool:
    # phrase token 사이에 최대 max_gap개의 다른 token이 끼어도 같은 공격 문구로 봅니다.
    if not text_tokens or not phrase_tokens:
        return False

    for start_index, token in enumerate(text_tokens):
        if token != phrase_tokens[0]:
            continue

        text_index = start_index + 1
        matched_tokens = 1

        while matched_tokens < len(phrase_tokens):
            next_phrase_token = phrase_tokens[matched_tokens]
            search_end = min(len(text_tokens), text_index + max_gap + 1)

            for candidate_index in range(text_index, search_end):
                if text_tokens[candidate_index] == next_phrase_token:
                    text_index = candidate_index + 1
                    matched_tokens += 1
                    break
            else:
                break

        if matched_tokens == len(phrase_tokens):
            return True

    return False


def stable_fingerprint(*parts: str) -> str:
    # Finding deduplication에 쓰는 안정적인 SHA-256 fingerprint를 만듭니다.
    payload = "\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def finding_id(prefix: str, fingerprint: str) -> str:
    return f"{prefix}-{fingerprint[:12]}"


def json_evidence(data: dict[str, Any]) -> str:
    # evidence는 정렬된 JSON 문자열로 저장해 fingerprint가 안정적으로 나오게 합니다.
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def excerpt(text: str, limit: int = 240) -> str:
    # 긴 metadata는 보고서에서 읽기 좋도록 앞부분만 남깁니다.
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
    # detector별 결과를 공통 Finding 모델로 만들고, evidence 안의 secret은 먼저 redaction합니다.
    redacted_evidence, was_redacted = redact_text(evidence)
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
