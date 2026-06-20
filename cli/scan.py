from __future__ import annotations

"""
AuditGuard scan 명령어 구현 모듈.

이 파일은 사용자가 터미널에서 `auditguard scan`을 실행했을 때의
입력 옵션을 정의하고, 실제 스캔 로직은 `core.scan_service`에 위임한다.

Member5 담당 관점:
- CLI 옵션을 사용자 친화적으로 노출한다.
- Markdown/JSON 리포트 출력을 파일 저장 또는 터미널 출력으로 연결한다.
- baseline 저장/비교 옵션을 scan pipeline으로 전달한다.

보안적 의미:
- CLI는 보안 지식이 많지 않은 사용자도 MCP tool metadata 검사를 실행할 수
  있게 해주는 진입점이다.
- 실제 detector 구현과 CLI를 분리해, 탐지기가 늘어나도 명령어 구조를 크게
  바꾸지 않고 결과를 같은 리포트 파이프라인으로 보낼 수 있다.
"""

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
    MCP tools metadata를 스캔하고 요청한 형식의 리포트를 출력한다.

    Args:
        input_path: 검사할 tools.json 경로. Typer 옵션에서 존재 여부와 읽기 가능
            여부를 먼저 검증한다.
        report_format: 출력 형식. 현재는 markdown/json만 지원한다.
        output_path: 지정하면 리포트를 파일로 저장하고, 지정하지 않으면 터미널에
            출력한다.
        save_baseline_path: 현재 metadata 상태를 baseline JSON으로 저장할 경로.
        baseline_path: 이전 baseline과 현재 metadata를 비교할 때 사용하는 경로.

    Security Note:
        baseline 옵션은 Tool Poisoning의 rug-pull 시나리오, 즉 처음에는 정상처럼
        보였던 MCP tool metadata가 나중에 변경되는 상황을 확인하기 위한 연결점이다.
    """

    try:
        # 스캔의 실제 책임은 service 계층에 둔다. CLI는 옵션을 받고 결과를 출력하는
        # 얇은 어댑터로 유지해야 테스트와 유지보수가 쉽다.
        report = run_scan(
            input_path=input_path,
            report_format=report_format,
            save_baseline_path=save_baseline_path,
            baseline_path=baseline_path,
        )

        if output_path is not None:
            _write_report(report, output_path)

    except ScanServiceError as error:
        # 내부 예외를 그대로 노출하지 않고 사용자가 이해할 수 있는 메시지로 출력한다.
        # Typer.Exit(code=1)을 사용하면 shell/script에서도 실패를 감지할 수 있다.
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(code=1) from error

    if output_path is None:
        console.print(report)


def _write_report(
    report: str,
    output_path: Path,
) -> None:
    """
    Rendered report 문자열을 지정한 파일에 UTF-8로 저장한다.

    파일 저장 실패는 CLI 전체에서 동일하게 처리할 수 있도록 `ScanServiceError`로
    감싼다. 이렇게 하면 권한 문제, 잘못된 경로, 디스크 오류가 발생해도 사용자는
    일관된 에러 메시지를 받는다.
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
