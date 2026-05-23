from __future__ import annotations

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
    """Render scan findings as a JSON array for automation."""
    return json.dumps(
        [_finding_to_dict(finding) for finding in findings],
        ensure_ascii=False,
        indent=2,
    )


def _finding_to_dict(finding: "Finding") -> dict[str, Any]:
    return {field: _field(finding, field) for field in FINDING_FIELDS}


def _field(finding: "Finding", name: str) -> Any:
    if name == "tool_name" and not hasattr(finding, name):
        return getattr(finding, "target")
    return getattr(finding, name)
