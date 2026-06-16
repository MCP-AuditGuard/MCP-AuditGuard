from __future__ import annotations

import typer
from rich.console import Console

from cli.help_text import AUDITGUARD_HELP_TEXT
from cli.scan import scan_command


app = typer.Typer(
    name="auditguard",
    help="MCP-AuditGuard CLI",
    no_args_is_help=True,
)

console = Console()


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
def web_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Web server host."),
    port: int = typer.Option(8000, "--port", help="Web server port."),
    reload: bool = typer.Option(False, "--reload", help="Reload on source changes."),
) -> None:
    """
    로컬 웹 인터페이스를 실행합니다.

    uvicorn은 웹 명령을 실제로 실행할 때만 import합니다.
    이렇게 하면 CLI help나 scan 테스트가 웹 서버 의존성 때문에 실패하지 않습니다.
    """

    from cli.web import web_command as run_web_command

    run_web_command(host=host, port=port, reload=reload)


app.command(
    name="web",
    help="Run the MCP-AuditGuard local web interface.",
)(web_command)


if __name__ == "__main__":
    app()
