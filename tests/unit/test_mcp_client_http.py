from __future__ import annotations

import ssl

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import anyio
import httpx
import pytest

from mcp import types

from core import mcp_client
from core.dynamic_scan_models import (
    DynamicScanStage,
    DynamicScanTimeouts,
    LocalCleanupStatus,
    McpProduct,
    McpScope,
    McpServerSummary,
    McpTransport,
    RemoteSessionTerminationStatus,
    ServerEnabledState,
    ServerSupportState,
    StreamableHttpConnectionConfig,
)


@dataclass
class FakeHttpState:
    events: list[str] = field(default_factory=list)
    client_kwargs: dict[str, Any] = field(default_factory=dict)
    transport_url: str | None = None
    terminate_on_close: bool | None = None
    initialize_result: Any = None
    initialize_error: Exception | None = None
    pages: list[Any] = field(default_factory=list)
    session_id: str | None = "session-secret"
    transport_open_delay: float = 0
    transport_close_delay: float = 0
    transport_close_error: Exception | None = None
    session_close_delay: float = 0
    session_close_error: Exception | None = None
    initialize_delay: float = 0
    list_delay: float = 0
    list_error: Exception | None = None
    delete_status: int = 204
    delete_delay: float = 0
    delete_error: Exception | None = None
    delete_url: str | None = None
    delete_headers: dict[str, str] | None = None


class FakeHttpClient:
    def __init__(self, state: FakeHttpState) -> None:
        self.state = state

    async def __aenter__(self) -> FakeHttpClient:
        self.state.events.append("http_client_open")
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.state.events.append("http_client_close")

    async def delete(
        self,
        url: str,
        *,
        headers: dict[str, str],
    ) -> Any:
        self.state.events.append("delete")
        self.state.delete_url = url
        self.state.delete_headers = dict(headers)
        if self.state.delete_delay:
            await anyio.sleep(self.state.delete_delay)
        if self.state.delete_error is not None:
            raise self.state.delete_error
        return SimpleNamespace(status_code=self.state.delete_status)


class FakeSession:
    def __init__(
        self,
        read_stream: object,
        write_stream: object,
        *,
        client_info: types.Implementation,
        state: FakeHttpState,
    ) -> None:
        assert read_stream == "http-read"
        assert write_stream == "http-write"
        assert client_info.name == "mcp-auditguard"
        self.state = state
        self.state.events.append("session_created")

    async def __aenter__(self) -> FakeSession:
        self.state.events.append("session_open")
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        if self.state.session_close_delay:
            await anyio.sleep(self.state.session_close_delay)
        self.state.events.append("session_close")
        if self.state.session_close_error is not None:
            raise self.state.session_close_error

    async def initialize(self) -> Any:
        self.state.events.append("initialize")
        if self.state.initialize_delay:
            await anyio.sleep(self.state.initialize_delay)
        if self.state.initialize_error is not None:
            raise self.state.initialize_error
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


def make_summary() -> McpServerSummary:
    return McpServerSummary(
        selection_id="claude:project:http-docs",
        product=McpProduct.CLAUDE,
        scope=McpScope.PROJECT,
        source_label="Claude project config",
        server_name="http-docs",
        transport=McpTransport.STREAMABLE_HTTP,
        enabled_state=ServerEnabledState.ENABLED,
        support_state=ServerSupportState.SUPPORTED,
        remote_origin="https://example.com",
    )


def make_connection(
    *,
    static_headers: dict[str, str] | None = None,
    environment_header_references: dict[str, str] | None = None,
    bearer_token_environment_reference: str | None = None,
) -> StreamableHttpConnectionConfig:
    return StreamableHttpConnectionConfig(
        server_name="http-docs",
        url=(
            "https://user:password@example.com/private/mcp"
            "?token=URL_SECRET"
        ),
        static_headers=static_headers or {},
        environment_header_references=(
            environment_header_references or {}
        ),
        bearer_token_environment_reference=(
            bearer_token_environment_reference
        ),
    )


def make_initialize_result() -> types.InitializeResult:
    return types.InitializeResult(
        protocolVersion=types.LATEST_PROTOCOL_VERSION,
        capabilities=types.ServerCapabilities(
            tools=types.ToolsCapability(),
        ),
        serverInfo=types.Implementation(
            name="fake-http-server",
            version="1.0",
        ),
    )


def make_tool(name: str) -> types.Tool:
    return types.Tool(
        name=name,
        description=f"{name} description",
        inputSchema={"type": "object"},
    )


def install_fake_http(
    monkeypatch: pytest.MonkeyPatch,
    state: FakeHttpState,
) -> None:
    client = FakeHttpClient(state)

    def fake_http_client_factory(**kwargs: Any) -> FakeHttpClient:
        state.client_kwargs = kwargs
        return client

    @asynccontextmanager
    async def fake_streamable_http_client(
        url: str,
        *,
        http_client: FakeHttpClient,
        terminate_on_close: bool,
    ):
        assert http_client is client
        state.transport_url = url
        state.terminate_on_close = terminate_on_close
        state.events.append("transport_start")
        if state.transport_open_delay:
            await anyio.sleep(state.transport_open_delay)
        state.events.append("transport_open")
        try:
            yield (
                "http-read",
                "http-write",
                lambda: state.session_id,
            )
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

    monkeypatch.setattr(
        mcp_client.httpx,
        "AsyncClient",
        fake_http_client_factory,
    )
    monkeypatch.setattr(
        mcp_client,
        "streamable_http_client",
        fake_streamable_http_client,
    )
    monkeypatch.setattr(
        mcp_client,
        "ClientSession",
        fake_session_factory,
    )


def run_snapshot(
    *,
    connection: StreamableHttpConnectionConfig,
    timeouts: DynamicScanTimeouts | None = None,
    environment: dict[str, str] | None = None,
):
    async def run():
        return await mcp_client.collect_tools_snapshot(
            connection,
            server_summary=make_summary(),
            timeouts=timeouts,
            environment=environment,
        )

    return anyio.run(run)


def test_http_initialize_pagination_and_cleanup_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeHttpState(
        initialize_result=make_initialize_result(),
        pages=[
            types.ListToolsResult(
                tools=[make_tool("search")],
                nextCursor="page-2",
            ),
            types.ListToolsResult(tools=[make_tool("read")]),
        ],
    )
    install_fake_http(monkeypatch, state)

    result = run_snapshot(connection=make_connection())

    assert [tool.tool_name for tool in result.tools] == ["search", "read"]
    assert result.protocol_version == types.LATEST_PROTOCOL_VERSION
    assert result.issues == []
    assert result.cleanup.local_cleanup.status == (
        LocalCleanupStatus.SUCCEEDED
    )
    assert result.cleanup.remote_session_termination.status == (
        RemoteSessionTerminationStatus.CONFIRMED
    )
    assert state.terminate_on_close is False
    assert state.events == [
        "http_client_open",
        "transport_start",
        "transport_open",
        "session_created",
        "session_open",
        "initialize",
        "list:None",
        "list:page-2",
        "session_close",
        "delete",
        "transport_close",
        "http_client_close",
    ]


def test_headers_and_bearer_are_resolved_only_at_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeHttpState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[])],
        session_id=None,
    )
    install_fake_http(monkeypatch, state)
    connection = make_connection(
        static_headers={"X-Static": "configured"},
        environment_header_references={"X-Env": "HOST_HEADER"},
        bearer_token_environment_reference="HOST_TOKEN",
    )

    result = run_snapshot(
        connection=connection,
        environment={
            "HOST_HEADER": "resolved-header",
            "HOST_TOKEN": "resolved-token",
            "UNRELATED_SECRET": "must-not-be-forwarded",
        },
    )

    assert result.issues == []
    assert state.client_kwargs["headers"] == {
        "X-Static": "configured",
        "X-Env": "resolved-header",
        "Authorization": "Bearer resolved-token",
    }
    assert "UNRELATED_SECRET" not in state.client_kwargs["headers"]
    assert state.client_kwargs["verify"] is True
    assert state.client_kwargs["follow_redirects"] is False
    assert state.client_kwargs["trust_env"] is False
    assert state.client_kwargs["timeout"].connect == 30.0
    assert state.transport_url == connection.url


def test_missing_header_environment_reference_prevents_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeHttpState()
    install_fake_http(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(
            environment_header_references={"X-Env": "MISSING_HEADER"},
        ),
        environment={},
    )

    assert state.events == []
    assert [issue.code for issue in result.issues] == [
        "environment_reference_missing"
    ]
    safe_result = str(result.model_dump())
    assert "MISSING_HEADER" not in safe_result
    assert "X-Env" not in safe_result


@pytest.mark.parametrize(
    "connection",
    [
        make_connection(
            static_headers={"Authorization": "Static secret"},
            bearer_token_environment_reference="HOST_TOKEN",
        ),
        make_connection(
            static_headers={"X-Policy": "static"},
            environment_header_references={"x-policy": "HOST_HEADER"},
        ),
    ],
)
def test_header_conflict_prevents_network(
    monkeypatch: pytest.MonkeyPatch,
    connection: StreamableHttpConnectionConfig,
) -> None:
    state = FakeHttpState()
    install_fake_http(monkeypatch, state)

    result = run_snapshot(
        connection=connection,
        environment={
            "HOST_TOKEN": "TEST_SECRET",
            "HOST_HEADER": "TEST_SECRET",
        },
    )

    assert state.events == []
    assert [issue.code for issue in result.issues] == [
        "http_header_conflict"
    ]
    assert "TEST_SECRET" not in str(result.model_dump())


@pytest.mark.parametrize(
    ("delay_field", "expected_code"),
    [
        ("transport_open_delay", "http_connect_timeout"),
        ("initialize_delay", "initialize_timeout"),
        ("list_delay", "list_tools_timeout"),
    ],
)
def test_http_stage_timeouts_are_structured(
    monkeypatch: pytest.MonkeyPatch,
    delay_field: str,
    expected_code: str,
) -> None:
    state = FakeHttpState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[])],
        session_id=None,
    )
    setattr(state, delay_field, 0.05)
    install_fake_http(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        timeouts=DynamicScanTimeouts(
            connect_seconds=0.01,
            initialize_seconds=0.01,
            list_tools_page_seconds=0.01,
        ),
    )

    assert expected_code in {issue.code for issue in result.issues}
    assert result.cleanup.local_cleanup.status == (
        LocalCleanupStatus.SUCCEEDED
    )


@pytest.mark.parametrize(
    ("initialize_error", "expected_code"),
    [
        (
            httpx.HTTPStatusError(
                "token=TEST_SECRET",
                request=httpx.Request(
                    "POST",
                    "https://example.com/private?token=TEST_SECRET",
                ),
                response=httpx.Response(
                    401,
                    request=httpx.Request(
                        "POST",
                        "https://example.com/private",
                    ),
                ),
            ),
            "http_authentication_failed",
        ),
        (
            httpx.HTTPStatusError(
                "redirect to secret path",
                request=httpx.Request(
                    "POST",
                    "https://example.com/private",
                ),
                response=httpx.Response(
                    302,
                    request=httpx.Request(
                        "POST",
                        "https://example.com/private",
                    ),
                ),
            ),
            "http_redirect_rejected",
        ),
        (
            httpx.RemoteProtocolError("TEST_SECRET invalid response"),
            "http_response_invalid",
        ),
        (
            httpx.ConnectError(
                "TEST_SECRET connection failure",
                request=httpx.Request(
                    "POST",
                    "https://example.com/private",
                ),
            ),
            "http_connection_failed",
        ),
    ],
)
def test_http_errors_are_safely_classified(
    monkeypatch: pytest.MonkeyPatch,
    initialize_error: Exception,
    expected_code: str,
) -> None:
    state = FakeHttpState(
        initialize_error=initialize_error,
        session_id=None,
    )
    install_fake_http(monkeypatch, state)

    result = run_snapshot(connection=make_connection())

    assert expected_code in {issue.code for issue in result.issues}
    safe_result = str(result.model_dump())
    assert "TEST_SECRET" not in safe_result
    assert "/private" not in safe_result
    assert "password" not in safe_result


def test_tls_verification_failure_is_safely_classified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tls_error = ssl.SSLCertVerificationError("TEST_SECRET certificate")
    connect_error = httpx.ConnectError(
        "TEST_SECRET connection",
        request=httpx.Request("POST", "https://example.com/private"),
    )
    connect_error.__cause__ = tls_error
    state = FakeHttpState(
        initialize_error=connect_error,
        session_id=None,
    )
    install_fake_http(monkeypatch, state)

    result = run_snapshot(connection=make_connection())

    assert [issue.code for issue in result.issues] == [
        "http_tls_verification_failed"
    ]
    assert "TEST_SECRET" not in str(result.model_dump())


def test_invalid_tools_response_is_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeHttpState(
        initialize_result=make_initialize_result(),
        pages=[SimpleNamespace(tools="invalid", nextCursor=None)],
        session_id=None,
    )
    install_fake_http(monkeypatch, state)

    result = run_snapshot(connection=make_connection())

    assert [issue.code for issue in result.issues] == [
        "list_tools_response_invalid"
    ]


def test_missing_session_id_is_not_applicable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeHttpState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[])],
        session_id=None,
    )
    install_fake_http(monkeypatch, state)

    result = run_snapshot(connection=make_connection())

    assert "delete" not in state.events
    assert result.cleanup.remote_session_termination.status == (
        RemoteSessionTerminationStatus.NOT_APPLICABLE
    )


@pytest.mark.parametrize(
    ("status_code", "basis_code"),
    [
        (200, "terminated"),
        (204, "terminated"),
        (404, "already_absent"),
    ],
)
def test_remote_session_termination_confirmed(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    basis_code: str,
) -> None:
    state = FakeHttpState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[])],
        delete_status=status_code,
    )
    install_fake_http(monkeypatch, state)

    result = run_snapshot(connection=make_connection())
    termination = result.cleanup.remote_session_termination

    assert termination.status == RemoteSessionTerminationStatus.CONFIRMED
    assert termination.safe_basis_code == basis_code
    assert state.delete_headers is not None
    assert set(state.delete_headers) == {
        "Mcp-Session-Id",
        "MCP-Protocol-Version",
    }
    assert "session-secret" not in str(result.model_dump())


@pytest.mark.parametrize(
    ("delete_status", "delete_error", "delete_delay", "expected_code"),
    [
        (500, None, 0, "remote_session_termination_unconfirmed"),
        (405, None, 0, "remote_session_termination_unconfirmed"),
        (
            204,
            httpx.ConnectError("TEST_SECRET"),
            0,
            "remote_session_termination_failed",
        ),
        (204, None, 0.05, "remote_session_termination_timeout"),
    ],
)
def test_remote_termination_failure_preserves_tools(
    monkeypatch: pytest.MonkeyPatch,
    delete_status: int,
    delete_error: Exception | None,
    delete_delay: float,
    expected_code: str,
) -> None:
    state = FakeHttpState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[make_tool("search")])],
        delete_status=delete_status,
        delete_error=delete_error,
        delete_delay=delete_delay,
    )
    install_fake_http(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        timeouts=DynamicScanTimeouts(
            remote_session_termination_seconds=0.01,
        ),
    )

    assert [tool.tool_name for tool in result.tools] == ["search"]
    assert result.cleanup.remote_session_termination.status == (
        RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED
    )
    assert expected_code in {issue.code for issue in result.issues}
    assert result.cleanup.local_cleanup.status == (
        LocalCleanupStatus.SUCCEEDED
    )
    assert "TEST_SECRET" not in str(result.model_dump())


@pytest.mark.parametrize(
    ("close_error", "close_delay", "expected_code"),
    [
        (
            RuntimeError("TEST_SECRET close failure"),
            0,
            "local_cleanup_failed",
        ),
        (None, 0.05, "local_cleanup_timeout"),
    ],
)
def test_local_http_cleanup_failure_is_separate(
    monkeypatch: pytest.MonkeyPatch,
    close_error: Exception | None,
    close_delay: float,
    expected_code: str,
) -> None:
    state = FakeHttpState(
        initialize_result=make_initialize_result(),
        pages=[types.ListToolsResult(tools=[make_tool("search")])],
        session_id=None,
        transport_close_error=close_error,
        transport_close_delay=close_delay,
    )
    install_fake_http(monkeypatch, state)

    result = run_snapshot(
        connection=make_connection(),
        timeouts=DynamicScanTimeouts(local_cleanup_seconds=0.01),
    )

    assert [tool.tool_name for tool in result.tools] == ["search"]
    assert result.cleanup.local_cleanup.status == LocalCleanupStatus.FAILED
    assert expected_code in {issue.code for issue in result.issues}
    assert result.cleanup.remote_session_termination.status == (
        RemoteSessionTerminationStatus.NOT_APPLICABLE
    )
    assert "TEST_SECRET" not in str(result.model_dump())
