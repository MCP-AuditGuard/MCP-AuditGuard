from __future__ import annotations

"""
JSON report renderer.

Finding 목록을 자동화 도구가 읽기 쉬운 JSON 배열로 변환한다.
Markdown이 사람용 결과라면 JSON은 CI, dashboard, 후속 분석 도구용 결과다.

보안적 의미:
- 구조화된 JSON은 severity/evidence/recommendation을 자동 처리하기 쉽다.
- `ensure_ascii=False`를 사용해 한국어 evidence와 recommendation을 읽을 수 있게 보존한다.
"""

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models import Finding


FINDING_FIELDS = (
    "id",
    "category",
    "owasp",
    "severity",
    "title",
    "tool_name",
    "target",
    "evidence",
    "recommendation",
)


def render_json(findings: list["Finding"]) -> str:
    """
    Finding 목록을 JSON 배열 문자열로 렌더링한다.

    Args:
        findings: detector와 baseline diff가 생성한 Finding 목록

    Returns:
        `ensure_ascii=False`, `indent=2`가 적용된 JSON 문자열
    """
    return json.dumps(
        [_finding_to_dict(finding) for finding in findings],
        ensure_ascii=False,
        indent=2,
    )


def _finding_to_dict(finding: "Finding") -> dict[str, Any]:
    """
    JSON report에 포함할 Finding 필드만 dict로 변환한다.

    나중에 confidence, location, fingerprint 같은 필드를 JSON에 추가하려면
    FINDING_FIELDS와 관련 테스트를 함께 수정한다.
    """
    return {field: _field(finding, field) for field in FINDING_FIELDS}


def _field(finding: "Finding", name: str) -> Any:
    """
    Finding 필드를 안전하게 가져온다.

    Pydantic Finding이 아닌 테스트용 mock 객체도 처리할 수 있게 `hasattr` 기반으로 접근한다.
    """
    if hasattr(finding, name):
        return getattr(finding, name)
    if name == "tool_name":
        # baseline diff Finding처럼 tool_name이 없으면 target에서 표시명을 추정한다.
        target = str(getattr(finding, "target", ""))
        return target.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
    return ""
