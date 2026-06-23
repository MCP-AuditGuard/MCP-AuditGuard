from __future__ import annotations

from pathlib import Path

import anyio
import typer

from core.dynamic_scan_models import (
    DiscoveryContext,
    DiscoveredMcpServer,
    DynamicScanResult,
    DynamicScanStatus,
    McpDiscoveryResult,
    McpServerSummary,
    ServerEnabledState,
    ServerSupportState,
)
from core.mcp_discovery import discover_mcp_servers
from core.redaction import redact_text
from core.scan_service import render_report


app = typer.Typer(
    name="mcp",
    help="Discover and dynamically scan configured MCP servers.",
    no_args_is_help=True,
)

_EXIT_CODES = {
    DynamicScanStatus.SUCCESS: 0,
    DynamicScanStatus.PARTIAL_SUCCESS: 2,
    DynamicScanStatus.FAILED: 1,
    DynamicScanStatus.TIMED_OUT: 3,
}


@app.command("list")
def list_servers(
    trust_project_config: bool = typer.Option(
        False,
        "--trust-project-config",
        help="Read MCP configuration from the trusted project scope.",
    ),
    project_root: Path | None = typer.Option(
        None,
        "--project-root",
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Optional project root used for MCP discovery.",
    ),
) -> None:
    """List discovered MCP servers without exposing connection secrets."""
    discovery = _discover(
        trust_project_config=trust_project_config,
        project_root=project_root,
    )

    typer.echo(f"MCP servers: {len(discovery.servers)}")
    for server in discovery.servers:
        _render_server_summary(server.to_summary())


@app.command("scan")
def scan_server(
    server_id: str = typer.Option(
        ...,
        "--server-id",
        help="Stable selection ID of the MCP server to scan.",
    ),
    trust_project_config: bool = typer.Option(
        False,
        "--trust-project-config",
        help="Read MCP configuration from the trusted project scope.",
    ),
    project_root: Path | None = typer.Option(
        None,
        "--project-root",
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Optional project root used for MCP discovery.",
    ),
) -> None:
    """Run a metadata-only dynamic scan against one discovered MCP server."""
    discovery = _discover(
        trust_project_config=trust_project_config,
        project_root=project_root,
    )
    selected = _select_server(discovery, server_id)
    _require_executable_server(selected)

    try:
        result = anyio.run(_run_selected_server, selected)
        _render_dynamic_result(result)
    except Exception as error:
        typer.echo(
            "Error: The dynamic MCP scan could not be completed safely.",
            err=True,
        )
        raise typer.Exit(code=1) from error

    exit_code = _EXIT_CODES[result.status]
    if exit_code:
        raise typer.Exit(code=exit_code)


def _build_discovery_context(
    *,
    trust_project_config: bool,
    project_root: Path | None,
) -> DiscoveryContext:
    return DiscoveryContext(
        current_working_directory=Path.cwd().resolve(strict=False),
        project_root=(
            project_root.resolve(strict=False)
            if project_root is not None
            else None
        ),
        user_home=Path.home().resolve(strict=False),
        include_trusted_project_config=trust_project_config,
    )


def _discover(
    *,
    trust_project_config: bool,
    project_root: Path | None,
) -> McpDiscoveryResult:
    context = _build_discovery_context(
        trust_project_config=trust_project_config,
        project_root=project_root,
    )

    try:
        return discover_mcp_servers(context)
    except Exception as error:
        typer.echo(
            "Error: MCP server discovery could not be completed safely.",
            err=True,
        )
        raise typer.Exit(code=1) from error


def _select_server(
    discovery: McpDiscoveryResult,
    server_id: str,
) -> DiscoveredMcpServer:
    normalized_id = server_id.strip()
    matches = [
        server
        for server in discovery.servers
        if server.selection_id == normalized_id
    ]

    if not matches:
        typer.echo(
            "Error: No MCP server matches the requested selection ID.",
            err=True,
        )
        raise typer.Exit(code=1)

    if len(matches) > 1:
        typer.echo(
            "Error: The requested selection ID is not unique.",
            err=True,
        )
        raise typer.Exit(code=1)

    return matches[0]


def _require_executable_server(server: DiscoveredMcpServer) -> None:
    if server.enabled_state == ServerEnabledState.DISABLED:
        typer.echo(
            "Error: The selected MCP server is disabled.",
            err=True,
        )
        raise typer.Exit(code=1)

    if server.support_state != ServerSupportState.SUPPORTED:
        reason = _safe_text(server.support_reason_code)
        typer.echo(
            f"Error: The selected MCP server is not executable "
            f"(reason={reason}).",
            err=True,
        )
        raise typer.Exit(code=1)

    if server.connection is None:
        typer.echo(
            "Error: The selected MCP server has no executable connection.",
            err=True,
        )
        raise typer.Exit(code=1)


async def _run_selected_server(
    server: DiscoveredMcpServer,
) -> DynamicScanResult:
    from core.dynamic_scan_service import run_dynamic_scan

    return await run_dynamic_scan(server)


def _render_server_summary(summary: McpServerSummary) -> None:
    typer.echo("Server")
    typer.echo(f"  selection_id: {_safe_text(summary.selection_id)}")
    typer.echo(f"  product: {summary.product.value}")
    typer.echo(f"  scope: {summary.scope.value}")
    typer.echo(f"  name: {_safe_text(summary.server_name)}")
    typer.echo(f"  transport: {summary.transport.value}")
    typer.echo(f"  enabled_state: {summary.enabled_state.value}")
    typer.echo(f"  support_state: {summary.support_state.value}")
    typer.echo(
        "  support_reason_code: "
        f"{_safe_text(summary.support_reason_code)}"
    )
    typer.echo(
        f"  command_basename: {_safe_text(summary.command_basename)}"
    )
    typer.echo(f"  http_origin: {_safe_text(summary.remote_origin)}")
    typer.echo(f"  argument_count: {summary.argument_count}")


def _render_dynamic_result(result: DynamicScanResult) -> None:
    typer.echo("Dynamic MCP scan")
    typer.echo(f"status: {result.status.value}")
    typer.echo("Target")
    _render_server_summary(result.target)

    typer.echo("Stages")
    if not result.stages:
        typer.echo("  none")
    for stage in result.stages:
        typer.echo(f"  {stage.stage.value}: {stage.status.value}")

    scan_summary = (
        result.scan_result.summary
        if result.scan_result is not None
        else None
    )
    finding_count = (
        scan_summary.finding_count if scan_summary is not None else 0
    )
    typer.echo(f"tools_collected: {len(result.collected_tools)}")
    typer.echo(f"findings: {finding_count}")
    typer.echo(
        "severity: "
        f"critical={scan_summary.by_severity.critical if scan_summary else 0} "
        f"high={scan_summary.by_severity.high if scan_summary else 0} "
        f"medium={scan_summary.by_severity.medium if scan_summary else 0} "
        f"low={scan_summary.by_severity.low if scan_summary else 0} "
        f"info={scan_summary.by_severity.info if scan_summary else 0}"
    )

    typer.echo("Tool activation")
    if not result.collected_tools:
        typer.echo("  none")
    for collected in result.collected_tools:
        typer.echo(
            "  "
            f"tool_id={_safe_text(collected.tool_id)} "
            f"name={_safe_text(collected.metadata.tool_name)} "
            f"status={collected.activation.status.value} "
            f"basis={_safe_text(collected.activation.safe_basis_code)}"
        )

    typer.echo("Issues")
    if not result.issues:
        typer.echo("  none")
    for issue in result.issues:
        typer.echo(
            "  "
            f"stage={issue.stage.value} "
            f"level={issue.level.value} "
            f"code={_safe_text(issue.code)} "
            f"message={_safe_text(issue.safe_message)}"
        )

    typer.echo("Cleanup")
    typer.echo(
        "  local: "
        f"{result.cleanup.local_cleanup.status.value}"
    )
    typer.echo(
        "  remote_session_termination: "
        f"{result.cleanup.remote_session_termination.status.value}"
    )
    remote_basis = _safe_text(
        result.cleanup.remote_session_termination.safe_basis_code
    )
    typer.echo(
        "  remote_basis: "
        f"{remote_basis}"
    )
    
    typer.echo("-" * 80)

    if result.scan_result is None:
        typer.echo("Scan report unavailable.")
    else:
        typer.echo(
            render_report(
                result.scan_result.findings,
                "markdown",
            )
        )

def _safe_text(value: object | None) -> str:
    if value is None:
        return "-"

    redacted, _ = redact_text(str(value))
    printable = "".join(
        character if character.isprintable() else " "
        for character in redacted
    )
    normalized = " ".join(printable.split())
    return normalized or "-"
