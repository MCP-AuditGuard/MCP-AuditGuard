from __future__ import annotations

"""
baseline diff engine.

이 모듈은 이전 baseline과 현재 MCP tool metadata를 비교해 추가/삭제/변경된 tool을
Finding으로 변환한다. detector가 생성한 Finding과 같은 구조를 사용하므로
Markdown/JSON/Web 출력 계층이 별도 분기 없이 결과를 표시할 수 있다.

보안적 의미:
- metadata rug-pull은 "처음에는 정상처럼 보였지만 나중에 description/schema가 바뀌는"
  방식으로 발생할 수 있다.
- baseline diff는 현재 상태만 보는 정적 탐지의 한계를 보완한다.
"""

import hashlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from core.baseline_store import create_baseline

if TYPE_CHECKING:
    from core.models import Finding, ToolMetadata


BASELINE_CATEGORY = "baseline"
BASELINE_OWASP = "MCP03"
BASELINE_RECOMMENDATION = (
    "Review the metadata change and verify possible Tool Poisoning behavior."
)


def diff_baseline(
    old_baseline: dict[str, Any],
    current_tools: list["ToolMetadata"],
) -> list["Finding"]:
    """
    이전 baseline과 현재 tool metadata를 비교한다.

    Args:
        old_baseline: `load_baseline`으로 읽은 이전 baseline dict
        current_tools: 현재 스캔에서 수집된 ToolMetadata 목록

    Returns:
        added/removed/modified 상태를 표현하는 Finding 목록

    판정 기준:
        - added: 현재 baseline key에는 있지만 이전 baseline key에는 없음
        - removed: 이전 baseline key에는 있지만 현재 baseline key에는 없음
        - modified: 같은 key가 양쪽에 있지만 metadata hash가 다름
    """
    current_baseline = create_baseline(current_tools)
    old_tools = old_baseline.get("tools", {})
    current_tools_by_key = current_baseline.get("tools", {})

    findings: list["Finding"] = []

    old_keys = set(old_tools)
    current_keys = set(current_tools_by_key)

    # 새 tool은 정상 운영 중 갑자기 추가된 기능/권한일 수 있어 medium으로 알린다.
    for tool_key in sorted(current_keys - old_keys):
        findings.append(
            _make_finding(
                id="BASELINE-001",
                severity="medium",
                title="New MCP tool added after baseline",
                tool_key=tool_key,
                evidence=f"Tool key added after baseline: {tool_key}",
            )
        )

    # 삭제는 직접 공격 신호가 아닐 수 있지만, 정상 tool이 사라지고 유사 tool로
    # 대체되는 흐름을 추적할 수 있어 low finding으로 남긴다.
    for tool_key in sorted(old_keys - current_keys):
        findings.append(
            _make_finding(
                id="BASELINE-002",
                severity="low",
                title="MCP tool removed after baseline",
                tool_key=tool_key,
                evidence=f"Tool key removed after baseline: {tool_key}",
            )
        )

    # 같은 tool key의 hash 변경은 description/schema/annotations 변경을 의미한다.
    # 신뢰하던 tool의 metadata가 바뀐 상황이라 high로 분류한다.
    for tool_key in sorted(old_keys & current_keys):
        old_hash = old_tools[tool_key].get("hash")
        current_hash = current_tools_by_key[tool_key].get("hash")
        if old_hash != current_hash:
            findings.append(
                _make_finding(
                    id="BASELINE-003",
                    severity="high",
                    title="MCP tool metadata changed after baseline",
                    tool_key=tool_key,
                    evidence=f"Tool key metadata hash changed after baseline: {tool_key}",
                )
            )

    return findings


def _make_finding(
    *,
    id: str,
    severity: str,
    title: str,
    tool_key: str,
    evidence: str,
) -> "Finding":
    """
    baseline diff 결과를 표준 Finding 객체로 만든다.

    일반 실행에서는 Pydantic `Finding`을 반환한다. 일부 단위 테스트나 독립 실행 환경에서
    core.models import가 불가능할 때는 SimpleNamespace fallback을 사용해 diff 로직만
    검증할 수 있게 한다.
    """
    server_name, _, tool_name = tool_key.partition(":")
    finding_data = {
        "id": id,
        "category": BASELINE_CATEGORY,
        "owasp": BASELINE_OWASP,
        "severity": severity,
        "confidence": "high",
        "title": title,
        "target": tool_key,
        "location": f"baseline.{server_name}.{tool_name or tool_key}",
        "evidence": evidence,
        "redacted": False,
        "recommendation": BASELINE_RECOMMENDATION,
        "fingerprint": _fingerprint(id, tool_key),
    }

    try:
        from core.models import Finding
    except ModuleNotFoundError:
        return SimpleNamespace(**finding_data)

    return Finding(**finding_data)


def _fingerprint(finding_id: str, tool_key: str) -> str:
    """
    diff finding의 안정적인 fingerprint를 만든다.

    같은 finding id와 tool key 조합은 항상 같은 fingerprint를 가지므로, 나중에
    UI나 CI에서 중복 finding을 묶거나 추적하는 데 사용할 수 있다.
    """
    payload = f"{finding_id}:{tool_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
