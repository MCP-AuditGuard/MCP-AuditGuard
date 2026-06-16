"""
AuditGuard baseline diff engine.

이 모듈은 이전 baseline과 현재 MCP tool metadata를 비교해
tool 추가, 삭제, metadata 변경을 Finding으로 변환한다.

팀원 5 담당 영역:
- baseline과 현재 metadata 비교
- added / removed / modified tool 탐지
- metadata rug-pull 가능성을 Finding으로 표현

보안적 의미:
MCP Tool Poisoning은 detector가 악성 문자열을 직접 찾는 경우도 있지만,
처음 승인된 metadata가 나중에 바뀌는 방식으로도 발생할 수 있다.
diff 결과를 Finding으로 반환하면 detector finding과 동일한 리포트 파이프라인에서
사용자가 변경 위험을 함께 검토할 수 있다.

semantic detector 연동 관점:
baseline diff는 embedding vector나 semantic score를 저장하지 않는다.
대신 metadata hash 변경 finding과 semantic detector finding을 같은 Finding 목록에 함께 담아
"metadata가 바뀌었고, 그 변경 내용이 의미적으로도 위험하다"는 상황을 리포트에서 나란히 보여준다.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from core.baseline_store import create_baseline

if TYPE_CHECKING:
    from core.models import Finding, ToolMetadata


# baseline diff finding에 공통으로 들어가는 분류값이다.
# baseline 변경은 metadata rug-pull 또는 Tool Poisoning 가능성과 연결되므로 MCP03으로 둔다.
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
    이전 baseline과 현재 tool metadata를 비교해 변경 finding을 만든다.

    Args:
        old_baseline: 이전 scan에서 저장한 baseline dict.
        current_tools: 현재 scan에서 수집한 ToolMetadata 목록.

    Returns:
        added, removed, modified 변경 사항을 표현하는 Finding 목록.

    Security Note:
        modified tool은 high severity로 처리한다. 같은 tool 이름이라도 description이나 schema가
        바뀌면 숨겨진 지시문이 새로 삽입되었을 수 있기 때문이다.

    비교 방식:
    1. 현재 tool 목록으로 새로운 baseline 구조를 만든다.
    2. 이전 baseline의 tool key 집합과 현재 baseline의 tool key 집합을 비교한다.
    3. 현재에만 있으면 added tool finding을 만든다.
    4. 이전에만 있으면 removed tool finding을 만든다.
    5. 양쪽 모두 있지만 hash가 다르면 modified tool finding을 만든다.

    detector와 독립적으로 동작하는 이유:
    - baseline diff는 특정 악성 문자열을 찾는 detector가 아니다.
    - "이전에 승인한 metadata와 달라졌다"는 무결성 변경 자체를 탐지한다.
    """
    current_baseline = create_baseline(current_tools)
    old_tools = old_baseline.get("tools", {})
    current_tools_by_key = current_baseline.get("tools", {})

    findings: list["Finding"] = []

    # dict key만 set으로 바꾸면 added/removed/common 비교를 간단하게 할 수 있다.
    old_keys = set(old_tools)
    current_keys = set(current_tools_by_key)

    # 신규 tool은 사용자가 승인한 baseline 이후 추가된 기능이다.
    # 위험도는 medium으로 두어 검토가 필요하지만 즉시 차단급은 아니게 표현한다.
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

    # 제거된 tool은 공격이라기보다 운영 변경일 수 있으므로 low로 기록한다.
    # 그래도 rug-pull 시나리오에서 정상 tool 제거가 의미 있을 수 있어 finding으로 남긴다.
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

    # 같은 key가 양쪽에 있어도 metadata hash가 달라지면 description/schema/annotations 중
    # 하나 이상이 바뀐 것이다. Tool Poisoning 문구가 나중에 삽입되는 rug-pull 가능성이 있어 high로 둔다.
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
    baseline diff 결과를 Finding 객체로 변환한다.

    Args:
        id: baseline diff finding id.
        severity: finding severity.
        title: 리포트에 표시할 finding 제목.
        tool_key: "{server_name}:{tool_name}" 형식의 tool key.
        evidence: 어떤 변경이 있었는지 설명하는 증거 문자열.

    Returns:
        core.models.Finding 또는 테스트 fallback용 SimpleNamespace.

    Security Note:
        diff 결과도 Finding 형태로 통일하면 Markdown/JSON renderer와 CLI 출력 흐름을 재사용할 수 있다.
        보안 리뷰어는 detector 결과와 baseline 변경 결과를 같은 화면에서 비교할 수 있다.

    core.models.Finding이 import 가능한 실제 프로젝트 환경에서는 Finding 모델을 반환한다.
    초기 테스트나 독립 실행 환경에서 core.models가 없을 수도 있어 SimpleNamespace fallback을 둔다.
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
    finding id와 tool key를 기반으로 안정적인 fingerprint를 만든다.

    Args:
        finding_id: Finding id.
        tool_key: "{server_name}:{tool_name}" 형식의 tool key.

    Returns:
        SHA-256 fingerprint 문자열.

    Security Note:
        fingerprint가 안정적이면 같은 변경 사항을 반복 추적하거나 리포트에서 중복 제거할 때 유리하다.

    같은 baseline 변경이 반복 탐지될 때 동일 fingerprint가 나오면,
    리포트 deduplication이나 추적 기능을 나중에 붙이기 쉽다.
    """
    payload = f"{finding_id}:{tool_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
