import pytest

from core.models import Detector, Finding, ToolMetadata
from core.scanner import DetectorRegistry, Scanner
from core.redaction import redact_finding


class AlwaysFindingDetector(Detector):
    id = "TEST-ALWAYS-FINDING"
    category = "test"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        return [
            Finding(
                id=self.id,
                category=self.category,
                owasp="TEST",
                severity="info",
                confidence="high",
                title="Test finding",
                target=tool.target,
                location="description",
                evidence=tool.description or "",
                recommendation="No action required.",
            )
        ]


class EmptyDetector(Detector):
    id = "TEST-EMPTY"
    category = "test"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        return []


class BrokenDetector(Detector):
    id = "TEST-BROKEN"
    category = "test"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        raise RuntimeError("detector failed")


class InvalidReturnDetector(Detector):
    id = "TEST-INVALID-RETURN"
    category = "test"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        # 일부러 잘못된 반환값을 만든다.
        # Scanner가 이런 detector 오류를 잡아내는지 테스트하기 위함.
        return ["not-a-finding"]  # type: ignore[list-item]


class SecretFindingDetector(Detector):
    id = "TEST-SECRET"
    category = "test"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        return [
            Finding(
                id=self.id,
                category=self.category,
                owasp="TEST",
                severity="high",
                confidence="high",
                title="Secret evidence test",
                target=tool.target,
                location="description",
                evidence="token=abc123456",
                recommendation="Remove secret.",
            )
        ]
    

def make_tool() -> ToolMetadata:
    return ToolMetadata.from_mcp_tool(
        raw_tool={
            "name": "search_file",
            "description": "Search files",
        },
        server_name="demo-server",
        source="tests/fixtures/test_tools.json",
    )


def test_scanner_returns_findings():
    tool = make_tool()

    scanner = Scanner(
        detectors=[
            AlwaysFindingDetector(),
            EmptyDetector(),
        ]
    )

    findings = scanner.scan([tool])

    assert len(findings) == 1
    assert findings[0].id == "TEST-ALWAYS-FINDING"
    assert findings[0].target == "demo-server.search_file"


def test_scan_with_result_collects_errors_when_continue_on_error_is_true():
    tool = make_tool()

    scanner = Scanner(
        detectors=[
            BrokenDetector(),
            AlwaysFindingDetector(),
        ],
        continue_on_error=True,
    )

    result = scanner.scan_with_result([tool])

    assert result.finding_count == 1
    assert result.error_count == 1
    assert result.has_errors is True
    assert result.errors[0].detector_id == "TEST-BROKEN"
    assert result.errors[0].target == "demo-server.search_file"


def test_scanner_raises_error_when_continue_on_error_is_false():
    tool = make_tool()

    scanner = Scanner(
        detectors=[
            BrokenDetector(),
        ],
        continue_on_error=False,
    )

    with pytest.raises(RuntimeError):
        scanner.scan([tool])


def test_scanner_rejects_invalid_detector_return_value():
    tool = make_tool()

    scanner = Scanner(
        detectors=[
            InvalidReturnDetector(),
        ],
        continue_on_error=True,
    )

    result = scanner.scan_with_result([tool])

    assert result.finding_count == 0
    assert result.error_count == 1
    assert result.errors[0].detector_id == "TEST-INVALID-RETURN"


def test_detector_registry_rejects_duplicate_detector_id():
    registry = DetectorRegistry()
    registry.register(AlwaysFindingDetector())

    with pytest.raises(ValueError):
        registry.register(AlwaysFindingDetector())


def test_finding_transformer_is_applied():
    tool = make_tool()

    def fake_redactor(finding: Finding) -> Finding:
        return finding.model_copy(
            update={
                "evidence": "[REDACTED]",
                "redacted": True,
            }
        )

    scanner = Scanner(
        detectors=[
            AlwaysFindingDetector(),
        ],
        finding_transformer=fake_redactor,
    )

    findings = scanner.scan([tool])

    assert len(findings) == 1
    assert findings[0].evidence == "[REDACTED]"
    assert findings[0].redacted is True


def test_scanner_applies_redaction_to_findings():
    tool = make_tool()

    scanner = Scanner(
        detectors=[
            SecretFindingDetector(),
        ],
        finding_transformer=redact_finding,
    )

    findings = scanner.scan([tool])

    assert len(findings) == 1
    assert findings[0].evidence == "token=[REDACTED_SECRET]"
    assert findings[0].redacted is True