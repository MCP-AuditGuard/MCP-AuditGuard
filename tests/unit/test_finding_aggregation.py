from __future__ import annotations

from core.models import Finding
from detectors.tool_poisoning.finding_aggregation import deduplicate_findings


def test_deduplicate_findings_keeps_more_severe_duplicate() -> None:
    low = _finding(severity="low", confidence="low", evidence="short")
    high = _finding(severity="high", confidence="medium", evidence="longer evidence")

    deduped = deduplicate_findings([low, high])

    assert deduped == [high]


def test_deduplicate_findings_keeps_distinct_locations() -> None:
    first = _finding(location="description")
    second = _finding(location="input_schema.properties.query.description")

    deduped = deduplicate_findings([first, second])

    assert deduped == [first, second]


def _finding(
    *,
    location: str = "description",
    severity: str = "medium",
    confidence: str = "medium",
    evidence: str = "evidence",
) -> Finding:
    return Finding(
        id="MCP03-ignore_previous_instructions",
        category="hidden_instruction",
        owasp="MCP03",
        severity=severity,
        confidence=confidence,
        title="Hidden instruction",
        target="demo.tool",
        location=location,
        evidence=evidence,
        redacted=False,
        recommendation="Remove suspicious metadata.",
    )
