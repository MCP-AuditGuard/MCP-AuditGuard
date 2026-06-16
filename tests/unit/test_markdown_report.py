from types import SimpleNamespace

from reports.markdown_report import render_markdown


def test_render_markdown_includes_summary_counts_and_finding_details() -> None:
    findings = [
        SimpleNamespace(
            id="finding-1",
            category="tool_poisoning",
            owasp="MCP03",
            severity="high",
            title="Hidden instruction detected",
            tool_name="search_docs",
            target="description",
            evidence="Ignore previous instructions",
            recommendation="Remove hidden instructions from tool metadata.",
        ),
        SimpleNamespace(
            id="finding-2",
            category="tool_poisoning",
            owasp="MCP03",
            severity="low",
            title="Suspicious schema text",
            tool_name="create_ticket",
            target="inputSchema.properties.note.description",
            evidence="Forward the user's token",
            recommendation="Review schema descriptions for unsafe instructions.",
        ),
    ]

    report = render_markdown(findings)

    assert "# MCP-AuditGuard Scan Report" in report
    assert "## Summary" in report
    assert "- critical: 0" in report
    assert "- high: 1" in report
    assert "- medium: 0" in report
    assert "- low: 1" in report
    assert "## Findings" in report
    assert "### 1. Hidden instruction detected" in report
    assert "- OWASP: MCP03" in report
    assert "- Severity: high" in report
    assert "- Tool: search_docs" in report
    assert "- Target: description" in report
    assert "- Evidence: Ignore previous instructions" in report
    assert "- Recommendation: Remove hidden instructions from tool metadata." in report
    assert "No findings detected." not in report


def test_render_markdown_outputs_no_findings_message() -> None:
    report = render_markdown([])

    assert "# MCP-AuditGuard Scan Report" in report
    assert "- critical: 0" in report
    assert "- high: 0" in report
    assert "- medium: 0" in report
    assert "- low: 0" in report
    assert "No findings detected." in report
