from __future__ import annotations

import os

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from core.scan_result import ScanResult
from reports.json_report import render_json
from reports.markdown_report import render_markdown


ReportFormat = Literal["markdown", "json"]


class ReportArtifactError(Exception):
    """리포트 파일 생성 또는 조회 중 발생하는 오류."""


@dataclass(frozen=True, slots=True)
class ReportArtifactPaths:
    """한 번의 스캔으로 저장된 리포트 파일 경로."""

    directory: Path
    markdown: Path
    json: Path


def get_reports_root() -> Path:
    """
    리포트 저장 최상위 경로를 반환한다.

    기본값:
        프로젝트루트/artifacts/reports

    환경변수 AUDITGUARD_REPORTS_DIR가 있으면
    해당 경로를 대신 사용한다.
    """
    project_root = Path(__file__).resolve().parents[1]
    default_root = project_root / "artifacts" / "reports"

    configured_root = os.getenv(
        "AUDITGUARD_REPORTS_DIR",
        str(default_root),
    )

    return Path(configured_root).expanduser().resolve()


def save_report_artifacts(
    result: ScanResult,
) -> ReportArtifactPaths:
    """
    ScanResult를 기존 renderer로 변환해
    Markdown과 JSON 파일을 모두 저장한다.
    """
    paths = _build_artifact_paths(result.scan_id)

    try:
        paths.directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        markdown_text = render_markdown(result.findings)
        json_text = render_json(result.findings)

        _write_text_atomic(
            paths.markdown,
            markdown_text,
        )
        _write_text_atomic(
            paths.json,
            json_text,
        )

    except OSError as error:
        raise ReportArtifactError(
            f"Could not save report files: {error}"
        ) from error

    return paths


def get_report_artifact(
    scan_id: UUID,
    report_format: ReportFormat,
) -> Path:
    """
    저장된 리포트 파일 경로를 반환한다.

    파일이 없으면 FileNotFoundError를 발생시킨다.
    """
    paths = _build_artifact_paths(scan_id)

    if report_format == "markdown":
        report_path = paths.markdown
    else:
        report_path = paths.json

    if not report_path.is_file():
        raise FileNotFoundError(
            f"Report was not found for scan: {scan_id}"
        )

    return report_path


def _build_artifact_paths(
    scan_id: UUID,
) -> ReportArtifactPaths:
    scan_directory = get_reports_root() / str(scan_id)

    return ReportArtifactPaths(
        directory=scan_directory,
        markdown=scan_directory / "report.md",
        json=scan_directory / "report.json",
    )


def _write_text_atomic(
    output_path: Path,
    content: str,
) -> None:
    """
    임시 파일을 먼저 쓴 뒤 최종 파일로 교체한다.

    저장 도중 프로그램이 중단되어 불완전한 파일이
    남는 가능성을 줄인다.
    """
    temporary_path = output_path.with_suffix(
        f"{output_path.suffix}.tmp"
    )

    temporary_path.write_text(
        content,
        encoding="utf-8",
    )

    temporary_path.replace(output_path)