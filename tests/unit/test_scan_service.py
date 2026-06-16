from __future__ import annotations

import pytest

from core import scan_service
from core.exceptions import ScanServiceError
from core.models import ToolMetadata


def make_tool(
    *,
    server_name: str = "server",
    tool_name: str = "tool",
    description: str | None = "Search project documents.",
) -> ToolMetadata:
    return ToolMetadata.from_mcp_tool(
        raw_tool={
            "name": tool_name,
            "description": description,
            "inputSchema": {"type": "object"},
            "outputSchema": {"type": "object"},
            "annotations": {"readOnlyHint": True},
        },
        server_name=server_name,
    )


def test_run_scan_returns_rendered_report(monkeypatch, tmp_path) -> None:
    input_path = tmp_path / "tools.json"
    input_path.write_text("[]", encoding="utf-8")
    tool = make_tool()
    captured: dict[str, object] = {}

    monkeypatch.setattr(scan_service, "collect_from_tools_json", lambda path: [tool])

    def fake_scan_tools(tools, detectors):
        captured["tools"] = tools
        captured["detectors"] = detectors
        return []

    monkeypatch.setattr(scan_service, "scan_tools", fake_scan_tools)

    report = scan_service.run_scan(
        input_path=input_path,
        report_format="json",
    )

    assert report == "[]"
    assert captured["tools"] == [tool]
    assert captured["detectors"]


def test_run_scan_rejects_unsupported_format(tmp_path) -> None:
    input_path = tmp_path / "tools.json"
    input_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ScanServiceError, match="Unsupported format"):
        scan_service.run_scan(
            input_path=input_path,
            report_format="xml",
        )


def test_run_scan_wraps_scanner_errors(monkeypatch, tmp_path) -> None:
    input_path = tmp_path / "tools.json"
    input_path.write_text("[]", encoding="utf-8")
    tool = make_tool()

    def broken_scan_tools(tools, detectors):
        raise RuntimeError("scanner unavailable")

    monkeypatch.setattr(scan_service, "collect_from_tools_json", lambda path: [tool])
    monkeypatch.setattr(scan_service, "scan_tools", broken_scan_tools)

    with pytest.raises(ScanServiceError, match="Scanner failed: scanner unavailable"):
        scan_service.run_scan(
            input_path=input_path,
            report_format="json",
        )
