from __future__ import annotations

"""
baseline diff engine.

이 모듈은 이전 baseline과 현재 수집한 MCP tool metadata를 비교해
추가/삭제/변경된 tool을 Finding으로 변환한다.

Member5 담당 관점:
- baseline_store가 만든 hash 기반 baseline을 비교한다.
- detector가 만든 Finding과 같은 형식으로 diff 결과를 반환한다.

보안적 의미:
- Tool Poisoning은 최초 등록 시점이 아니라 업데이트 이후 발생할 수 있다.
- 따라서 현재 metadata만 보는 정적 스캔에 더해, 이전 정상 상태와 비교하는
  rug-pull 탐지가 필요하다.
- diff 결과도 Finding으로 반환하면 Markdown/JSON/Web 리포트가 별도 분기 없이
  같은 파이프라인으로 결과를 보여줄 수 있다.
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
        old_baseline: `baseline_store.load_baseline`으로 읽은 이전 baseline dict
        current_tools: 현재 스캔에서 수집된 ToolMetadata 목록

    Returns:
        추가/삭제/변경된 tool에 대한 Finding 목록

    판정 기준:
        - added: 현재 baseline key에는 있지만 이전 baseline key에는 없음
        - removed: 이전 baseline key에는 있지만 현재 baseline key에는 없음
        - modified: 양쪽에 key가 있지만 metadata hash가 다름

    Security Note:
        modified는 high severity로 본다. 같은 tool 이름을 유지한 채 description이나
        schema가 바뀌는 경우, 사용자가 기존 신뢰를 바탕으로 악성 metadata를 그대로
        연결할 수 있기 때문이다.
    """
    current_baseline = create_baseline(current_tools)
    old_tools = old_baseline.get("tools", {})
    current_tools_by_key = current_baseline.get("tools", {})

    findings: list["Finding"] = []

    old_keys = set(old_tools)
    current_keys = set(current_tools_by_key)

    # 새 tool은 정상 운영 중 갑자기 추가된 권한/기능일 수 있으므로 medium으로 알린다.
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

    # 삭제 자체는 직접적인 poisoning보다 낮은 위험으로 보지만,
    # 정상 tool이 사라지고 유사한 악성 tool로 대체되는 흐름을 추적할 단서가 된다.
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

    # hash 변경은 metadata 내용 변경을 의미한다. 어떤 필드가 hash에 들어가는지는
    # baseline_store.normalize_tool이 결정한다.
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

    테스트 환경에서 core.models가 import되지 않는 특수 상황을 고려해
    fallback으로 SimpleNamespace를 반환한다. 일반 실행에서는 Pydantic Finding이
    반환되어 scanner detector 결과와 동일하게 report renderer로 전달된다.
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
    diff finding의 안정적인 fingerprint를 생성한다.

    같은 finding id와 같은 tool key 조합은 항상 같은 fingerprint를 갖는다.
    나중에 웹 UI나 CI에서 중복 finding을 묶거나 추적할 때 사용할 수 있다.
    """
    payload = f"{finding_id}:{tool_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
