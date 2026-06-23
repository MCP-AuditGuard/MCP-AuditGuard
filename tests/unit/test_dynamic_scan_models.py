from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.dynamic_scan_models import (
    ClaudePermissionRule,
    CleanupResult,
    CollectedTool,
    DiscoveryContext,
    DiscoveredMcpServer,
    DynamicScanIssue,
    DynamicScanResult,
    DynamicScanStage,
    DynamicScanStageResult,
    DynamicScanStatus,
    DynamicScanTimeouts,
    DynamicStageStatus,
    HostToolPolicy,
    HttpConnectionPolicy,
    IssueLevel,
    LocalCleanupResult,
    LocalCleanupStatus,
    McpDiscoveryResult,
    McpProduct,
    McpProtocolMetadata,
    McpScope,
    McpServerImplementation,
    McpServerSummary,
    McpSnapshotResult,
    McpTransport,
    PermissionEffect,
    PolicySourceCoverage,
    RemoteSessionTerminationResult,
    RemoteSessionTerminationStatus,
    ResolvedStdioConnection,
    ResolvedStreamableHttpConnection,
    ServerEnabledState,
    ServerSupportState,
    StdioConnectionConfig,
    StreamableHttpConnectionConfig,
    ToolActivationAssessment,
    ToolActivationStatus,
    build_tool_id,
)
from core.models import ToolMetadata
from core.scan_result import ScanResult


def make_tool(tool_name: str = "search") -> ToolMetadata:
    return ToolMetadata.from_mcp_tool(
        raw_tool={
            "name": tool_name,
            "description": "Search documents.",
            "inputSchema": {"type": "object"},
        },
        server_name="docs",
        source="mcp:codex:user:docs",
    )


def make_policy(
    product: McpProduct = McpProduct.CODEX,
) -> HostToolPolicy:
    return HostToolPolicy(
        product=product,
        source_coverage=PolicySourceCoverage.COMPLETE,
    )


def make_summary() -> McpServerSummary:
    return McpServerSummary(
        selection_id="codex:user:docs",
        product=McpProduct.CODEX,
        scope=McpScope.USER,
        source_label="Codex user config",
        server_name="docs",
        transport=McpTransport.STDIO,
        enabled_state=ServerEnabledState.ENABLED,
        support_state=ServerSupportState.SUPPORTED,
        command_basename=r"C:\Tools\npx.cmd",
        argument_count=3,
    )


def make_cleanup() -> CleanupResult:
    return CleanupResult(
        local_cleanup=LocalCleanupResult(
            status=LocalCleanupStatus.SUCCEEDED,
        ),
        remote_session_termination=RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
        ),
    )


def test_transport_configs_keep_secrets_out_of_repr_and_serialization() -> None:
    stdio = StdioConnectionConfig(
        server_name="docs",
        command=r"C:\Tools\npx.cmd",
        args=["-y", "secret-package"],
        cwd=r"C:\Private\Project",
        env_values={"TOKEN": "TEST_SECRET"},
        env_references={"API_KEY": "HOST_API_KEY"},
    )
    http = StreamableHttpConnectionConfig(
        server_name="remote",
        url="https://user:password@example.com/mcp?token=TEST_SECRET",
        static_headers={"Authorization": "Bearer TEST_SECRET"},
        environment_header_references={"X-API-Key": "HOST_API_KEY"},
        bearer_token_environment_reference="HOST_BEARER_TOKEN",
    )

    serialized = f"{stdio.model_dump()} {http.model_dump()}"
    represented = f"{stdio!r} {http!r}"

    for secret in (
        "TEST_SECRET",
        "HOST_API_KEY",
        "HOST_BEARER_TOKEN",
        "secret-package",
        "Private",
        "password",
    ):
        assert secret not in serialized
        assert secret not in represented

    assert stdio.command == r"C:\Tools\npx.cmd"
    assert http.static_headers["Authorization"] == "Bearer TEST_SECRET"


def test_resolved_connections_also_hide_resolved_secret_values() -> None:
    stdio = ResolvedStdioConnection(
        server_name="docs",
        command="python",
        args=["server.py"],
        environment={"TOKEN": "TEST_SECRET"},
    )
    http = ResolvedStreamableHttpConnection(
        server_name="remote",
        url="https://example.com/mcp?token=TEST_SECRET",
        headers={"Authorization": "Bearer TEST_SECRET"},
    )

    assert "TEST_SECRET" not in repr(stdio)
    assert "TEST_SECRET" not in repr(http)
    assert "TEST_SECRET" not in str(stdio.model_dump())
    assert "TEST_SECRET" not in str(http.model_dump())


def test_http_policy_cannot_disable_tls_or_enable_redirects() -> None:
    with pytest.raises(ValidationError):
        HttpConnectionPolicy(verify_tls=False)

    with pytest.raises(ValidationError):
        HttpConnectionPolicy(follow_redirects=True)

    with pytest.raises(ValidationError):
        StreamableHttpConnectionConfig(
            server_name="remote",
            url="file:///tmp/mcp.sock",
        )

    with pytest.raises(ValidationError):
        StdioConnectionConfig(
            server_name="docs",
            command="   ",
        )


def test_validation_errors_and_host_policy_hide_sensitive_inputs() -> None:
    with pytest.raises(ValidationError) as error_info:
        StreamableHttpConnectionConfig(
            server_name="remote",
            url="file:///tmp/mcp.sock?token=TEST_SECRET",
        )

    policy = HostToolPolicy(
        product=McpProduct.CLAUDE,
        source_coverage=PolicySourceCoverage.COMPLETE,
        claude_permission_rules=[
            ClaudePermissionRule(
                effect=PermissionEffect.DENY,
                tool_name_pattern="mcp__secret_server__*",
                source_label="Claude project config",
            )
        ],
    )

    assert "TEST_SECRET" not in str(error_info.value)
    assert "secret_server" not in repr(policy)
    assert "secret_server" not in str(policy.model_dump())


def test_host_policy_preserves_codex_enabled_tools_configuration() -> None:
    missing_allow_list = HostToolPolicy(product=McpProduct.CODEX)
    explicit_empty_allow_list = HostToolPolicy(
        product=McpProduct.CODEX,
        codex_enabled_tools_configured=True,
        codex_enabled_tools=[],
    )

    assert missing_allow_list.codex_enabled_tools == []
    assert missing_allow_list.codex_enabled_tools_configured is False
    assert explicit_empty_allow_list.codex_enabled_tools == []
    assert explicit_empty_allow_list.codex_enabled_tools_configured is True


def test_server_summary_keeps_only_command_basename_and_remote_origin() -> None:
    stdio_summary = make_summary()
    http_summary = McpServerSummary(
        selection_id="claude:project:remote",
        product=McpProduct.CLAUDE,
        scope=McpScope.PROJECT,
        source_label="Claude project config",
        server_name="remote",
        transport=McpTransport.STREAMABLE_HTTP,
        enabled_state=ServerEnabledState.UNKNOWN,
        support_state=ServerSupportState.SUPPORTED,
        remote_origin="https://user:password@example.com:8443/mcp?token=secret",
    )

    assert stdio_summary.command_basename == "npx.cmd"
    assert http_summary.remote_origin == "https://example.com:8443"
    assert "password" not in str(http_summary.model_dump())
    assert "token" not in str(http_summary.model_dump())

    with pytest.raises(ValidationError):
        McpServerSummary(
            **{
                **make_summary().model_dump(),
                "selection_id": "   ",
            }
        )


def test_supported_discovered_server_requires_matching_connection() -> None:
    with pytest.raises(ValidationError, match="must include a connection"):
        DiscoveredMcpServer(
            **make_summary().model_dump(),
            tool_policy=make_policy(),
        )

    server = DiscoveredMcpServer.model_validate(
        {
            **make_summary().model_dump(),
            "connection": {
                "transport": "stdio",
                "server_name": "docs",
                "command": "npx",
            },
            "tool_policy": make_policy(),
        }
    )

    assert isinstance(server.connection, StdioConnectionConfig)
    assert server.to_summary() == make_summary()

    with pytest.raises(ValidationError, match="transport must match"):
        DiscoveredMcpServer(
            **make_summary().model_dump(),
            connection=StreamableHttpConnectionConfig(
                server_name="docs",
                url="https://example.com/mcp",
            ),
            tool_policy=make_policy(),
        )

    with pytest.raises(ValidationError, match="server_name must match"):
        DiscoveredMcpServer(
            **make_summary().model_dump(),
            connection=StdioConnectionConfig(
                server_name="different-server",
                command="npx",
            ),
            tool_policy=make_policy(),
        )


def test_supported_disabled_server_can_remain_visible_without_connection() -> None:
    summary_data = make_summary().model_dump()
    summary_data["enabled_state"] = ServerEnabledState.DISABLED
    summary_data["support_reason_code"] = "server_disabled"

    server = DiscoveredMcpServer(
        **summary_data,
        tool_policy=make_policy(),
    )

    assert server.support_state == ServerSupportState.SUPPORTED
    assert server.enabled_state == ServerEnabledState.DISABLED
    assert server.connection is None


def test_unsupported_discovered_server_rejects_connection() -> None:
    summary_data = make_summary().model_dump()
    summary_data["support_state"] = ServerSupportState.UNSUPPORTED

    with pytest.raises(
        ValidationError,
        match="unsupported or invalid server must not include a connection",
    ):
        DiscoveredMcpServer(
            **summary_data,
            connection=StdioConnectionConfig(
                server_name="docs",
                command="npx",
            ),
            tool_policy=make_policy(),
        )


def test_discovered_server_rejects_mismatched_policy_product() -> None:
    with pytest.raises(ValidationError, match="tool policy product"):
        DiscoveredMcpServer(
            **make_summary().model_dump(),
            connection=StdioConnectionConfig(
                server_name="docs",
                command="npx",
            ),
            tool_policy=make_policy(McpProduct.CLAUDE),
        )


def test_discovery_result_exposes_safe_summaries_without_connections() -> None:
    server = DiscoveredMcpServer(
        **make_summary().model_dump(),
        connection=StdioConnectionConfig(
            server_name="docs",
            command="npx",
            env_values={"TOKEN": "TEST_SECRET"},
        ),
        tool_policy=make_policy(),
    )
    result = McpDiscoveryResult(
        servers=[server],
        source_statuses={"codex:user": "found"},
    )

    assert result.summaries == [make_summary()]
    assert "TEST_SECRET" not in str(result.model_dump())


def test_collected_tool_uses_stable_id_and_direct_metadata_pairing() -> None:
    tool = make_tool()
    assessment = ToolActivationAssessment(
        tool_name=tool.tool_name,
        status=ToolActivationStatus.DISABLED,
        product=McpProduct.CODEX,
        policy_source_labels=["Codex user config"],
        safe_basis_code="codex_disabled_match",
    )
    tool_id = build_tool_id(
        server_selection_id="codex:user:docs",
        tool_name=tool.tool_name,
        snapshot_ordinal=0,
    )

    collected = CollectedTool(
        tool_id=tool_id,
        metadata=tool,
        activation=assessment,
    )

    assert collected.tool_id == tool_id
    assert len(tool_id) == 20
    assert collected.metadata is tool
    assert collected.activation.status == ToolActivationStatus.DISABLED

    with pytest.raises(ValidationError, match="must match"):
        CollectedTool(
            tool_id=tool_id,
            metadata=tool,
            activation=assessment.model_copy(
                update={"tool_name": "different-tool"}
            ),
        )


def test_build_tool_id_normalizes_text_and_rejects_invalid_inputs() -> None:
    normalized_id = build_tool_id(
        server_selection_id="codex:user:docs",
        tool_name="search",
        snapshot_ordinal=0,
    )
    padded_id = build_tool_id(
        server_selection_id="  codex:user:docs  ",
        tool_name="  search  ",
        snapshot_ordinal=0,
    )

    assert padded_id == normalized_id

    with pytest.raises(ValueError, match="required text"):
        build_tool_id(
            server_selection_id="   ",
            tool_name="search",
            snapshot_ordinal=0,
        )

    with pytest.raises(ValueError, match="non-negative"):
        build_tool_id(
            server_selection_id="codex:user:docs",
            tool_name="search",
            snapshot_ordinal=-1,
        )


def test_cleanup_keeps_local_and_remote_states_independent() -> None:
    issue = DynamicScanIssue(
        stage=DynamicScanStage.REMOTE_SESSION_TERMINATION,
        code="session_delete_unconfirmed",
        level=IssueLevel.WARNING,
        safe_message="Remote session termination could not be confirmed.",
        server_id="claude:project:remote",
    )
    cleanup = CleanupResult(
        local_cleanup=LocalCleanupResult(
            status=LocalCleanupStatus.SUCCEEDED,
        ),
        remote_session_termination=RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED,
            safe_basis_code="method_not_allowed",
            issues=[issue],
        ),
    )

    assert cleanup.local_cleanup.status == LocalCleanupStatus.SUCCEEDED
    assert (
        cleanup.remote_session_termination.status
        == RemoteSessionTerminationStatus.ATTEMPTED_UNCONFIRMED
    )


def test_snapshot_result_contains_protocol_data_without_host_policy() -> None:
    snapshot = McpSnapshotResult(
        server_summary=make_summary(),
        protocol_version="2025-11-25",
        server_implementation=McpServerImplementation(
            name="test-server",
            version="1.0",
        ),
        tools=[make_tool()],
        cleanup=make_cleanup(),
    )

    assert snapshot.tools[0].tool_name == "search"
    assert "tool_policy" not in McpSnapshotResult.model_fields


def test_timeout_policy_requires_positive_finite_waits() -> None:
    timeouts = DynamicScanTimeouts()

    assert timeouts.stdio_start_seconds == 10
    assert timeouts.connect_seconds == 30
    assert timeouts.remote_session_termination_seconds == 5

    with pytest.raises(ValidationError):
        DynamicScanTimeouts(initialize_seconds=0)

    with pytest.raises(ValidationError):
        DynamicScanTimeouts(connect_seconds=float("inf"))


def test_dynamic_result_wraps_existing_scan_result_without_changing_it() -> None:
    tool = make_tool()
    activation = ToolActivationAssessment(
        tool_name=tool.tool_name,
        status=ToolActivationStatus.ENABLED,
        product=McpProduct.CODEX,
        policy_source_labels=["Codex user config"],
        safe_basis_code="codex_enabled_allow_match",
    )
    collected = CollectedTool(
        tool_id=build_tool_id(
            server_selection_id="codex:user:docs",
            tool_name=tool.tool_name,
            snapshot_ordinal=0,
        ),
        metadata=tool,
        activation=activation,
    )
    now = datetime.now(timezone.utc)
    scan_result = ScanResult(
        scan_type="dynamic",
        source_type="mcp_server",
        source="mcp:codex:user:docs",
        started_at=now,
        completed_at=now,
        tools=[tool],
        findings=[],
    )

    result = DynamicScanResult(
        status=DynamicScanStatus.SUCCESS,
        target=make_summary(),
        stages=[
            DynamicScanStageResult(
                stage=DynamicScanStage.SCAN,
                status=DynamicStageStatus.SUCCEEDED,
            )
        ],
        protocol_metadata=McpProtocolMetadata(
            protocol_version="2025-11-25",
            server_implementation=McpServerImplementation(
                name="test-server",
                version="1.0",
            ),
        ),
        collected_tools=[collected],
        cleanup=make_cleanup(),
        scan_result=scan_result,
    )

    assert result.scan_result is scan_result
    assert result.scan_result.schema_version == "1.0"
    assert result.collected_tools[0].metadata == result.scan_result.tools[0]
    assert "cancelled" not in {status.value for status in DynamicScanStatus}


def test_dynamic_result_rejects_duplicate_stages_and_file_scan_result() -> None:
    stage = DynamicScanStageResult(
        stage=DynamicScanStage.SCAN,
        status=DynamicStageStatus.SUCCEEDED,
    )

    with pytest.raises(ValidationError, match="stages must be unique"):
        DynamicScanResult(
            status=DynamicScanStatus.SUCCESS,
            target=make_summary(),
            stages=[stage, stage],
            cleanup=make_cleanup(),
        )

    now = datetime.now(timezone.utc)
    file_result = ScanResult(
        source="tools.json",
        started_at=now,
        completed_at=now,
        tools=[],
        findings=[],
    )

    with pytest.raises(ValidationError, match="dynamic scan_type"):
        DynamicScanResult(
            status=DynamicScanStatus.SUCCESS,
            target=make_summary(),
            cleanup=make_cleanup(),
            scan_result=file_result,
        )


def test_dynamic_result_rejects_mismatched_tool_product_and_server() -> None:
    tool = make_tool()
    activation = ToolActivationAssessment(
        tool_name=tool.tool_name,
        status=ToolActivationStatus.ENABLED,
        product=McpProduct.CODEX,
        policy_source_labels=["Codex user config"],
        safe_basis_code="codex_enabled_allow_match",
    )
    collected = CollectedTool(
        tool_id=build_tool_id(
            server_selection_id="codex:user:docs",
            tool_name=tool.tool_name,
            snapshot_ordinal=0,
        ),
        metadata=tool,
        activation=activation,
    )

    with pytest.raises(ValidationError, match="activation product"):
        DynamicScanResult(
            status=DynamicScanStatus.SUCCESS,
            target=make_summary().model_copy(
                update={"product": McpProduct.CLAUDE}
            ),
            collected_tools=[collected],
            cleanup=make_cleanup(),
        )

    with pytest.raises(ValidationError, match="metadata server_name"):
        DynamicScanResult(
            status=DynamicScanStatus.SUCCESS,
            target=make_summary().model_copy(
                update={"server_name": "different-server"}
            ),
            collected_tools=[collected],
            cleanup=make_cleanup(),
        )


def test_discovery_context_is_data_only() -> None:
    context = DiscoveryContext(
        current_working_directory="C:/work/project",
        project_root=None,
        user_home="C:/Users/tester",
    )

    assert context.current_working_directory.name == "project"
    assert context.include_trusted_project_config is False
