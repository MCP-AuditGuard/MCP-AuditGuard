from __future__ import annotations

import os
import ssl

from collections.abc import Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

import anyio
import httpx

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS

from core.dynamic_scan_models import (
    CleanupResult,
    DynamicScanIssue,
    DynamicScanStage,
    DynamicScanTimeouts,
    IssueLevel,
    LocalCleanupResult,
    LocalCleanupStatus,
    McpServerImplementation,
    McpServerSummary,
    McpSnapshotResult,
    McpTransport,
    RemoteSessionTerminationResult,
    RemoteSessionTerminationStatus,
    ResolvedStdioConnection,
    ResolvedStreamableHttpConnection,
    ServerEnabledState,
    ServerSupportState,
    StdioConnectionConfig,
    StreamableHttpConnectionConfig,
)
from core.models import ToolMetadata


_CLIENT_INFO = types.Implementation(
    name="mcp-auditguard",
    version="0.1.0",
)
_MCP_SESSION_ID_HEADER = "Mcp-Session-Id"
_MCP_PROTOCOL_VERSION_HEADER = "MCP-Protocol-Version"


class _HttpConfigurationError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


async def collect_tools_snapshot(
    connection: (
        StdioConnectionConfig
        | StreamableHttpConnectionConfig
        | None
    ),
    *,
    server_summary: McpServerSummary,
    timeouts: DynamicScanTimeouts | None = None,
    environment: Mapping[str, str] | None = None,
) -> McpSnapshotResult:
    """Collect one tools/list snapshot without invoking any MCP tool."""
    effective_timeouts = timeouts or DynamicScanTimeouts()
    issues: list[DynamicScanIssue] = []
    tools: list[ToolMetadata] = []
    protocol_version: str | None = None
    server_implementation: McpServerImplementation | None = None

    preflight_issue = _validate_target(
        connection=connection,
        server_summary=server_summary,
    )
    if preflight_issue is not None:
        return _snapshot_result(
            server_summary=server_summary,
            issues=[preflight_issue],
        )

    if isinstance(connection, StreamableHttpConnectionConfig):
        return await _collect_http_snapshot(
            connection=connection,
            server_summary=server_summary,
            timeouts=effective_timeouts,
            environment=environment,
        )

    assert isinstance(connection, StdioConnectionConfig)

    try:
        resolved = _resolve_stdio_connection(
            connection,
            environment=environment,
        )
    except KeyError:
        return _snapshot_result(
            server_summary=server_summary,
            issues=[
                _issue(
                    server_summary,
                    stage=DynamicScanStage.CONFIGURATION,
                    code="environment_reference_missing",
                    safe_message=(
                        "A required environment reference is unavailable."
                    ),
                )
            ],
        )

    stack = AsyncExitStack()
    stderr_sink = None
    cleanup_timeout_scope = stack.enter_context(
        anyio.fail_after(float("inf"))
    )

    try:
        stderr_sink = open(
            os.devnull,
            "w",
            encoding="utf-8",
        )
        stack.callback(stderr_sink.close)

        server_parameters = StdioServerParameters(
            command=resolved.command,
            args=resolved.args,
            env=resolved.environment,
            cwd=resolved.cwd,
        )

        try:
            read_stream, write_stream = await stack.enter_async_context(
                _stdio_transport(
                    server_parameters=server_parameters,
                    stderr_sink=stderr_sink,
                    timeout_seconds=(
                        effective_timeouts.stdio_start_seconds
                    ),
                )
            )
        except TimeoutError:
            issues.append(
                _issue(
                    server_summary,
                    stage=DynamicScanStage.CONNECT,
                    code="stdio_start_timeout",
                    safe_message=(
                        "The STDIO MCP process did not start in time."
                    ),
                )
            )
        except (OSError, RuntimeError):
            issues.append(
                _issue(
                    server_summary,
                    stage=DynamicScanStage.CONNECT,
                    code="stdio_start_failed",
                    safe_message="The STDIO MCP process could not be started.",
                )
            )
        else:
            try:
                session = await stack.enter_async_context(
                    _client_session(
                        read_stream=read_stream,
                        write_stream=write_stream,
                        timeout_seconds=(
                            effective_timeouts.connect_seconds
                        ),
                    )
                )
            except TimeoutError:
                issues.append(
                    _issue(
                        server_summary,
                        stage=DynamicScanStage.CONNECT,
                        code="session_open_timeout",
                        safe_message=(
                            "The MCP client session did not open in time."
                        ),
                    )
                )
            except Exception:
                issues.append(
                    _issue(
                        server_summary,
                        stage=DynamicScanStage.CONNECT,
                        code="session_open_failed",
                        safe_message=(
                            "The MCP client session could not be opened."
                        ),
                    )
                )
            else:
                initialize_result = await _initialize_session(
                    session=session,
                    server_summary=server_summary,
                    timeout_seconds=(
                        effective_timeouts.initialize_seconds
                    ),
                    issues=issues,
                    transport=McpTransport.STDIO,
                )

                if initialize_result is not None:
                    protocol_version = str(
                        initialize_result.protocolVersion
                    )
                    server_implementation = _server_implementation(
                        initialize_result,
                    )

                    if server_implementation is None:
                        issues.append(
                            _issue(
                                server_summary,
                                stage=DynamicScanStage.INITIALIZE,
                                code="server_info_invalid",
                                safe_message=(
                                    "The MCP server implementation metadata "
                                    "is invalid."
                                ),
                                level=IssueLevel.WARNING,
                            )
                        )
                    if initialize_result.capabilities.tools is None:
                        issues.append(
                            _issue(
                                server_summary,
                                stage=DynamicScanStage.INITIALIZE,
                                code="tools_capability_missing",
                                safe_message=(
                                    "The MCP server does not advertise the "
                                    "tools capability."
                                ),
                            )
                        )
                    else:
                        tools.extend(
                            await _collect_tool_pages(
                                session=session,
                                server_summary=server_summary,
                                timeout_seconds=(
                                    effective_timeouts.list_tools_page_seconds
                                ),
                                issues=issues,
                                transport=McpTransport.STDIO,
                            )
                        )
    except Exception:
        issues.append(
            _issue(
                server_summary,
                stage=DynamicScanStage.CONNECT,
                code="mcp_client_failed",
                safe_message=(
                    "The MCP client failed before snapshot collection "
                    "completed."
                ),
            )
        )
    finally:
        cleanup = await _close_local_resources(
            stack=stack,
            cleanup_timeout_scope=cleanup_timeout_scope,
            server_summary=server_summary,
            timeout_seconds=effective_timeouts.local_cleanup_seconds,
        )
        issues.extend(cleanup.issues)

        if stderr_sink is not None and not stderr_sink.closed:
            stderr_sink.close()

    return McpSnapshotResult(
        server_summary=server_summary,
        protocol_version=protocol_version,
        server_implementation=server_implementation,
        tools=tools,
        issues=issues,
        cleanup=CleanupResult(
            local_cleanup=cleanup,
            remote_session_termination=RemoteSessionTerminationResult(
                status=(
                    RemoteSessionTerminationStatus.NOT_APPLICABLE
                ),
            ),
        ),
    )


async def _collect_http_snapshot(
    *,
    connection: StreamableHttpConnectionConfig,
    server_summary: McpServerSummary,
    timeouts: DynamicScanTimeouts,
    environment: Mapping[str, str] | None,
) -> McpSnapshotResult:
    issues: list[DynamicScanIssue] = []
    tools: list[ToolMetadata] = []
    protocol_version: str | None = None
    server_implementation: McpServerImplementation | None = None

    try:
        resolved = _resolve_http_connection(
            connection,
            environment=environment,
        )
    except KeyError:
        return _snapshot_result(
            server_summary=server_summary,
            issues=[
                _issue(
                    server_summary,
                    stage=DynamicScanStage.CONFIGURATION,
                    code="environment_reference_missing",
                    safe_message=(
                        "A required environment reference is unavailable."
                    ),
                )
            ],
        )
    except _HttpConfigurationError as error:
        return _snapshot_result(
            server_summary=server_summary,
            issues=[
                _issue(
                    server_summary,
                    stage=DynamicScanStage.CONFIGURATION,
                    code=error.code,
                    safe_message=error.safe_message,
                )
            ],
        )

    transport_stack, transport_cleanup_scope = _resource_stack()
    session_stack: AsyncExitStack | None = None
    session_cleanup_scope: anyio.CancelScope | None = None
    http_client: httpx.AsyncClient | None = None
    get_session_id: Callable[[], str | None] | None = None
    session_cleanup = LocalCleanupResult(
        status=LocalCleanupStatus.SUCCEEDED,
    )
    transport_cleanup = LocalCleanupResult(
        status=LocalCleanupStatus.SUCCEEDED,
    )
    remote_termination = RemoteSessionTerminationResult(
        status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
    )

    try:
        try:
            http_client = _create_http_client(
                headers=resolved.headers,
                connect_timeout_seconds=timeouts.connect_seconds,
            )
            await transport_stack.enter_async_context(http_client)
            (
                read_stream,
                write_stream,
                get_session_id,
            ) = await transport_stack.enter_async_context(
                _streamable_http_transport(
                    url=resolved.url,
                    http_client=http_client,
                    timeout_seconds=timeouts.connect_seconds,
                )
            )
        except TimeoutError:
            issues.append(
                _issue(
                    server_summary,
                    stage=DynamicScanStage.CONNECT,
                    code="http_connect_timeout",
                    safe_message=(
                        "The Streamable HTTP connection did not open in time."
                    ),
                )
            )
        except Exception as error:
            issues.append(
                _http_operation_issue(
                    error,
                    server_summary=server_summary,
                    stage=DynamicScanStage.CONNECT,
                    default_code="http_connection_failed",
                    default_message=(
                        "The Streamable HTTP connection could not be opened."
                    ),
                )
            )
        else:
            session_stack, session_cleanup_scope = _resource_stack()
            try:
                session = await session_stack.enter_async_context(
                    _client_session(
                        read_stream=read_stream,
                        write_stream=write_stream,
                        timeout_seconds=timeouts.connect_seconds,
                    )
                )
            except TimeoutError:
                issues.append(
                    _issue(
                        server_summary,
                        stage=DynamicScanStage.CONNECT,
                        code="http_connect_timeout",
                        safe_message=(
                            "The MCP client session did not open in time."
                        ),
                    )
                )
            except Exception as error:
                issues.append(
                    _http_operation_issue(
                        error,
                        server_summary=server_summary,
                        stage=DynamicScanStage.CONNECT,
                        default_code="session_open_failed",
                        default_message=(
                            "The MCP client session could not be opened."
                        ),
                    )
                )
            else:
                initialize_result = await _initialize_session(
                    session=session,
                    server_summary=server_summary,
                    timeout_seconds=timeouts.initialize_seconds,
                    issues=issues,
                    transport=McpTransport.STREAMABLE_HTTP,
                )

                if initialize_result is not None:
                    protocol_version = str(
                        initialize_result.protocolVersion
                    )
                    server_implementation = _server_implementation(
                        initialize_result,
                    )

                    if server_implementation is None:
                        issues.append(
                            _issue(
                                server_summary,
                                stage=DynamicScanStage.INITIALIZE,
                                code="server_info_invalid",
                                safe_message=(
                                    "The MCP server implementation metadata "
                                    "is invalid."
                                ),
                                level=IssueLevel.WARNING,
                            )
                        )
                    if initialize_result.capabilities.tools is None:
                        issues.append(
                            _issue(
                                server_summary,
                                stage=DynamicScanStage.INITIALIZE,
                                code="tools_capability_missing",
                                safe_message=(
                                    "The MCP server does not advertise the "
                                    "tools capability."
                                ),
                            )
                        )
                    else:
                        tools.extend(
                            await _collect_tool_pages(
                                session=session,
                                server_summary=server_summary,
                                timeout_seconds=(
                                    timeouts.list_tools_page_seconds
                                ),
                                issues=issues,
                                transport=McpTransport.STREAMABLE_HTTP,
                            )
                        )
    except Exception:
        issues.append(
            _issue(
                server_summary,
                stage=DynamicScanStage.CONNECT,
                code="mcp_client_failed",
                safe_message=(
                    "The MCP client failed before snapshot collection "
                    "completed."
                ),
            )
        )
    finally:
        if session_stack is not None and session_cleanup_scope is not None:
            session_cleanup = await _close_local_resources(
                stack=session_stack,
                cleanup_timeout_scope=session_cleanup_scope,
                server_summary=server_summary,
                timeout_seconds=timeouts.local_cleanup_seconds,
            )
            issues.extend(session_cleanup.issues)

        if http_client is not None and get_session_id is not None:
            remote_termination = await _terminate_http_session(
                http_client=http_client,
                url=resolved.url,
                get_session_id=get_session_id,
                protocol_version=protocol_version,
                server_summary=server_summary,
                timeout_seconds=(
                    timeouts.remote_session_termination_seconds
                ),
            )
            issues.extend(remote_termination.issues)

        transport_cleanup = await _close_local_resources(
            stack=transport_stack,
            cleanup_timeout_scope=transport_cleanup_scope,
            server_summary=server_summary,
            timeout_seconds=timeouts.local_cleanup_seconds,
        )
        issues.extend(transport_cleanup.issues)

    return McpSnapshotResult(
        server_summary=server_summary,
        protocol_version=protocol_version,
        server_implementation=server_implementation,
        tools=tools,
        issues=issues,
        cleanup=CleanupResult(
            local_cleanup=_merge_local_cleanup(
                session_cleanup,
                transport_cleanup,
            ),
            remote_session_termination=remote_termination,
        ),
    )


def _resource_stack() -> tuple[AsyncExitStack, anyio.CancelScope]:
    stack = AsyncExitStack()
    cleanup_timeout_scope = stack.enter_context(
        anyio.fail_after(float("inf"))
    )
    return stack, cleanup_timeout_scope


def _create_http_client(
    *,
    headers: Mapping[str, str],
    connect_timeout_seconds: float,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=dict(headers),
        verify=True,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(
            None,
            connect=connect_timeout_seconds,
        ),
    )


@asynccontextmanager
async def _streamable_http_transport(
    *,
    url: str,
    http_client: httpx.AsyncClient,
    timeout_seconds: float,
):
    with anyio.fail_after(timeout_seconds) as connect_scope:
        async with streamable_http_client(
            url,
            http_client=http_client,
            terminate_on_close=False,
        ) as streams:
            connect_scope.deadline = float("inf")
            yield streams


@asynccontextmanager
async def _stdio_transport(
    *,
    server_parameters: StdioServerParameters,
    stderr_sink: Any,
    timeout_seconds: float,
):
    with anyio.fail_after(timeout_seconds) as startup_scope:
        async with stdio_client(
            server_parameters,
            errlog=stderr_sink,
        ) as streams:
            startup_scope.deadline = float("inf")
            yield streams


@asynccontextmanager
async def _client_session(
    *,
    read_stream: Any,
    write_stream: Any,
    timeout_seconds: float,
):
    with anyio.fail_after(timeout_seconds) as connect_scope:
        async with ClientSession(
            read_stream,
            write_stream,
            client_info=_CLIENT_INFO,
        ) as session:
            connect_scope.deadline = float("inf")
            yield session


def _validate_target(
    *,
    connection: (
        StdioConnectionConfig
        | StreamableHttpConnectionConfig
        | None
    ),
    server_summary: McpServerSummary,
) -> DynamicScanIssue | None:
    if server_summary.enabled_state == ServerEnabledState.DISABLED:
        return _issue(
            server_summary,
            stage=DynamicScanStage.SELECTION,
            code="server_disabled",
            safe_message="The selected MCP server is disabled.",
        )

    if server_summary.support_state != ServerSupportState.SUPPORTED:
        return _issue(
            server_summary,
            stage=DynamicScanStage.SELECTION,
            code="server_not_supported",
            safe_message="The selected MCP server is not executable.",
        )

    if connection is None:
        return _issue(
            server_summary,
            stage=DynamicScanStage.CONFIGURATION,
            code="connection_missing",
            safe_message=(
                "The selected MCP server has no executable connection."
            ),
        )

    connection_matches_transport = (
        server_summary.transport == McpTransport.STDIO
        and isinstance(connection, StdioConnectionConfig)
    ) or (
        server_summary.transport == McpTransport.STREAMABLE_HTTP
        and isinstance(connection, StreamableHttpConnectionConfig)
    )
    if not connection_matches_transport:
        return _issue(
            server_summary,
            stage=DynamicScanStage.CONFIGURATION,
            code="connection_transport_mismatch",
            safe_message=(
                "The MCP connection transport does not match the selected "
                "server."
            ),
        )

    if connection.server_name != server_summary.server_name:
        return _issue(
            server_summary,
            stage=DynamicScanStage.CONFIGURATION,
            code="connection_target_mismatch",
            safe_message=(
                "The MCP connection does not match the selected server."
            ),
        )

    return None


def _resolve_stdio_connection(
    connection: StdioConnectionConfig,
    *,
    environment: Mapping[str, str] | None,
) -> ResolvedStdioConnection:
    source_environment = os.environ if environment is None else environment
    resolved_environment = dict(connection.env_values)

    for target_name, source_name in connection.env_references.items():
        resolved_environment[target_name] = source_environment[source_name]

    return ResolvedStdioConnection(
        server_name=connection.server_name,
        command=connection.command,
        args=list(connection.args),
        cwd=connection.cwd,
        environment=resolved_environment,
    )


def _resolve_http_connection(
    connection: StreamableHttpConnectionConfig,
    *,
    environment: Mapping[str, str] | None,
) -> ResolvedStreamableHttpConnection:
    if (
        connection.http_policy.verify_tls is not True
        or connection.http_policy.follow_redirects is not False
    ):
        raise _HttpConfigurationError(
            "http_policy_invalid",
            "The Streamable HTTP security policy is invalid.",
        )

    parsed_url = urlsplit(connection.url)
    if parsed_url.scheme not in {"http", "https"}:
        raise _HttpConfigurationError(
            "http_scheme_not_supported",
            "The Streamable HTTP URL scheme is not supported.",
        )

    source_environment = os.environ if environment is None else environment
    headers: dict[str, str] = {}
    normalized_names: set[str] = set()

    def add_header(name: str, value: str) -> None:
        normalized_name = name.strip()
        if (
            not normalized_name
            or not value
            or any(
                character in name or character in value
                for character in ("\r", "\n", "\0")
            )
        ):
            raise _HttpConfigurationError(
                "http_header_invalid",
                "A configured Streamable HTTP header is invalid.",
            )

        comparison_name = normalized_name.casefold()
        if comparison_name in normalized_names:
            raise _HttpConfigurationError(
                "http_header_conflict",
                "A Streamable HTTP header is configured more than once.",
            )

        normalized_names.add(comparison_name)
        headers[normalized_name] = value

    for name, value in connection.static_headers.items():
        add_header(name, value)

    for (
        target_name,
        source_name,
    ) in connection.environment_header_references.items():
        add_header(target_name, source_environment[source_name])

    if connection.bearer_token_environment_reference is not None:
        token = source_environment[
            connection.bearer_token_environment_reference
        ]
        if not token.strip():
            raise _HttpConfigurationError(
                "http_header_invalid",
                "A configured Streamable HTTP header is invalid.",
            )
        add_header("Authorization", f"Bearer {token}")

    return ResolvedStreamableHttpConnection(
        server_name=connection.server_name,
        url=connection.url,
        headers=headers,
        http_policy=connection.http_policy,
    )


async def _initialize_session(
    *,
    session: ClientSession,
    server_summary: McpServerSummary,
    timeout_seconds: float,
    issues: list[DynamicScanIssue],
    transport: McpTransport,
) -> types.InitializeResult | None:
    try:
        with anyio.fail_after(timeout_seconds):
            result = await session.initialize()
    except TimeoutError:
        issues.append(
            _issue(
                server_summary,
                stage=DynamicScanStage.INITIALIZE,
                code="initialize_timeout",
                safe_message="MCP initialization did not complete in time.",
            )
        )
        return None
    except RuntimeError as error:
        code = (
            "protocol_version_unsupported"
            if "Unsupported protocol version" in str(error)
            else "initialize_failed"
        )
        issues.append(
            _issue(
                server_summary,
                stage=DynamicScanStage.INITIALIZE,
                code=code,
                safe_message=(
                    "The MCP server returned an unsupported protocol version."
                    if code == "protocol_version_unsupported"
                    else "MCP initialization failed."
                ),
            )
        )
        return None
    except Exception as error:
        if transport == McpTransport.STREAMABLE_HTTP:
            issues.append(
                _http_operation_issue(
                    error,
                    server_summary=server_summary,
                    stage=DynamicScanStage.INITIALIZE,
                    default_code="initialize_failed",
                    default_message="MCP initialization failed.",
                )
            )
        else:
            issues.append(
                _issue(
                    server_summary,
                    stage=DynamicScanStage.INITIALIZE,
                    code="initialize_failed",
                    safe_message="MCP initialization failed.",
                )
            )
        return None

    if str(result.protocolVersion) not in SUPPORTED_PROTOCOL_VERSIONS:
        issues.append(
            _issue(
                server_summary,
                stage=DynamicScanStage.INITIALIZE,
                code="protocol_version_unsupported",
                safe_message=(
                    "The MCP server returned an unsupported protocol version."
                ),
            )
        )
        return None

    return result


def _server_implementation(
    initialize_result: types.InitializeResult,
) -> McpServerImplementation | None:
    try:
        return McpServerImplementation(
            name=initialize_result.serverInfo.name,
            version=initialize_result.serverInfo.version,
        )
    except Exception:
        return None


async def _collect_tool_pages(
    *,
    session: ClientSession,
    server_summary: McpServerSummary,
    timeout_seconds: float,
    issues: list[DynamicScanIssue],
    transport: McpTransport,
) -> list[ToolMetadata]:
    collected_at = datetime.now(timezone.utc)
    collected_tools: list[ToolMetadata] = []
    collected_names: set[str] = set()
    seen_cursors: set[str] = set()
    cursor: str | None = None
    item_index = 0
    received_item_count = 0

    while True:
        try:
            with anyio.fail_after(timeout_seconds):
                if cursor is None:
                    page = await session.list_tools()
                else:
                    page = await session.list_tools(
                        params=types.PaginatedRequestParams(
                            cursor=cursor,
                        )
                    )
        except TimeoutError:
            issues.append(
                _issue(
                    server_summary,
                    stage=DynamicScanStage.LIST_TOOLS,
                    code="list_tools_timeout",
                    safe_message=(
                        "An MCP tools/list page did not arrive in time."
                    ),
                )
            )
            break
        except Exception as error:
            if transport == McpTransport.STREAMABLE_HTTP:
                issues.append(
                    _http_operation_issue(
                        error,
                        server_summary=server_summary,
                        stage=DynamicScanStage.LIST_TOOLS,
                        default_code="list_tools_failed",
                        default_message=(
                            "An MCP tools/list request failed."
                        ),
                    )
                )
            else:
                issues.append(
                    _issue(
                        server_summary,
                        stage=DynamicScanStage.LIST_TOOLS,
                        code="list_tools_failed",
                        safe_message="An MCP tools/list request failed.",
                    )
                )
            break

        page_tools = getattr(page, "tools", None)
        if not isinstance(page_tools, list):
            issues.append(
                _issue(
                    server_summary,
                    stage=DynamicScanStage.LIST_TOOLS,
                    code="list_tools_response_invalid",
                    safe_message=(
                        "The MCP tools/list response has an invalid tool "
                        "collection."
                    ),
                )
            )
            break

        for sdk_tool in page_tools:
            current_index = item_index
            item_index += 1
            received_item_count += 1

            try:
                raw_tool = _tool_to_raw_dict(sdk_tool)
                metadata = ToolMetadata.from_mcp_tool(
                    raw_tool,
                    server_name=server_summary.server_name,
                    source=f"mcp:{server_summary.selection_id}",
                    collected_at=collected_at,
                )
            except Exception:
                issues.append(
                    _issue(
                        server_summary,
                        stage=DynamicScanStage.METADATA_VALIDATION,
                        code="tool_metadata_invalid",
                        safe_message=(
                            "An MCP tool metadata item could not be converted."
                        ),
                        level=IssueLevel.WARNING,
                        item_index=current_index,
                        tool_name=_safe_tool_name(sdk_tool),
                    )
                )
                continue

            if metadata.tool_name in collected_names:
                issues.append(
                    _issue(
                        server_summary,
                        stage=DynamicScanStage.METADATA_VALIDATION,
                        code="duplicate_tool_name",
                        safe_message=(
                            "A duplicate MCP tool name was ignored."
                        ),
                        level=IssueLevel.WARNING,
                        item_index=current_index,
                        tool_name=metadata.tool_name,
                    )
                )
                continue

            collected_names.add(metadata.tool_name)
            collected_tools.append(metadata)

        next_cursor = getattr(page, "nextCursor", None)
        if next_cursor is None:
            break
        if not isinstance(next_cursor, str) or not next_cursor:
            issues.append(
                _issue(
                    server_summary,
                    stage=DynamicScanStage.LIST_TOOLS,
                    code="pagination_cursor_invalid",
                    safe_message=(
                        "The MCP server returned an invalid pagination cursor."
                    ),
                )
            )
            break
        if next_cursor in seen_cursors:
            issues.append(
                _issue(
                    server_summary,
                    stage=DynamicScanStage.LIST_TOOLS,
                    code="pagination_cursor_repeated",
                    safe_message=(
                        "The MCP server repeated a pagination cursor."
                    ),
                )
            )
            break

        seen_cursors.add(next_cursor)
        cursor = next_cursor

    if received_item_count > 0 and not collected_tools:
        issues.append(
            _issue(
                server_summary,
                stage=DynamicScanStage.METADATA_VALIDATION,
                code="all_tool_metadata_invalid",
                safe_message="No valid MCP tool metadata could be collected.",
            )
        )

    return collected_tools


def _tool_to_raw_dict(sdk_tool: Any) -> dict[str, Any]:
    if isinstance(sdk_tool, Mapping):
        return dict(sdk_tool)

    model_dump = getattr(sdk_tool, "model_dump", None)
    if model_dump is None:
        raise TypeError("SDK tool must be serializable")

    raw_tool = model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    if not isinstance(raw_tool, dict):
        raise TypeError("SDK tool serialization must produce an object")

    return raw_tool


def _safe_tool_name(sdk_tool: Any) -> str | None:
    name = (
        sdk_tool.get("name")
        if isinstance(sdk_tool, Mapping)
        else getattr(sdk_tool, "name", None)
    )
    if not isinstance(name, str):
        return None

    normalized = name.strip()
    if not normalized or len(normalized) > 128:
        return None

    return normalized


def _http_operation_issue(
    error: BaseException,
    *,
    server_summary: McpServerSummary,
    stage: DynamicScanStage,
    default_code: str,
    default_message: str,
) -> DynamicScanIssue:
    connection_stage = (
        DynamicScanStage.CONNECT
        if stage != DynamicScanStage.LIST_TOOLS
        else stage
    )

    if _contains_exception(error, httpx.ConnectTimeout):
        return _issue(
            server_summary,
            stage=connection_stage,
            code=(
                "http_connect_timeout"
                if stage != DynamicScanStage.LIST_TOOLS
                else "list_tools_timeout"
            ),
            safe_message=(
                "The Streamable HTTP connection did not complete in time."
                if stage != DynamicScanStage.LIST_TOOLS
                else "An MCP tools/list page did not arrive in time."
            ),
        )

    if _contains_exception(error, httpx.TimeoutException):
        timeout_code = (
            "initialize_timeout"
            if stage == DynamicScanStage.INITIALIZE
            else (
                "list_tools_timeout"
                if stage == DynamicScanStage.LIST_TOOLS
                else "http_connect_timeout"
            )
        )
        return _issue(
            server_summary,
            stage=stage,
            code=timeout_code,
            safe_message=(
                "The Streamable HTTP operation did not complete in time."
            ),
        )

    if _contains_tls_verification_error(error):
        return _issue(
            server_summary,
            stage=connection_stage,
            code="http_tls_verification_failed",
            safe_message=(
                "The Streamable HTTP server certificate could not be "
                "verified."
            ),
        )

    if _contains_exception(error, httpx.ConnectError):
        return _issue(
            server_summary,
            stage=connection_stage,
            code="http_connection_failed",
            safe_message=(
                "The Streamable HTTP server could not be reached."
            ),
        )

    status_error = _find_exception(error, httpx.HTTPStatusError)
    if status_error is not None:
        status_code = status_error.response.status_code
        if status_code in {401, 403}:
            return _issue(
                server_summary,
                stage=connection_stage,
                code="http_authentication_failed",
                safe_message=(
                    "The Streamable HTTP server rejected authentication."
                ),
            )
        if 300 <= status_code < 400:
            return _issue(
                server_summary,
                stage=connection_stage,
                code="http_redirect_rejected",
                safe_message=(
                    "The Streamable HTTP server returned a redirect that "
                    "was not followed."
                ),
            )
        return _issue(
            server_summary,
            stage=stage,
            code="http_request_failed",
            safe_message="The Streamable HTTP request failed.",
        )

    if _contains_exception(
        error,
        (
            httpx.DecodingError,
            httpx.ProtocolError,
        ),
    ):
        return _issue(
            server_summary,
            stage=stage,
            code="http_response_invalid",
            safe_message=(
                "The Streamable HTTP server returned an invalid response."
            ),
        )

    return _issue(
        server_summary,
        stage=stage,
        code=default_code,
        safe_message=default_message,
    )


def _contains_tls_verification_error(error: BaseException) -> bool:
    return _contains_exception(
        error,
        (
            ssl.SSLCertVerificationError,
            ssl.CertificateError,
        ),
    )


def _contains_exception(
    error: BaseException,
    expected_type: type[BaseException] | tuple[type[BaseException], ...],
) -> bool:
    return _find_exception(error, expected_type) is not None


def _find_exception(
    error: BaseException,
    expected_type: type[BaseException] | tuple[type[BaseException], ...],
) -> BaseException | None:
    pending = [error]
    visited: set[int] = set()

    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in visited:
            continue
        visited.add(identity)

        if isinstance(current, expected_type):
            return current

        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)

    return None


async def _terminate_http_session(
    *,
    http_client: httpx.AsyncClient,
    url: str,
    get_session_id: Callable[[], str | None],
    protocol_version: str | None,
    server_summary: McpServerSummary,
    timeout_seconds: float,
) -> RemoteSessionTerminationResult:
    try:
        session_id = get_session_id()
    except Exception:
        session_id = None

    if not session_id:
        return RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
        )

    request_headers = {
        _MCP_SESSION_ID_HEADER: session_id,
    }
    if protocol_version is not None:
        request_headers[_MCP_PROTOCOL_VERSION_HEADER] = protocol_version

    try:
        with anyio.fail_after(timeout_seconds):
            response = await http_client.delete(
                url,
                headers=request_headers,
            )
    except (TimeoutError, httpx.TimeoutException):
        issue = _issue(
            server_summary,
            stage=DynamicScanStage.REMOTE_SESSION_TERMINATION,
            code="remote_session_termination_timeout",
            safe_message=(
                "Remote MCP session termination could not be confirmed "
                "within the timeout."
            ),
            level=IssueLevel.WARNING,
        )
        return RemoteSessionTerminationResult(
            status=(
                RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED
            ),
            safe_basis_code="termination_timeout",
            issues=[issue],
        )
    except Exception:
        issue = _issue(
            server_summary,
            stage=DynamicScanStage.REMOTE_SESSION_TERMINATION,
            code="remote_session_termination_failed",
            safe_message=(
                "Remote MCP session termination could not be confirmed."
            ),
            level=IssueLevel.WARNING,
        )
        return RemoteSessionTerminationResult(
            status=(
                RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED
            ),
            safe_basis_code="termination_unconfirmed",
            issues=[issue],
        )

    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        issue = _issue(
            server_summary,
            stage=DynamicScanStage.REMOTE_SESSION_TERMINATION,
            code="remote_session_termination_unconfirmed",
            safe_message=(
                "Remote MCP session termination could not be confirmed."
            ),
            level=IssueLevel.WARNING,
        )
        return RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED,
            safe_basis_code="termination_unconfirmed",
            issues=[issue],
        )

    if status_code in {200, 204}:
        return RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.CONFIRMED,
            safe_basis_code="terminated",
        )
    if status_code == 404:
        return RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.CONFIRMED,
            safe_basis_code="already_absent",
        )

    basis_code = (
        "method_not_supported"
        if status_code == 405
        else "termination_unconfirmed"
    )
    issue = _issue(
        server_summary,
        stage=DynamicScanStage.REMOTE_SESSION_TERMINATION,
        code="remote_session_termination_unconfirmed",
        safe_message=(
            "Remote MCP session termination could not be confirmed."
        ),
        level=IssueLevel.WARNING,
    )
    return RemoteSessionTerminationResult(
        status=RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED,
        safe_basis_code=basis_code,
        issues=[issue],
    )


def _merge_local_cleanup(
    *results: LocalCleanupResult,
) -> LocalCleanupResult:
    issues = [
        issue
        for result in results
        for issue in result.issues
    ]
    return LocalCleanupResult(
        status=(
            LocalCleanupStatus.FAILED
            if issues
            else LocalCleanupStatus.SUCCEEDED
        ),
        issues=issues,
    )


async def _close_local_resources(
    *,
    stack: AsyncExitStack,
    cleanup_timeout_scope: anyio.CancelScope,
    server_summary: McpServerSummary,
    timeout_seconds: float,
) -> LocalCleanupResult:
    cleanup_issues: list[DynamicScanIssue] = []

    try:
        cleanup_timeout_scope.shield = True
        cleanup_timeout_scope.deadline = (
            anyio.current_time() + timeout_seconds
        )
        await stack.aclose()
    except TimeoutError:
        cleanup_issues.append(
            _issue(
                server_summary,
                stage=DynamicScanStage.LOCAL_CLEANUP,
                code="local_cleanup_timeout",
                safe_message=(
                    "Local MCP resources did not close within the timeout."
                ),
            )
        )
    except Exception:
        cleanup_issues.append(
            _issue(
                server_summary,
                stage=DynamicScanStage.LOCAL_CLEANUP,
                code="local_cleanup_failed",
                safe_message="Local MCP resources could not be fully closed.",
            )
        )

    return LocalCleanupResult(
        status=(
            LocalCleanupStatus.FAILED
            if cleanup_issues
            else LocalCleanupStatus.SUCCEEDED
        ),
        issues=cleanup_issues,
    )


def _snapshot_result(
    *,
    server_summary: McpServerSummary,
    issues: list[DynamicScanIssue],
) -> McpSnapshotResult:
    return McpSnapshotResult(
        server_summary=server_summary,
        issues=issues,
        cleanup=CleanupResult(
            local_cleanup=LocalCleanupResult(
                status=LocalCleanupStatus.SUCCEEDED,
            ),
            remote_session_termination=RemoteSessionTerminationResult(
                status=(
                    RemoteSessionTerminationStatus.NOT_APPLICABLE
                ),
            ),
        ),
    )


def _issue(
    server_summary: McpServerSummary,
    *,
    stage: DynamicScanStage,
    code: str,
    safe_message: str,
    level: IssueLevel = IssueLevel.ERROR,
    item_index: int | None = None,
    tool_name: str | None = None,
) -> DynamicScanIssue:
    return DynamicScanIssue(
        stage=stage,
        code=code,
        level=level,
        safe_message=safe_message,
        server_id=server_summary.selection_id,
        item_index=item_index,
        tool_name=tool_name,
    )
