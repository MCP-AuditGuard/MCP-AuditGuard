from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.dynamic_scan_models import (
    CleanupResult,
    DiscoveryContext,
    DynamicScanResult,
    DynamicScanStatus,
    LocalCleanupResult,
    LocalCleanupStatus,
    McpDiscoveryResult,
    McpProduct,
    McpScope,
    McpServerSummary,
    McpTransport,
    RemoteSessionTerminationResult,
    RemoteSessionTerminationStatus,
    ServerEnabledState,
    ServerSupportState,
)
from core.mcp_monitoring_models import (
    BaselineLifecycleStatus,
    ComparisonStatus,
    MonitoringIdentity,
    MonitoringScanStatus,
    MonitoredServerState,
    RegistrationIdentity,
    VerificationStatus,
)
from core.mcp_monitoring_service import (
    CandidateDecisionResult,
    MonitoredScanResult,
    MonitoredServerListResult,
)
from web.app import app
from web.routers.mcp_servers import (
    get_discovery_context_factory,
    get_mcp_monitoring_service,
)


BASE_URL = "http://127.0.0.1:8000"
FIXED_TIME = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
GROUP_KEY = "mcpgrp_" + "1" * 32
TARGET_KEY = "mcptgt_" + "2" * 32
CANDIDATE_ID = "cand_security_candidate"


def test_allowed_host_get_health_succeeds() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_untrusted_host_is_rejected_before_endpoint() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get(
            "/health",
            headers={"Host": "evil.example"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "error_code": "host_not_allowed",
        "message": "The request host is not allowed.",
        "details": None,
    }
    assert "evil.example" not in response.text


def test_request_token_route_returns_no_store_same_origin_response() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/api/security/request-token")

    assert response.status_code == 200
    payload = response.json()
    assert payload["header_name"] == "X-AuditGuard-Request-Token"
    assert payload["request_token"]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    _assert_no_cors_headers(response)


def test_mcp_scan_requires_same_origin_and_request_token() -> None:
    service = SecuritySpyService()

    with _client_for(service) as client:
        valid_headers = _request_security_headers(client)
        response = client.post(
            "/api/mcp/servers/codex:user:docs/scan",
            json={},
            headers=valid_headers,
        )
        assert response.status_code == 200
        assert service.calls == [("scan", "codex:user:docs")]

        token_header = "X-AuditGuard-Request-Token"
        for headers in (
            {token_header: valid_headers[token_header]},
            {"Origin": valid_headers["Origin"]},
            {
                "Origin": valid_headers["Origin"],
                token_header: "wrong",
            },
            {
                "Origin": "http://evil.example",
                token_header: valid_headers[token_header],
            },
            {
                "Origin": "http://127.0.0.1:9000",
                token_header: valid_headers[token_header],
            },
        ):
            rejected = client.post(
                "/api/mcp/servers/codex:user:docs/scan",
                json={},
                headers=headers,
            )
            assert rejected.status_code == 403
            _assert_security_error_is_safe(rejected)

    assert service.calls == [("scan", "codex:user:docs")]


@pytest.mark.parametrize(
    "origin",
    [
        "http://[::1",
        "http://[",
        "http://127.0.0.1:invalid",
        "http://127.0.0.1:99999",
        "http://[SECRET_MALFORMED_ORIGIN",
    ],
)
def test_malformed_origin_returns_403_without_service_call(
    origin: str,
) -> None:
    service = SecuritySpyService()

    with _client_for(service) as client:
        valid_headers = _request_security_headers(client)
        response = client.post(
            "/api/mcp/servers/codex:user:docs/scan",
            json={},
            headers={
                "Origin": origin,
                "X-AuditGuard-Request-Token": valid_headers[
                    "X-AuditGuard-Request-Token"
                ],
            },
        )

    assert response.status_code == 403
    assert response.json() == {
        "error_code": "origin_not_allowed",
        "message": "The request origin is not allowed.",
        "details": None,
    }
    assert "SECRET_MALFORMED_ORIGIN" not in response.text
    assert "SECRET_REQUEST_TOKEN" not in response.text
    assert "SECRET_COMMAND_VALUE" not in response.text
    assert "SECRET_ABSOLUTE_PATH" not in response.text
    assert service.calls == []


def test_token_is_only_accepted_from_header() -> None:
    service = SecuritySpyService()

    with _client_for(service) as client:
        token_response = client.get("/api/security/request-token")
        token = token_response.json()["request_token"]
        client.cookies.set("request_token", token)
        response = client.post(
            f"/api/mcp/servers/codex:user:docs/scan?request_token={token}",
            json={"request_token": token},
            headers={"Origin": str(client.base_url).rstrip("/")},
        )

    assert response.status_code == 403
    assert response.json()["error_code"] == "request_token_invalid"
    assert token not in response.text
    assert service.calls == []


def test_candidate_decision_routes_are_protected_before_service_call() -> None:
    service = SecuritySpyService()

    with _client_for(service) as client:
        valid_headers = _request_security_headers(client)
        approve = client.post(
            f"/api/mcp/candidates/{CANDIDATE_ID}/approve",
            json={
                "monitoring_target_key": TARGET_KEY,
                "expected_state_version": 0,
            },
            headers=valid_headers,
        )
        assert approve.status_code == 200

        reject = client.post(
            f"/api/mcp/candidates/{CANDIDATE_ID}/reject",
            json={
                "monitoring_target_key": TARGET_KEY,
                "expected_state_version": 1,
            },
        )
        assert reject.status_code == 403
        _assert_security_error_is_safe(reject)

    assert service.calls == [("approve", CANDIDATE_ID)]


def test_scan_upload_is_rejected_before_multipart_body_is_processed() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            "/api/scans/upload",
            files={
                "file": (
                    "SECRET_ABSOLUTE_PATH.json",
                    b'{"tools":[]}',
                    "application/json",
                )
            },
        )

    assert response.status_code == 403
    assert response.json()["error_code"] == "origin_not_allowed"
    assert "SECRET_ABSOLUTE_PATH" not in response.text


def test_sample_scan_requires_security_headers_then_keeps_route_behavior() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        missing_headers = client.post("/api/scans/sample/not-a-sample")
        valid_headers = _request_security_headers(client)
        route_response = client.post(
            "/api/scans/sample/not-a-sample",
            headers=valid_headers,
        )

    assert missing_headers.status_code == 403
    assert missing_headers.json()["error_code"] == "origin_not_allowed"
    assert route_response.status_code == 404


def test_get_apis_do_not_require_origin_or_token() -> None:
    service = SecuritySpyService()

    with _client_for(service) as client:
        samples = client.get("/api/samples")
        servers = client.get("/api/mcp/servers")
        missing_report = client.get(
            "/api/reports/00000000-0000-0000-0000-000000000000/json"
        )

    assert samples.status_code == 200
    assert servers.status_code == 200
    assert servers.json()["total"] == 0
    assert missing_report.status_code == 404


def test_body_validation_runs_after_security_passes() -> None:
    service = SecuritySpyService()

    with _client_for(service) as client:
        response = client.post(
            f"/api/mcp/candidates/{CANDIDATE_ID}/approve",
            json={
                "monitoring_target_key": TARGET_KEY,
                "expected_state_version": -1,
            },
            headers=_request_security_headers(client),
        )

    assert response.status_code == 422
    assert service.calls == []


def test_cors_headers_are_not_added() -> None:
    service = SecuritySpyService()

    with _client_for(service) as client:
        token = client.get("/api/security/request-token")
        servers = client.get("/api/mcp/servers")
        post_failure = client.post(
            "/api/mcp/servers/codex:user:docs/scan",
            json={},
        )
        preflight = client.options(
            "/api/mcp/servers/codex:user:docs/scan",
            headers={"Origin": "http://evil.example"},
        )

    for response in (token, servers, post_failure, preflight):
        _assert_no_cors_headers(response)


def test_openapi_and_docs_work_on_allowed_host() -> None:
    with TestClient(app, base_url=BASE_URL) as client:
        openapi = client.get("/openapi.json")
        docs = client.get("/docs")

    assert openapi.status_code == 200
    assert docs.status_code == 200
    assert "/api/security/request-token" not in openapi.json()["paths"]


class SecuritySpyService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def list_monitored_servers(
        self,
        context: DiscoveryContext,
    ) -> MonitoredServerListResult:
        return MonitoredServerListResult(
            servers=[],
            discovery_result=McpDiscoveryResult(),
        )

    async def scan_monitored_server(
        self,
        context: DiscoveryContext,
        selection_id: str,
        *,
        reconsider_rejected: bool = False,
    ) -> MonitoredScanResult:
        self.calls.append(("scan", selection_id))
        return MonitoredScanResult(
            server_summary=_server_summary(),
            monitoring_identity=_identity(),
            dynamic_scan_result=DynamicScanResult(
                status=DynamicScanStatus.SUCCESS,
                target=_server_summary(),
                cleanup=_cleanup(),
                scan_result=None,
            ),
            monitoring_state=_state(),
        )

    def approve_candidate(
        self,
        candidate_id: str,
        *,
        expected_state_version: int,
        monitoring_target_key: str | None = None,
        safe_reason_code: str | None = None,
    ) -> CandidateDecisionResult:
        self.calls.append(("approve", candidate_id))
        return _decision_result("approved")

    def reject_candidate(
        self,
        candidate_id: str,
        *,
        expected_state_version: int,
        monitoring_target_key: str | None = None,
        safe_reason_code: str | None = None,
    ) -> CandidateDecisionResult:
        self.calls.append(("reject", candidate_id))
        return _decision_result("rejected")


@contextmanager
def _client_for(service: object) -> Iterator[TestClient]:
    app.dependency_overrides[get_mcp_monitoring_service] = lambda: service
    app.dependency_overrides[get_discovery_context_factory] = (
        lambda: _discovery_context
    )
    try:
        with TestClient(app, base_url=BASE_URL) as client:
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


def _discovery_context(include_trusted_project_config: bool) -> DiscoveryContext:
    return DiscoveryContext(
        current_working_directory=Path.cwd(),
        project_root=Path.cwd(),
        user_home=Path.home(),
        include_trusted_project_config=include_trusted_project_config,
    )


def _server_summary() -> McpServerSummary:
    return McpServerSummary(
        selection_id="codex:user:docs",
        product=McpProduct.CODEX,
        scope=McpScope.USER,
        source_label="Codex user config",
        server_name="docs",
        transport=McpTransport.STDIO,
        enabled_state=ServerEnabledState.ENABLED,
        support_state=ServerSupportState.SUPPORTED,
        command_basename="python",
        argument_count=1,
    )


def _identity() -> MonitoringIdentity:
    return MonitoringIdentity(
        monitoring_group_key=GROUP_KEY,
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
    )


def _state() -> MonitoredServerState:
    return MonitoredServerState(
        monitoring_group_key=GROUP_KEY,
        monitoring_target_key=TARGET_KEY,
        identity=_identity(),
        state_version=1,
        current_approved_id=None,
        last_scan_status=MonitoringScanStatus.SUCCESS,
        baseline_lifecycle=BaselineLifecycleStatus.CANDIDATE_PENDING,
        comparison_status=ComparisonStatus.NOT_COMPARED,
        verification_status=VerificationStatus.UNVERIFIED,
        updated_at=FIXED_TIME,
    )


def _decision_result(decision: str) -> CandidateDecisionResult:
    return CandidateDecisionResult(
        decision=decision,
        candidate_id=CANDIDATE_ID,
        monitoring_group_key=GROUP_KEY,
        monitoring_target_key=TARGET_KEY,
        baseline_id="base_security_baseline" if decision == "approved" else None,
        history_id="hist_security_history",
        committed_state=_state(),
    )


def _cleanup() -> CleanupResult:
    return CleanupResult(
        local_cleanup=LocalCleanupResult(status=LocalCleanupStatus.SUCCEEDED),
        remote_session_termination=RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
        ),
    )


def _assert_security_error_is_safe(response) -> None:
    payload = response.json()
    assert set(payload) == {"error_code", "message", "details"}
    assert payload["details"] is None
    assert "SECRET_HOST_VALUE" not in response.text
    assert "SECRET_ORIGIN_VALUE" not in response.text
    assert "SECRET_REQUEST_TOKEN" not in response.text
    assert "SECRET_COMMAND_VALUE" not in response.text
    assert "SECRET_ABSOLUTE_PATH" not in response.text


def _assert_no_cors_headers(response) -> None:
    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Access-Control-Allow-Credentials" not in response.headers
