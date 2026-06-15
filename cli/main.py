from __future__ import annotations

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
    """


@app.command("help")
def help_command() -> None:
    """
    Show MCP-AuditGuard usage examples and option guide.
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