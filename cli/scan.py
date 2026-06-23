from __future__ import annotations

"""
AuditGuard `scan` 명령어 구현 모듈.

이 파일은 사용자가 `auditguard scan`으로 tools.json 기반 정적 스캔을 실행할 때의
옵션을 정의하고, 실제 스캔은 `core.scan_service.run_scan`에 위임한다.

Member5 담당 관점:
- CLI 옵션을 사용자 친화적으로 노출한다.
- Markdown/JSON report를 터미널 출력 또는 파일 저장으로 연결한다.
- baseline 저장/비교 옵션을 scan pipeline에 전달한다.

보안적 의미:
- CLI는 비전문 사용자도 MCP tool metadata 점검을 실행하게 해주는 인터페이스다.
- detector와 CLI를 분리해 탐지기가 추가되어도 명령어 구조를 크게 바꾸지 않는다.
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
        input_path: 검사할 tools.json 경로. Typer 옵션에서 파일 존재/읽기 가능 여부를
            먼저 검증한다.
        report_format: 출력 형식. 현재는 markdown/json만 지원한다.
        output_path: 지정하면 파일 저장, 지정하지 않으면 터미널 출력.
        save_baseline_path: 현재 metadata 상태를 baseline JSON으로 저장할 경로.
        baseline_path: 이전 baseline과 현재 metadata를 비교할 때 사용할 경로.

    Security Note:
        `--baseline`은 이전에 정상으로 판단한 metadata와 현재 metadata를 비교해
        rug-pull 또는 사후 Tool Poisoning 가능성을 확인하는 옵션이다.
    """

    try:
        # CLI 계층은 입력/출력만 맡고, 스캔 순서와 예외 변환은 service 계층에 둔다.
        # 이렇게 해야 Web UI와 CLI가 같은 scan 동작을 재사용할 수 있다.
        report = run_scan(
            input_path=input_path,
            report_format=report_format,
            save_baseline_path=save_baseline_path,
            baseline_path=baseline_path,
        )

        if output_path is not None:
            _write_report(report, output_path)

    except ScanServiceError as error:
        # 내부 traceback 대신 사용자가 이해할 수 있는 에러 메시지를 출력한다.
        # Exit code 1은 shell script나 CI에서 실패를 감지할 수 있게 한다.
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(code=1) from error

    if output_path is None:
        console.print(report)


def _write_report(
    report: str,
    output_path: Path,
) -> None:
    """
    렌더링된 report 문자열을 지정한 파일에 UTF-8로 저장한다.

    파일 쓰기 실패는 CLI에서 일관되게 처리할 수 있도록 `ScanServiceError`로 감싼다.
    예를 들어 권한 문제, 잘못된 경로, 디스크 오류가 모두 같은 사용자 친화적
    에러 출력 흐름을 탄다.
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
