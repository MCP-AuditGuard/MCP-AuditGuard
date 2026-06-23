from __future__ import annotations

"""
CLI/Web/MCP scan이 공유하는 scan orchestration service.

이 모듈은 tools.json 파일 스캔, MCP 서버에서 수집한 ToolMetadata 스캔, baseline 저장/비교,
report rendering을 한 흐름으로 연결한다. detector 자체를 구현하지 않고, detector registry와
scanner를 호출해 Finding을 모으는 역할이다.

Member5 담당 관점:
- `auditguard scan`의 핵심 실행 흐름을 제공한다.
- Markdown/JSON renderer와 baseline diff를 scan 결과에 연결한다.
- 최신 구조에서는 `execute_tool_scan`을 통해 파일 기반 scan과 MCP 동적 scan이 같은
  정적 metadata 분석 pipeline을 공유한다.

보안적 의미:
- detector 결과와 baseline diff 결과를 모두 Finding으로 합치면, 사용자는
  "현재 metadata 안의 위험"과 "이전 정상 상태 대비 변경 위험"을 한 리포트에서 본다.
- detector 경고와 evidence는 redaction을 거쳐 secret-like 값이 report에 노출되지 않게 한다.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.baseline_store import load_baseline, save_baseline
from core.diff_engine import diff_baseline
from core.exceptions import ScanServiceError
from core.models import Finding, ToolMetadata
from core.redaction import redact_finding, redact_text
from core.scan_result import ScanResult, ScanSourceType, ScanType
from core.scanner import DetectorRunError, Scanner
from core.tool_collector import collect_from_tools_json
from detectors.registry import create_default_detectors
from reports.json_report import render_json
from reports.markdown_report import render_markdown

SUPPORTED_FORMATS = {"markdown", "json"}


def execute_scan(
    *,
    input_path: Path,
    source_label: str | None = None,
    save_baseline_path: Path | None = None,
    baseline_path: Path | None = None,
) -> ScanResult:
    """
    tools.json 파일을 읽어 정적 scan을 수행한다.

    Args:
        input_path: 검사할 tools.json 경로
        source_label: Web 업로드나 sample scan에서 표시할 사용자 친화적 source 이름
        save_baseline_path: 현재 metadata baseline을 저장할 경로
        baseline_path: 이전 baseline과 비교할 경로

    Returns:
        수집된 tool, finding, warning, summary 계산 정보를 포함한 ScanResult

    동작:
        파일 입력을 ToolMetadata 목록으로 변환한 뒤 `execute_tool_scan`에 넘긴다.
        이렇게 파일 기반 scan과 MCP 동적 scan이 같은 detector/report/baseline 경로를
        공유할 수 있다.
    """
    tools = _collect_tools(input_path)

    return execute_tool_scan(
        tools=tools,
        scan_type="static",
        source_type="tools_json",
        source=source_label or str(input_path),
        save_baseline_path=save_baseline_path,
        baseline_path=baseline_path,
    )


def execute_tool_scan(
    *,
    tools: list[ToolMetadata],
    scan_type: ScanType,
    source_type: ScanSourceType,
    source: str,
    warnings: list[str] | None = None,
    save_baseline_path: Path | None = None,
    baseline_path: Path | None = None,
) -> ScanResult:
    """
    이미 수집된 ToolMetadata 목록을 공통 metadata scan pipeline으로 검사한다.

    Args:
        tools: scanner에 전달할 ToolMetadata 목록
        scan_type: static/dynamic 등 scan 출처 유형
        source_type: tools_json, mcp_server 등 입력 source 유형
        source: 리포트와 Web UI에 표시할 source 문자열
        warnings: MCP discovery/client 단계에서 이미 발생한 경고 목록
        save_baseline_path: 현재 metadata baseline 저장 경로
        baseline_path: 이전 baseline 비교 경로

    Returns:
        detector 결과, baseline diff 결과, redacted warning을 포함한 ScanResult

    Security Note:
        `finding_transformer=redact_finding`을 scanner에 주입해 detector가 secret-like
        evidence를 만들더라도 report로 나가기 전에 redaction을 적용한다.
    """
    started_at = datetime.now(timezone.utc)
    scan_warnings = list(warnings or [])

    try:
        # detector 목록은 registry에서 만들고, scanner는 실행/오류 수집을 담당한다.
        scanner = Scanner(
            create_default_detectors(),
            finding_transformer=redact_finding,
        )
        scanner_result = scanner.scan_with_result(tools)
    except Exception as error:
        raise ScanServiceError(f"Scanner failed: {error}") from error

    findings = list(scanner_result.findings)
    scan_warnings.extend(
        # detector 하나가 실패해도 전체 scan을 중단하지 않고 warning으로 남긴다.
        # warning에도 secret-like 문자열이 있을 수 있으므로 _format_detector_warning에서 redaction한다.
        _format_detector_warning(error)
        for error in scanner_result.errors
    )

    baseline_compared = baseline_path is not None

    if baseline_path is not None:
        # baseline diff Finding도 detector Finding과 같은 리스트에 합친다.
        # report renderer는 결과 출처를 몰라도 같은 구조로 출력할 수 있다.
        old_baseline = _load_baseline(baseline_path)
        findings.extend(diff_baseline(old_baseline, tools))

    if save_baseline_path is not None:
        # baseline에는 detector 결과나 embedding vector가 아니라 metadata hash 기준만 저장한다.
        _save_baseline(tools, save_baseline_path)

    completed_at = datetime.now(timezone.utc)

    return ScanResult(
        scan_type=scan_type,
        source_type=source_type,
        source=source,
        started_at=started_at,
        completed_at=completed_at,
        tools=tools,
        findings=findings,
        baseline_compared=baseline_compared,
        warnings=scan_warnings,
    )


def run_scan(
    *,
    input_path: Path,
    report_format: str,
    save_baseline_path: Path | None = None,
    baseline_path: Path | None = None,
) -> str:
    """
    CLI용 scan 실행 함수.

    `execute_scan`이 구조화된 ScanResult를 반환하는 반면, 이 함수는 사용자가 요청한
    report 형식까지 렌더링해 문자열로 반환한다.
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
    )

    return render_report(result.findings, normalized_format)


def _collect_tools(input_path: Path) -> list[ToolMetadata]:
    """
    tools.json을 ToolMetadata 목록으로 수집하고 사용자 친화적 예외로 변환한다.

    파일 없음, JSON 파싱 실패, 잘못된 tools.json 구조는 CLI/Web에서 그대로 보여줄
    수 있는 `ScanServiceError` 메시지로 바꾼다.
    """
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


def _format_detector_warning(error: DetectorRunError) -> str:
    """
    detector 실행 실패 정보를 warning 문자열로 변환하고 secret-like 값을 마스킹한다.

    detector 실패 메시지에는 입력 metadata 일부가 섞일 수 있다. 따라서 warning도
    evidence와 같은 보안 기준으로 redaction 처리한다.
    """
    warning = (
        f"Detector {error.detector_id} ({error.detector_category}) failed "
        f"for {error.target}: {error.message}"
    )
    redacted_warning, _ = redact_text(warning)
    return redacted_warning


def _load_baseline(baseline_path: Path) -> dict[str, Any]:
    """
    baseline JSON을 로드하고 파일/파싱 오류를 ScanServiceError로 변환한다.
    """
    try:
        return load_baseline(str(baseline_path))
    except FileNotFoundError as error:
        raise ScanServiceError(f"Baseline file not found: {baseline_path}") from error
    except json.JSONDecodeError as error:
        raise ScanServiceError(f"Could not parse baseline JSON: {error.msg}") from error
    except OSError as error:
        raise ScanServiceError(f"Could not read baseline file: {error}") from error


def _save_baseline(tools: list[ToolMetadata], baseline_path: Path) -> None:
    """
    baseline JSON 저장 실패를 ScanServiceError로 변환한다.
    """
    try:
        save_baseline(tools, str(baseline_path))
    except OSError as error:
        raise ScanServiceError(f"Could not save baseline: {error}") from error


def render_report(findings: list[Finding], report_format: str) -> str:
    """
    Finding 목록을 Markdown 또는 JSON report 문자열로 변환한다.

    이 함수는 CLI scan뿐 아니라 MCP 동적 scan 결과 출력에서도 재사용된다.
    지원 형식이 추가되면 `SUPPORTED_FORMATS`, 이 함수, 관련 테스트를 함께 수정한다.
    """
    if report_format == "markdown":
        return render_markdown(findings)
    if report_format == "json":
        return render_json(findings)
    raise ScanServiceError("Unsupported format. Use 'markdown' or 'json'.")
