from __future__ import annotations

"""
Markdown report renderer.

이 모듈은 detector와 baseline diff가 만든 Finding 목록을 사람이 읽기 쉬운
Markdown 문서로 변환한다.

Member5 담당 관점:
- CLI 터미널 출력과 report.md 저장에 사용할 문자열을 만든다.
- 웹 대시보드에서 다운로드할 Markdown artifact 생성에도 재사용된다.

보안적 의미:
- 보안 도구의 결과는 탐지만큼 설명이 중요하다.
- evidence와 recommendation을 함께 보여주면 사용자가 "왜 위험한지"와
  "어떻게 조치해야 하는지"를 바로 확인할 수 있다.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Finding


SEVERITIES = ("critical", "high", "medium", "low")


def render_markdown(findings: list["Finding"]) -> str:
    """
    Finding 목록을 Markdown 리포트 문자열로 렌더링한다.

    Args:
        findings: scanner detector와 baseline diff가 생성한 Finding 목록

    Returns:
        Markdown 형식의 scan report 문자열

    구성:
        - 제목
        - severity summary
        - finding 상세 목록

    Security Note:
        Summary를 먼저 보여주면 사용자가 전체 위험 수준을 빠르게 판단할 수 있다.
        상세 섹션에는 evidence와 recommendation을 포함해 수동 검토와 발표 자료에
        그대로 활용할 수 있게 한다.
    """
    lines = [
        "# MCP-AuditGuard Scan Report",
        "",
        "## Summary",
    ]

    # critical/high/medium/low를 고정 순서로 출력해 리포트 간 비교가 쉽도록 한다.
    severity_counts = _count_by_severity(findings)
    for severity in SEVERITIES:
        lines.append(f"- {severity}: {severity_counts[severity]}")

    lines.extend(["", "## Findings"])

    if not findings:
        # finding이 없을 때도 빈 문서가 아니라 명시적인 안전 메시지를 출력한다.
        lines.append("")
        lines.append("No findings detected.")
        return "\n".join(lines)

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

    return "\n".join(lines)


def _count_by_severity(findings: list["Finding"]) -> dict[str, int]:
    """
    severity별 Finding 개수를 계산한다.

    `info` 등 Markdown summary에 표시하지 않는 severity는 의도적으로 무시한다.
    현재 발표/리포트의 핵심 판단 축은 critical/high/medium/low다.
    """
    counts = {severity: 0 for severity in SEVERITIES}
    for finding in findings:
        severity = str(getattr(finding, "severity", "")).lower()
        if severity in counts:
            counts[severity] += 1
    return counts


def _field(finding: "Finding", name: str) -> str:
    """
    Finding 필드를 안전하게 문자열로 꺼낸다.

    일부 테스트나 fallback 경로에서는 Pydantic Finding이 아니라 SimpleNamespace 같은
    mock 객체가 들어올 수 있다. 이 helper는 그런 경우에도 renderer가 깨지지 않도록
    필드 접근을 한 곳에서 처리한다.
    """
    if hasattr(finding, name):
        return str(getattr(finding, name))
    if name == "tool_name":
        # baseline diff Finding은 tool_name 필드가 없을 수 있어 target에서 마지막
        # 구성 요소를 추정한다. 리포트가 비어 보이는 것을 막기 위한 표시용 fallback이다.
        target = str(getattr(finding, "target", ""))
        return target.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
    return ""
