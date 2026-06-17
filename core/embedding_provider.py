from __future__ import annotations

import math

from functools import lru_cache
from pathlib import Path
from typing import Protocol


DEFAULT_EMBEDDING_MODEL_PATH = Path("models/embedding/bge-small-en-v1.5")


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the local embedding provider cannot be initialized."""


class EmbeddingProvider(Protocol):
    """Small interface used by semantic detectors."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector for each input text."""


class SentenceTransformerEmbeddingProvider:
    """Local sentence-transformers embedding provider."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_EMBEDDING_MODEL_PATH,
    ) -> None:
        self.model_path = Path(model_path)
        self._model = None

    @property
    def is_available(self) -> bool:
        return self.model_path.exists()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [
            [float(value) for value in vector]
            for vector in embeddings
        ]

    def _load_model(self):
        if self._model is not None:
            return self._model

        if not self.model_path.exists():
            raise EmbeddingUnavailableError(
                f"local embedding model not found: {self.model_path}"
            )

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise EmbeddingUnavailableError(
                "sentence-transformers is not installed. "
                "Install the semantic extra to enable semantic similarity detection."
            ) from error

        self._model = SentenceTransformer(str(self.model_path))
        return self._model


@lru_cache(maxsize=1)
def get_default_embedding_provider() -> SentenceTransformerEmbeddingProvider:
    return SentenceTransformerEmbeddingProvider()


def cosine_similarity(
    first: list[float],
    second: list[float],
) -> float:
    if len(first) != len(second):
        raise ValueError("embedding vectors must have the same dimensions")

    dot_product = sum(a * b for a, b in zip(first, second, strict=True))
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))

    if first_norm == 0 or second_norm == 0:
        return 0.0

    return dot_product / (first_norm * second_norm)
