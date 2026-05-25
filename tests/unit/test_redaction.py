from core.models import Finding
from core.redaction import redact_finding, redact_text


def make_finding(evidence: str) -> Finding:
    return Finding(
        id="TEST-FINDING",
        category="test",
        owasp="TEST",
        severity="high",
        confidence="high",
        title="Test finding",
        target="demo.search",
        location="description",
        evidence=evidence,
        recommendation="No action required.",
    )


def test_redact_text_masks_generic_token_assignment():
    redacted, changed = redact_text("token=abc123456")

    assert changed is True
    assert redacted == "token=[REDACTED_SECRET]"


def test_redact_text_masks_github_token():
    redacted, changed = redact_text(
        "Use ghp_abcdefghijklmnopqrstuvwxyz123456"
    )

    assert changed is True
    assert "[REDACTED_GITHUB_TOKEN]" in redacted
    assert "ghp_" not in redacted


def test_redact_text_returns_original_when_no_secret_exists():
    redacted, changed = redact_text("normal evidence text")

    assert changed is False
    assert redacted == "normal evidence text"


def test_redact_finding_updates_evidence_and_flag():
    finding = make_finding("password=my-secret-password")

    redacted = redact_finding(finding)

    assert redacted.evidence == "password=[REDACTED_SECRET]"
    assert redacted.redacted is True


def test_redact_finding_keeps_finding_when_no_secret_exists():
    finding = make_finding("normal evidence text")

    redacted = redact_finding(finding)

    assert redacted.evidence == "normal evidence text"
    assert redacted.redacted is False