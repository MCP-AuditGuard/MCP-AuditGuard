from __future__ import annotations

import atexit
import os
import sys

from pathlib import Path

from mcp.server.fastmcp import FastMCP


argument_marker = sys.argv[1]
cleanup_marker = Path(sys.argv[2])
environment_marker = os.environ.get("MCP_TEST_VALUE", "missing")

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


if __name__ == "__main__":
    server.run(transport="stdio")
