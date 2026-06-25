from __future__ import annotations

"""
Markdown report renderer.

Finding 목록을 사람이 읽기 쉬운 Markdown 문서로 변환한다. CLI 터미널 출력,
`--output report.md`, Web UI 다운로드 artifact에서 모두 재사용된다.

보안적 의미:
- evidence는 어떤 metadata가 위험했는지 보여준다.
- recommendation은 사용자가 어떤 조치를 해야 하는지 설명한다.
- Summary를 상단에 배치해 전체 위험도를 빠르게 파악할 수 있게 한다.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Finding


SEVERITIES = ("critical", "high", "medium", "low")


def render_markdown(findings: list["Finding"]) -> str:
    """
    Finding 목록을 Markdown report 문자열로 렌더링한다.

    Args:
        findings: detector, semantic scan, baseline diff가 생성한 Finding 목록

    Returns:
        Markdown 형식의 scan report 문자열
    """
    lines = [
        "# MCP-AuditGuard Scan Report",
        "",
        "## Summary",
    ]

    # critical/high/medium/low를 고정 순서로 출력해 리포트 간 비교를 쉽게 한다.
    severity_counts = _count_by_severity(findings)
    for severity in SEVERITIES:
        lines.append(f"- {severity}: {severity_counts[severity]}")

    lines.extend(["", "## Findings"])

    if not findings:
        # 빈 결과도 명시적으로 표현해야 사용자가 scan 실패와 "finding 없음"을 구분할 수 있다.
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
    """Markdown Summary에 표시할 severity별 finding 개수를 계산한다."""
    counts = {severity: 0 for severity in SEVERITIES}
    for finding in findings:
        severity = str(getattr(finding, "severity", "")).lower()
        if severity in counts:
            counts[severity] += 1
    return counts


def _field(finding: "Finding", name: str) -> str:
    """
    Finding 필드를 안전하게 문자열로 꺼낸다.

    테스트에서는 SimpleNamespace 같은 mock 객체가 들어올 수 있고, baseline diff Finding은
    tool_name이 없을 수 있다. 이 helper는 그런 경우에도 report rendering이 깨지지
    않도록 fallback을 제공한다.
    """
    if hasattr(finding, name):
        return str(getattr(finding, name))
    if name == "tool_name":
        # baseline diff처럼 tool_name 필드가 없는 경우 target의 마지막 요소를 표시용으로 사용한다.
        target = str(getattr(finding, "target", ""))
        return target.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
    return ""
