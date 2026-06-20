from __future__ import annotations

"""
MCP-AuditGuard CLI 최상위 진입점.

이 모듈은 Typer app을 만들고 `help`, `scan`, `web` 명령을 등록한다.
실제 scan 로직은 `cli.scan`, 웹 서버 실행은 `cli.web`에 두어 책임을 분리한다.

Member5 담당 관점:
- 사용자가 실행하는 명령어 표면을 구성한다.
- Typer 기본 --help와 별도 `auditguard help` 사용 가이드를 함께 제공한다.

유지보수 포인트:
- 새로운 사용자 명령을 추가할 때는 이 파일에서 app.command로 등록한다.
- 명령이 커지면 구현은 별도 모듈에 두고 여기서는 연결만 하는 구조를 유지한다.
"""

import typer
from rich.console import Console

from cli.scan import scan_command
from cli.web import web_command


app = typer.Typer(
    name="auditguard",
    help="MCP-AuditGuard CLI",
    no_args_is_help=True,
)

console = Console()


AUDITGUARD_HELP_TEXT = """\
MCP-AuditGuard Usage Guide

Purpose
  MCP-AuditGuard scans MCP tool metadata, descriptions, schemas,
  annotations, and baseline changes for Tool Poisoning or suspicious
  metadata tampering.

Basic scan
  auditguard scan --input tools.json
  python -m cli.main scan --input tools.json

Output format
  auditguard scan --input tools.json --format markdown
  auditguard scan --input tools.json --format json

Write a report file
  auditguard scan --input tools.json --output report.md
  auditguard scan --input tools.json --format json --output report.json

Save a baseline
  auditguard scan --input tools.json --save-baseline baseline.json

Compare with a previous baseline
  auditguard scan --input tools-new.json --baseline baseline.json

Run local web interface
  auditguard web

Run local web interface for development
  auditguard web --reload

Change web server port
  auditguard web --port 8080

Scan options
  --input, -i           Required path to tools.json.
  --format, -f          Report format: markdown or json.
                        Default: markdown.
  --output, -o          Optional report output path.
  --save-baseline       Optional path to save current metadata baseline.
  --baseline            Optional previous baseline JSON path to compare.

Web options
  --host                Web server host. Default: 127.0.0.1.
  --port                Web server port. Default: 8000.
  --reload              Restart automatically when source code changes.

Built-in Typer help
  auditguard --help
  auditguard scan --help
  auditguard web --help
"""


@app.callback()
def main() -> None:
    """
    MCP-AuditGuard command line interface.

    Typer callback은 app 자체의 공통 진입점이다. 현재는 별도 공통 옵션이 없지만,
    추후 전역 verbose/debug 옵션을 추가할 때 이 함수가 확장 지점이 된다.
    """


@app.command("help")
def help_command() -> None:
    """
    MCP-AuditGuard 사용 예시와 옵션 가이드를 출력한다.

    Typer의 `--help`는 옵션 목록을 자동 생성하는 기술적 도움말이고,
    이 명령은 데모/발표/일반 사용자 실행 흐름을 설명하는 작업 중심 가이드다.
    """

    # Typer가 제공하는 --help와 별도로,
    # 실제 작업 중심의 사용 예제를 출력합니다.
    console.print(AUDITGUARD_HELP_TEXT)


# scan.py의 기존 scan_command를
# auditguard scan 명령으로 등록합니다.
app.command(
    name="scan",
    help="Scan MCP tools metadata and render a report.",
)(scan_command)


# web.py의 web_command를
# auditguard web 명령으로 등록합니다.
app.command(
    name="web",
    help="Run the MCP-AuditGuard local web interface.",
)(web_command)


if __name__ == "__main__":
    app()
