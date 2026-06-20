from __future__ import annotations

"""
CLI와 Web UI가 공통으로 사용하는 scan orchestration service.

이 모듈은 입력 파일 수집, detector 실행, baseline 저장/비교, report rendering을
한 흐름으로 연결한다. CLI와 Web이 같은 scan 동작을 공유하도록 만든 중심 계층이다.

Member5 담당 관점:
- CLI 옵션을 실제 scan pipeline에 연결한다.
- Markdown/JSON renderer를 호출한다.
- baseline 저장과 baseline diff를 scan 결과에 합친다.

보안적 의미:
- detector 결과와 baseline diff 결과를 모두 Finding으로 합치면 사용자는
  "현재 metadata 안의 위험"과 "이전 대비 변경 위험"을 한 번에 볼 수 있다.
- 파일/JSON 파싱 오류를 사용자 친화적인 메시지로 변환해 데모와 CLI 사용성을 높인다.
"""

import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

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

def execute_scan(
    *,
    input_path: Path,
    source_label: str | None = None,
    save_baseline_path: Path | None = None,
    baseline_path: Path | None = None,
) -> ScanResult:
    """
    MCP tools.json을 스캔하고 구조화된 ScanResult를 반환한다.

    Args:
        input_path: 검사할 tools.json 경로
        source_label: Web UI나 sample scan에서 표시할 사용자 친화적 source 이름
        save_baseline_path: 현재 metadata baseline을 저장할 경로
        baseline_path: 이전 baseline과 비교할 경로

    Returns:
        tools, findings, summary 계산에 필요한 시간 정보를 포함한 ScanResult

    실행 순서:
        tools.json 수집 -> detector 실행 -> baseline diff 추가 -> baseline 저장 ->
        ScanResult 생성
    """
    started_at = datetime.now(timezone.utc)

    tools = _collect_tools(input_path)
    findings = _scan_tools(tools)

    baseline_compared = baseline_path is not None

    if baseline_path is not None:
        # baseline diff finding도 detector finding과 같은 리스트에 합친다.
        # 이렇게 해야 report renderer와 Web UI가 결과 출처를 구분하지 않고 표시할 수 있다.
        old_baseline = _load_baseline(baseline_path)
        findings.extend(diff_baseline(old_baseline, tools))

    if save_baseline_path is not None:
        # 저장은 현재 스캔된 metadata 기준이다. detector 결과나 embedding vector는
        # baseline에 저장하지 않는다.
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
) -> str:
    """
    CLI용 scan 실행 함수.

    `execute_scan`이 구조화된 ScanResult를 반환하는 반면, 이 함수는 사용자가 요청한
    Markdown/JSON 문자열까지 렌더링해 반환한다.
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

    return _render_report(result.findings,normalized_format,)


def _collect_tools(input_path: Path) -> list[ToolMetadata]:
    """
    tools.json을 ToolMetadata 목록으로 수집한다.

    파일 없음, JSON 파싱 실패, schema 형태 오류를 `ScanServiceError`로 변환한다.
    CLI/Web 계층은 이 예외 메시지를 그대로 사용자에게 보여줄 수 있다.
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


def _scan_tools(tools: list[ToolMetadata]) -> list[Finding]:
    """
    기본 detector 목록을 생성하고 scanner를 실행한다.

    detector registry는 탐지기 추가/삭제의 중심 지점이다. CLI는 어떤 detector가
    있는지 알 필요 없이 이 service를 호출하기만 하면 된다.
    """
    detectors = create_default_detectors()
    try:
        return scan_tools(tools, detectors)
    except Exception as error:
        raise ScanServiceError(f"Scanner failed: {error}") from error


def _load_baseline(baseline_path: Path) -> dict[str, Any]:
    """
    baseline JSON을 로드하고 읽기/파싱 오류를 사용자 친화적으로 변환한다.
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
    baseline JSON 저장 실패를 scan service 예외로 변환한다.
    """
    try:
        save_baseline(tools, str(baseline_path))
    except OSError as error:
        raise ScanServiceError(f"Could not save baseline: {error}") from error


def _render_report(findings: list[Finding], report_format: str) -> str:
    """
    Finding 목록을 요청한 report 형식으로 변환한다.

    지원 형식은 SUPPORTED_FORMATS와 반드시 함께 관리해야 한다.
    """
    if report_format == "markdown":
        return render_markdown(findings)
    if report_format == "json":
        return render_json(findings)
    raise ScanServiceError("Unsupported format. Use 'markdown' or 'json'.")
