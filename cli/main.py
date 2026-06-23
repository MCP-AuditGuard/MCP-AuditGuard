from __future__ import annotations

"""
MCP-AuditGuard CLI 최상위 진입점.

이 모듈은 `auditguard` 명령 아래에 사용자가 실행할 수 있는 하위 명령을 등록한다.
Member5가 담당한 `scan`/`help` 흐름과, 이후 추가된 `web`/`mcp` 명령을 한 Typer app에
묶어 CLI 표면을 구성한다.

유지보수 포인트:
- 새 명령을 추가할 때는 이 파일에서 `app.command` 또는 `app.add_typer`로 등록한다.
- 명령 구현이 커지면 이 파일에 직접 로직을 넣지 말고 별도 모듈에 둔다.
- `auditguard help`는 Typer 기본 `--help`와 다르게 실제 사용 예시 중심의 안내다.
"""

import typer
from rich.console import Console

from cli.mcp import app as mcp_app
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

    현재는 공통 옵션이 없지만, 추후 `--verbose`나 `--debug`처럼 모든 명령에 적용할
    전역 옵션이 필요해지면 이 callback이 확장 지점이 된다.
    """


@app.command("help")
def help_command() -> None:
    """
    MCP-AuditGuard 사용 예시와 옵션 가이드를 출력한다.

    Typer의 `--help`는 옵션 정의를 자동으로 보여주는 기술적 도움말이다.
    반면 이 custom help command는 발표/데모/일반 사용자 실행을 위한 작업 중심
    가이드를 제공한다.
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


app.add_typer(
    mcp_app,
    name="mcp",
    help="Discover and statically scan configured MCP servers.",
)


if __name__ == "__main__":
    app()
