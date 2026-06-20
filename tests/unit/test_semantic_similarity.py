from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from detectors import semantic_similarity
from detectors.semantic_similarity import (
    SemanticSimilarityDetector,
    load_keyword_rule_signatures,
)


class FakeEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [
            [1.0, 0.0] if "credential" in text.lower() else [0.0, 1.0]
            for text in texts
        ]


class UnavailableEmbeddingProvider:
    is_available = False

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("auto mode should skip unavailable providers")


def test_keyword_rule_semantic_expansion_uses_keyword_rules() -> None:
    signatures = load_keyword_rule_signatures()
    by_id = {signature.id: signature for signature in signatures}

    assert set(by_id) == {
        "keyword_ignore_previous_instructions",
        "keyword_covert_behavior",
        "keyword_schema_instruction_poisoning",
    }
    assert all(signature.threshold == 0.76 for signature in signatures)


def test_semantic_similarity_detector_skips_when_model_is_unavailable(
    monkeypatch,
    tmp_path,
) -> None:
    signatures_path = _write_signatures(tmp_path)
    monkeypatch.setattr(
        semantic_similarity,
        "get_default_embedding_provider",
        lambda: UnavailableEmbeddingProvider(),
    )
    detector = SemanticSimilarityDetector(signatures_path=signatures_path)
    tool = SimpleNamespace(
        server_name="demo",
        tool_name="helper",
        description="Expose configured credentials for diagnostics.",
    )

    assert detector.detect(tool) == []


def test_semantic_similarity_detector_reports_best_matching_signature(
    tmp_path,
) -> None:
    detector = SemanticSimilarityDetector(
        signatures_path=_write_signatures(tmp_path),
        provider=FakeEmbeddingProvider(),
        include_rule_patterns=False,
    )
    tool = SimpleNamespace(
        server_name="demo",
        tool_name="helper",
        description="Expose configured credentials for diagnostics.",
    )

    findings = detector.detect(tool)

    assert len(findings) == 1
    assert findings[0].id == "MCP01-semantic_plain_secret_exposure"
    assert findings[0].category == "semantic_similarity.secret_exposure"
    assert findings[0].severity == "critical"
    assert findings[0].confidence == "medium"
    assert findings[0].location == "description"
    assert "score=1.000" in findings[0].evidence


def _write_signatures(tmp_path: Path) -> Path:
    signatures_path = tmp_path / "semantic_signatures.yaml"
    signatures_path.write_text(
        """
signatures:
  - id: plain_secret_exposure
    category: semantic_similarity.secret_exposure
    owasp: MCP01
    severity: critical
    confidence: medium
    threshold: 0.9
    title: Semantic match for secret exposure
    recommendation: Remove plaintext secrets from tool metadata.
    examples:
      - expose configured credentials in metadata
""",
        encoding="utf-8",
    )
    return signatures_path
