from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from core.exceptions import ScanServiceError
from core.scan_service import run_scan


console = Console()


def scan_command(
    input_path: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to tools.json.",
    ),
    report_format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Report format: markdown or json.",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        file_okay=True,
        dir_okay=False,
        writable=True,
        help="Optional path to write the report.",
    ),
    save_baseline_path: Path | None = typer.Option(
        None,
        "--save-baseline",
        file_okay=True,
        dir_okay=False,
        writable=True,
        help="Optional path to save the current metadata baseline.",
    ),
    baseline_path: Path | None = typer.Option(
        None,
        "--baseline",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Optional previous baseline JSON path to compare against.",
    ),
) -> None:
    """
    Scan MCP tools metadata and render a report.
    """

    try:
        report = run_scan(
            input_path=input_path,
            report_format=report_format,
            save_baseline_path=save_baseline_path,
            baseline_path=baseline_path,
        )

        if output_path is not None:
            _write_report(report, output_path)

    except ScanServiceError as error:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(code=1) from error

    if output_path is None:
        console.print(report)


def _write_report(
    report: str,
    output_path: Path,
) -> None:
    """
    Rendered report 문자열을 지정한 파일에 UTF-8로 저장합니다.
    """

    try:
        output_path.write_text(
            report,
            encoding="utf-8",
        )

    except OSError as error:
        raise ScanServiceError(
            f"Could not write report: {error}"
        ) from error