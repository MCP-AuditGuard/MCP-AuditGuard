from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.dynamic_scan_models import (
    CleanupResult,
    CollectedTool,
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
    ToolActivationAssessment,
    ToolActivationStatus,
)
from core.mcp_monitoring_models import (
    BaselineHistoryEventType,
    BaselineHistoryRecord,
    BaselineComparisonResult,
    ComparisonStatus,
    ConfigurationFingerprint,
    FieldPresence,
    MonitoringCandidate,
    MonitoringIdentity,
    MonitoringScanStatus,
    MonitoredServerState,
    RegistrationIdentity,
    ToolChange,
    ToolChangeType,
    ToolFieldChange,
    ToolSnapshot,
)
from core.mcp_monitoring_service import (
    BaselineHistoryDeletionResult,
    BaselineRevocationResult,
    MonitoredServerListItem,
    MonitoredServerListResult,
)
from core.models import ToolMetadata
from core.scan_result import ScanResult
from web.mcp_schemas import (
    BaselineCandidateResponse,
    BaselineComparisonResponse,
    BaselineHistoryDeletionRequest,
    BaselineHistoryDeletionResponse,
    BaselineHistoryListResponse,
    BaselineRevocationRequest,
    BaselineRevocationResponse,
    CandidateDecisionRequest,
    DynamicScanSummaryResponse,
    McpServerListResponse,
)


FIXED_TIME = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
GROUP_KEY = "mcpgrp_" + "1" * 32
TARGET_KEY = "mcptgt_" + "2" * 32
CONTEXT_ID = "mcpctx_" + "3" * 32
SNAPSHOT_ID = "snap_" + "4" * 20
APPROVED_SNAPSHOT_ID = "snap_" + "5" * 20


def test_candidate_response_filters_config_summary_and_hashes() -> None:
    candidate = _candidate()

    response = BaselineCandidateResponse.from_core(candidate)
    payload = response.model_dump()
    rendered = response.model_dump_json()

    assert payload["configuration_fingerprint"]["safe_summary"] == {
        "transport": "stdio",
        "command_basename": "server.py",
        "argument_count": 2,
        "cwd_present": True,
        "env_key_count": 1,
        "env_literal_key_count": 1,
        "env_reference_key_count": 0,
    }
    assert payload["configuration_fingerprint"]["fingerprint_hash_prefix"] == (
        "a" * 16
    )
    assert "secret_path" not in rendered
    assert "C:/Users/USER/.codex/config.toml" not in rendered
    assert "a" * 64 not in rendered


def test_comparison_response_truncates_values_and_uses_hash_prefixes() -> None:
    comparison = _comparison()

    response = BaselineComparisonResponse.from_core(comparison)
    field = response.tool_changes[0].field_changes[0]
    rendered = response.model_dump_json()

    assert len(field.old_value_text or "") == 4000
    assert field.old_value_truncated is True
    assert len(field.new_value_text or "") == 12000
    assert field.new_value_truncated is True
    assert field.old_value_hash_prefix == "b" * 16
    assert field.new_value_hash_prefix == "c" * 16
    assert "b" * 64 not in rendered
    assert "c" * 64 not in rendered


def test_dynamic_scan_response_omits_collected_tools_and_scan_source() -> None:
    result = _dynamic_result(source="C:/Users/USER/.secret/mcp-tools.json")

    response = DynamicScanSummaryResponse.from_core(result)
    payload = response.model_dump()
    rendered = response.model_dump_json()

    assert payload["scan_result"]["summary"]["tool_count"] == 1
    assert "collected_tools" not in rendered
    assert '"tools"' not in rendered
    assert "C:/Users/USER/.secret/mcp-tools.json" not in rendered
    assert "sensitive_tool_source" not in rendered


def test_candidate_decision_request_rejects_extra_and_unsafe_reason() -> None:
    with pytest.raises(ValidationError):
        CandidateDecisionRequest.model_validate(
            {
                "monitoring_target_key": TARGET_KEY,
                "expected_state_version": 0,
                "safe_reason_code": "unsafe reason",
            }
        )

    with pytest.raises(ValidationError):
        CandidateDecisionRequest.model_validate(
            {
                "monitoring_target_key": TARGET_KEY,
                "expected_state_version": 0,
                "safe_reason_code": "safe_reason",
                "unexpected": "value",
            }
        )


def test_baseline_revocation_request_rejects_extra_and_unsafe_reason() -> None:
    with pytest.raises(ValidationError):
        BaselineRevocationRequest.model_validate(
            {
                "expected_state_version": 0,
                "expected_current_approved_id": "base_safe_baseline",
                "safe_reason_code": "unsafe reason",
            }
        )

    with pytest.raises(ValidationError):
        BaselineRevocationRequest.model_validate(
            {
                "expected_state_version": 0,
                "expected_current_approved_id": "base_safe_baseline",
                "safe_reason_code": "safe_reason",
                "unexpected": "value",
            }
        )


def test_baseline_revocation_response_is_safe_state_summary() -> None:
    state = _state(
        selection_id="codex:user:docs",
        target_key=TARGET_KEY,
        server_name="docs",
    ).model_copy(
        update={
            "state_version": 3,
            "current_approved_id": None,
        }
    )
    result = BaselineRevocationResult(
        monitoring_group_key=GROUP_KEY,
        monitoring_target_key=TARGET_KEY,
        removed_baseline_id="base_safe_baseline",
        history_id="hist_revoked",
        committed_state=state,
        warnings=["index_rebuild_pending"],
    )

    response = BaselineRevocationResponse.from_core(result)
    payload = response.model_dump()
    rendered = response.model_dump_json()

    assert payload == {
        "decision": "baseline_revoked",
        "monitoring_group_key": GROUP_KEY,
        "monitoring_target_key": TARGET_KEY,
        "removed_baseline_id": "base_safe_baseline",
        "history_id": "hist_revoked",
        "state_version": 3,
        "current_approved_id": None,
        "baseline_lifecycle": "none",
        "comparison_status": "not_compared",
        "verification_status": "unverified",
        "last_scan_status": "not_scanned",
        "warnings": ["index_rebuild_pending"],
    }
    assert "snapshot" not in rendered
    assert "configuration_fingerprint" not in rendered
    assert "command" not in rendered
    assert "args" not in rendered
    assert "env" not in rendered


def test_server_list_response_total_matches_server_count() -> None:
    empty_response = McpServerListResponse.from_core(
        MonitoredServerListResult(
            servers=[],
            discovery_result=McpDiscoveryResult(),
        ),
        include_trusted_project_config=True,
    )

    response = McpServerListResponse.from_core(
        MonitoredServerListResult(
            servers=[
                _list_item(
                    selection_id="codex:user:docs",
                    target_key=TARGET_KEY,
                    server_name="docs",
                ),
                _list_item(
                    selection_id="codex:user:search",
                    target_key="mcptgt_" + "6" * 32,
                    server_name="search",
                ),
            ],
            discovery_result=McpDiscoveryResult(),
        ),
        include_trusted_project_config=False,
    )

    assert empty_response.total == 0
    assert empty_response.servers == []
    assert empty_response.include_trusted_project_config is True
    assert response.total == 2
    assert response.total == len(response.servers)
    assert response.include_trusted_project_config is False


def test_history_list_response_total_matches_record_count() -> None:
    empty_response = BaselineHistoryListResponse.from_core(TARGET_KEY, [])
    response = BaselineHistoryListResponse.from_core(
        TARGET_KEY,
        [
            _history_record("hist_safe_history_1"),
            _history_record("hist_safe_history_2"),
            _history_record("hist_safe_history_3"),
        ],
    )

    assert empty_response.total == 0
    assert empty_response.records == []
    assert response.total == 3
    assert response.total == len(response.records)


def test_history_deletion_request_validates_version_and_response_is_safe() -> None:
    with pytest.raises(ValidationError):
        BaselineHistoryDeletionRequest.model_validate(
            {
                "expected_state_version": -1,
            }
        )

    state = _state(
        selection_id="codex:user:docs",
        target_key=TARGET_KEY,
        server_name="docs",
    )
    result = BaselineHistoryDeletionResult(
        monitoring_group_key=GROUP_KEY,
        monitoring_target_key=TARGET_KEY,
        deleted_history_count=2,
        committed_state=state,
    )

    response = BaselineHistoryDeletionResponse.from_core(result)
    payload = response.model_dump()

    assert payload["decision"] == "baseline_history_deleted"
    assert payload["deleted_history_count"] == 2
    assert payload["history_ids"] == []
    assert payload["monitoring_target_key"] == TARGET_KEY
    assert "snapshot" not in response.model_dump_json()


def _candidate() -> MonitoringCandidate:
    return MonitoringCandidate(
        candidate_id="cand_safe_candidate",
        monitoring_group_key=GROUP_KEY,
        monitoring_target_key=TARGET_KEY,
        selection_id="codex:user:docs",
        configuration_fingerprint=ConfigurationFingerprint(
            fingerprint="a" * 64,
            transport=McpTransport.STDIO,
            safe_summary={
                "transport": "stdio",
                "command_basename": "server.py",
                "argument_count": 2,
                "cwd_present": True,
                "env_key_count": 1,
                "env_literal_key_count": 1,
                "env_reference_key_count": 0,
                "secret_path": "C:/Users/USER/.codex/config.toml",
            },
        ),
        snapshot=ToolSnapshot(
            snapshot_id=SNAPSHOT_ID,
            snapshot_hash="d" * 64,
            normalization_version="mcp-tool-normalization-v1",
            tools=[],
            tool_count=0,
            created_at=FIXED_TIME,
            source_scan_id="scan_safe",
        ),
        comparison_result=None,
        dynamic_scan_status=MonitoringScanStatus.SUCCESS,
        scan_id="scan_safe",
        created_at=FIXED_TIME,
        state_version_at_creation=0,
    )


def _comparison() -> BaselineComparisonResult:
    return BaselineComparisonResult(
        comparison_status=ComparisonStatus.CHANGED,
        matched=False,
        change_categories=["tool_changed"],
        approved_snapshot_id=APPROVED_SNAPSHOT_ID,
        current_snapshot_id=SNAPSHOT_ID,
        approved_snapshot_hash="f" * 64,
        current_snapshot_hash="e" * 64,
        added_count=0,
        removed_count=0,
        changed_count=1,
        unchanged_count=0,
        tool_changes=[
            ToolChange(
                change_type=ToolChangeType.CHANGED,
                tool_key="docs.search",
                tool_name="search",
                old_tool_hash="0" * 64,
                new_tool_hash="1" * 64,
                field_changes=[
                    ToolFieldChange(
                        field_name="description",
                        old_presence=FieldPresence.VALUE,
                        new_presence=FieldPresence.VALUE,
                        old_value="x" * 5000,
                        new_value={"description": "y" * 13000},
                        old_value_hash="b" * 64,
                        new_value_hash="c" * 64,
                    )
                ],
            )
        ],
    )


def _dynamic_result(*, source: str) -> DynamicScanResult:
    summary = _server_summary()
    tool = ToolMetadata.from_mcp_tool(
        {
            "name": "search",
            "description": "Search docs.",
            "inputSchema": {"type": "object"},
        },
        server_name=summary.server_name,
        source="sensitive_tool_source",
        collected_at=FIXED_TIME,
    )
    scan = ScanResult(
        scan_type="dynamic",
        source_type="mcp_server",
        source=source,
        started_at=FIXED_TIME,
        completed_at=FIXED_TIME,
        tools=[tool],
        findings=[],
    )
    return DynamicScanResult(
        status=DynamicScanStatus.SUCCESS,
        target=summary,
        collected_tools=[
            CollectedTool(
                tool_id="1" * 20,
                metadata=tool,
                activation=ToolActivationAssessment(
                    tool_name=tool.tool_name,
                    status=ToolActivationStatus.ENABLED,
                    product=summary.product,
                    safe_basis_code="enabled_by_host",
                ),
            )
        ],
        cleanup=_cleanup(),
        scan_result=scan,
    )


def _server_summary(
    *,
    selection_id: str = "codex:user:docs",
    server_name: str = "docs",
) -> McpServerSummary:
    return McpServerSummary(
        selection_id=selection_id,
        product=McpProduct.CODEX,
        scope=McpScope.USER,
        source_label="Codex user config",
        server_name=server_name,
        transport=McpTransport.STDIO,
        enabled_state=ServerEnabledState.ENABLED,
        support_state=ServerSupportState.SUPPORTED,
        command_basename="C:/secret/bin/server.py",
        argument_count=2,
    )


def _cleanup() -> CleanupResult:
    return CleanupResult(
        local_cleanup=LocalCleanupResult(status=LocalCleanupStatus.SUCCEEDED),
        remote_session_termination=RemoteSessionTerminationResult(
            status=RemoteSessionTerminationStatus.NOT_APPLICABLE,
        ),
    )


def _identity(
    *,
    selection_id: str = "codex:user:docs",
    target_key: str = TARGET_KEY,
    server_name: str = "docs",
) -> MonitoringIdentity:
    return MonitoringIdentity(
        monitoring_group_key=GROUP_KEY,
        monitoring_target_key=target_key,
        product=McpProduct.CODEX,
        normalized_server_name=server_name,
        display_server_name=server_name,
        context_identity=CONTEXT_ID,
        context_label="user:codex",
        registration_identity=RegistrationIdentity(
            selection_id=selection_id,
            scope=McpScope.USER,
            safe_source_label="Codex user config",
            context_identity=CONTEXT_ID,
        ),
    )


def _state(
    *,
    selection_id: str,
    target_key: str,
    server_name: str,
) -> MonitoredServerState:
    identity = _identity(
        selection_id=selection_id,
        target_key=target_key,
        server_name=server_name,
    )
    return MonitoredServerState(
        monitoring_group_key=identity.monitoring_group_key,
        monitoring_target_key=identity.monitoring_target_key,
        identity=identity,
        updated_at=FIXED_TIME,
    )


def _list_item(
    *,
    selection_id: str,
    target_key: str,
    server_name: str,
) -> MonitoredServerListItem:
    return MonitoredServerListItem(
        server_summary=_server_summary(
            selection_id=selection_id,
            server_name=server_name,
        ),
        monitoring_identity=_identity(
            selection_id=selection_id,
            target_key=target_key,
            server_name=server_name,
        ),
        monitoring_state=_state(
            selection_id=selection_id,
            target_key=target_key,
            server_name=server_name,
        ),
        related_target_count=1,
        related_approved_target_count=0,
        can_scan=True,
    )


def _history_record(history_id: str) -> BaselineHistoryRecord:
    return BaselineHistoryRecord(
        history_id=history_id,
        monitoring_group_key=GROUP_KEY,
        monitoring_target_key=TARGET_KEY,
        event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
        candidate_id="cand_safe_candidate",
        baseline_id="base_safe_baseline",
        created_at=FIXED_TIME,
        safe_reason_code="user_approved",
    )
