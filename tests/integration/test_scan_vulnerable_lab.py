from __future__ import annotations

import json
from pathlib import Path

import pytest

from detectors.obfuscation.encoded_payload import EncodedPayloadDetector
from detectors.obfuscation.homoglyph import HomoglyphDetector
from detectors.obfuscation.html_comment import HtmlCommentDetector
from detectors.obfuscation.unicode_obfuscation import UnicodeObfuscationDetector


ROOT = Path(__file__).resolve().parents[2]
EXPANDED_LAB_ROOT = ROOT / "vulnerable-lab" / "expanded-112"
BENIGN_LAB_ROOT = ROOT / "vulnerable-lab" / "benign-lab" / "mcp03-benign-100"
GENERAL_BENIGN_LAB_ROOT = ROOT / "vulnerable-lab" / "benign-lab" / "general-benign-100"
MVP_SCENARIO_SLUGS = {
    "hidden_description",
    "schema_poisoning",
    "base64_instruction",
    "zero_width_obfuscation",
    "metadata_rug_pull",
    "cross_tool_admin",
}
DIFFICULTY_ORDER = {"Low": 0, "Medium": 1, "High": 2}
MEMBER3_OBFUSCATION_CASES = [
    (
        "LAB-036-base64-instruction",
        EncodedPayloadDetector,
        "obfuscation.base64",
    ),
    (
        "LAB-037-zero-width-obfuscation",
        UnicodeObfuscationDetector,
        "obfuscation.zero_width_unicode",
    ),
    (
        "LAB-046-html-comment-instruction",
        HtmlCommentDetector,
        "obfuscation.html_comment",
    ),
    (
        "LAB-048-url-encoded-instruction",
        EncodedPayloadDetector,
        "obfuscation.url_encoding",
    ),
    (
        "LAB-049-homoglyph-secret-request",
        HomoglyphDetector,
        "obfuscation.homoglyph",
    ),
]


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


def _benign_sort_key(case_path: Path) -> str:
    tool = _load_tools(case_path)[0]
    return tool.get("_meta", {}).get("benign_id", "")


def _benign_lab_cases() -> list[Path]:
    return sorted(
        BENIGN_LAB_ROOT.glob("*/*/tools.json"),
        key=_benign_sort_key,
    )


def _general_benign_lab_cases() -> list[Path]:
    return sorted(
        GENERAL_BENIGN_LAB_ROOT.glob("*/*/tools.json"),
        key=_benign_sort_key,
    )


def _load_tools(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
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


def test_expanded_lab_contains_112_scenarios() -> None:
    case_paths = _expanded_lab_cases()
    scenario_ids = []

    for case_path in case_paths:
        tools = _load_tools(case_path)
        assert len(tools) == 1, f"{case_path} must contain exactly one scenario"
        scenario_ids.append(tools[0].get("_meta", {}).get("scenario_id"))

    assert len(case_paths) == 112
    assert len(set(scenario_ids)) == 112
    assert scenario_ids[0] == "LAB-001"
    assert scenario_ids[-1] == "LAB-112"


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


@pytest.mark.parametrize("case_path", _benign_lab_cases())
def test_benign_lab_fixture_shape(case_path: Path) -> None:
    tools = _load_tools(case_path)

    assert len(tools) == 1
    tool = tools[0]
    meta = tool.get("_meta", {})

    assert tool["name"]
    assert tool["description"]
    assert "inputSchema" in tool
    assert meta.get("benign_id", "").startswith("BENIGN-")
    assert meta.get("category") == "MCP03 benign false-positive control"
    assert meta.get("expected_result") == "No finding from default MCP03/obfuscation detectors."


def test_benign_lab_contains_100_scenarios() -> None:
    case_paths = _benign_lab_cases()
    benign_ids = [_load_tools(case_path)[0].get("_meta", {}).get("benign_id") for case_path in case_paths]

    assert len(case_paths) == 100
    assert len(set(benign_ids)) == 100
    assert benign_ids[0] == "BENIGN-001"
    assert benign_ids[-1] == "BENIGN-100"


@pytest.mark.parametrize("case_path", _general_benign_lab_cases())
def test_general_benign_lab_fixture_shape(case_path: Path) -> None:
    tools = _load_tools(case_path)

    assert len(tools) == 1
    tool = tools[0]
    meta = tool.get("_meta", {})

    assert tool["name"]
    assert tool["description"]
    assert "inputSchema" in tool
    assert meta.get("benign_id", "").startswith("BENIGN-")
    assert meta.get("benign_set") == "General Benign Set"
    assert meta.get("category") == "Market-like benign MCP server"
    assert meta.get("market_group")
    assert meta.get("expected_result") == "No finding from default detectors."


def test_general_benign_lab_contains_100_scenarios() -> None:
    case_paths = _general_benign_lab_cases()
    benign_ids = [_load_tools(case_path)[0].get("_meta", {}).get("benign_id") for case_path in case_paths]

    assert len(case_paths) == 100
    assert len(set(benign_ids)) == 100
    assert benign_ids[0] == "BENIGN-101"
    assert benign_ids[-1] == "BENIGN-200"


@pytest.mark.parametrize(
    ("case_slug", "detector_class", "expected_category"),
    MEMBER3_OBFUSCATION_CASES,
)
def test_member3_obfuscation_fixtures_trigger_specific_detectors(
    case_slug: str,
    detector_class: type,
    expected_category: str,
) -> None:
    scanner = pytest.importorskip("core.scanner")
    collector = pytest.importorskip("core.tool_collector")

    if not hasattr(collector, "load_tools_json") or not hasattr(scanner, "scan_tools"):
        pytest.skip("Scanner integration API is not available yet.")

    tools = collector.load_tools_json(EXPANDED_LAB_ROOT / case_slug / "tools.json")
    findings = scanner.scan_tools(tools, [detector_class()])
    categories = {finding.category for finding in findings}

    assert expected_category in categories


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


def test_benign_lab_false_positive_rate_when_scanner_is_available() -> None:
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
    total_tools = 0
    total_findings = 0

    for case_path in _benign_lab_cases():
        tools = collector.load_tools_json(case_path)
        findings = scanner.scan_tools(tools, detectors)
        total_tools += len(tools)
        total_findings += len(findings)

    false_positive_rate = total_findings / total_tools
    assert false_positive_rate <= 0.05


def test_general_benign_lab_false_positive_rate_when_scanner_is_available() -> None:
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
    total_tools = 0
    total_findings = 0

    for case_path in _general_benign_lab_cases():
        tools = collector.load_tools_json(case_path)
        findings = scanner.scan_tools(tools, detectors)
        total_tools += len(tools)
        total_findings += len(findings)

    false_positive_rate = total_findings / total_tools
    assert false_positive_rate <= 0.05
