from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.embedding_provider import (
    EmbeddingProvider,
    EmbeddingUnavailableError,
    cosine_similarity,
    get_default_embedding_provider,
)
from core.models import Finding
from core.redaction import redact_text
from detectors.tool_poisoning.hidden_instruction import iter_text_values, load_rules


DEFAULT_SIGNATURES_PATH = Path(__file__).resolve().parents[1] / "rules" / "semantic_signatures.yaml"
DEFAULT_THRESHOLD = 0.82
KEYWORD_RULE_THRESHOLD = 0.76


@dataclass(frozen=True)
class SemanticSignature:
    id: str
    category: str
    owasp: str
    severity: str
    confidence: str
    threshold: float
    title: str
    recommendation: str
    examples: tuple[str, ...]


class SemanticSimilarityDetector:
    id = "SEMANTIC-SIMILARITY"
    category = "semantic_similarity"
    name = "semantic_similarity"

    def __init__(
        self,
        *,
        signatures_path: str | Path | None = None,
        provider: EmbeddingProvider | None = None,
        mode: str = "auto",
        include_rule_patterns: bool = True,
    ) -> None:
        self.signatures_path = Path(signatures_path) if signatures_path else None
        self.provider = provider
        self.mode = mode
        self.include_rule_patterns = include_rule_patterns

    def detect(self, tool: Any) -> list[Finding]:
        provider = self._get_provider()

        if provider is None:
            return []

        chunks = _collect_text_chunks(tool)
        if not chunks:
            return []

        signatures = self._load_signatures()
        if not signatures:
            return []

        signature_texts = [
            example
            for signature in signatures
            for example in signature.examples
        ]
        chunk_texts = [text for _, text in chunks]

        try:
            signature_embeddings = provider.embed_texts(signature_texts)
            chunk_embeddings = provider.embed_texts(chunk_texts)
        except EmbeddingUnavailableError:
            if self.mode == "auto":
                return []
            raise

        findings: list[Finding] = []
        signature_offset = 0

        for signature in signatures:
            example_count = len(signature.examples)
            example_embeddings = signature_embeddings[
                signature_offset : signature_offset + example_count
            ]
            signature_offset += example_count

            best_match = _find_best_match(
                chunks=chunks,
                chunk_embeddings=chunk_embeddings,
                example_embeddings=example_embeddings,
            )

            if best_match is None:
                continue

            location, text, score = best_match
            if score < signature.threshold:
                continue

            findings.append(
                _build_finding(
                    tool=tool,
                    signature=signature,
                    location=location,
                    text=text,
                    score=score,
                )
            )

        return findings

    def _load_signatures(self) -> list[SemanticSignature]:
        signatures: list[SemanticSignature] = []

        if self.signatures_path is not None:
            signatures.extend(load_semantic_signatures(self.signatures_path))

        if self.include_rule_patterns:
            signatures.extend(load_keyword_rule_signatures())

        return signatures

    def _get_provider(self) -> EmbeddingProvider | None:
        if self.mode in {"false", "off", "disabled"}:
            return None

        if self.provider is not None:
            return self.provider

        provider = get_default_embedding_provider()

        is_available = getattr(provider, "is_available", True)
        if self.mode == "auto" and not is_available:
            return None

        return provider


def load_semantic_signatures(path: str | Path = DEFAULT_SIGNATURES_PATH) -> list[SemanticSignature]:
    with Path(path).open("r", encoding="utf-8") as signature_file:
        data = yaml.safe_load(signature_file) or {}

    signatures: list[SemanticSignature] = []

    for raw_signature in data.get("signatures", []):
        examples = tuple(
            str(example).strip()
            for example in raw_signature.get("examples", [])
            if str(example).strip()
        )
        if not examples:
            continue

        signatures.append(
            SemanticSignature(
                id=str(raw_signature.get("id", "semantic_match")),
                category=str(raw_signature.get("category", "semantic_similarity")),
                owasp=str(raw_signature.get("owasp", "MCP03")),
                severity=str(raw_signature.get("severity", "medium")),
                confidence=str(raw_signature.get("confidence", "medium")),
                threshold=float(raw_signature.get("threshold", DEFAULT_THRESHOLD)),
                title=str(raw_signature.get("title", "Semantic similarity match")),
                recommendation=str(
                    raw_signature.get(
                        "recommendation",
                        "Review semantically similar risky metadata.",
                    )
                ),
                examples=examples,
            )
        )

    return signatures


def load_keyword_rule_signatures() -> list[SemanticSignature]:
    signatures: list[SemanticSignature] = []

    for rule in load_rules():
        rule_id = str(rule.get("id", "rule"))
        semantic_examples = rule.get("semantic_examples")
        if semantic_examples is not None:
            examples = tuple(
                str(example).strip()
                for example in semantic_examples
                if str(example).strip()
            )
        elif rule.get("type", "keyword") == "keyword":
            examples = tuple(
                str(pattern).strip()
                for pattern in rule.get("patterns", [])
                if str(pattern).strip()
            )
        else:
            continue

        examples = tuple(
            str(pattern).strip()
            for pattern in examples
            if str(pattern).strip()
        )
        if not examples:
            continue

        signatures.append(
            SemanticSignature(
                id=f"keyword_{rule_id}",
                category=f"semantic_similarity.{rule.get('category', 'tool_poisoning')}",
                owasp=str(rule.get("owasp", "MCP03")),
                severity=str(rule.get("severity", "medium")),
                confidence="medium",
                threshold=float(rule.get("semantic_threshold", KEYWORD_RULE_THRESHOLD)),
                title=f"Semantic match for {rule_id} keyword rule",
                recommendation=str(
                    rule.get(
                        "recommendation",
                        "Review metadata that is semantically similar to suspicious keyword rules.",
                    )
                ),
                examples=examples,
            )
        )

    return signatures


def _collect_text_chunks(tool: Any) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []

    for field_name in ("title", "description"):
        value = _get_field(tool, field_name)
        if isinstance(value, str) and value.strip():
            chunks.append((field_name, value.strip()))

    for field_name in ("input_schema", "output_schema", "annotations", "meta"):
        value = _get_field(tool, field_name)
        if value is None:
            continue
        for location, text in iter_text_values(value, field_name):
            if _is_ignored_location(location):
                continue
            stripped_text = text.strip()
            if stripped_text:
                chunks.append((location, stripped_text))

    return chunks


def _find_best_match(
    *,
    chunks: list[tuple[str, str]],
    chunk_embeddings: list[list[float]],
    example_embeddings: list[list[float]],
) -> tuple[str, str, float] | None:
    best_match: tuple[str, str, float] | None = None

    for (location, text), chunk_embedding in zip(chunks, chunk_embeddings, strict=True):
        for example_embedding in example_embeddings:
            score = cosine_similarity(chunk_embedding, example_embedding)
            if best_match is None or score > best_match[2]:
                best_match = (location, text, score)

    return best_match


def _build_finding(
    *,
    tool: Any,
    signature: SemanticSignature,
    location: str,
    text: str,
    score: float,
) -> Finding:
    redacted_text, redacted = redact_text(text)
    evidence = f"score={score:.3f}; text={redacted_text}"

    return Finding(
        id=f"{signature.owasp}-semantic_{signature.id}",
        category=signature.category,
        owasp=signature.owasp,
        severity=signature.severity,
        confidence=signature.confidence,
        title=signature.title,
        target=_target_name(tool),
        location=location,
        evidence=evidence,
        redacted=redacted,
        recommendation=signature.recommendation,
    )


def _get_field(tool: Any, field_name: str) -> Any:
    if isinstance(tool, dict):
        return tool.get(field_name) or tool.get(_to_camel_case(field_name))
    return getattr(tool, field_name, None)


def _target_name(tool: Any) -> str:
    server_name = _get_field(tool, "server_name") or "unknown-server"
    tool_name = _get_field(tool, "tool_name") or _get_field(tool, "name") or "unknown-tool"
    return f"{server_name}.{tool_name}"


def _to_camel_case(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def _is_ignored_location(location: str) -> bool:
    ignored_parts = (
        "_meta.expected_signal",
        "meta.expected_signal",
        "_meta.real_world_reference",
        "meta.real_world_reference",
        "_meta.difficulty",
        "meta.difficulty",
        "_meta.scenario_id",
        "meta.scenario_id",
    )
    return any(location.endswith(part) or location == part for part in ignored_parts)
