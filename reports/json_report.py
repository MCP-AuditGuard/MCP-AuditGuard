from __future__ import annotations

"""
JSON report renderer.

이 모듈은 Finding 목록을 자동화 도구가 읽기 쉬운 JSON 배열로 변환한다.

Member5 담당 관점:
- CLI `--format json` 출력과 report.json 저장을 담당한다.
- Markdown이 사람용이라면 JSON은 CI, dashboard, 후속 분석 도구용 출력이다.

보안적 의미:
- JSON 리포트는 보안 점검 결과를 다른 시스템에 연결하기 쉽다.
- 예를 들어 GitHub Actions, 품질 게이트, 별도 dashboard가 Finding 결과를
  구조적으로 파싱할 수 있다.
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
        findings: scanner detector와 baseline diff가 생성한 Finding 목록

    Returns:
        `ensure_ascii=False`, `indent=2`가 적용된 JSON 문자열

    Security Note:
        `ensure_ascii=False`는 한국어 evidence/recommendation을 사람이 읽을 수 있게
        보존한다. `indent=2`는 Git diff나 PR 리뷰에서 변경 내용을 확인하기 쉽게 한다.
    """
    return json.dumps(
        [_finding_to_dict(finding) for finding in findings],
        ensure_ascii=False,
        indent=2,
    )


def _finding_to_dict(finding: "Finding") -> dict[str, Any]:
    """
    report에 공개할 Finding 필드만 dict로 변환한다.

    현재 JSON renderer는 발표와 자동화에 필요한 핵심 필드만 출력한다. 나중에
    confidence, location, fingerprint 같은 필드를 JSON에 추가하려면
    `FINDING_FIELDS`와 관련 테스트를 함께 수정하면 된다.
    """
    return {field: _field(finding, field) for field in FINDING_FIELDS}


def _field(finding: "Finding", name: str) -> Any:
    """
    Finding 필드를 안전하게 가져온다.

    Markdown renderer와 동일하게, Pydantic Finding이 아닌 테스트용 mock 객체나
    baseline diff fallback 객체가 들어와도 JSON 생성이 중단되지 않게 한다.
    """
    if hasattr(finding, name):
        return getattr(finding, name)
    if name == "tool_name":
        # baseline diff 결과처럼 tool_name이 없는 객체는 target에서 표시명을 추정한다.
        target = str(getattr(finding, "target", ""))
        return target.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
    return ""
