from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import anyio
import pytest

from mcp import types

from core import mcp_client
from core.dynamic_scan_models import (
    DynamicScanStage,
    DynamicScanTimeouts,
    IssueLevel,
    LocalCleanupStatus,
    McpProduct,
    McpScope,
    McpServerSummary,
    McpTransport,
    ServerEnabledState,
    ServerSupportState,
    StdioConnectionConfig,
    StreamableHttpConnectionConfig,
)


@dataclass
class FakeClientState:
    events: list[str] = field(default_factory=list)
    server_parameters: Any = None
    initialize_result: Any = None
    pages: list[Any] = field(default_factory=list)
    transport_open_delay: float = 0
    transport_close_delay: float = 0
    transport_close_error: Exception | None = None
    initialize_delay: float = 0
    list_delay: float = 0
    list_error: Exception | None = None


class FakeSession:
    def __init__(
        self,
        read_stream: object,
        write_stream: object,
        *,
        client_info: types.Implementation,
        state: FakeClientState,
    ) -> None:
        self.state = state
        self.state.events.append("session_created")
        assert read_stream == "read"
        assert write_stream == "write"
        assert client_info.name == "mcp-auditguard"

    async def __aenter__(self) -> FakeSession:
        self.state.events.append("session_open")
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.state.events.append("session_close")

    async def initialize(self) -> Any:
        self.state.events.append("initialize")
        if self.state.initialize_delay:
            await anyio.sleep(self.state.initialize_delay)
        return self.state.initialize_result

    async def list_tools(
        self,
        cursor: str | None = None,
        *,
        params: types.PaginatedRequestParams | None = None,
    ) -> Any:
        requested_cursor = (
            params.cursor if params is not None else cursor
        )
        self.state.events.append(f"list:{requested_cursor}")
        if self.state.list_delay:
            await anyio.sleep(self.state.list_delay)
        if self.state.list_error is not None:
            raise self.state.list_error
        return self.state.pages.pop(0)


class FakeTool:
    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.name = document.get("name")

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return dict(self.document)


def make_summary(
    *,
    enabled_state: ServerEnabledState = ServerEnabledState.ENABLED,
    support_state: ServerSupportState = ServerSupportState.SUPPORTED,
    transport: McpTransport = McpTransport.STDIO,
) -> McpServerSummary:
    return McpServerSummary(
        selection_id="codex:user:docs",
        product=McpProduct.CODEX,
        scope=McpScope.USER,
        source_label="Codex user config",
        server_name="docs",
        transport=transport,
        enabled_state=enabled_state,
        support_state=support_state,
        command_basename="python",
    )


def make_connection() -> StdioConnectionConfig:
    return StdioConnectionConfig(
        server_name="docs",
        command="python",
        args=["server.py"],
    )


def make_initialize_result(
    *,
    with_tools: bool = True,
) -> types.InitializeResult:
    return types.InitializeResult(
        protocolVersion=types.LATEST_PROTOCOL_VERSION,
        capabilities=types.ServerCapabilities(
            tools=types.ToolsCapability() if with_tools else None,
        ),
        serverInfo=types.Implementation(
            name="fake-server",
            version="1.0",
        ),
    )


def make_tool(name: str) -> types.Tool:
    return types.Tool(
        name=name,
        description=f"{name} description",
        inputSchema={"type": "object"},
        _meta={"extension": name},
    )


def install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    state: FakeClientState,
) -> None:
    @asynccontextmanager
    async def fake_stdio_client(
        server_parameters: Any,
        *,
        errlog: Any,
    ):
        state.server_parameters = server_parameters
        state.events.append("transport_start")
        if state.transport_open_delay:
            await anyio.sleep(state.transport_open_delay)
        state.events.append("transport_open")
        assert errlog is not None
        try:
            yield "read", "write"
        finally:
            if state.transport_close_delay:
                await anyio.sleep(state.transport_close_delay)
            state.events.append("transport_close")
            if state.transport_close_error is not None:
                raise state.transport_close_error

    def fake_session_factory(
        read_stream: object,
        write_stream: object,
        *,
        client_info: types.Implementation,
    ) -> FakeSession:
        return FakeSession(
            read_stream,
            write_stream,
            client_info=client_info,
            state=state,
        )

    monkeypatch.setattr(mcp_client, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(
        mcp_client,
        "ClientSession",
        fake_session_factory,
    )


def run_snapshot(
    *,
    connection: (
        StdioConnectionConfig
        | StreamableHttpConnectionConfig
        | None
    ),
    summary: McpServerSummary,
    timeouts: DynamicScanTimeouts | None = None,
    environment: dict[str, str] | None = None,
):
    async def run():
        return await mcp_client.collect_tools_snapshot(
            connection,
            server_summary=summary,
            timeouts=timeouts,
            environment=environment,
        )

    return anyio.run(run)


def test_collects_paginated_tools_after_initialize_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        initialize_result=make_initialize_result(),
        pages=[
            types.ListToolsResult(
                tools=[make_tool("search")],
                nextCursor="page-2",
            ),
            types.ListToolsResult(
                tools=[make_tool("read")],
            ),
        ],
    )
    install_fake_client(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
    )

    assert [tool.tool_name for tool in result.tools] == ["search", "read"]
    assert result.tools[0].raw["_meta"] == {"extension": "search"}
    assert result.protocol_version == types.LATEST_PROTOCOL_VERSION
    assert result.server_implementation is not None
    assert result.server_implementation.name == "fake-server"
    assert result.issues == []
    assert (
        result.cleanup.local_cleanup.status
        == LocalCleanupStatus.SUCCEEDED
    )
    assert state.events == [
        "transport_start",
        "transport_open",
        "session_created",
        "session_open",
        "initialize",
        "list:None",
        "list:page-2",
        "session_close",
        "transport_close",
    ]


def test_resolves_only_configured_environment_and_preserves_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[])],
    )
    install_fake_client(monkeypatch, state)
    connection = StdioConnectionConfig(
        server_name="docs",
        command="python",
        args=["value with spaces", "x & echo not-a-shell"],
        env_values={"STATIC": "configured"},
        env_references={"TOKEN": "HOST_TOKEN"},
    )

    result = run_snapshot(
        connection=connection,
        summary=make_summary(),
        environment={
            "HOST_TOKEN": "resolved-value",
            "UNRELATED_SECRET": "must-not-be-forwarded",
        },
    )

    assert result.issues == []
    assert state.server_parameters.command == "python"
    assert state.server_parameters.args == [
        "value with spaces",
        "x & echo not-a-shell",
    ]
    assert state.server_parameters.env == {
        "STATIC": "configured",
        "TOKEN": "resolved-value",
    }
    assert "UNRELATED_SECRET" not in state.server_parameters.env


@pytest.mark.parametrize(
    ("summary", "connection", "expected_code"),
    [
        (
            make_summary(enabled_state=ServerEnabledState.DISABLED),
            make_connection(),
            "server_disabled",
        ),
        (
            make_summary(
                support_state=ServerSupportState.UNSUPPORTED,
            ),
            None,
            "server_not_supported",
        ),
        (
            make_summary(
                support_state=ServerSupportState.INVALID,
            ),
            None,
            "server_not_supported",
        ),
    ],
)
def test_non_executable_targets_do_not_start_transport(
    monkeypatch: pytest.MonkeyPatch,
    summary: McpServerSummary,
    connection: (
        StdioConnectionConfig
        | StreamableHttpConnectionConfig
        | None
    ),
    expected_code: str,
) -> None:
    called = False

    def fail_if_called(*args: Any, **kwargs: Any) -> None:
        nonlocal called
        called = True
        raise AssertionError("transport must not start")

    monkeypatch.setattr(mcp_client, "stdio_client", fail_if_called)

    result = run_snapshot(
        connection=connection,
        summary=summary,
    )

    assert called is False
    assert [issue.code for issue in result.issues] == [expected_code]


def test_missing_environment_reference_does_not_start_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_if_called(*args: Any, **kwargs: Any) -> None:
        nonlocal called
        called = True
        raise AssertionError("transport must not start")

    monkeypatch.setattr(mcp_client, "stdio_client", fail_if_called)
    connection = StdioConnectionConfig(
        server_name="docs",
        command="python",
        env_references={"TOKEN": "MISSING_TOKEN"},
    )

    result = run_snapshot(
        connection=connection,
        summary=make_summary(),
        environment={},
    )

    assert called is False
    assert [issue.code for issue in result.issues] == [
        "environment_reference_missing"
    ]
    assert "TOKEN" not in str(result.model_dump())


def test_tools_capability_missing_skips_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        initialize_result=make_initialize_result(with_tools=False),
    )
    install_fake_client(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
    )

    assert [issue.code for issue in result.issues] == [
        "tools_capability_missing"
    ]
    assert not any(event.startswith("list:") for event in state.events)
    assert state.events[-2:] == ["session_close", "transport_close"]


def test_invalid_server_info_is_warning_and_valid_tools_are_collected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        initialize_result=SimpleNamespace(
            protocolVersion=types.LATEST_PROTOCOL_VERSION,
            capabilities=SimpleNamespace(
                tools=types.ToolsCapability(),
            ),
            serverInfo=SimpleNamespace(
                name="",
                version="1.0",
            ),
        ),
        pages=[
            types.ListToolsResult(
                tools=[make_tool("search")],
            )
        ],
    )
    install_fake_client(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
    )

    assert [tool.tool_name for tool in result.tools] == ["search"]
    assert [issue.code for issue in result.issues] == [
        "server_info_invalid"
    ]
    assert result.issues[0].level == IssueLevel.WARNING
    assert "list:None" in state.events


def test_unsupported_protocol_version_skips_list_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        initialize_result=types.InitializeResult(
            protocolVersion="1900-01-01",
            capabilities=types.ServerCapabilities(
                tools=types.ToolsCapability(),
            ),
            serverInfo=types.Implementation(
                name="old-server",
                version="1.0",
            ),
        )
    )
    install_fake_client(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
    )

    assert [issue.code for issue in result.issues] == [
        "protocol_version_unsupported"
    ]
    assert not any(event.startswith("list:") for event in state.events)
    assert state.events[-2:] == ["session_close", "transport_close"]


def test_partial_metadata_duplicate_and_repeated_cursor_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        initialize_result=make_initialize_result(),
        pages=[
            SimpleNamespace(
                tools=[
                    FakeTool(
                        {
                            "name": "search",
                            "inputSchema": {"type": "object"},
                        }
                    ),
                    FakeTool(
                        {
                            "name": " ",
                            "inputSchema": {"type": "object"},
                        }
                    ),
                ],
                nextCursor="repeat",
            ),
            SimpleNamespace(
                tools=[
                    FakeTool(
                        {
                            "name": "search",
                            "inputSchema": {"type": "object"},
                        }
                    ),
                    FakeTool(
                        {
                            "name": "read",
                            "inputSchema": {"type": "object"},
                            "futureField": {"preserved": True},
                        }
                    ),
                ],
                nextCursor="repeat",
            ),
        ],
    )
    install_fake_client(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
    )

    assert [tool.tool_name for tool in result.tools] == ["search", "read"]
    assert result.tools[1].raw["futureField"] == {"preserved": True}
    assert [issue.code for issue in result.issues] == [
        "tool_metadata_invalid",
        "duplicate_tool_name",
        "pagination_cursor_repeated",
    ]
    assert result.issues[0].item_index == 1
    assert result.issues[0].level == IssueLevel.WARNING
    assert result.issues[1].item_index == 2
    assert result.issues[1].level == IssueLevel.WARNING
    assert result.issues[2].stage == DynamicScanStage.LIST_TOOLS


@pytest.mark.parametrize(
    ("initialize_delay", "list_error", "expected_code"),
    [
        (0.05, None, "initialize_timeout"),
        (0, RuntimeError("unsafe details"), "list_tools_failed"),
    ],
)
def test_error_and_timeout_paths_close_session_and_transport(
    monkeypatch: pytest.MonkeyPatch,
    initialize_delay: float,
    list_error: Exception | None,
    expected_code: str,
) -> None:
    state = FakeClientState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[])],
        initialize_delay=initialize_delay,
        list_error=list_error,
    )
    install_fake_client(monkeypatch, state)
    timeouts = DynamicScanTimeouts(
        initialize_seconds=0.01,
        list_tools_page_seconds=0.01,
    )

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
        timeouts=timeouts,
    )

    assert expected_code in {issue.code for issue in result.issues}
    assert state.events[-2:] == ["session_close", "transport_close"]
    assert (
        result.cleanup.local_cleanup.status
        == LocalCleanupStatus.SUCCEEDED
    )


def test_all_invalid_metadata_is_not_reported_as_empty_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        initialize_result=make_initialize_result(),
        pages=[
            SimpleNamespace(
                tools=[
                    FakeTool(
                        {
                            "name": "",
                            "inputSchema": {"type": "object"},
                        }
                    )
                ],
                nextCursor=None,
            )
        ],
    )
    install_fake_client(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
    )

    assert result.tools == []
    assert [issue.code for issue in result.issues] == [
        "tool_metadata_invalid",
        "all_tool_metadata_invalid",
    ]


def test_stdio_start_timeout_is_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        transport_open_delay=0.05,
    )
    install_fake_client(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
        timeouts=DynamicScanTimeouts(stdio_start_seconds=0.01),
    )

    assert [issue.code for issue in result.issues] == [
        "stdio_start_timeout"
    ]
    assert state.events == ["transport_start"]
    assert (
        result.cleanup.local_cleanup.status
        == LocalCleanupStatus.SUCCEEDED
    )


def test_cleanup_failure_is_returned_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[])],
        transport_close_error=RuntimeError("unsafe details"),
    )
    install_fake_client(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
    )

    assert [issue.code for issue in result.issues] == [
        "local_cleanup_failed"
    ]
    assert (
        result.cleanup.local_cleanup.status
        == LocalCleanupStatus.FAILED
    )
    assert [
        issue.code for issue in result.cleanup.local_cleanup.issues
    ] == ["local_cleanup_failed"]
    assert "unsafe details" not in str(result.model_dump())


def test_cleanup_timeout_is_returned_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeClientState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[])],
        transport_close_delay=0.05,
    )
    install_fake_client(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        summary=make_summary(),
        timeouts=DynamicScanTimeouts(local_cleanup_seconds=0.01),
    )

    assert [issue.code for issue in result.issues] == [
        "local_cleanup_timeout"
    ]
    assert (
        result.cleanup.local_cleanup.status
        == LocalCleanupStatus.FAILED
    )
