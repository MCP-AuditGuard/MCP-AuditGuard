from __future__ import annotations

from core.models import Finding


_SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
_CONFIDENCE_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """Return a stable list with duplicate detector findings collapsed.

    The default scanner does not call this yet because changing global finding
    counts affects historical reports. This utility is the aggregation layer for
    the raw/canonical MCP03 pipeline and can be enabled once report deltas are
    reviewed.
    """
    by_key: dict[tuple[str, str, str], Finding] = {}
    order: list[tuple[str, str, str]] = []

    for finding in findings:
        key = (finding.target, finding.location, finding.id)
        current = by_key.get(key)
        if current is None:
            by_key[key] = finding
            order.append(key)
            continue

        by_key[key] = _choose_more_actionable(current, finding)

    return [by_key[key] for key in order]


def _choose_more_actionable(left: Finding, right: Finding) -> Finding:
    left_rank = (
        _SEVERITY_RANK.get(left.severity, 0),
        _CONFIDENCE_RANK.get(left.confidence, 0),
        len(left.evidence),
    )
    right_rank = (
        _SEVERITY_RANK.get(right.severity, 0),
        _CONFIDENCE_RANK.get(right.confidence, 0),
        len(right.evidence),
    )
    return right if right_rank > left_rank else left
