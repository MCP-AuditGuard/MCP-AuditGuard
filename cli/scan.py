"""
AuditGuard scan command module.

이 모듈은 `auditguard scan` 명령에서 실제로 호출되는 scan command를 정의한다.
최신 구조에서는 Typer app 자체는 `cli/main.py`가 소유하고, 이 파일은 scan 명령의
옵션과 출력 처리만 담당한다.

팀원 5 담당 영역:
- tools.json 입력 옵션 제공
- Markdown/JSON 리포트 형식 선택
- 리포트 파일 저장 옵션 제공
- baseline 저장 및 이전 baseline 비교 옵션 연결
- scan service에서 발생한 오류를 사용자 친화적인 CLI 메시지로 변환

실행 흐름:
tools.json 입력
→ core.scan_service.run_scan() 호출
→ ToolMetadata 수집
→ detector 실행
→ baseline diff finding 추가
→ Markdown/JSON report 생성
→ 터미널 출력 또는 파일 저장

보안적 의미:
CLI는 비전문 사용자도 MCP tool metadata 보안 점검을 실행할 수 있게 해주는
사용자 인터페이스다. 사용자는 MCP 서버를 AI Agent에 연결하기 전,
description/schema/annotations에 숨겨진 Tool Poisoning 위험과 baseline 이후
metadata rug-pull 가능성을 확인할 수 있다.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from core.exceptions import ScanServiceError
from core.scan_service import run_scan
from cli.help_text import AUDITGUARD_HELP_TEXT


# Rich Console은 에러 메시지를 색상으로 구분해 CLI 가독성을 높인다.
# 보안 도구에서는 실패 원인을 사용자가 빠르게 이해하는 것이 중요하다.
console = Console()


# `python -m cli.scan scan ...` 실행을 지원하기 위한 작은 Typer app이다.
# 기본 패키지 entrypoint는 `cli.main:app`이지만, 문서와 시연에서 cli.scan 직접 실행도 사용할 수 있다.
app = typer.Typer(
    name="auditguard-scan",
    help="MCP-AuditGuard scan command",
    no_args_is_help=True,
)


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
    enable_semantic: bool = typer.Option(
        False,
        "--enable-semantic",
        help="Enable local embedding similarity detection.",
    ),
    semantic_threshold: float = typer.Option(
        0.82,
        "--semantic-threshold",
        min=0.0,
        max=1.0,
        help="Semantic cosine similarity threshold.",
    ),
    embedding_model_path: Path | None = typer.Option(
        None,
        "--embedding-model-path",
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Optional local embedding model directory.",
    ),
) -> None:
    """
    MCP tool metadata를 스캔하고 Markdown 또는 JSON 리포트를 출력한다.

    Args:
        input_path: 분석할 tools.json 파일 경로.
        report_format: 출력 리포트 형식. markdown 또는 json을 지원한다.
        output_path: 리포트를 파일로 저장할 선택 경로.
        save_baseline_path: 현재 metadata baseline을 저장할 선택 경로.
        baseline_path: 이전 baseline과 현재 metadata를 비교할 선택 경로.
        enable_semantic: 로컬 임베딩 유사도 기반 semantic detector 활성화 여부.
        semantic_threshold: semantic finding으로 판단할 cosine similarity 기준값.
        embedding_model_path: 로컬 임베딩 모델 디렉터리 경로.

    Returns:
        없음. 결과는 터미널 출력 또는 파일 저장으로 전달된다.

    Security Note:
        baseline 저장은 현재 정상 metadata 상태를 기록하고,
        baseline 비교는 이후 description/schema/annotations 변경을 rug-pull 가능성으로
        검토할 수 있게 한다. detector finding과 baseline diff finding은 같은 report로 출력된다.
    """

    try:
        report = run_scan(
            input_path=input_path,
            report_format=report_format,
            save_baseline_path=save_baseline_path,
            baseline_path=baseline_path,
            enable_semantic=enable_semantic,
            semantic_threshold=semantic_threshold,
            embedding_model_path=embedding_model_path,
        )

        if output_path is not None:
            _write_report(report, output_path)

    except ScanServiceError as error:
        # 내부 traceback 대신 사용자가 이해할 수 있는 짧은 에러만 보여준다.
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(code=1) from error

    # --output이 없을 때만 터미널에 출력한다.
    # 파일 저장을 선택한 경우에는 shell script에서 다루기 쉽도록 조용히 종료한다.
    if output_path is None:
        console.print(report)


def _write_report(
    report: str,
    output_path: Path,
) -> None:
    """
    렌더링된 report 문자열을 지정한 파일에 UTF-8로 저장한다.

    Args:
        report: Markdown 또는 JSON 리포트 문자열.
        output_path: 저장할 파일 경로.

    Returns:
        없음.

    Security Note:
        파일 출력은 CI artifact, 보안 리뷰 기록, 발표 자료로 남기기 쉽다.
        이 함수는 외부 서버 전송 없이 로컬 파일 저장만 수행한다.
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


@app.command("scan")
def standalone_scan_command(
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
    enable_semantic: bool = typer.Option(
        False,
        "--enable-semantic",
        help="Enable local embedding similarity detection.",
    ),
    semantic_threshold: float = typer.Option(
        0.82,
        "--semantic-threshold",
        min=0.0,
        max=1.0,
        help="Semantic cosine similarity threshold.",
    ),
    embedding_model_path: Path | None = typer.Option(
        None,
        "--embedding-model-path",
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Optional local embedding model directory.",
    ),
) -> None:
    """
    `python -m cli.scan scan ...` 실행을 위한 wrapper command다.

    실제 scan 처리는 `scan_command`에 위임해 `auditguard scan`과 동일한 동작을 유지한다.
    """

    scan_command(
        input_path=input_path,
        report_format=report_format,
        output_path=output_path,
        save_baseline_path=save_baseline_path,
        baseline_path=baseline_path,
        enable_semantic=enable_semantic,
        semantic_threshold=semantic_threshold,
        embedding_model_path=embedding_model_path,
    )


@app.command("help")
def help_command() -> None:
    """
    `python -m cli.scan help` 실행 시 작업 중심 사용 가이드를 출력한다.
    """

    console.print(AUDITGUARD_HELP_TEXT)


if __name__ == "__main__":
    app()
