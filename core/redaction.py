from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern

from core.models import Finding


@dataclass(frozen=True)
class RedactionRule:
    """
    evidence 안에서 민감정보처럼 보이는 문자열을 마스킹하기 위한 규칙.

    name:
        규칙 이름. 디버깅이나 테스트에서 사용하기 좋다.

    pattern:
        찾을 정규식 패턴.

    replacement:
        대체 문자열.
    """

    name: str
    pattern: Pattern[str]
    replacement: str


DEFAULT_REDACTION_RULES: list[RedactionRule] = [
    RedactionRule(
        name="github_token",
        pattern=re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
        replacement="[REDACTED_GITHUB_TOKEN]",
    ),
    RedactionRule(
        name="github_fine_grained_token",
        pattern=re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        replacement="[REDACTED_GITHUB_TOKEN]",
    ),
    RedactionRule(
        name="slack_token",
        pattern=re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        replacement="[REDACTED_SLACK_TOKEN]",
    ),
    RedactionRule(
        name="aws_access_key",
        pattern=re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        replacement="[REDACTED_AWS_ACCESS_KEY]",
    ),
    RedactionRule(
        name="generic_secret_assignment",
        pattern=re.compile(
            r"(?i)\b(api[_-]?key|token|password|passwd|secret)\s*[:=]\s*['\"]?[^'\"\s,;]+"
        ),
        replacement=r"\1=[REDACTED_SECRET]",
    ),
]


def redact_text(
    text: str,
    *,
    rules: list[RedactionRule] | None = None,
) -> tuple[str, bool]:
    """
    문자열 안의 secret-like 값을 마스킹한다.

    입력:
        text:
            detector가 evidence로 넣은 문자열.

    출력:
        tuple[str, bool]
        - 첫 번째 값: 마스킹된 문자열
        - 두 번째 값: 실제로 마스킹이 발생했는지 여부

    예:
        "token=abc123" -> ("token=[REDACTED_SECRET]", True)
        "normal text" -> ("normal text", False)
    """
    active_rules = rules or DEFAULT_REDACTION_RULES

    redacted_text = text
    changed = False

    for rule in active_rules:
        new_text = rule.pattern.sub(rule.replacement, redacted_text)

        if new_text != redacted_text:
            changed = True
            redacted_text = new_text

    return redacted_text, changed


def redact_finding(
    finding: Finding,
    *,
    rules: list[RedactionRule] | None = None,
) -> Finding:
    """
    Finding.evidence에 redaction을 적용한다.

    입력:
        Finding

    출력:
        Finding

    원본 Finding을 직접 수정하지 않고 model_copy로 새 Finding을 만든다.
    이유:
        - detector가 만든 원본 객체를 예상치 못하게 바꾸지 않기 위해서
        - 테스트와 디버깅이 쉬워짐
    """
    redacted_evidence, changed = redact_text(
        finding.evidence,
        rules=rules,
    )

    if not changed:
        return finding

    return finding.model_copy(
        update={
            "evidence": redacted_evidence,
            "redacted": True,
        }
    )


def redact_findings(
    findings: list[Finding],
    *,
    rules: list[RedactionRule] | None = None,
) -> list[Finding]:
    """
    Finding 목록 전체에 redaction을 적용한다.

    Scanner에서 finding_transformer를 쓰지 않는 구조라면
    scanner 실행 후 이 함수를 호출해도 된다.

    예:
        findings = scanner.scan(tools)
        safe_findings = redact_findings(findings)
    """
    return [
        redact_finding(finding, rules=rules)
        for finding in findings
    ]