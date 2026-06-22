from __future__ import annotations

import sys

from pathlib import Path

import anyio

from core.mcp_client import collect_tools_snapshot
from core.dynamic_scan_models import (
    LocalCleanupStatus,
    McpProduct,
    McpScope,
    McpServerSummary,
    McpTransport,
    ServerEnabledState,
    ServerSupportState,
    StdioConnectionConfig,
)


def test_real_stdio_sdk_snapshot_uses_separate_args_and_cleans_up(
    tmp_path: Path,
) -> None:
    fixture_server = (
        Path(__file__).parents[1] / "fixtures" / "stdio_mcp_server.py"
    )
    cleanup_marker = tmp_path / "server-closed.txt"
    argument_marker = "value with spaces & no shell"
    connection = StdioConnectionConfig(
        server_name="fixture",
        command=sys.executable,
        args=[
            str(fixture_server),
            argument_marker,
            str(cleanup_marker),
        ],
        env_references={
            "MCP_TEST_VALUE": "HOST_MCP_TEST_VALUE",
        },
    )
    summary = McpServerSummary(
        selection_id="test:stdio:fixture",
        product=McpProduct.CLAUDE,
        scope=McpScope.PROJECT,
        source_label="Test STDIO fixture",
        server_name="fixture",
        transport=McpTransport.STDIO,
        enabled_state=ServerEnabledState.ENABLED,
        support_state=ServerSupportState.SUPPORTED,
        command_basename=Path(sys.executable).name,
        argument_count=3,
    )

    async def run():
        return await collect_tools_snapshot(
            connection,
            server_summary=summary,
            environment={
                "HOST_MCP_TEST_VALUE": "resolved-at-execution",
                "UNRELATED_SECRET": "must-not-be-forwarded",
            },
        )

    result = anyio.run(run)

    assert [tool.tool_name for tool in result.tools] == ["echo"]
    assert result.tools[0].description == (
        f"{argument_marker}|resolved-at-execution"
    )
    assert result.tools[0].raw["_meta"] == {"fixture": "stdio"}
    assert result.issues == []
    assert (
        result.cleanup.local_cleanup.status
        == LocalCleanupStatus.SUCCEEDED
    )
    assert cleanup_marker.read_text(encoding="utf-8") == "closed"
