from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.dynamic_scan_models import (
    CleanupResult,
    CollectedTool,
    DiscoveryContext,
    DiscoveredMcpServer,
    DynamicScanIssue,
    DynamicScanResult,
    DynamicScanStage,
    DynamicScanStatus,
    HostToolPolicy,
    IssueLevel,
    LocalCleanupResult,
    LocalCleanupStatus,
    McpDiscoveryResult,
    McpProduct,
    McpScope,
    McpTransport,
    PolicySourceCoverage,
    RemoteSessionTerminationResult,
    RemoteSessionTerminationStatus,
    ServerEnabledState,
    ServerSupportState,
    StdioConnectionConfig,
    ToolActivationAssessment,
    ToolActivationStatus,
)
from core.mcp_baseline_repository import (
    MonitoringConflictError,
    MonitoringIntegrityError,
    MonitoringNotFoundError,
    MonitoringSchemaError,
    MonitoringStorageError,
)
from core.mcp_baseline_store import FileMcpBaselineRepository
from core.mcp_monitoring_service import (
    McpMonitoringService,
    MonitoringDiscoveryError,
    MonitoringScanError,
    MonitoringServiceError,
)
from core.models import ToolMetadata
from core.scan_result import ScanResult
from web.app import app
from web.routers.mcp_servers import (
    get_discovery_context_factory,
    get_mcp_monitoring_service,
)


FIXED_TIME = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
TARGET_KEY = "mcptgt_" + "2" * 32
CANDIDATE_ID = "cand_safe_candidate"


def test_mcp_monitoring_routes_use_service_and_return_safe_dtos(
    tmp_path: Path,
) -> None:
    server = _server()
    discovery = FakeDiscovery([server])
    runner = FakeRunner()
    service = McpMonitoringService(
        FileMcpBaselineRepository(tmp_path),
        discover_servers=discovery,
        dynamic_scan_runner=runner,
        clock=lambda: FIXED_TIME,
    )

    with _client_for(service, _context_factory(tmp_path)) as client:
        listed_response = client.get(
            "/api/mcp/servers",
            params={"include_trusted_project_config": "true"},
        )
        assert listed_response.status_code == 200
        listed = listed_response.json()

        assert listed["total"] == 1
        assert listed["total"] == len(listed["servers"])
        assert listed["include_trusted_project_config"] is True
        assert listed["servers"][0]["server"]["command_basename"] == "node.exe"
        assert listed["servers"][0]["server"]["argument_count"] == 2
        assert discovery.contexts[0].include_trusted_project_config is True
        _assert_no_connection_secrets(listed_response.text)

        scan_response = client.post(
            "/api/mcp/servers/codex:user:docs/scan",
            json={
                "include_trusted_project_config": True,
                "reconsider_rejected": True,
            },
            headers=_request_security_headers(client),
        )
        assert scan_response.status_code == 200
        scanned = scan_response.json()

        assert runner.calls == 1
        assert discovery.contexts[-1].include_trusted_project_config is True
        assert scanned["dynamic_scan_result"]["status"] == "success"
        assert scanned["candidate_created"] is True
        assert scanned["candidate"]["snapshot"]["tool_count"] == 1
        assert "collected_tools" not in scan_response.text
        assert '"tools"' not in scan_response.text
        _assert_no_connection_secrets(scan_response.text)

        target_key = scanned["monitoring_state"]["monitoring_target_key"]
        group_key = scanned["monitoring_state"]["monitoring_group_key"]
        candidate_id = scanned["candidate"]["candidate_id"]
        state_version = scanned["monitoring_state"]["state_version"]

        target_response = client.get(f"/api/mcp/targets/{target_key}")
        assert target_response.status_code == 200
        assert target_response.json()["monitoring_target_key"] == target_key

        group_response = client.get(f"/api/mcp/groups/{group_key}")
        assert group_response.status_code == 200
        assert group_response.json()["target_keys"] == [target_key]

        candidate_response = client.get(
            f"/api/mcp/candidates/{candidate_id}",
            params={"monitoring_target_key": target_key},
        )
        assert candidate_response.status_code == 200
        assert candidate_response.json()["candidate_id"] == candidate_id

        approve_response = client.post(
            f"/api/mcp/candidates/{candidate_id}/approve",
            json={
                "monitoring_target_key": target_key,
                "expected_state_version": state_version,
                "safe_reason_code": "user_approved",
            },
            headers=_request_security_headers(client),
        )
        assert approve_response.status_code == 200
        approved = approve_response.json()
        assert approved["decision"] == "approved"
        assert approved["baseline_id"] == approved["current_approved_id"]
        assert approved["state_version"] == state_version + 1

        revoke_response = client.post(
            f"/api/mcp/targets/{target_key}/baseline/revoke",
            json={
                "expected_state_version": approved["state_version"],
                "expected_current_approved_id": approved["baseline_id"],
                "safe_reason_code": "user_revoked",
            },
            headers=_request_security_headers(client),
        )
        assert revoke_response.status_code == 200
        revoked = revoke_response.json()
        assert revoked["decision"] == "baseline_revoked"
        assert revoked["removed_baseline_id"] == approved["baseline_id"]
        assert revoked["current_approved_id"] is None
        assert revoked["state_version"] == approved["state_version"] + 1
        assert "snapshot" not in revoke_response.text
        assert "configuration_fingerprint" not in revoke_response.text
        _assert_no_connection_secrets(revoke_response.text)

        history_response = client.get(f"/api/mcp/targets/{target_key}/history")
        assert history_response.status_code == 200
        history_payload = history_response.json()
        history_events = [
            record["event_type"]
            for record in history_payload["records"]
        ]
        assert history_payload["total"] == len(history_payload["records"])
        assert history_events == ["candidate_approved", "baseline_revoked"]

        delete_history_response = client.request(
            "DELETE",
            f"/api/mcp/targets/{target_key}/history",
            json={
                "expected_state_version": revoked["state_version"],
            },
            headers=_request_security_headers(client),
        )
        assert delete_history_response.status_code == 200
        deleted_history = delete_history_response.json()
        assert deleted_history["decision"] == "baseline_history_deleted"
        assert deleted_history["deleted_history_count"] == 2
        assert deleted_history["history_ids"] == []
        assert deleted_history["state_version"] == revoked["state_version"] + 1

        empty_history_response = client.get(f"/api/mcp/targets/{target_key}/history")
        assert empty_history_response.status_code == 200
        assert empty_history_response.json()["records"] == []
        assert empty_history_response.json()["total"] == 0


def test_server_list_echoes_include_trusted_project_config(
    tmp_path: Path,
) -> None:
    discovery = FakeDiscovery([])
    service = McpMonitoringService(
        FileMcpBaselineRepository(tmp_path),
        discover_servers=discovery,
        dynamic_scan_runner=FakeRunner(),
        clock=lambda: FIXED_TIME,
    )

    with _client_for(service, _context_factory(tmp_path)) as client:
        default_response = client.get("/api/mcp/servers")
        trusted_response = client.get(
            "/api/mcp/servers",
            params={"include_trusted_project_config": "true"},
        )

    assert default_response.status_code == 200
    assert default_response.json()["include_trusted_project_config"] is False
    assert default_response.json()["total"] == 0
    assert default_response.json()["servers"] == []
    assert trusted_response.status_code == 200
    assert trusted_response.json()["include_trusted_project_config"] is True
    assert trusted_response.json()["total"] == 0
    assert trusted_response.json()["servers"] == []
    assert [
        context.include_trusted_project_config
        for context in discovery.contexts
    ] == [False, True]


def test_failed_dynamic_scan_is_returned_as_http_200(tmp_path: Path) -> None:
    server = _server()
    discovery = FakeDiscovery([server])
    runner = FakeRunner(status=DynamicScanStatus.FAILED, with_scan_result=False)
    service = McpMonitoringService(
        FileMcpBaselineRepository(tmp_path),
        discover_servers=discovery,
        dynamic_scan_runner=runner,
        clock=lambda: FIXED_TIME,
    )

    with _client_for(service, _context_factory(tmp_path)) as client:
        response = client.post(
            "/api/mcp/servers/codex:user:docs/scan",
            json={},
            headers=_request_security_headers(client),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["dynamic_scan_result"]["status"] == "failed"
    assert data["candidate"] is None
    assert data["warnings"] == []


def test_revoke_baseline_route_returns_conflict_for_missing_or_stale_baseline(
    tmp_path: Path,
) -> None:
    server = _server()
    discovery = FakeDiscovery([server])
    service = McpMonitoringService(
        FileMcpBaselineRepository(tmp_path),
        discover_servers=discovery,
        dynamic_scan_runner=FakeRunner(),
        clock=lambda: FIXED_TIME,
    )

    with _client_for(service, _context_factory(tmp_path)) as client:
        scan_response = client.post(
            "/api/mcp/servers/codex:user:docs/scan",
            json={},
            headers=_request_security_headers(client),
        )
        scanned = scan_response.json()
        target_key = scanned["monitoring_state"]["monitoring_target_key"]
        missing_response = client.post(
            f"/api/mcp/targets/{target_key}/baseline/revoke",
            json={
                "expected_state_version": scanned["monitoring_state"]["state_version"],
                "expected_current_approved_id": "base_safe_baseline",
            },
            headers=_request_security_headers(client),
        )
        assert missing_response.status_code == 409
        assert missing_response.json()["error_code"] == "monitoring_conflict"

        candidate_id = scanned["candidate"]["candidate_id"]
        approved_response = client.post(
            f"/api/mcp/candidates/{candidate_id}/approve",
            json={
                "monitoring_target_key": target_key,
                "expected_state_version": scanned["monitoring_state"]["state_version"],
            },
            headers=_request_security_headers(client),
        )
        approved = approved_response.json()

        stale_response = client.post(
            f"/api/mcp/targets/{target_key}/baseline/revoke",
            json={
                "expected_state_version": approved["state_version"] - 1,
                "expected_current_approved_id": approved["baseline_id"],
            },
            headers=_request_security_headers(client),
        )
        mismatch_response = client.post(
            f"/api/mcp/targets/{target_key}/baseline/revoke",
            json={
                "expected_state_version": approved["state_version"],
                "expected_current_approved_id": "base_other",
            },
            headers=_request_security_headers(client),
        )

    assert stale_response.status_code == 409
    assert mismatch_response.status_code == 409


def test_reject_candidate_route_passes_safe_body_to_service() -> None:
    service = DecisionSpyService(decision="rejected")

    with _client_for(service, _static_context_factory()) as client:
        response = client.post(
            f"/api/mcp/candidates/{CANDIDATE_ID}/reject",
            json={
                "monitoring_target_key": TARGET_KEY,
                "expected_state_version": 7,
                "safe_reason_code": "not_expected",
            },
            headers=_request_security_headers(client),
        )

    assert response.status_code == 200
    assert response.json()["decision"] == "rejected"
    assert service.calls == [
        (
            "reject",
            CANDIDATE_ID,
            TARGET_KEY,
            7,
            "not_expected",
        )
    ]


def test_revoke_baseline_route_passes_safe_body_to_service() -> None:
    service = DecisionSpyService(decision="baseline_revoked")

    with _client_for(service, _static_context_factory()) as client:
        response = client.post(
            f"/api/mcp/targets/{TARGET_KEY}/baseline/revoke",
            json={
                "expected_state_version": 8,
                "expected_current_approved_id": "base_safe_baseline",
                "safe_reason_code": "user_revoked",
            },
            headers=_request_security_headers(client),
        )

    assert response.status_code == 200
    assert response.json()["decision"] == "baseline_revoked"
    assert response.json()["removed_baseline_id"] == "base_safe_baseline"
    assert service.calls == [
        (
            "revoke",
            TARGET_KEY,
            8,
            "base_safe_baseline",
            "user_revoked",
        )
    ]


def test_delete_history_route_passes_safe_body_to_service() -> None:
    service = DecisionSpyService(decision="baseline_history_deleted")

    with _client_for(service, _static_context_factory()) as client:
        response = client.request(
            "DELETE",
            f"/api/mcp/targets/{TARGET_KEY}/history",
            json={
                "expected_state_version": 9,
            },
            headers=_request_security_headers(client),
        )

    assert response.status_code == 200
    assert response.json()["decision"] == "baseline_history_deleted"
    assert response.json()["deleted_history_count"] == 1
    assert response.json()["history_ids"] == []
    assert service.calls == [
        (
            "delete_history",
            TARGET_KEY,
            9,
        )
    ]


@pytest.mark.parametrize(
    ("error", "status_code", "error_code"),
    [
        (
            MonitoringNotFoundError("secret C:/path"),
            404,
            "monitoring_not_found",
        ),
        (
            MonitoringConflictError("secret C:/path"),
            409,
            "monitoring_conflict",
        ),
        (
            MonitoringDiscoveryError("secret C:/path"),
            503,
            "monitoring_discovery_unavailable",
        ),
        (
            MonitoringScanError("secret C:/path"),
            502,
            "monitoring_scan_failed",
        ),
        (
            MonitoringSchemaError("secret C:/path"),
            500,
            "monitoring_storage_invalid",
        ),
        (
            MonitoringIntegrityError("secret C:/path"),
            500,
            "monitoring_storage_integrity_error",
        ),
        (
            MonitoringStorageError("secret C:/path"),
            500,
            "monitoring_storage_error",
        ),
        (
            MonitoringServiceError("secret C:/path"),
            400,
            "monitoring_service_error",
        ),
    ],
)
def test_monitoring_errors_are_mapped_to_safe_json(
    error: Exception,
    status_code: int,
    error_code: str,
) -> None:
    secret_error = type(error)(
        "SECRET_COMMAND_VALUE SECRET_ARGUMENT_VALUE "
        "SECRET_ABSOLUTE_PATH SECRET_TOKEN_VALUE"
    )
    service = RaisingService(secret_error)

    with _client_for(service, _static_context_factory()) as client:
        response = client.get(f"/api/mcp/targets/{TARGET_KEY}")

    assert response.status_code == status_code
    payload = response.json()
    assert payload["error_code"] == error_code
    assert payload["message"]
    assert payload["details"] is None
    assert "error" not in payload
    assert "detail" not in payload
    assert "SECRET_COMMAND_VALUE" not in response.text
    assert "SECRET_ARGUMENT_VALUE" not in response.text
    assert "SECRET_ABSOLUTE_PATH" not in response.text
    assert "SECRET_TOKEN_VALUE" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {
            "monitoring_target_key": TARGET_KEY,
            "expected_state_version": -1,
        },
        {
            "monitoring_target_key": TARGET_KEY,
            "expected_state_version": 0,
            "safe_reason_code": "bad reason",
        },
        {
            "monitoring_target_key": TARGET_KEY,
            "expected_state_version": 0,
            "unexpected": "value",
        },
    ],
)
def test_candidate_decision_request_validation(body: dict[str, object]) -> None:
    service = DecisionSpyService(decision="approved")

    with _client_for(service, _static_context_factory()) as client:
        response = client.post(
            f"/api/mcp/candidates/{CANDIDATE_ID}/approve",
            json=body,
            headers=_request_security_headers(client),
        )

    assert response.status_code == 422
    assert service.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {
            "expected_state_version": -1,
            "expected_current_approved_id": "base_safe_baseline",
        },
        {
            "expected_state_version": 0,
            "expected_current_approved_id": "base_safe_baseline",
            "safe_reason_code": "bad reason",
        },
        {
            "expected_state_version": 0,
            "expected_current_approved_id": "base_safe_baseline",
            "unexpected": "value",
        },
    ],
)
def test_baseline_revocation_request_validation(body: dict[str, object]) -> None:
    service = DecisionSpyService(decision="baseline_revoked")

    with _client_for(service, _static_context_factory()) as client:
        response = client.post(
            f"/api/mcp/targets/{TARGET_KEY}/baseline/revoke",
            json=body,
            headers=_request_security_headers(client),
        )

    assert response.status_code == 422
    assert service.calls == []


def test_unsafe_methods_are_not_registered() -> None:
    service = DecisionSpyService(decision="approved")

    with _client_for(service, _static_context_factory()) as client:
        assert (
            client.get("/api/mcp/servers/codex:user:docs/scan").status_code
            == 405
        )
        assert (
            client.get(f"/api/mcp/candidates/{CANDIDATE_ID}/approve").status_code
            == 405
        )
        assert (
            client.get(f"/api/mcp/candidates/{CANDIDATE_ID}/reject").status_code
            == 405
        )
        assert (
            client.get(f"/api/mcp/targets/{TARGET_KEY}/baseline/revoke").status_code
            == 405
        )


def test_existing_basic_routes_still_work() -> None:
    with TestClient(app, base_url="http://127.0.0.1") as client:
        health = client.get("/health")
        samples = client.get("/api/samples")
        openapi = client.get("/openapi.json")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert samples.status_code == 200
    assert openapi.status_code == 200
    assert "/api/mcp/servers" in openapi.json()["paths"]


class FakeDiscovery:
    def __init__(self, servers: list[DiscoveredMcpServer]) -> None:
        self.servers = servers
        self.contexts: list[DiscoveryContext] = []

    def __call__(self, context: DiscoveryContext) -> McpDiscoveryResult:
        self.contexts.append(context)
        return McpDiscoveryResult(
            servers=list(self.servers),
            issues=[
                DynamicScanIssue(
                    stage=DynamicScanStage.DISCOVERY,
                    code="safe_discovery_warning",
                    level=IssueLevel.WARNING,
                    safe_message="A safe discovery warning was recorded.",
                )
            ],
        )


class FakeRunner:
    def __init__(
        self,
        *,
        status: DynamicScanStatus = DynamicScanStatus.SUCCESS,
        with_scan_result: bool = True,
    ) -> None:
        self.status = status
        self.with_scan_result = with_scan_result
        self.calls = 0

    async def __call__(self, server: DiscoveredMcpServer) -> DynamicScanResult:
        self.calls += 1
        return _dynamic_result(
            server,
            status=self.status,
            with_scan_result=self.with_scan_result,
        )


class RaisingService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_monitoring_target_state(self, monitoring_target_key: str) -> None:
        raise self.error


class DecisionSpyService:
    def __init__(self, *, decision: str) -> None:
        self.decision = decision
        self.calls: list[tuple[object, ...]] = []

    def approve_candidate(
        self,
        candidate_id: str,
        *,
        expected_state_version: int,
        monitoring_target_key: str | None = None,
        safe_reason_code: str | None = None,
    ):
        self.calls.append(
            (
                "approve",
                candidate_id,
                monitoring_target_key,
                expected_state_version,
                safe_reason_code,
            )
        )
        return _decision_result("approved")

    def reject_candidate(
        self,
        candidate_id: str,
        *,
        expected_state_version: int,
        monitoring_target_key: str | None = None,
        safe_reason_code: str | None = None,
    ):
        self.calls.append(
            (
                "reject",
                candidate_id,
                monitoring_target_key,
                expected_state_version,
                safe_reason_code,
            )
        )
        return _decision_result("rejected")

    def revoke_current_baseline(
        self,
        monitoring_target_key: str,
        *,
        expected_state_version: int,
        expected_current_approved_id: str,
        safe_reason_code: str | None = None,
    ):
        self.calls.append(
            (
                "revoke",
                monitoring_target_key,
                expected_state_version,
                expected_current_approved_id,
                safe_reason_code,
            )
        )
        return _revocation_result()

    def delete_target_history(
        self,
        monitoring_target_key: str,
        *,
        expected_state_version: int,
    ):
        self.calls.append(
            (
                "delete_history",
                monitoring_target_key,
                expected_state_version,
            )
        )
        return _history_deletion_result()


@contextmanager
def _client_for(
    service: object,
    context_factory: Callable[[bool], DiscoveryContext],
) -> Iterator[TestClient]:
    app.dependency_overrides[get_mcp_monitoring_service] = lambda: service
    app.dependency_overrides[get_discovery_context_factory] = (
        lambda: context_factory
    )
    try:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _request_security_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/security/request-token")
    payload = response.json()
    return {
        "Origin": str(client.base_url).rstrip("/"),
        payload["header_name"]: payload["request_token"],
    }


def _context_factory(tmp_path: Path) -> Callable[[bool], DiscoveryContext]:
    project_root = tmp_path / "project"
    user_home = tmp_path / "home"
    project_root.mkdir(parents=True, exist_ok=True)
    user_home.mkdir(parents=True, exist_ok=True)

    def build(include_trusted_project_config: bool) -> DiscoveryContext:
        return DiscoveryContext(
            current_working_directory=project_root,
            project_root=project_root,
            user_home=user_home,
            include_trusted_project_config=include_trusted_project_config,
        )

    return build


def _static_context_factory() -> Callable[[bool], DiscoveryContext]:
    def build(include_trusted_project_config: bool) -> DiscoveryContext:
        return DiscoveryContext(
            current_working_directory=Path.cwd(),
            project_root=Path.cwd(),
            user_home=Path.home(),
            include_trusted_project_config=include_trusted_project_config,
        )

    return build


def _server() -> DiscoveredMcpServer:
    return DiscoveredMcpServer(
        selection_id="codex:user:docs",
        product=McpProduct.CODEX,
        scope=McpScope.USER,
        source_label="Codex user config",
        server_name="docs",
        transport=McpTransport.STDIO,
        enabled_state=ServerEnabledState.ENABLED,
        support_state=ServerSupportState.SUPPORTED,
        command_basename="C:/private/bin/node.exe",
        argument_count=2,
        connection=StdioConnectionConfig(
            server_name="docs",
            command="C:/private/bin/node.exe",
            args=["server.js", "--token=SECRET_TOKEN"],
            cwd="C:/private/project",
            env_values={"TOKEN": "SECRET_TOKEN"},
        ),
        tool_policy=HostToolPolicy(
            product=McpProduct.CODEX,
            source_coverage=PolicySourceCoverage.COMPLETE,
        ),
    )


def _dynamic_result(
    server: DiscoveredMcpServer,
    *,
    status: DynamicScanStatus = DynamicScanStatus.SUCCESS,
    with_scan_result: bool = True,
) -> DynamicScanResult:
    tools = [] if not with_scan_result else [_tool(server.server_name)]
    collected_tools = [
        CollectedTool(
            tool_id=f"{index + 1:020x}",
            metadata=tool,
            activation=ToolActivationAssessment(
                tool_name=tool.tool_name,
                status=ToolActivationStatus.ENABLED,
                product=server.product,
                safe_basis_code="enabled_by_host",
            ),
        )
        for index, tool in enumerate(tools)
    ]
    scan = (
        ScanResult(
            scan_type="dynamic",
            source_type="mcp_server",
            source="C:/private/source/tools.json",
            started_at=FIXED_TIME,
            completed_at=FIXED_TIME,
            tools=tools,
            findings=[],
        )
        if with_scan_result
        else None
    )
    return DynamicScanResult(
        status=status,
        target=server.to_summary(),
        collected_tools=collected_tools,
        cleanup=_cleanup(),
        scan_result=scan,
    )


def _tool(server_name: str) -> ToolMetadata:
    return ToolMetadata.from_mcp_tool(
        {
            "name": "search",
            "description": "Search docs.",
            "inputSchema": {"type": "object"},
        },
        server_name=server_name,
        source="C:/private/source/tools.json",
        collected_at=FIXED_TIME,
    )


def _cleanup() -> CleanupResult:
    return CleanupResult(
        local_cleanup=LocalCleanupResult(status=LocalCleanupStatus.SUCCEEDED),
        remote_session_termination=RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
        ),
    )


def _decision_result(decision: str):
    from core.mcp_monitoring_models import (
        BaselineLifecycleStatus,
        ComparisonStatus,
        MonitoringScanStatus,
        MonitoredServerState,
        RegistrationIdentity,
        VerificationStatus,
    )
    from core.mcp_monitoring_service import CandidateDecisionResult
    from core.mcp_monitoring_models import MonitoringIdentity

    state = MonitoredServerState(
        monitoring_group_key="mcpgrp_" + "1" * 32,
        monitoring_target_key=TARGET_KEY,
        identity=MonitoringIdentity(
            monitoring_group_key="mcpgrp_" + "1" * 32,
            monitoring_target_key=TARGET_KEY,
            product=McpProduct.CODEX,
            normalized_server_name="docs",
            display_server_name="docs",
            context_identity="mcpctx_" + "3" * 32,
            context_label="codex:user",
            registration_identity=RegistrationIdentity(
                selection_id="codex:user:docs",
                scope=McpScope.USER,
                safe_source_label="Codex user config",
                context_identity="mcpctx_" + "3" * 32,
            ),
        ),
        state_version=8,
        current_approved_id=(
            "base_safe_baseline" if decision == "approved" else None
        ),
        last_scan_status=MonitoringScanStatus.SUCCESS,
        baseline_lifecycle=(
            BaselineLifecycleStatus.APPROVED
            if decision == "approved"
            else BaselineLifecycleStatus.REJECTED
        ),
        comparison_status=ComparisonStatus.MATCHED,
        verification_status=VerificationStatus.VERIFIED,
        updated_at=FIXED_TIME,
    )
    return CandidateDecisionResult(
        decision=decision,
        candidate_id=CANDIDATE_ID,
        monitoring_group_key=state.monitoring_group_key,
        monitoring_target_key=state.monitoring_target_key,
        baseline_id=state.current_approved_id,
        history_id="hist_safe_history",
        committed_state=state,
    )


def _revocation_result():
    from core.mcp_monitoring_models import (
        BaselineLifecycleStatus,
        ComparisonStatus,
        MonitoringIdentity,
        MonitoringScanStatus,
        MonitoredServerState,
        RegistrationIdentity,
        VerificationStatus,
    )
    from core.mcp_monitoring_service import BaselineRevocationResult

    state = MonitoredServerState(
        monitoring_group_key="mcpgrp_" + "1" * 32,
        monitoring_target_key=TARGET_KEY,
        identity=MonitoringIdentity(
            monitoring_group_key="mcpgrp_" + "1" * 32,
            monitoring_target_key=TARGET_KEY,
            product=McpProduct.CODEX,
            normalized_server_name="docs",
            display_server_name="docs",
            context_identity="mcpctx_" + "3" * 32,
            context_label="codex:user",
            registration_identity=RegistrationIdentity(
                selection_id="codex:user:docs",
                scope=McpScope.USER,
                safe_source_label="Codex user config",
                context_identity="mcpctx_" + "3" * 32,
            ),
        ),
        state_version=9,
        current_approved_id=None,
        last_scan_status=MonitoringScanStatus.SUCCESS,
        baseline_lifecycle=BaselineLifecycleStatus.NONE,
        comparison_status=ComparisonStatus.NOT_COMPARED,
        verification_status=VerificationStatus.UNVERIFIED,
        updated_at=FIXED_TIME,
    )
    return BaselineRevocationResult(
        monitoring_group_key=state.monitoring_group_key,
        monitoring_target_key=state.monitoring_target_key,
        removed_baseline_id="base_safe_baseline",
        history_id="hist_revoked_history",
        committed_state=state,
    )


def _history_deletion_result():
    from core.mcp_monitoring_service import BaselineHistoryDeletionResult

    state = _state_for_history_deletion()
    return BaselineHistoryDeletionResult(
        monitoring_group_key=state.monitoring_group_key,
        monitoring_target_key=state.monitoring_target_key,
        deleted_history_count=1,
        committed_state=state,
    )


def _state_for_history_deletion():
    from core.mcp_monitoring_models import (
        BaselineLifecycleStatus,
        ComparisonStatus,
        MonitoringIdentity,
        MonitoringScanStatus,
        MonitoredServerState,
        RegistrationIdentity,
        VerificationStatus,
    )

    return MonitoredServerState(
        monitoring_group_key="mcpgrp_" + "1" * 32,
        monitoring_target_key=TARGET_KEY,
        identity=MonitoringIdentity(
            monitoring_group_key="mcpgrp_" + "1" * 32,
            monitoring_target_key=TARGET_KEY,
            product=McpProduct.CODEX,
            normalized_server_name="docs",
            display_server_name="docs",
            context_identity="mcpctx_" + "3" * 32,
            context_label="codex:user",
            registration_identity=RegistrationIdentity(
                selection_id="codex:user:docs",
                scope=McpScope.USER,
                safe_source_label="Codex user config",
                context_identity="mcpctx_" + "3" * 32,
            ),
        ),
        state_version=10,
        current_approved_id="base_safe_baseline",
        last_scan_status=MonitoringScanStatus.SUCCESS,
        baseline_lifecycle=BaselineLifecycleStatus.APPROVED,
        comparison_status=ComparisonStatus.MATCHED,
        verification_status=VerificationStatus.VERIFIED,
        updated_at=FIXED_TIME,
    )


def _assert_no_connection_secrets(rendered: str) -> None:
    assert "SECRET_TOKEN" not in rendered
    assert "--token" not in rendered
    assert "C:/private/project" not in rendered
    assert "C:/private/source/tools.json" not in rendered
