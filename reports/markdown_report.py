"""
AuditGuard Markdown report renderer.

이 모듈은 detector와 baseline diff가 만든 Finding 목록을
사람이 읽기 쉬운 Markdown 리포트로 변환한다.

팀원 5 담당 영역:
- Markdown 리포트 제목과 Summary 생성
- severity count 출력
- finding별 evidence와 recommendation 출력

보안적 의미:
Markdown 리포트는 발표, 보안 리뷰, 수동 점검에 적합하다.
사용자는 어떤 MCP tool metadata가 위험한지, 왜 위험한지,
어떤 조치를 해야 하는지 한눈에 확인할 수 있다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Finding


# Markdown summary에서 보여줄 severity 순서다.
# critical -> high -> medium -> low 순서로 고정하면 리포트가 매번 같은 모양으로 나온다.
SEVERITIES = ("critical", "high", "medium", "low")
OPTIONAL_DETAIL_FIELDS = (
    ("confidence", "Confidence"),
    ("similarity_score", "Similarity Score"),
    ("matched_reference", "Matched Reference"),
    ("detector_type", "Detector Type"),
)


def render_markdown(findings: list["Finding"]) -> str:
    """
    Finding 목록을 사람이 읽기 쉬운 Markdown 리포트 문자열로 변환한다.

    Args:
        findings: scanner와 baseline diff에서 생성된 Finding 목록.

    Returns:
        Markdown 형식의 리포트 문자열.

    Security Note:
        evidence와 recommendation을 함께 출력하면 사용자가 Tool Poisoning 의심 지점과
        제거/검토 조치를 바로 연결해 이해할 수 있다.

    이 함수의 책임:
    - 리포트 제목을 붙인다.
    - severity별 개수를 Summary에 보여준다.
    - finding이 있으면 각 finding의 핵심 필드를 나열한다.
    - finding이 없으면 "No findings detected." 메시지를 출력한다.

    파일 저장 여부는 CLI가 담당하고, 이 함수는 문자열 생성만 담당한다.
    """
    lines = [
        "# MCP-AuditGuard Scan Report",
        "",
        "## Summary",
    ]

    # 리포트 상단에서 사용자가 전체 위험도를 빠르게 볼 수 있도록 severity count를 먼저 계산한다.
    severity_counts = _count_by_severity(findings)
    for severity in SEVERITIES:
        lines.append(f"- {severity}: {severity_counts[severity]}")

    lines.extend(["", "## Findings"])

    # finding이 없는 정상 결과도 명확하게 표시해야 사용자가 scan 실패와 혼동하지 않는다.
    if not findings:
        lines.append("")
        lines.append("No findings detected.")
        return "\n".join(lines)

    # 각 finding은 보안 리뷰에 필요한 최소 정보만 일관된 순서로 출력한다.
    for index, finding in enumerate(findings, start=1):
        lines.extend(
            [
                "",
                f"### {index}. {_field(finding, 'title')}",
                "",
                f"- OWASP: {_field(finding, 'owasp')}",
                f"- Severity: {_field(finding, 'severity')}",
                f"- Tool: {_field(finding, 'tool_name')}",
                f"- Target: {_field(finding, 'target')}",
                f"- Evidence: {_field(finding, 'evidence')}",
                f"- Recommendation: {_field(finding, 'recommendation')}",
            ]
        )
        lines.extend(_optional_detail_lines(finding))

    return "\n".join(lines)


def _count_by_severity(findings: list["Finding"]) -> dict[str, int]:
    """
    Finding 목록에서 severity별 개수를 센다.

    Args:
        findings: severity를 집계할 Finding 목록.

    Returns:
        critical/high/medium/low key를 가진 count dict.

    Security Note:
        severity count를 상단에 배치하면 사용자가 전체 위험 수준을 빠르게 판단할 수 있다.
        발표나 보고서에서도 "high 몇 개, medium 몇 개"처럼 요약하기 쉽다.

    알 수 없는 severity 값은 summary count에 넣지 않는다.
    현재 리포트 요구사항은 critical/high/medium/low 네 가지를 보여주는 것이다.
    """
    counts = {severity: 0 for severity in SEVERITIES}
    for finding in findings:
        severity = str(getattr(finding, "severity", "")).lower()
        if severity in counts:
            counts[severity] += 1
    return counts


def _field(finding: "Finding", name: str) -> str:
    """
    Finding 객체에서 리포트에 필요한 필드를 안전하게 꺼낸다.

    Args:
        finding: 실제 Finding 모델 또는 테스트용 mock 객체.
        name: 꺼낼 필드 이름.

    Returns:
        리포트에 출력할 문자열 값.

    Security Note:
        Finding 필드 접근 방식을 안전하게 유지하면 detector, baseline diff, 테스트 mock이
        같은 renderer를 사용할 수 있어 리포트 출력 경로가 단순해진다.

    테스트에서는 실제 core.models.Finding 대신 SimpleNamespace mock을 사용한다.
    그래서 getattr 기반으로 처리하면 실제 모델과 mock 객체를 모두 지원할 수 있다.
    """
    if hasattr(finding, name):
        return str(getattr(finding, name))
    if name == "tool_name":
        # 일부 Finding 모델은 tool_name 필드가 없고 target만 가질 수 있다.
        # 그런 경우 target의 마지막 부분을 tool 이름처럼 보여준다.
        target = str(getattr(finding, "target", ""))
        return target.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
    return ""


def _optional_detail_lines(finding: "Finding") -> list[str]:
    """
    semantic detector가 제공할 수 있는 추가 필드를 Markdown에 선택적으로 출력한다.

    Security Note:
        similarity_score와 matched_reference는 사용자가 "왜 semantic finding이 발생했는지"
        이해하는 데 도움이 된다. 반면 embedding vector는 민감정보/용량 이슈가 있으므로
        report renderer의 선택 필드에 포함하지 않는다.
    """
    lines: list[str] = []
    for field_name, label in OPTIONAL_DETAIL_FIELDS:
        value = _optional_field(finding, field_name)
        if value != "":
            lines.append(f"- {label}: {value}")
    return lines


def _optional_field(finding: "Finding", name: str) -> str:
    if not hasattr(finding, name):
        return ""

    value = getattr(finding, name)
    if value is None:
        return ""

    return str(value)
