from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models import ToolMetadata


BASELINE_VERSION = 1


def normalize_tool(tool: "ToolMetadata") -> dict[str, Any]:
    """Return the stable metadata fields used for baseline hashing."""
    return {
        "server_name": tool.server_name,
        "tool_name": tool.tool_name,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "output_schema": tool.output_schema,
        "annotations": tool.annotations,
    }


def hash_tool_metadata(tool: "ToolMetadata") -> str:
    """Return a stable sha256 hash for a tool's normalized metadata."""
    normalized = normalize_tool(tool)
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_baseline(tools: list["ToolMetadata"]) -> dict[str, Any]:
    """Create a baseline document keyed by server and tool name."""
    baseline: dict[str, Any] = {
        "version": BASELINE_VERSION,
        "tools": {},
    }

    for tool in tools:
        key = f"{tool.server_name}:{tool.tool_name}"
        baseline["tools"][key] = {
            "hash": hash_tool_metadata(tool),
            "metadata": normalize_tool(tool),
        }

    return baseline


def save_baseline(tools: list["ToolMetadata"], path: str) -> None:
    """Save a baseline JSON document to disk."""
    baseline_path = Path(path)
    baseline = create_baseline(tools)
    baseline_path.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_baseline(path: str) -> dict[str, Any]:
    """Load a baseline JSON document from disk."""
    baseline_path = Path(path)
    return json.loads(baseline_path.read_text(encoding="utf-8"))
