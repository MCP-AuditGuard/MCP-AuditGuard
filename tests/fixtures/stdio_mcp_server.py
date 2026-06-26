from __future__ import annotations

import atexit
import os
import sys
import time

from pathlib import Path

import anyio

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server


argument_marker = sys.argv[1]
cleanup_marker = Path(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 else "normal"
pid_marker = Path(sys.argv[4]) if len(sys.argv) > 4 else None
environment_marker = os.environ.get("MCP_TEST_VALUE", "missing")

if pid_marker is not None:
    pid_marker.write_text(str(os.getpid()), encoding="utf-8")

server = FastMCP("auditguard-test-server")


@server.tool(
    description=f"{argument_marker}|{environment_marker}",
    meta={"fixture": "stdio"},
)
def echo(value: str) -> str:
    """Return the supplied value."""
    return value


@atexit.register
def mark_cleanup() -> None:
    cleanup_marker.write_text("closed", encoding="utf-8")


async def run_fastmcp_server() -> None:
    await server.run_stdio_async()
    if mode == "cleanup-timeout":
        await anyio.sleep_forever()


async def run_list_timeout_server() -> None:
    timeout_server = Server(
        "auditguard-list-timeout-server",
        version="1.0.0",
    )

    @timeout_server.list_tools()
    async def list_tools(
        _: types.ListToolsRequest,
    ) -> types.ListToolsResult:
        await anyio.sleep_forever()
        return types.ListToolsResult(tools=[])

    async with stdio_server() as streams:
        read_stream, write_stream = streams
        await timeout_server.run(
            read_stream,
            write_stream,
            timeout_server.create_initialization_options(),
        )


if __name__ == "__main__":
    if mode == "initialize-timeout":
        while True:
            time.sleep(60)
    elif mode == "list-tools-timeout":
        anyio.run(run_list_timeout_server)
    elif mode in {"normal", "cleanup-timeout"}:
        anyio.run(run_fastmcp_server)
    else:
        raise ValueError(f"unsupported fixture mode: {mode}")
