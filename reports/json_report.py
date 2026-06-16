"""
AuditGuard JSON report renderer.

이 모듈은 detector와 baseline diff가 만든 Finding 목록을
자동화 시스템이 읽기 쉬운 JSON 배열로 변환한다.

팀원 5 담당 영역:
- Finding 목록을 JSON report로 변환
- 자동화에 필요한 핵심 필드만 안정적으로 출력
- 한글 evidence/title이 깨지지 않도록 ensure_ascii=False 적용

보안적 의미:
JSON 리포트는 GitHub Actions, dashboard, 후속 분석 도구, SARIF 확장 같은
자동화 흐름과 연결하기 쉽다. 사람이 읽는 Markdown과 달리 기계가 안정적으로
파싱할 수 있는 구조를 제공한다.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models import Finding


# 자동화 도구가 소비하기 쉬운 JSON report에 포함할 필드 목록이다.
# tuple로 고정해두면 출력 순서가 안정적이고 테스트도 예측 가능하다.
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
OPTIONAL_FINDING_FIELDS = (
    "confidence",
    "similarity_score",
    "matched_reference",
    "detector_type",
)
EXCLUDED_REPORT_FIELDS = {
    "embedding",
    "vector",
    "embedding_vector",
}


def render_json(findings: list["Finding"]) -> str:
    """
    Finding 목록을 자동화용 JSON 배열 문자열로 변환한다.

    Args:
        findings: scanner와 baseline diff에서 생성된 Finding 목록.

    Returns:
        JSON 배열 형태의 문자열.

    Security Note:
        JSON report는 CI/CD나 dashboard에서 MCP Tool Poisoning finding을 자동으로 집계하고
        차단 정책 또는 알림 정책으로 연결할 수 있는 기반이 된다.

    출력 옵션:
    - ensure_ascii=False: 한글 evidence/title을 \\uXXXX로 깨지게 보이지 않게 한다.
    - indent=2: 사람이 읽고 PR에서 diff 보기 쉬운 형태로 만든다.

    파일 저장 여부는 CLI가 담당하고, 이 함수는 JSON 문자열 생성만 담당한다.
    """
    return json.dumps(
        [_finding_to_dict(finding) for finding in findings],
        ensure_ascii=False,
        indent=2,
    )


def _finding_to_dict(finding: "Finding") -> dict[str, Any]:
    """
    Finding 객체 하나를 JSON 직렬화 가능한 dict로 바꾼다.

    Args:
        finding: 실제 Finding 모델 또는 테스트용 mock 객체.

    Returns:
        JSON 직렬화 가능한 dict.

    Security Note:
        semantic detector가 제공하는 similarity_score, matched_reference 같은 설명 필드는 보존한다.
        하지만 embedding vector 계열 값은 용량과 민감정보 처리 이슈가 있으므로 JSON report에 포함하지 않는다.

    FINDING_FIELDS에 정의된 필드만 내보내서 리포트 스키마가 과도하게 커지지 않게 한다.
    """
    result = {field: _field(finding, field) for field in FINDING_FIELDS}

    for field in OPTIONAL_FINDING_FIELDS:
        value = _optional_field(finding, field)
        if value is not None:
            result[field] = value

    for field, value in _extra_fields(finding).items():
        if field not in result and field not in EXCLUDED_REPORT_FIELDS:
            result[field] = value

    return result


def _field(finding: "Finding", name: str) -> Any:
    """
    Finding에서 특정 필드를 안전하게 읽는다.

    Args:
        finding: 실제 Finding 모델 또는 테스트용 mock 객체.
        name: 꺼낼 필드 이름.

    Returns:
        JSON report에 넣을 값.

    Security Note:
        detector finding과 baseline diff finding이 같은 renderer를 공유하려면
        일부 필드가 없을 때도 안전한 fallback이 필요하다.

    실제 Finding 모델과 테스트용 SimpleNamespace mock을 모두 지원하기 위해 hasattr/getattr을 쓴다.
    tool_name이 없으면 target에서 마지막 segment를 추출해 fallback으로 사용한다.
    """
    if hasattr(finding, name):
        return getattr(finding, name)
    if name == "tool_name":
        target = str(getattr(finding, "target", ""))
        return target.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
    return ""


def _optional_field(finding: "Finding", name: str) -> Any | None:
    if not hasattr(finding, name):
        return None

    value = getattr(finding, name)
    if value is None:
        return None

    return value


def _extra_fields(finding: "Finding") -> dict[str, Any]:
    """
    mock 객체나 향후 확장 Finding에 들어온 추가 필드를 가능한 한 보존한다.

    Security Note:
        JSON report는 자동화 연동을 위한 형식이므로 detector_type 같은 확장 필드는 유용하다.
        단, embedding/vector 원문은 baseline과 report에 저장하지 않는 정책을 유지한다.
    """
    if hasattr(finding, "model_dump"):
        data = finding.model_dump(exclude_none=True)
    else:
        data = {
            key: value
            for key, value in vars(finding).items()
            if not key.startswith("_")
        }

    return {
        key: value
        for key, value in data.items()
        if key not in EXCLUDED_REPORT_FIELDS
    }
