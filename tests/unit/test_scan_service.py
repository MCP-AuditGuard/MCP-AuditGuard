from __future__ import annotations

import pytest

from core import scan_service
from core.exceptions import ScanServiceError
from core.models import Detector, Finding, ToolMetadata


class RecordingDetector(Detector):
    id = "TEST-RECORDING"
    category = "test"

    def __init__(self) -> None:
        self.tools: list[ToolMetadata] = []

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        self.tools.append(tool)
        return []


class SecretFindingDetector(Detector):
    id = "TEST-SECRET-FINDING"
    category = "test"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        return [
            Finding(
                id=self.id,
                category=self.category,
                owasp="TEST",
                severity="high",
                confidence="high",
                title="Secret evidence",
                target=tool.target,
                location="description",
                evidence="token=abc123456",
                recommendation="Remove the secret.",
            )
        ]


class BrokenDetector(Detector):
    id = "TEST-BROKEN"
    category = "test"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        raise RuntimeError("password=super-secret")


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
    detector = RecordingDetector()

    monkeypatch.setattr(scan_service, "collect_from_tools_json", lambda path: [tool])
    monkeypatch.setattr(
        scan_service,
        "create_default_detectors",
        lambda: [detector],
    )

    report = scan_service.run_scan(
        input_path=input_path,
        report_format="json",
    )

    assert report == "[]"
    assert detector.tools == [tool]


def test_execute_scan_preserves_static_file_result_contract(
    monkeypatch,
    tmp_path,
) -> None:
    input_path = tmp_path / "tools.json"
    input_path.write_text("[]", encoding="utf-8")
    tool = make_tool()

    monkeypatch.setattr(scan_service, "collect_from_tools_json", lambda path: [tool])
    monkeypatch.setattr(scan_service, "create_default_detectors", lambda: [])

    result = scan_service.execute_scan(
        input_path=input_path,
        source_label="uploaded-tools.json",
    )

    assert result.scan_type == "static"
    assert result.source_type == "tools_json"
    assert result.source == "uploaded-tools.json"
    assert result.tools == [tool]
    assert result.findings == []
    assert result.baseline_compared is False
    assert result.warnings == []


def test_execute_tool_scan_redacts_findings_and_keeps_detector_warnings(
    monkeypatch,
) -> None:
    tool = make_tool()
    initial_warnings = ["metadata warning"]

    monkeypatch.setattr(
        scan_service,
        "create_default_detectors",
        lambda: [BrokenDetector(), SecretFindingDetector()],
    )

    result = scan_service.execute_tool_scan(
        tools=[tool],
        scan_type="dynamic",
        source_type="mcp_server",
        source="mcp:test:server",
        warnings=initial_warnings,
    )

    assert result.scan_type == "dynamic"
    assert result.source_type == "mcp_server"
    assert result.source == "mcp:test:server"
    assert result.tools == [tool]
    assert len(result.findings) == 1
    assert result.findings[0].evidence == "token=[REDACTED_SECRET]"
    assert result.findings[0].redacted is True
    assert result.warnings[0] == "metadata warning"
    assert "TEST-BROKEN" in result.warnings[1]
    assert "password=[REDACTED_SECRET]" in result.warnings[1]
    assert "super-secret" not in result.warnings[1]
    assert initial_warnings == ["metadata warning"]


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

    def broken_scan_with_result(scanner, tools):
        raise RuntimeError("scanner unavailable")

    monkeypatch.setattr(scan_service, "collect_from_tools_json", lambda path: [tool])
    monkeypatch.setattr(scan_service, "create_default_detectors", lambda: [])
    monkeypatch.setattr(
        scan_service.Scanner,
        "scan_with_result",
        broken_scan_with_result,
    )

    with pytest.raises(ScanServiceError, match="Scanner failed: scanner unavailable"):
        scan_service.run_scan(
            input_path=input_path,
            report_format="json",
        )
