from __future__ import annotations

from pathlib import Path

from core.embedding_provider import EmbeddingUnavailableError
from core.runtime_preflight import run_runtime_preflight


class ReadyEmbeddingProvider:
    def __init__(
        self,
        model_path: Path,
    ) -> None:
        self.model_path = model_path
        self.is_available = True
        self.received_texts: list[str] | None = None

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self.received_texts = texts

        return [
            [0.1, 0.2, 0.3, 0.4],
        ]


class UnavailableEmbeddingProvider:
    def __init__(
        self,
        model_path: Path,
    ) -> None:
        self.model_path = model_path
        self.is_available = False
        self.embed_called = False

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self.embed_called = True

        raise AssertionError(
            "사용 불가능한 provider의 embed_texts()가 "
            "호출되면 안 됩니다."
        )


class RaisingEmbeddingProvider:
    is_available = True

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        raise EmbeddingUnavailableError(
            "test embedding model unavailable"
        )


class EmptyEmbeddingProvider:
    is_available = True

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return [[]]


class MultipleEmbeddingProvider:
    is_available = True

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return [
            [0.1, 0.2],
            [0.3, 0.4],
        ]


class NonFiniteEmbeddingProvider:
    is_available = True

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return [
            [0.1, float("nan")],
        ]


def test_runtime_preflight_succeeds_when_embedding_is_created(
    tmp_path: Path,
) -> None:
    model_path = (
        tmp_path
        / "models"
        / "embedding"
        / "bge-small-en-v1.5"
    )
    model_path.mkdir(parents=True)

    provider = ReadyEmbeddingProvider(model_path)

    result = run_runtime_preflight(
        provider=provider,
        test_text="semantic preflight test",
    )

    assert result.semantic_ready is True
    assert result.succeeded is True
    assert result.provider_name == "ReadyEmbeddingProvider"
    assert result.model_path == model_path.resolve()
    assert result.embedding_dimension == 4
    assert result.error_code is None
    assert result.error_message is None

    assert provider.received_texts == [
        "semantic preflight test",
    ]


def test_runtime_preflight_fails_before_embedding_when_provider_unavailable(
    tmp_path: Path,
) -> None:
    model_path = (
        tmp_path
        / "missing-model"
    )

    provider = UnavailableEmbeddingProvider(
        model_path
    )

    result = run_runtime_preflight(
        provider=provider,
    )

    assert result.semantic_ready is False
    assert result.succeeded is False
    assert (
        result.error_code
        == "semantic_provider_unavailable"
    )
    assert result.model_path == model_path.resolve()
    assert result.embedding_dimension is None
    assert result.error_message is not None
    assert str(model_path.resolve()) in result.error_message
    assert provider.embed_called is False


def test_runtime_preflight_converts_embedding_unavailable_error_to_result(
) -> None:
    result = run_runtime_preflight(
        provider=RaisingEmbeddingProvider(),
    )

    assert result.semantic_ready is False
    assert (
        result.error_code
        == "semantic_embedding_unavailable"
    )
    assert result.embedding_dimension is None
    assert result.error_message == (
        "test embedding model unavailable"
    )


def test_runtime_preflight_rejects_empty_embedding_vector(
) -> None:
    result = run_runtime_preflight(
        provider=EmptyEmbeddingProvider(),
    )

    assert result.semantic_ready is False
    assert result.error_code == "empty_embedding_vector"
    assert result.embedding_dimension is None


def test_runtime_preflight_rejects_unexpected_embedding_count(
) -> None:
    result = run_runtime_preflight(
        provider=MultipleEmbeddingProvider(),
    )

    assert result.semantic_ready is False
    assert (
        result.error_code
        == "unexpected_embedding_count"
    )
    assert result.embedding_dimension is None


def test_runtime_preflight_rejects_non_finite_embedding_value(
) -> None:
    result = run_runtime_preflight(
        provider=NonFiniteEmbeddingProvider(),
    )

    assert result.semantic_ready is False
    assert (
        result.error_code
        == "non_finite_embedding_value"
    )
    assert result.embedding_dimension is None


def test_runtime_preflight_rejects_empty_test_text(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()

    provider = ReadyEmbeddingProvider(model_path)

    result = run_runtime_preflight(
        provider=provider,
        test_text="   ",
    )

    assert result.semantic_ready is False
    assert result.error_code == "invalid_preflight_text"
    assert provider.received_texts is None