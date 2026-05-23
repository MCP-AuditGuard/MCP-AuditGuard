from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Finding


SEVERITIES = ("critical", "high", "medium", "low")


def render_markdown(findings: list["Finding"]) -> str:
    """Render scan findings as a human-readable Markdown report."""
    lines = [
        "# MCP-AuditGuard Scan Report",
        "",
        "## Summary",
    ]

    severity_counts = _count_by_severity(findings)
    for severity in SEVERITIES:
        lines.append(f"- {severity}: {severity_counts[severity]}")

    lines.extend(["", "## Findings"])

    if not findings:
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
    counts = {severity: 0 for severity in SEVERITIES}
    for finding in findings:
        severity = str(getattr(finding, "severity", "")).lower()
        if severity in counts:
            counts[severity] += 1
    return counts


def _field(finding: "Finding", name: str) -> str:
    return str(getattr(finding, name))
