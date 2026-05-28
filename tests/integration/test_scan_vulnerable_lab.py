from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LAB_CASES = [
    ROOT / "vulnerable-lab" / "01-hidden-description" / "tools.json",
    ROOT / "vulnerable-lab" / "02-schema-poisoning" / "tools.json",
    ROOT / "vulnerable-lab" / "03-base64-instruction" / "tools.json",
    ROOT / "vulnerable-lab" / "04-zero-width-obfuscation" / "tools.json",
    ROOT / "vulnerable-lab" / "05-metadata-rug-pull" / "tools-after.json",
    ROOT / "vulnerable-lab" / "06-cross-tool-poisoning" / "tools.json",
]


def _load_tools(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "tools" in payload, f"{path} must use the MCP listTools-style tools array"
    assert payload["tools"], f"{path} must include at least one tool"
    return payload["tools"]


@pytest.mark.parametrize("case_path", LAB_CASES)
def test_vulnerable_lab_fixture_shape(case_path: Path) -> None:
    tools = _load_tools(case_path)

    for tool in tools:
        assert tool["name"]
        assert tool["description"]
        assert "inputSchema" in tool


def test_benign_and_malicious_fixtures_are_separated() -> None:
    benign_tools = _load_tools(ROOT / "tests" / "fixtures" / "benign_tools.json")
    malicious_tools = _load_tools(ROOT / "tests" / "fixtures" / "malicious_tools.json")

    benign_text = json.dumps(benign_tools).lower()
    malicious_text = json.dumps(malicious_tools).lower()

    assert "evil.example" not in benign_text
    assert "ignore previous instructions" not in benign_text
    assert "evil.example" in malicious_text
    assert "ignore" in malicious_text


def test_vulnerable_lab_recall_when_scanner_is_available() -> None:
    cli_scan = pytest.importorskip("cli.scan")
    scanner = pytest.importorskip("core.scanner")
    collector = pytest.importorskip("core.tool_collector")

    if (
        not hasattr(collector, "load_tools_json")
        or not hasattr(scanner, "scan_tools")
        or not hasattr(cli_scan, "_default_detectors")
    ):
        pytest.skip("Scanner integration API is not available yet.")

    detectors = cli_scan._default_detectors()
    detected = 0
    for case_path in LAB_CASES:
        tools = collector.load_tools_json(case_path)
        findings = scanner.scan_tools(tools, detectors)
        if findings:
            detected += 1

    assert detected >= 5


def test_benign_false_positive_rate_when_scanner_is_available() -> None:
    cli_scan = pytest.importorskip("cli.scan")
    scanner = pytest.importorskip("core.scanner")
    collector = pytest.importorskip("core.tool_collector")

    if (
        not hasattr(collector, "load_tools_json")
        or not hasattr(scanner, "scan_tools")
        or not hasattr(cli_scan, "_default_detectors")
    ):
        pytest.skip("Scanner integration API is not available yet.")

    detectors = cli_scan._default_detectors()
    tools = collector.load_tools_json(ROOT / "tests" / "fixtures" / "benign_tools.json")
    findings = scanner.scan_tools(tools, detectors)

    false_positive_rate = len(findings) / len(tools)
    assert false_positive_rate <= 0.20
