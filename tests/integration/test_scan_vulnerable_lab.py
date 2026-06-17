from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
EXPANDED_LAB_ROOT = ROOT / "vulnerable-lab" / "expanded-82"
MVP_SCENARIO_SLUGS = {
    "hidden_description",
    "schema_poisoning",
    "base64_instruction",
    "zero_width_obfuscation",
    "metadata_rug_pull",
    "cross_tool_admin",
}
DIFFICULTY_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def _scenario_sort_key(case_path: Path) -> tuple[int, int, str]:
    tool = _load_tools(case_path)[0]
    meta = tool.get("_meta", {})
    category = meta.get("category", "")
    category_number = int(category.split()[0].removeprefix("MCP"))

    return (
        category_number,
        DIFFICULTY_ORDER[meta.get("difficulty", "")],
        meta.get("scenario_id", ""),
    )


def _expanded_lab_cases() -> list[Path]:
    return sorted(
        EXPANDED_LAB_ROOT.glob("LAB-*/tools.json"),
        key=_scenario_sort_key,
    )


def _load_tools(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "tools" in payload, f"{path} must use the MCP listTools-style tools array"
    assert payload["tools"], f"{path} must include at least one tool"
    return payload["tools"]


@pytest.mark.parametrize("case_path", _expanded_lab_cases())
def test_vulnerable_lab_fixture_shape(case_path: Path) -> None:
    tools = _load_tools(case_path)

    for tool in tools:
        assert tool["name"]
        assert tool["description"]
        assert "inputSchema" in tool


def test_expanded_lab_contains_82_scenarios() -> None:
    case_paths = _expanded_lab_cases()
    scenario_ids = []

    for case_path in case_paths:
        tools = _load_tools(case_path)
        assert len(tools) == 1, f"{case_path} must contain exactly one scenario"
        scenario_ids.append(tools[0].get("_meta", {}).get("scenario_id"))

    assert len(case_paths) == 82
    assert len(set(scenario_ids)) == 82
    assert scenario_ids[0] == "LAB-001"
    assert scenario_ids[-1] == "LAB-082"


def test_expanded_lab_is_sorted_by_category_then_difficulty() -> None:
    sort_keys = [_scenario_sort_key(case_path) for case_path in _expanded_lab_cases()]

    assert sort_keys == sorted(sort_keys)


def test_expanded_lab_scenarios_have_evaluation_metadata() -> None:
    difficulties = set()
    categories = set()
    references = set()

    for case_path in _expanded_lab_cases():
        tool = _load_tools(case_path)[0]
        meta = tool.get("_meta", {})

        assert meta.get("scenario_id")
        assert meta.get("difficulty") in {"Low", "Medium", "High"}
        assert meta.get("category", "").startswith("MCP")
        assert meta.get("expected_signal")
        assert meta.get("real_world_reference") in {
            "Reported",
            "Demonstrated",
            "Plausible",
        }

        difficulties.add(meta["difficulty"])
        categories.add(meta["category"])
        references.add(meta["real_world_reference"])

    assert difficulties == {"Low", "Medium", "High"}
    assert len(categories) == 10
    assert references == {"Reported", "Demonstrated", "Plausible"}


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
    detector_registry = pytest.importorskip("detectors.registry")
    scanner = pytest.importorskip("core.scanner")
    collector = pytest.importorskip("core.tool_collector")

    if (
        not hasattr(collector, "load_tools_json")
        or not hasattr(scanner, "scan_tools")
        or not hasattr(detector_registry, "create_default_detectors")
    ):
        pytest.skip("Scanner integration API is not available yet.")

    detectors = detector_registry.create_default_detectors()
    detected = 0
    for case_path in _expanded_lab_cases():
        tools = collector.load_tools_json(case_path)
        tool_slug = tools[0].tool_name.removeprefix(
            f"lab_{tools[0].meta.get('scenario_id', 'LAB-000')[-3:]}_"
        )
        if tool_slug not in MVP_SCENARIO_SLUGS:
            continue

        findings = scanner.scan_tools(tools, detectors)
        if findings:
            detected += 1

    assert detected >= 5


def test_benign_false_positive_rate_when_scanner_is_available() -> None:
    detector_registry = pytest.importorskip("detectors.registry")
    scanner = pytest.importorskip("core.scanner")
    collector = pytest.importorskip("core.tool_collector")

    if (
        not hasattr(collector, "load_tools_json")
        or not hasattr(scanner, "scan_tools")
        or not hasattr(detector_registry, "create_default_detectors")
    ):
        pytest.skip("Scanner integration API is not available yet.")

    detectors = detector_registry.create_default_detectors()
    tools = collector.load_tools_json(ROOT / "tests" / "fixtures" / "benign_tools.json")
    findings = scanner.scan_tools(tools, detectors)

    false_positive_rate = len(findings) / len(tools)
    assert false_positive_rate <= 0.20
