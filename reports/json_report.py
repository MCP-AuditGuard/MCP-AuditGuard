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
    if hasattr(finding, name):
        return getattr(finding, name)
    if name == "tool_name":
        target = str(getattr(finding, "target", ""))
        return target.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
    return ""
