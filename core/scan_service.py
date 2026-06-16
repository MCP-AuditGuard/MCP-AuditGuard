from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
import json
from pathlib import Path
from typing import Any

from core.baseline_store import load_baseline, save_baseline
from core.diff_engine import diff_baseline
from core.exceptions import ScanServiceError
from core.scanner import scan_tools
from core.tool_collector import collect_from_tools_json
from detectors.registry import create_default_detectors
from reports.json_report import render_json
from reports.markdown_report import render_markdown
from core.models import Finding, ToolMetadata
from core.scan_result import ScanResult

SUPPORTED_FORMATS = {"markdown", "json"}
SEMANTIC_DETECTOR_UNAVAILABLE = (
    "Semantic similarity detector is not available. "
    "Please implement detectors/semantic/embedding_similarity.py first."
)


def execute_scan(
    *,
    input_path: Path,
    source_label: str | None = None,
    save_baseline_path: Path | None = None,
    baseline_path: Path | None = None,
    enable_semantic: bool = False,
    semantic_threshold: float = 0.82,
    embedding_model_path: Path | None = None,
) -> ScanResult:
    """
    tools.json 기반 정적 scan을 실행하고 ScanResult를 반환한다.

    semantic detector는 옵션으로만 활성화한다.
    로컬 임베딩 모델 로딩은 느릴 수 있고 프로젝트별 의존성이 다를 수 있으므로,
    기본 scan에서는 기존 키워드/정규식 detector만 사용한다.
    """
    started_at = datetime.now(timezone.utc)

    tools = _collect_tools(input_path)
    findings = _scan_tools(
        tools,
        enable_semantic=enable_semantic,
        semantic_threshold=semantic_threshold,
        embedding_model_path=embedding_model_path,
    )

    baseline_compared = baseline_path is not None

    if baseline_path is not None:
        old_baseline = _load_baseline(baseline_path)
        findings.extend(diff_baseline(old_baseline, tools))

    if save_baseline_path is not None:
        _save_baseline(tools, save_baseline_path)

    completed_at = datetime.now(timezone.utc)

    return ScanResult(
        scan_type="static",
        source_type="tools_json",
        source=source_label or str(input_path),
        started_at=started_at,
        completed_at=completed_at,
        tools=tools,
        findings=findings,
        baseline_compared=baseline_compared,
    )


def run_scan(
    *,
    input_path: Path,
    report_format: str,
    save_baseline_path: Path | None = None,
    baseline_path: Path | None = None,
    enable_semantic: bool = False,
    semantic_threshold: float = 0.82,
    embedding_model_path: Path | None = None,
) -> str:
    """
    CLI와 웹에서 재사용할 수 있는 scan workflow 함수다.

    Args:
        enable_semantic: True이면 로컬 임베딩 유사도 detector를 detector list에 추가한다.
        semantic_threshold: semantic detector가 사용할 cosine similarity 기준값.
        embedding_model_path: 선택적 로컬 embedding model 경로.

    Security Note:
        semantic scan은 외부 API를 호출하지 않고 로컬 detector에만 연결한다.
        detector가 아직 구현되지 않았다면 전체 CLI import를 깨뜨리지 않고 사용자 친화적 에러를 낸다.
    """
    normalized_format = report_format.lower()

    if normalized_format not in SUPPORTED_FORMATS:
        raise ScanServiceError(
            "Unsupported format. Use 'markdown' or 'json'."
        )

    result = execute_scan(
        input_path=input_path,
        save_baseline_path=save_baseline_path,
        baseline_path=baseline_path,
        enable_semantic=enable_semantic,
        semantic_threshold=semantic_threshold,
        embedding_model_path=embedding_model_path,
    )

    return _render_report(result.findings,normalized_format,)


def _collect_tools(input_path: Path) -> list[ToolMetadata]:
    try:
        return collect_from_tools_json(input_path)
    except FileNotFoundError as error:
        raise ScanServiceError(f"Input file not found: {input_path}") from error
    except json.JSONDecodeError as error:
        raise ScanServiceError(f"Could not parse tools JSON: {error.msg}") from error
    except OSError as error:
        raise ScanServiceError(f"Could not read input file: {error}") from error
    except ValueError as error:
        raise ScanServiceError(str(error)) from error
    except Exception as error:
        if error.__class__.__name__ == "ToolCollectionError":
            message = str(error)
            if message.startswith("invalid JSON file"):
                raise ScanServiceError(f"Could not parse tools JSON: {message}") from error
            raise ScanServiceError(message) from error
        raise


def _scan_tools(
    tools: list[ToolMetadata],
    *,
    enable_semantic: bool = False,
    semantic_threshold: float = 0.82,
    embedding_model_path: Path | None = None,
) -> list[Finding]:
    detectors = _create_detectors(
        enable_semantic=enable_semantic,
        semantic_threshold=semantic_threshold,
        embedding_model_path=embedding_model_path,
    )
    try:
        return scan_tools(tools, detectors)
    except Exception as error:
        raise ScanServiceError(f"Scanner failed: {error}") from error


def _create_detectors(
    *,
    enable_semantic: bool = False,
    semantic_threshold: float = 0.82,
    embedding_model_path: Path | None = None,
) -> list[Any]:
    """
    기본 detector 목록에 semantic detector를 선택적으로 추가한다.

    Security Note:
        semantic detector는 로컬 embedding model을 사용하는 전제다.
        member5 코드는 detector 알고리즘을 구현하지 않고, detector가 있을 때만 안전하게 연결한다.
    """
    detectors: list[Any] = list(create_default_detectors())

    if not enable_semantic:
        return detectors

    detector_class = _load_semantic_detector()
    detectors.append(
        _instantiate_semantic_detector(
            detector_class,
            semantic_threshold=semantic_threshold,
            embedding_model_path=embedding_model_path,
        )
    )
    return detectors


def _load_semantic_detector() -> type[Any]:
    try:
        module = import_module("detectors.semantic.embedding_similarity")
    except ImportError as error:
        raise ScanServiceError(SEMANTIC_DETECTOR_UNAVAILABLE) from error

    detector_class = getattr(module, "EmbeddingSimilarityDetector", None)
    if detector_class is None:
        raise ScanServiceError(SEMANTIC_DETECTOR_UNAVAILABLE)

    return detector_class


def _instantiate_semantic_detector(
    detector_class: type[Any],
    *,
    semantic_threshold: float,
    embedding_model_path: Path | None,
) -> Any:
    """
    semantic detector를 가능한 constructor 형태에 맞춰 유연하게 생성한다.

    detector 구현은 다른 팀원이 담당하므로 signature가 조금 달라도 CLI가 쉽게 깨지지 않게 한다.
    우선 권장 형태인 threshold/model_path 인자를 시도하고, 실패하면 더 단순한 형태로 fallback한다.
    """
    keyword_attempts: list[dict[str, Any]] = [
        {
            "threshold": semantic_threshold,
            "model_path": embedding_model_path,
        },
        {
            "threshold": semantic_threshold,
        },
        {},
    ]

    if embedding_model_path is None:
        keyword_attempts[0].pop("model_path")

    last_error: TypeError | None = None
    for kwargs in keyword_attempts:
        try:
            return detector_class(**kwargs)
        except TypeError as error:
            last_error = error

    raise ScanServiceError(
        f"Semantic similarity detector could not be initialized: {last_error}"
    )


def _load_baseline(baseline_path: Path) -> dict[str, Any]:
    try:
        return load_baseline(str(baseline_path))
    except FileNotFoundError as error:
        raise ScanServiceError(f"Baseline file not found: {baseline_path}") from error
    except json.JSONDecodeError as error:
        raise ScanServiceError(f"Could not parse baseline JSON: {error.msg}") from error
    except OSError as error:
        raise ScanServiceError(f"Could not read baseline file: {error}") from error


def _save_baseline(tools: list[ToolMetadata], baseline_path: Path) -> None:
    try:
        save_baseline(tools, str(baseline_path))
    except OSError as error:
        raise ScanServiceError(f"Could not save baseline: {error}") from error


def _render_report(findings: list[Finding], report_format: str) -> str:
    if report_format == "markdown":
        return render_markdown(findings)
    if report_format == "json":
        return render_json(findings)
    raise ScanServiceError("Unsupported format. Use 'markdown' or 'json'.")
