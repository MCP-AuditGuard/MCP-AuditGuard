from __future__ import annotations

import typer
import uvicorn
from rich.console import Console


console = Console()


def web_command(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help=(
            "Web server host address. "
            "The default only allows access from this PC."
        ),
    ),
    port: int = typer.Option(
        8000,
        "--port",
        min=1,
        max=65535,
        help="Web server port.",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help=(
            "Automatically restart the server when source code changes. "
            "Use this option during development."
        ),
    ),
) -> None:
    """
    Run the MCP-AuditGuard local web interface.
    """

    server_url = f"http://{host}:{port}"

    console.print()
    console.print("[bold green]MCP-AuditGuard web server[/bold green]")
    console.print(f"Address: [link={server_url}]{server_url}[/link]")

    if reload:
        console.print(
            "Mode: [yellow]development reload enabled[/yellow]"
        )
    else:
        console.print(
            "Mode: [green]normal[/green]"
        )

    console.print(
        "Stop server: [bold]Ctrl+C[/bold]"
    )
    console.print()

    uvicorn.run(
        "web.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )