from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from core.baseline_store import create_baseline

if TYPE_CHECKING:
    from core.models import Finding, ToolMetadata


BASELINE_CATEGORY = "baseline"
BASELINE_OWASP = "MCP03"
BASELINE_RECOMMENDATION = (
    "Review the metadata change and verify possible Tool Poisoning behavior."
)


def diff_baseline(
    old_baseline: dict[str, Any],
    current_tools: list["ToolMetadata"],
) -> list["Finding"]:
    """Compare an old baseline with current tool metadata."""
    current_baseline = create_baseline(current_tools)
    old_tools = old_baseline.get("tools", {})
    current_tools_by_key = current_baseline.get("tools", {})

    findings: list["Finding"] = []

    old_keys = set(old_tools)
    current_keys = set(current_tools_by_key)

    for tool_key in sorted(current_keys - old_keys):
        findings.append(
            _make_finding(
                id="BASELINE-001",
                severity="medium",
                title="New MCP tool added after baseline",
                tool_key=tool_key,
                evidence=f"Tool key added after baseline: {tool_key}",
            )
        )

    for tool_key in sorted(old_keys - current_keys):
        findings.append(
            _make_finding(
                id="BASELINE-002",
                severity="low",
                title="MCP tool removed after baseline",
                tool_key=tool_key,
                evidence=f"Tool key removed after baseline: {tool_key}",
            )
        )

    for tool_key in sorted(old_keys & current_keys):
        old_hash = old_tools[tool_key].get("hash")
        current_hash = current_tools_by_key[tool_key].get("hash")
        if old_hash != current_hash:
            findings.append(
                _make_finding(
                    id="BASELINE-003",
                    severity="high",
                    title="MCP tool metadata changed after baseline",
                    tool_key=tool_key,
                    evidence=f"Tool key metadata hash changed after baseline: {tool_key}",
                )
            )

    return findings


def _make_finding(
    *,
    id: str,
    severity: str,
    title: str,
    tool_key: str,
    evidence: str,
) -> "Finding":
    server_name, _, tool_name = tool_key.partition(":")
    finding_data = {
        "id": id,
        "category": BASELINE_CATEGORY,
        "owasp": BASELINE_OWASP,
        "severity": severity,
        "confidence": "high",
        "title": title,
        "target": tool_key,
        "location": f"baseline.{server_name}.{tool_name or tool_key}",
        "evidence": evidence,
        "redacted": False,
        "recommendation": BASELINE_RECOMMENDATION,
        "fingerprint": _fingerprint(id, tool_key),
    }

    try:
        from core.models import Finding
    except ModuleNotFoundError:
        return SimpleNamespace(**finding_data)

    return Finding(**finding_data)


def _fingerprint(finding_id: str, tool_key: str) -> str:
    payload = f"{finding_id}:{tool_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
