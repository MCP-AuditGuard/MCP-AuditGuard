from __future__ import annotations

import math

from dataclasses import dataclass
from pathlib import Path

from core.embedding_provider import (
    EmbeddingProvider,
    EmbeddingUnavailableError,
    get_default_embedding_provider,
)


DEFAULT_PREFLIGHT_TEXT = (
    "MCP AuditGuard semantic embedding runtime preflight check."
)


@dataclass(frozen=True)
class RuntimePreflightResult:
    """
    MCP-AuditGuard 사용자용 프로그램 시작 전 검사 결과.

    semantic_ready:
        Semantic 모델과 embedding provider가 실제로 동작하면 True.

    provider_name:
        실제 사용한 embedding provider 클래스 이름.

    model_path:
        로컬 Semantic 모델 경로.
        테스트용 provider처럼 모델 경로가 없는 경우 None.

    embedding_dimension:
        테스트 임베딩 벡터의 차원.
        검사에 실패하면 None.

    error_code:
        프로그램에서 판단하기 위한 안전한 오류 코드.
        성공하면 None.

    error_message:
        콘솔 로그에 표시할 상세 오류 메시지.
        성공하면 None.
    """

    semantic_ready: bool
    provider_name: str
    model_path: Path | None
    embedding_dimension: int | None
    error_code: str | None
    error_message: str | None

    @property
    def succeeded(self) -> bool:
        """
        호출부에서 자연스럽게 성공 여부를 확인하기 위한 별칭.
        """

        return self.semantic_ready


def run_runtime_preflight(
    *,
    provider: EmbeddingProvider | None = None,
    test_text: str = DEFAULT_PREFLIGHT_TEXT,
) -> RuntimePreflightResult:
    """
    사용자용 실행파일을 시작하기 전에 Semantic 실행 환경을 검사한다.

    검사 범위:
    1. Embedding Provider 생성
    2. Provider 사용 가능 상태 확인
    3. 로컬 모델 경로 확인
    4. 테스트 문장 임베딩 생성
    5. 반환 벡터 개수 확인
    6. 임베딩 차원 확인
    7. NaN, infinity 등의 비정상 값 확인

    provider를 전달하지 않으면 실제 프로그램에서 사용하는
    get_default_embedding_provider()를 사용한다.

    단위 테스트에서는 가짜 provider를 전달해 실제 모델 없이
    빠르게 검사할 수 있다.
    """

    try:
        selected_provider = (
            provider
            if provider is not None
            else get_default_embedding_provider()
        )
    except Exception as error:
        return _failure_result(
            provider_name="unknown",
            model_path=None,
            error_code="provider_initialization_failed",
            error_message=(
                "Embedding provider를 생성하지 못했습니다: "
                f"{error}"
            ),
        )

    provider_name = type(selected_provider).__name__
    model_path = _get_provider_model_path(selected_provider)

    is_available = getattr(
        selected_provider,
        "is_available",
        True,
    )

    if not is_available:
        if model_path is not None:
            message = (
                "로컬 Semantic 모델을 사용할 수 없습니다: "
                f"{model_path}"
            )
        else:
            message = (
                "Semantic embedding provider를 사용할 수 없습니다."
            )

        return _failure_result(
            provider_name=provider_name,
            model_path=model_path,
            error_code="semantic_provider_unavailable",
            error_message=message,
        )

    normalized_test_text = test_text.strip()

    if not normalized_test_text:
        return _failure_result(
            provider_name=provider_name,
            model_path=model_path,
            error_code="invalid_preflight_text",
            error_message=(
                "Semantic 사전 검사 문장이 비어 있습니다."
            ),
        )

    try:
        embeddings = selected_provider.embed_texts(
            [normalized_test_text]
        )
    except EmbeddingUnavailableError as error:
        return _failure_result(
            provider_name=provider_name,
            model_path=model_path,
            error_code="semantic_embedding_unavailable",
            error_message=str(error),
        )
    except Exception as error:
        return _failure_result(
            provider_name=provider_name,
            model_path=model_path,
            error_code="semantic_embedding_failed",
            error_message=(
                "Semantic 모델을 로드하거나 임베딩을 생성하지 "
                f"못했습니다: {error}"
            ),
        )

    validation_error = _validate_embeddings(embeddings)

    if validation_error is not None:
        error_code, error_message = validation_error

        return _failure_result(
            provider_name=provider_name,
            model_path=model_path,
            error_code=error_code,
            error_message=error_message,
        )

    embedding_dimension = len(embeddings[0])

    return RuntimePreflightResult(
        semantic_ready=True,
        provider_name=provider_name,
        model_path=model_path,
        embedding_dimension=embedding_dimension,
        error_code=None,
        error_message=None,
    )


def _get_provider_model_path(
    provider: EmbeddingProvider,
) -> Path | None:
    """
    Provider에 model_path 속성이 있으면 Path로 정규화한다.

    EmbeddingProvider Protocol에는 embed_texts()만 필수이므로,
    테스트 Provider나 다른 구현은 model_path를 가지지 않아도 된다.
    """

    raw_model_path = getattr(
        provider,
        "model_path",
        None,
    )

    if raw_model_path is None:
        return None

    try:
        return Path(raw_model_path).resolve()
    except (TypeError, ValueError, OSError):
        return None


def _validate_embeddings(
    embeddings: list[list[float]],
) -> tuple[str, str] | None:
    """
    사전 검사에서 반환된 임베딩 결과가 정상인지 검사한다.

    정상이라면 None을 반환하고,
    문제가 있으면 (오류 코드, 오류 메시지)를 반환한다.
    """

    if len(embeddings) != 1:
        return (
            "unexpected_embedding_count",
            (
                "Semantic 사전 검사는 임베딩 1개를 기대했지만 "
                f"{len(embeddings)}개가 반환되었습니다."
            ),
        )

    vector = embeddings[0]

    if not vector:
        return (
            "empty_embedding_vector",
            "Semantic 모델이 빈 임베딩 벡터를 반환했습니다.",
        )

    for index, value in enumerate(vector):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return (
                "invalid_embedding_value",
                (
                    "Semantic 임베딩에 숫자가 아닌 값이 있습니다. "
                    f"index={index}"
                ),
            )

        if not math.isfinite(numeric_value):
            return (
                "non_finite_embedding_value",
                (
                    "Semantic 임베딩에 NaN 또는 무한대 값이 있습니다. "
                    f"index={index}"
                ),
            )

    return None


def _failure_result(
    *,
    provider_name: str,
    model_path: Path | None,
    error_code: str,
    error_message: str,
) -> RuntimePreflightResult:
    """
    실패 결과 생성을 한곳으로 모은다.
    """

    return RuntimePreflightResult(
        semantic_ready=False,
        provider_name=provider_name,
        model_path=model_path,
        embedding_dimension=None,
        error_code=error_code,
        error_message=error_message,
    )