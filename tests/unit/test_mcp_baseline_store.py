from __future__ import annotations

import json
import threading

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from core import mcp_baseline_store as baseline_store_module
from core.dynamic_scan_models import McpProduct, McpScope, McpTransport
from core.mcp_baseline_repository import (
    ApprovalCommit,
    BaselineHistoryDeletionCommit,
    BaselineRevocationCommit,
    CandidateCommit,
    MonitoringConflictError,
    MonitoringIntegrityError,
    MonitoringNotFoundError,
    MonitoringSchemaError,
    MonitoringStorageError,
    RejectionCommit,
    StateCommit,
)
from core.mcp_baseline_store import (
    FileMcpBaselineRepository,
    get_default_monitoring_root,
)
from core.mcp_metadata_diff import compare_tool_snapshots
from core.mcp_metadata_normalizer import (
    calculate_sha256,
    canonical_json_bytes,
    create_tool_snapshot,
    normalize_tool_metadata,
)
from core.mcp_monitoring_models import (
    ApprovedBaseline,
    BaselineComparisonResult,
    BaselineHistoryEventType,
    BaselineHistoryRecord,
    BaselineLifecycleStatus,
    ComparisonStatus,
    ConfigurationFingerprint,
    MonitoringCandidate,
    MonitoringIdentity,
    MonitoringScanStatus,
    MonitoredServerState,
    RegistrationIdentity,
    ToolSnapshot,
    VerificationStatus,
)
from core.models import ToolMetadata


GROUP = "mcpgrp_" + "1" * 32
TARGET = "mcptgt_" + "2" * 32
OTHER_TARGET = "mcptgt_" + "3" * 32
CONTEXT = "mcpctx_" + "4" * 32
OTHER_GROUP = "mcpgrp_" + "5" * 32
FIXED_TIME = datetime(2026, 6, 24, tzinfo=timezone.utc)
_UNSET = object()


def make_identity(
    *,
    group: str = GROUP,
    target: str = TARGET,
) -> MonitoringIdentity:
    return MonitoringIdentity(
        monitoring_group_key=group,
        monitoring_target_key=target,
        product=McpProduct.CODEX,
        normalized_server_name="docs",
        display_server_name="Docs",
        context_identity=CONTEXT,
        context_label="Project",
        registration_identity=RegistrationIdentity(
            selection_id="selection-one",
            scope=McpScope.PROJECT,
            safe_source_label="Project config",
            context_identity=CONTEXT,
        ),
    )


def make_state(
    *,
    group: str = GROUP,
    target: str = TARGET,
    state_version: int = 0,
    pending: list[str] | None = None,
    rejected: list[str] | None = None,
    approved: str | None = None,
    superseded: list[str] | None = None,
    history: list[str] | None = None,
    identity: MonitoringIdentity | None = None,
) -> MonitoredServerState:
    return MonitoredServerState(
        monitoring_group_key=group,
        monitoring_target_key=target,
        identity=identity or make_identity(group=group, target=target),
        state_version=state_version,
        current_approved_id=approved,
        pending_candidate_ids=pending or [],
        rejected_candidate_ids=rejected or [],
        superseded_baseline_ids=superseded or [],
        history_ids=history or [],
        last_scan_status=MonitoringScanStatus.SUCCESS
        if state_version
        else MonitoringScanStatus.NOT_SCANNED,
        baseline_lifecycle=BaselineLifecycleStatus.CANDIDATE_PENDING
        if pending
        else (
            BaselineLifecycleStatus.APPROVED
            if approved
            else BaselineLifecycleStatus.NONE
        ),
        comparison_status=ComparisonStatus.MATCHED
        if approved
        else ComparisonStatus.NOT_COMPARED,
        verification_status=VerificationStatus.VERIFIED
        if approved
        else VerificationStatus.UNVERIFIED,
        last_scan_at=FIXED_TIME if state_version else None,
        last_seen_selection_id="selection-one" if state_version else None,
        updated_at=FIXED_TIME,
    )


def make_tool(
    *,
    tool_name: str = "search",
    description: str = "Search docs.",
    secret: str | None = None,
) -> ToolMetadata:
    raw_tool: dict[str, object] = {
        "name": tool_name,
        "title": "Search",
        "description": description,
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
        "outputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True},
        "_meta": {"version": "1.0"},
    }
    if secret is not None:
        raw_tool["secret"] = secret
    return ToolMetadata.from_mcp_tool(
        raw_tool,
        server_name="docs",
        source="mcp:test",
        collected_at=FIXED_TIME,
    )


def make_snapshot(*tools: ToolMetadata) -> ToolSnapshot:
    return create_tool_snapshot(
        list(tools) or [make_tool()],
        created_at=FIXED_TIME,
        source_scan_id="scan-one",
    )


def make_fingerprint() -> ConfigurationFingerprint:
    return ConfigurationFingerprint(
        fingerprint="a" * 64,
        transport=McpTransport.STDIO,
        safe_summary={"transport": "stdio"},
    )


def make_candidate(
    *,
    candidate_id: str = "cand_one",
    target: str = TARGET,
    group: str = GROUP,
    snapshot: ToolSnapshot | None = None,
    comparison_result: BaselineComparisonResult | None | object = _UNSET,
    state_version_at_creation: int = 0,
) -> MonitoringCandidate:
    snapshot = snapshot or make_snapshot()
    comparison = (
        compare_tool_snapshots(snapshot, snapshot)
        if comparison_result is _UNSET
        else comparison_result
    )
    return MonitoringCandidate(
        candidate_id=candidate_id,
        monitoring_group_key=group,
        monitoring_target_key=target,
        selection_id="selection-one",
        configuration_fingerprint=make_fingerprint(),
        snapshot=snapshot,
        comparison_result=comparison,  # type: ignore[arg-type]
        dynamic_scan_status=MonitoringScanStatus.SUCCESS,
        scan_id="scan-one",
        created_at=FIXED_TIME,
        state_version_at_creation=state_version_at_creation,
    )


def make_approved(
    *,
    baseline_id: str = "base_one",
    target: str = TARGET,
    group: str = GROUP,
    candidate_id: str = "cand_one",
    snapshot: ToolSnapshot | None = None,
) -> ApprovedBaseline:
    return ApprovedBaseline(
        baseline_id=baseline_id,
        monitoring_group_key=group,
        monitoring_target_key=target,
        approved_at=FIXED_TIME,
        approved_from_candidate_id=candidate_id,
        selection_id_at_approval="selection-one",
        configuration_fingerprint=make_fingerprint(),
        snapshot=snapshot or make_snapshot(),
    )


def make_history(
    *,
    history_id: str = "hist_one",
    event_type: BaselineHistoryEventType = BaselineHistoryEventType.CANDIDATE_CREATED,
    target: str = TARGET,
    group: str = GROUP,
    candidate_id: str | None = "cand_one",
    baseline_id: str | None = None,
    previous_approved_id: str | None = None,
    new_approved_id: str | None = None,
) -> BaselineHistoryRecord:
    return BaselineHistoryRecord(
        history_id=history_id,
        monitoring_group_key=group,
        monitoring_target_key=target,
        event_type=event_type,
        candidate_id=candidate_id,
        baseline_id=baseline_id,
        previous_approved_id=previous_approved_id,
        new_approved_id=new_approved_id,
        created_at=FIXED_TIME,
        safe_reason_code="test",
    )


def candidate_path(repo: FileMcpBaselineRepository, candidate_id: str) -> Path:
    return (
        repo.root
        / "groups"
        / GROUP
        / "targets"
        / TARGET
        / "candidates"
        / f"{candidate_id}.json"
    )


def approved_path(repo: FileMcpBaselineRepository, baseline_id: str) -> Path:
    return (
        repo.root
        / "groups"
        / GROUP
        / "targets"
        / TARGET
        / "approved"
        / f"{baseline_id}.json"
    )


def history_path(repo: FileMcpBaselineRepository, history_id: str) -> Path:
    return (
        repo.root
        / "groups"
        / GROUP
        / "targets"
        / TARGET
        / "history"
        / f"{history_id}.json"
    )


def state_path(
    repo: FileMcpBaselineRepository,
    target: str = TARGET,
    group: str = GROUP,
) -> Path:
    return repo.root / "groups" / group / "targets" / target / "state.json"


def fail_json_dumps_for_document_type(
    monkeypatch: pytest.MonkeyPatch,
    document_type: str,
    error: Exception,
) -> None:
    original_dumps = json.dumps

    def maybe_fail_json_dumps(data: object, *args: object, **kwargs: object) -> str:
        if isinstance(data, dict) and data.get("document_type") == document_type:
            raise error

        return original_dumps(data, *args, **kwargs)

    monkeypatch.setattr(baseline_store_module.json, "dumps", maybe_fail_json_dumps)


def test_default_monitoring_root_policy(tmp_path: Path) -> None:
    env_root = tmp_path / "env-root"
    assert get_default_monitoring_root(
        environ={"AUDITGUARD_MCP_MONITORING_DIR": str(env_root)},
        home=tmp_path,
    ) == env_root.resolve()

    with pytest.raises(MonitoringStorageError):
        get_default_monitoring_root(
            environ={"AUDITGUARD_MCP_MONITORING_DIR": "relative"},
            home=tmp_path,
        )

    assert get_default_monitoring_root(
        platform_name="win32",
        environ={"LOCALAPPDATA": str(tmp_path / "LocalAppData")},
        home=tmp_path,
    ) == (tmp_path / "LocalAppData" / "AuditGuard" / "mcp-monitoring").resolve()
    assert get_default_monitoring_root(
        platform_name="darwin",
        environ={},
        home=tmp_path,
    ) == (
        tmp_path
        / "Library"
        / "Application Support"
        / "AuditGuard"
        / "mcp-monitoring"
    ).resolve()
    assert get_default_monitoring_root(
        platform_name="linux",
        environ={"XDG_DATA_HOME": str(tmp_path / "xdg")},
        home=tmp_path,
    ) == (tmp_path / "xdg" / "auditguard" / "mcp-monitoring").resolve()
    assert get_default_monitoring_root(
        platform_name="linux",
        environ={},
        home=tmp_path,
    ) == (
        tmp_path / ".local" / "share" / "auditguard" / "mcp-monitoring"
    ).resolve()
    assert get_default_monitoring_root(
        platform_name="win32",
        environ={},
        home=tmp_path,
    ) == (tmp_path / ".auditguard" / "mcp-monitoring").resolve()


def test_initial_state_creates_storage_structure_and_indexes(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    state = make_state()

    assert repo.load_target_state(TARGET) is None
    saved = repo.save_initial_target_state(state)
    loaded = repo.load_target_state(TARGET)

    assert saved == state
    assert loaded == state
    target_dir = repo.root / "groups" / GROUP / "targets" / TARGET
    assert (target_dir / "state.json").is_file()
    assert (target_dir / "candidates").is_dir()
    assert (target_dir / "approved").is_dir()
    assert (target_dir / "history").is_dir()
    assert (target_dir / "quarantine").is_dir()
    assert (repo.root / "index.json").is_file()
    assert (repo.root / "groups" / GROUP / "index.json").is_file()


def test_atomic_write_replace_failure_keeps_existing_final(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    path = tmp_path / "mcp-monitoring" / "atomic.json"
    path.parent.mkdir(parents=True)
    path.write_text("old", encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(repo, "_replace", fail_replace)

    with pytest.raises(MonitoringStorageError):
        repo._write_text_atomic(path, "new")

    assert path.read_text(encoding="utf-8") == "old"
    assert list(path.parent.glob("*.tmp")) == []


def test_write_model_atomic_converts_json_dumps_type_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    path = repo.root / "atomic.json"
    path.parent.mkdir(parents=True)
    path.write_text("old", encoding="utf-8")
    candidate = make_candidate()

    def fail_json_dumps(*args: object, **kwargs: object) -> str:
        raise TypeError("SECRET_VALUE")

    monkeypatch.setattr(baseline_store_module.json, "dumps", fail_json_dumps)

    with pytest.raises(MonitoringStorageError) as error_info:
        repo._write_model_atomic(path, candidate)

    assert str(error_info.value) == "could not serialize monitoring document"
    assert "SECRET_VALUE" not in str(error_info.value)
    assert path.read_text(encoding="utf-8") == "old"


def test_write_model_atomic_converts_json_dumps_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    path = repo.root / "atomic.json"
    path.parent.mkdir(parents=True)
    path.write_text("old", encoding="utf-8")
    candidate = make_candidate()

    def fail_json_dumps(*args: object, **kwargs: object) -> str:
        raise ValueError("SECRET_VALUE")

    monkeypatch.setattr(baseline_store_module.json, "dumps", fail_json_dumps)

    with pytest.raises(MonitoringStorageError) as error_info:
        repo._write_model_atomic(path, candidate)

    assert str(error_info.value) == "could not serialize monitoring document"
    assert "SECRET_VALUE" not in str(error_info.value)
    assert path.read_text(encoding="utf-8") == "old"


def test_write_model_atomic_converts_pydantic_serialization_error(
    tmp_path: Path,
) -> None:
    class BrokenModel:
        def model_dump(self, *, mode: str) -> dict[str, object]:
            raise PydanticSerializationError("SECRET_VALUE")

    repo = FileMcpBaselineRepository(tmp_path)
    path = repo.root / "atomic.json"
    path.parent.mkdir(parents=True)
    path.write_text("old", encoding="utf-8")

    with pytest.raises(MonitoringStorageError) as error_info:
        repo._write_model_atomic(path, BrokenModel())

    assert str(error_info.value) == "could not serialize monitoring document"
    assert "SECRET_VALUE" not in str(error_info.value)
    assert path.read_text(encoding="utf-8") == "old"


def test_directory_fsync_failure_after_replace_keeps_commit_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    def fail_directory_fsync(directory: Path) -> None:
        raise OSError("directory fsync failed")

    monkeypatch.setattr(repo, "_fsync_directory", fail_directory_fsync)

    result = repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert result.committed_state == new_state
    assert repo.load_target_state(TARGET) == new_state


def test_body_file_fsync_failure_keeps_existing_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    repo._save_immutable_document(candidate_path(repo, candidate.candidate_id), candidate)
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    def fail_file_fsync(fd: int) -> None:
        raise OSError("file fsync failed")

    monkeypatch.setattr(baseline_store_module.os, "fsync", fail_file_fsync)

    with pytest.raises(MonitoringStorageError):
        repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert repo.load_target_state(TARGET).state_version == 0  # type: ignore[union-attr]


def test_candidate_document_serialization_failure_keeps_state_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    initial_state = make_state()
    repo.save_initial_target_state(initial_state)
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])
    fail_json_dumps_for_document_type(
        monkeypatch,
        "monitoring_candidate",
        TypeError("SECRET_VALUE"),
    )

    with pytest.raises(MonitoringStorageError) as error_info:
        repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert str(error_info.value) == "could not serialize monitoring document"
    assert "SECRET_VALUE" not in str(error_info.value)
    assert repo.load_target_state(TARGET) == initial_state
    assert not candidate_path(repo, candidate.candidate_id).exists()


def test_state_document_serialization_failure_keeps_old_state_and_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    initial_state = make_state()
    repo.save_initial_target_state(initial_state)
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])
    fail_json_dumps_for_document_type(
        monkeypatch,
        "monitored_server_state",
        TypeError("SECRET_VALUE"),
    )

    with pytest.raises(MonitoringStorageError) as error_info:
        repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert str(error_info.value) == "could not serialize monitoring document"
    assert repo.load_target_state(TARGET) == initial_state
    assert repo.load_candidate(candidate.candidate_id, TARGET) == candidate
    assert [orphan.document_id for orphan in repo.find_orphan_documents(TARGET)] == [
        candidate.candidate_id
    ]


def test_immutable_candidate_is_idempotent_but_not_overwritten(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    repo.commit_candidate(CandidateCommit(0, candidate, new_state))
    repo._save_immutable_document(candidate_path(repo, candidate.candidate_id), candidate)

    changed_candidate = make_candidate(
        snapshot=make_snapshot(make_tool(description="Changed")),
    )
    with pytest.raises(MonitoringConflictError, match="immutable document"):
        repo._save_immutable_document(
            candidate_path(repo, changed_candidate.candidate_id),
            changed_candidate,
        )


def test_candidate_commit_and_state_commit_point(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    result = repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert result.committed_state == new_state
    assert result.document_ids == [candidate.candidate_id]
    assert repo.load_target_state(TARGET) == new_state
    assert repo.load_candidate(candidate.candidate_id, TARGET) == candidate


def test_state_commit_updates_only_state_document(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    initial_state = make_state()
    repo.save_initial_target_state(initial_state)
    new_state = make_state(state_version=1).model_copy(
        update={
            "last_scan_status": MonitoringScanStatus.FAILED,
            "comparison_status": ComparisonStatus.COMPARISON_FAILED,
            "verification_status": VerificationStatus.UNAVAILABLE,
        }
    )

    result = repo.commit_state(StateCommit(0, new_state))

    assert result.committed_state == new_state
    assert result.document_ids == []
    assert repo.load_target_state(TARGET) == new_state
    assert list((state_path(repo).parent / "candidates").glob("*.json")) == []
    assert list((state_path(repo).parent / "approved").glob("*.json")) == []
    assert list((state_path(repo).parent / "history").glob("*.json")) == []


def test_state_commit_rejects_conflicting_transitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    initial_state = make_state()
    repo.save_initial_target_state(initial_state)
    valid_next = make_state(state_version=1)

    with pytest.raises(MonitoringConflictError, match="state version"):
        repo.commit_state(StateCommit(1, valid_next))

    changed_group = make_state(group=OTHER_GROUP, target=TARGET, state_version=1)
    with pytest.raises(MonitoringConflictError, match="group"):
        repo.commit_state(StateCommit(0, changed_group))

    wrong_next_version = make_state(state_version=2)
    with pytest.raises(MonitoringConflictError, match="increase by one"):
        repo.commit_state(StateCommit(0, wrong_next_version))

    changed_target = make_state(target=OTHER_TARGET, state_version=1)
    monkeypatch.setattr(
        repo,
        "_load_existing_state_for_commit",
        lambda _new_state: initial_state,
    )
    with pytest.raises(MonitoringConflictError, match="target"):
        repo.commit_state(StateCommit(0, changed_target))

    assert repo.load_target_state(TARGET) == initial_state


def test_state_commit_index_failure_is_best_effort(tmp_path: Path) -> None:
    repo = IndexFailingRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    new_state = make_state(state_version=1)

    result = repo.commit_state(StateCommit(0, new_state))

    assert result.document_ids == []
    assert result.warnings == ["index_rebuild_pending"]
    assert repo.load_target_state(TARGET) == new_state


def test_state_commit_serialization_failure_keeps_old_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    initial_state = make_state()
    repo.save_initial_target_state(initial_state)
    new_state = make_state(state_version=1)
    fail_json_dumps_for_document_type(
        monkeypatch,
        "monitored_server_state",
        TypeError("SECRET_VALUE"),
    )

    with pytest.raises(MonitoringStorageError) as error_info:
        repo.commit_state(StateCommit(0, new_state))

    assert str(error_info.value) == "could not serialize monitoring document"
    assert "SECRET_VALUE" not in str(error_info.value)
    assert repo.load_target_state(TARGET) == initial_state


def test_same_target_concurrent_state_commits_one_success(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    results: list[str] = []

    def commit() -> None:
        new_state = make_state(state_version=1)
        try:
            repo.commit_state(StateCommit(0, new_state))
            results.append("success")
        except MonitoringConflictError:
            results.append("conflict")

    threads = [threading.Thread(target=commit), threading.Thread(target=commit)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["conflict", "success"]
    assert repo.load_target_state(TARGET).state_version == 1  # type: ignore[union-attr]


def test_initial_candidate_allows_missing_comparison_result(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate(comparison_result=None)
    new_state = make_state(
        state_version=1,
        pending=[candidate.candidate_id],
    ).model_copy(
        update={
            "comparison_status": ComparisonStatus.NOT_COMPARED,
            "verification_status": VerificationStatus.REVIEW_REQUIRED,
            "last_comparison": None,
        }
    )

    repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    stored = json.loads(
        candidate_path(repo, candidate.candidate_id).read_text(encoding="utf-8")
    )
    assert stored["comparison_result"] is None
    assert repo.load_candidate(candidate.candidate_id, TARGET) == candidate


def test_candidate_comparison_result_must_reference_current_snapshot() -> None:
    snapshot = make_snapshot()
    other_snapshot = make_snapshot(make_tool(tool_name="lookup"))
    mismatched = compare_tool_snapshots(snapshot, other_snapshot)

    with pytest.raises(ValidationError, match="current snapshot id"):
        make_candidate(snapshot=snapshot, comparison_result=mismatched)

    data = make_candidate(snapshot=snapshot).model_dump(mode="json")
    data["comparison_result"]["current_snapshot_hash"] = "b" * 64
    with pytest.raises(ValidationError, match="current snapshot hash"):
        MonitoringCandidate.model_validate(data)


def test_candidate_commit_state_failure_leaves_orphan_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    def fail_state_commit(state: MonitoredServerState) -> None:
        raise MonitoringStorageError("state write failed")

    monkeypatch.setattr(repo, "_write_state_commit", fail_state_commit)

    with pytest.raises(MonitoringStorageError):
        repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert repo.load_target_state(TARGET).state_version == 0  # type: ignore[union-attr]
    assert repo.load_candidate(candidate.candidate_id, TARGET) == candidate
    assert [orphan.document_id for orphan in repo.find_orphan_documents(TARGET)] == [
        candidate.candidate_id
    ]


def test_approval_and_rejection_commits_update_state(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    candidate_state = make_state(state_version=1, pending=[candidate.candidate_id])
    repo.commit_candidate(CandidateCommit(0, candidate, candidate_state))

    approved = make_approved(candidate_id=candidate.candidate_id)
    approve_history = make_history(
        history_id="hist_approve",
        event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
        candidate_id=candidate.candidate_id,
        baseline_id=approved.baseline_id,
        new_approved_id=approved.baseline_id,
    )
    approved_state = make_state(
        state_version=2,
        approved=approved.baseline_id,
        history=[approve_history.history_id],
    )

    repo.commit_approval(ApprovalCommit(1, approved, approve_history, approved_state))

    assert repo.load_target_state(TARGET) == approved_state
    assert repo.load_approved_baseline(approved.baseline_id, TARGET) == approved
    assert repo.list_target_history(TARGET) == [approve_history]

    rejected_candidate = make_candidate(
        candidate_id="cand_two",
        state_version_at_creation=2,
        snapshot=make_snapshot(make_tool(description="Rejected")),
    )
    pending_state = make_state(
        state_version=3,
        approved=approved.baseline_id,
        pending=[rejected_candidate.candidate_id],
        history=[approve_history.history_id],
    )
    repo.commit_candidate(CandidateCommit(2, rejected_candidate, pending_state))
    reject_history = make_history(
        history_id="hist_reject",
        event_type=BaselineHistoryEventType.CANDIDATE_REJECTED,
        candidate_id=rejected_candidate.candidate_id,
    )
    rejected_state = make_state(
        state_version=4,
        approved=approved.baseline_id,
        rejected=[rejected_candidate.candidate_id],
        history=[approve_history.history_id, reject_history.history_id],
    )

    repo.commit_rejection(RejectionCommit(3, reject_history, rejected_state))

    assert repo.load_target_state(TARGET) == rejected_state
    assert repo.list_target_history(TARGET) == [approve_history, reject_history]


def test_approval_failure_after_documents_leaves_state_unchanged_and_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    candidate_state = make_state(state_version=1, pending=[candidate.candidate_id])
    repo.commit_candidate(CandidateCommit(0, candidate, candidate_state))
    approved = make_approved()
    history = make_history(
        history_id="hist_approve",
        event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
        baseline_id=approved.baseline_id,
        candidate_id=candidate.candidate_id,
        new_approved_id=approved.baseline_id,
    )
    approved_state = make_state(
        state_version=2,
        approved=approved.baseline_id,
        history=[history.history_id],
    )

    def fail_state_commit(state: MonitoredServerState) -> None:
        raise MonitoringStorageError("state write failed")

    monkeypatch.setattr(repo, "_write_state_commit", fail_state_commit)

    with pytest.raises(MonitoringStorageError):
        repo.commit_approval(ApprovalCommit(1, approved, history, approved_state))

    assert repo.load_target_state(TARGET) == candidate_state
    orphan_ids = {orphan.document_id for orphan in repo.find_orphan_documents(TARGET)}
    assert approved.baseline_id in orphan_ids
    assert history.history_id in orphan_ids


def test_state_version_and_target_conflicts_are_rejected(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    with pytest.raises(MonitoringConflictError):
        repo.commit_candidate(CandidateCommit(99, candidate, new_state))

    other_candidate = make_candidate(
        candidate_id="cand_other",
        target=OTHER_TARGET,
        state_version_at_creation=0,
    )
    with pytest.raises(MonitoringConflictError):
        repo.commit_candidate(CandidateCommit(0, other_candidate, new_state))

    assert repo.load_target_state(TARGET).state_version == 0  # type: ignore[union-attr]
    assert not candidate_path(repo, "cand_other").exists()


def test_invalid_candidate_commit_references_are_rejected_before_document_write(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    initial_state = make_state()
    repo.save_initial_target_state(initial_state)
    candidate = make_candidate()
    new_state = make_state(state_version=1)

    with pytest.raises(MonitoringConflictError, match="not referenced as pending"):
        repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert repo.load_target_state(TARGET) == initial_state
    assert not candidate_path(repo, candidate.candidate_id).exists()


def test_invalid_approval_commit_references_are_rejected_before_document_write(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    candidate_state = make_state(state_version=1, pending=[candidate.candidate_id])
    repo.commit_candidate(CandidateCommit(0, candidate, candidate_state))
    approved = make_approved(candidate_id=candidate.candidate_id)
    history = make_history(
        history_id="hist_approve",
        event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
        candidate_id=candidate.candidate_id,
        baseline_id=approved.baseline_id,
        new_approved_id=approved.baseline_id,
    )

    wrong_current_state = make_state(
        state_version=2,
        approved="base_other",
        history=[history.history_id],
    )
    with pytest.raises(MonitoringConflictError, match="not current"):
        repo.commit_approval(ApprovalCommit(1, approved, history, wrong_current_state))

    missing_history_state = make_state(
        state_version=2,
        approved=approved.baseline_id,
    )
    with pytest.raises(MonitoringConflictError, match="history"):
        repo.commit_approval(ApprovalCommit(1, approved, history, missing_history_state))

    still_pending_state = make_state(
        state_version=2,
        pending=[candidate.candidate_id],
        approved=approved.baseline_id,
        history=[history.history_id],
    )
    with pytest.raises(MonitoringConflictError, match="still pending"):
        repo.commit_approval(ApprovalCommit(1, approved, history, still_pending_state))

    wrong_history = make_history(
        history_id="hist_wrong",
        event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
        candidate_id=candidate.candidate_id,
        baseline_id=approved.baseline_id,
        new_approved_id="base_other",
    )
    wrong_history_state = make_state(
        state_version=2,
        approved=approved.baseline_id,
        history=[wrong_history.history_id],
    )
    with pytest.raises(MonitoringConflictError, match="history"):
        repo.commit_approval(
            ApprovalCommit(1, approved, wrong_history, wrong_history_state)
        )

    assert repo.load_target_state(TARGET) == candidate_state
    assert not approved_path(repo, approved.baseline_id).exists()
    assert not history_path(repo, history.history_id).exists()


def test_invalid_rejection_commit_references_are_rejected_before_document_write(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    approved = "base_existing"
    pending_candidate = "cand_pending"
    old_state = make_state(
        state_version=1,
        pending=[pending_candidate],
        approved=approved,
    )
    repo.save_initial_target_state(make_state())
    repo._write_state_commit(old_state)
    history = make_history(
        history_id="hist_reject",
        event_type=BaselineHistoryEventType.CANDIDATE_REJECTED,
        candidate_id=pending_candidate,
    )

    missing_history_state = make_state(
        state_version=2,
        rejected=[pending_candidate],
        approved=approved,
    )
    with pytest.raises(MonitoringConflictError, match="history"):
        repo.commit_rejection(RejectionCommit(1, history, missing_history_state))

    not_rejected_state = make_state(
        state_version=2,
        approved=approved,
        history=[history.history_id],
    )
    with pytest.raises(MonitoringConflictError, match="not rejected"):
        repo.commit_rejection(RejectionCommit(1, history, not_rejected_state))

    still_pending_state = make_state(
        state_version=2,
        rejected=[pending_candidate],
        approved=approved,
        history=[history.history_id],
    ).model_copy(update={"pending_candidate_ids": [pending_candidate]})
    with pytest.raises(MonitoringConflictError, match="still pending"):
        repo.commit_rejection(RejectionCommit(1, history, still_pending_state))

    changed_approved_state = make_state(
        state_version=2,
        rejected=[pending_candidate],
        approved="base_other",
        history=[history.history_id],
    )
    with pytest.raises(MonitoringConflictError, match="current approved"):
        repo.commit_rejection(RejectionCommit(1, history, changed_approved_state))

    no_candidate_history = make_history(
        history_id="hist_no_candidate",
        event_type=BaselineHistoryEventType.CANDIDATE_REJECTED,
        candidate_id=None,
    )
    no_candidate_state = make_state(
        state_version=2,
        rejected=[pending_candidate],
        approved=approved,
        history=[no_candidate_history.history_id],
    )
    with pytest.raises(MonitoringConflictError, match="must reference"):
        repo.commit_rejection(
            RejectionCommit(1, no_candidate_history, no_candidate_state)
        )

    assert repo.load_target_state(TARGET) == old_state
    assert not history_path(repo, history.history_id).exists()


def test_baseline_revocation_commit_writes_history_and_state(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    candidate_state = make_state(state_version=1, pending=[candidate.candidate_id])
    repo.commit_candidate(CandidateCommit(0, candidate, candidate_state))
    approved = make_approved(candidate_id=candidate.candidate_id)
    approve_history = make_history(
        history_id="hist_approve",
        event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
        candidate_id=candidate.candidate_id,
        baseline_id=approved.baseline_id,
        new_approved_id=approved.baseline_id,
    )
    approved_state = make_state(
        state_version=2,
        approved=approved.baseline_id,
        history=[approve_history.history_id],
    )
    repo.commit_approval(ApprovalCommit(1, approved, approve_history, approved_state))
    revoke_history = make_history(
        history_id="hist_revoke",
        event_type=BaselineHistoryEventType.BASELINE_REVOKED,
        candidate_id=None,
        baseline_id=approved.baseline_id,
        previous_approved_id=approved.baseline_id,
        new_approved_id=None,
    )
    revoked_state = make_state(
        state_version=3,
        superseded=[approved.baseline_id],
        history=[approve_history.history_id, revoke_history.history_id],
    )

    result = repo.commit_baseline_revocation(
        BaselineRevocationCommit(
            2,
            approved.baseline_id,
            revoke_history,
            revoked_state,
        )
    )

    assert result.committed_state == revoked_state
    assert result.document_ids == [revoke_history.history_id]
    assert repo.load_target_state(TARGET) == revoked_state
    assert repo.load_history_record(revoke_history.history_id, TARGET) == revoke_history
    assert repo.load_approved_baseline(approved.baseline_id, TARGET) == approved
    assert approved_path(repo, approved.baseline_id).exists()


def test_history_deletion_commit_clears_state_refs_and_history_files(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    approved = make_approved()
    approve_history = make_history(
        history_id="hist_approve",
        event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
        baseline_id=approved.baseline_id,
        new_approved_id=approved.baseline_id,
    )
    reject_history = make_history(
        history_id="hist_reject",
        event_type=BaselineHistoryEventType.CANDIDATE_REJECTED,
        candidate_id="cand_rejected",
    )
    old_state = make_state(
        state_version=2,
        approved=approved.baseline_id,
        history=[approve_history.history_id, reject_history.history_id],
    )
    repo.save_initial_target_state(make_state())
    repo._save_immutable_document(approved_path(repo, approved.baseline_id), approved)
    repo._save_immutable_document(history_path(repo, approve_history.history_id), approve_history)
    repo._save_immutable_document(history_path(repo, reject_history.history_id), reject_history)
    repo._write_state_commit(old_state)

    new_state = make_state(
        state_version=3,
        history=[],
    )
    result = repo.commit_history_deletion(
        BaselineHistoryDeletionCommit(2, new_state)
    )

    assert result.committed_state == new_state
    assert result.document_ids == [
        approve_history.history_id,
        reject_history.history_id,
    ]
    assert repo.load_target_state(TARGET) == new_state
    assert repo.list_target_history(TARGET) == []
    assert not history_path(repo, approve_history.history_id).exists()
    assert not history_path(repo, reject_history.history_id).exists()
    assert approved_path(repo, approved.baseline_id).exists()


def test_baseline_revocation_preserves_candidate_lists_and_dedupes_superseded(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    approved = make_approved()
    approve_history = make_history(
        history_id="hist_approve",
        event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
        baseline_id=approved.baseline_id,
        new_approved_id=approved.baseline_id,
    )
    old_state = make_state(
        state_version=2,
        approved=approved.baseline_id,
        pending=["cand_pending"],
        rejected=["cand_rejected"],
        superseded=["base_old"],
        history=[approve_history.history_id],
    )
    repo.save_initial_target_state(make_state())
    repo._save_immutable_document(approved_path(repo, approved.baseline_id), approved)
    repo._save_immutable_document(history_path(repo, approve_history.history_id), approve_history)
    repo._write_state_commit(old_state)
    revoke_history = make_history(
        history_id="hist_revoke",
        event_type=BaselineHistoryEventType.BASELINE_REVOKED,
        candidate_id=None,
        baseline_id=approved.baseline_id,
        previous_approved_id=approved.baseline_id,
    )
    revoked_state = make_state(
        state_version=3,
        pending=["cand_pending"],
        rejected=["cand_rejected"],
        superseded=["base_old", approved.baseline_id],
        history=[approve_history.history_id, revoke_history.history_id],
    )

    repo.commit_baseline_revocation(
        BaselineRevocationCommit(
            2,
            approved.baseline_id,
            revoke_history,
            revoked_state,
        )
    )

    committed = repo.load_target_state(TARGET)
    assert committed is not None
    assert committed.pending_candidate_ids == ["cand_pending"]
    assert committed.rejected_candidate_ids == ["cand_rejected"]
    assert committed.superseded_baseline_ids == ["base_old", approved.baseline_id]


def test_invalid_baseline_revocation_references_are_rejected_before_history_write(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    approved = make_approved()
    old_state = make_state(state_version=2, approved=approved.baseline_id)
    repo.save_initial_target_state(make_state())
    repo._save_immutable_document(approved_path(repo, approved.baseline_id), approved)
    repo._write_state_commit(old_state)
    revoke_history = make_history(
        history_id="hist_revoke",
        event_type=BaselineHistoryEventType.BASELINE_REVOKED,
        candidate_id=None,
        baseline_id=approved.baseline_id,
        previous_approved_id=approved.baseline_id,
    )

    missing_history_state = make_state(
        state_version=3,
        superseded=[approved.baseline_id],
    )
    with pytest.raises(MonitoringConflictError, match="history"):
        repo.commit_baseline_revocation(
            BaselineRevocationCommit(
                2,
                approved.baseline_id,
                revoke_history,
                missing_history_state,
            )
        )

    changed_pending_state = make_state(
        state_version=3,
        pending=["cand_new"],
        superseded=[approved.baseline_id],
        history=[revoke_history.history_id],
    )
    with pytest.raises(MonitoringConflictError, match="pending"):
        repo.commit_baseline_revocation(
            BaselineRevocationCommit(
                2,
                approved.baseline_id,
                revoke_history,
                changed_pending_state,
            )
        )

    with pytest.raises(MonitoringConflictError, match="current approved"):
        repo.commit_baseline_revocation(
            BaselineRevocationCommit(
                2,
                "base_other",
                revoke_history,
                make_state(
                    state_version=3,
                    superseded=["base_other"],
                    history=[revoke_history.history_id],
                ),
            )
        )

    assert repo.load_target_state(TARGET) == old_state
    assert not history_path(repo, revoke_history.history_id).exists()


def test_baseline_revocation_state_write_failure_keeps_previous_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    approved = make_approved()
    old_state = make_state(state_version=2, approved=approved.baseline_id)
    repo.save_initial_target_state(make_state())
    repo._save_immutable_document(approved_path(repo, approved.baseline_id), approved)
    repo._write_state_commit(old_state)
    revoke_history = make_history(
        history_id="hist_revoke",
        event_type=BaselineHistoryEventType.BASELINE_REVOKED,
        candidate_id=None,
        baseline_id=approved.baseline_id,
        previous_approved_id=approved.baseline_id,
    )
    revoked_state = make_state(
        state_version=3,
        superseded=[approved.baseline_id],
        history=[revoke_history.history_id],
    )

    def fail_state_commit(state: MonitoredServerState) -> None:
        raise MonitoringStorageError("state write failed")

    monkeypatch.setattr(repo, "_write_state_commit", fail_state_commit)

    with pytest.raises(MonitoringStorageError):
        repo.commit_baseline_revocation(
            BaselineRevocationCommit(
                2,
                approved.baseline_id,
                revoke_history,
                revoked_state,
            )
        )

    assert repo.load_target_state(TARGET) == old_state
    assert history_path(repo, revoke_history.history_id).exists()


def test_baseline_revocation_history_write_failure_keeps_previous_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    approved = make_approved()
    old_state = make_state(state_version=2, approved=approved.baseline_id)
    repo.save_initial_target_state(make_state())
    repo._save_immutable_document(approved_path(repo, approved.baseline_id), approved)
    repo._write_state_commit(old_state)
    revoke_history = make_history(
        history_id="hist_revoke",
        event_type=BaselineHistoryEventType.BASELINE_REVOKED,
        candidate_id=None,
        baseline_id=approved.baseline_id,
        previous_approved_id=approved.baseline_id,
    )
    revoked_state = make_state(
        state_version=3,
        superseded=[approved.baseline_id],
        history=[revoke_history.history_id],
    )

    def fail_history_write(path: Path, model: object) -> None:
        if path == history_path(repo, revoke_history.history_id):
            raise MonitoringStorageError("history write failed")
        repo._write_model_atomic(path, model)

    monkeypatch.setattr(repo, "_save_immutable_document", fail_history_write)

    with pytest.raises(MonitoringStorageError):
        repo.commit_baseline_revocation(
            BaselineRevocationCommit(
                2,
                approved.baseline_id,
                revoke_history,
                revoked_state,
            )
        )

    assert repo.load_target_state(TARGET) == old_state
    assert not history_path(repo, revoke_history.history_id).exists()


def test_schema_errors_are_not_treated_as_empty_state(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    path = state_path(repo)
    original = json.loads(path.read_text(encoding="utf-8"))

    corrupted = {**original, "schema_version": "unknown"}
    path.write_text(json.dumps(corrupted), encoding="utf-8")
    with pytest.raises(MonitoringSchemaError):
        repo.load_target_state(TARGET)

    corrupted = {**original, "document_type": "other"}
    path.write_text(json.dumps(corrupted), encoding="utf-8")
    with pytest.raises(MonitoringSchemaError):
        repo.load_target_state(TARGET)

    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(MonitoringSchemaError):
        repo.load_target_state(TARGET)

    missing = dict(original)
    missing.pop("identity")
    path.write_text(json.dumps(missing), encoding="utf-8")
    with pytest.raises(MonitoringSchemaError):
        repo.load_target_state(TARGET)


def test_filename_id_target_and_hash_integrity_are_verified(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])
    repo.commit_candidate(CandidateCommit(0, candidate, new_state))
    path = candidate_path(repo, candidate.candidate_id)
    data = json.loads(path.read_text(encoding="utf-8"))

    data["candidate_id"] = "cand_other"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(MonitoringIntegrityError):
        repo.load_candidate(candidate.candidate_id, TARGET)

    data["candidate_id"] = candidate.candidate_id
    data["monitoring_target_key"] = OTHER_TARGET
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(MonitoringIntegrityError):
        repo.load_candidate(candidate.candidate_id, TARGET)

    data["monitoring_target_key"] = TARGET
    data["monitoring_group_key"] = "mcpgrp_" + "9" * 32
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(MonitoringIntegrityError):
        repo.load_candidate(candidate.candidate_id)

    data["monitoring_group_key"] = GROUP
    data["snapshot"]["tools"][0]["fields"]["title"]["value"] = "Tampered"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(MonitoringIntegrityError):
        repo.load_candidate(candidate.candidate_id, TARGET)


def test_snapshot_hash_snapshot_id_and_duplicate_keys_are_verified(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])
    repo.commit_candidate(CandidateCommit(0, candidate, new_state))
    path = candidate_path(repo, candidate.candidate_id)
    original = json.loads(path.read_text(encoding="utf-8"))

    data = json.loads(json.dumps(original))
    data["snapshot"]["snapshot_hash"] = "b" * 64
    data["comparison_result"]["current_snapshot_hash"] = "b" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(MonitoringIntegrityError):
        repo.load_candidate(candidate.candidate_id, TARGET)

    data = json.loads(json.dumps(original))
    data["snapshot"]["snapshot_id"] = "snap_" + "0" * 20
    data["comparison_result"]["current_snapshot_id"] = "snap_" + "0" * 20
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(MonitoringIntegrityError):
        repo.load_candidate(candidate.candidate_id, TARGET)

    data = json.loads(json.dumps(original))
    tool = data["snapshot"]["tools"][0]
    data["snapshot"]["tools"].append(tool)
    data["snapshot"]["tool_count"] = 2
    data["snapshot"]["snapshot_hash"] = calculate_sha256(
        canonical_json_bytes(
            {
                "version": data["snapshot"]["normalization_version"],
                "tools": [
                    {
                        "tool_key": item["tool_key"],
                        "tool_hash": item["tool_hash"],
                    }
                    for item in data["snapshot"]["tools"]
                ],
            }
        )
    )
    data["snapshot"]["snapshot_id"] = (
        "snap_" + data["snapshot"]["snapshot_hash"][:20]
    )
    data["comparison_result"]["current_snapshot_hash"] = data["snapshot"][
        "snapshot_hash"
    ]
    data["comparison_result"]["current_snapshot_id"] = data["snapshot"]["snapshot_id"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(MonitoringIntegrityError):
        repo.load_candidate(candidate.candidate_id, TARGET)


class IndexFailingRepository(FileMcpBaselineRepository):
    def __init__(self, root: Path | str) -> None:
        super().__init__(root)
        self.group_index_calls = 0
        self.root_index_calls = 0

    def rebuild_group_index(self, monitoring_group_key: str):
        self.group_index_calls += 1
        raise MonitoringStorageError("group index failed")

    def rebuild_root_index(self):
        self.root_index_calls += 1
        raise MonitoringStorageError("root index failed")


class RootIntegrityFailingRepository(FileMcpBaselineRepository):
    def rebuild_root_index(self):
        raise MonitoringIntegrityError("root index failed")


def test_index_failure_does_not_roll_back_any_commit_type(tmp_path: Path) -> None:
    repo = IndexFailingRepository(tmp_path)
    state = make_state()
    # Initial state uses best-effort index rebuild as well.
    repo.save_initial_target_state(state)
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    result = repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert result.warnings == ["index_rebuild_pending"]
    assert repo.load_target_state(TARGET) == new_state
    assert repo.group_index_calls >= 2
    assert repo.root_index_calls >= 2

    approved = make_approved(candidate_id=candidate.candidate_id)
    approve_history = make_history(
        history_id="hist_approve",
        event_type=BaselineHistoryEventType.CANDIDATE_APPROVED,
        candidate_id=candidate.candidate_id,
        baseline_id=approved.baseline_id,
        new_approved_id=approved.baseline_id,
    )
    approved_state = make_state(
        state_version=2,
        approved=approved.baseline_id,
        history=[approve_history.history_id],
    )
    approval_result = repo.commit_approval(
        ApprovalCommit(1, approved, approve_history, approved_state)
    )

    assert approval_result.warnings == ["index_rebuild_pending"]
    assert repo.load_target_state(TARGET) == approved_state

    rejected_candidate = make_candidate(
        candidate_id="cand_two",
        state_version_at_creation=2,
        snapshot=make_snapshot(make_tool(description="Rejected")),
    )
    pending_state = make_state(
        state_version=3,
        approved=approved.baseline_id,
        pending=[rejected_candidate.candidate_id],
        history=[approve_history.history_id],
    )
    repo.commit_candidate(CandidateCommit(2, rejected_candidate, pending_state))
    reject_history = make_history(
        history_id="hist_reject",
        event_type=BaselineHistoryEventType.CANDIDATE_REJECTED,
        candidate_id=rejected_candidate.candidate_id,
    )
    rejected_state = make_state(
        state_version=4,
        approved=approved.baseline_id,
        rejected=[rejected_candidate.candidate_id],
        history=[approve_history.history_id, reject_history.history_id],
    )
    rejection_result = repo.commit_rejection(
        RejectionCommit(3, reject_history, rejected_state)
    )

    assert rejection_result.warnings == ["index_rebuild_pending"]
    assert repo.load_target_state(TARGET) == rejected_state


def test_root_index_integrity_failure_is_best_effort_after_state_commit(
    tmp_path: Path,
) -> None:
    repo = RootIntegrityFailingRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    result = repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert result.warnings == ["index_rebuild_pending"]
    assert repo.load_target_state(TARGET) == new_state


def test_index_model_validation_errors_are_best_effort_after_state_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    def fail_group_index_validation(*args: object, **kwargs: object) -> None:
        MonitoredServerState.model_validate({"invalid": "state"})

    monkeypatch.setattr(
        baseline_store_module,
        "MonitoringGroupIndex",
        fail_group_index_validation,
    )

    result = repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert result.warnings == ["index_rebuild_pending"]
    assert repo.load_target_state(TARGET) == new_state


def test_root_index_model_validation_error_is_best_effort_after_state_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])

    def fail_root_index_validation(*args: object, **kwargs: object) -> None:
        MonitoredServerState.model_validate({"invalid": "state"})

    monkeypatch.setattr(
        baseline_store_module,
        "MonitoringRootIndex",
        fail_root_index_validation,
    )

    result = repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert result.warnings == ["index_rebuild_pending"]
    assert repo.load_target_state(TARGET) == new_state


def test_group_index_serialization_failure_is_best_effort_after_state_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])
    fail_json_dumps_for_document_type(
        monkeypatch,
        "monitoring_group_index",
        TypeError("SECRET_VALUE"),
    )

    result = repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert result.committed_state == new_state
    assert result.warnings == ["index_rebuild_pending"]
    assert repo.load_target_state(TARGET) == new_state


def test_root_index_serialization_failure_is_best_effort_after_state_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])
    fail_json_dumps_for_document_type(
        monkeypatch,
        "monitoring_root_index",
        ValueError("SECRET_VALUE"),
    )

    result = repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    assert result.committed_state == new_state
    assert result.warnings == ["index_rebuild_pending"]
    assert repo.load_target_state(TARGET) == new_state


def test_index_rebuild_from_target_state_after_index_damage(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    (repo.root / "index.json").write_text("{bad", encoding="utf-8")
    (repo.root / "groups" / GROUP / "index.json").write_text("{bad", encoding="utf-8")

    group_index = repo.rebuild_group_index(GROUP)
    root_index = repo.rebuild_root_index()

    assert group_index.targets[0].monitoring_target_key == TARGET
    assert root_index.groups[0].monitoring_group_key == GROUP


def test_list_group_targets_reads_state_without_touching_indexes(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    repo.save_initial_target_state(make_state(target=OTHER_TARGET))
    root_index_path = repo.root / "index.json"
    group_index_path = repo.root / "groups" / GROUP / "index.json"
    root_before = root_index_path.read_text(encoding="utf-8")
    group_before = group_index_path.read_text(encoding="utf-8")
    root_mtime_before = root_index_path.stat().st_mtime_ns
    group_mtime_before = group_index_path.stat().st_mtime_ns

    targets = repo.list_group_targets(GROUP)

    assert targets == sorted([TARGET, OTHER_TARGET])
    assert root_index_path.read_text(encoding="utf-8") == root_before
    assert group_index_path.read_text(encoding="utf-8") == group_before
    assert root_index_path.stat().st_mtime_ns == root_mtime_before
    assert group_index_path.stat().st_mtime_ns == group_mtime_before


def test_list_group_targets_works_without_index_files(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    root_index_path = repo.root / "index.json"
    group_index_path = repo.root / "groups" / GROUP / "index.json"
    root_index_path.unlink()
    group_index_path.unlink()

    targets = repo.list_group_targets(GROUP)

    assert targets == [TARGET]
    assert not root_index_path.exists()
    assert not group_index_path.exists()


def test_list_group_targets_does_not_create_empty_group_index(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)

    assert repo.list_group_targets(GROUP) == []
    assert not (repo.root / "index.json").exists()
    assert not (repo.root / "groups" / GROUP / "index.json").exists()


def test_list_group_targets_validates_state_schema_and_location(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    original = json.loads(state_path(repo).read_text(encoding="utf-8"))
    broken = dict(original)
    broken["schema_version"] = "unknown"
    state_path(repo).write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(MonitoringSchemaError):
        repo.list_group_targets(GROUP)

    state_path(repo).write_text(json.dumps(original), encoding="utf-8")
    misplaced = make_state(group=GROUP, target=TARGET)
    bad_path = state_path(repo, target=TARGET, group=OTHER_GROUP)
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text(
        json.dumps(misplaced.model_dump(mode="json")),
        encoding="utf-8",
    )
    with pytest.raises(MonitoringIntegrityError):
        repo.list_group_targets(OTHER_GROUP)


def test_group_index_rebuild_rejects_state_group_path_mismatch(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    misplaced_state = make_state(group=GROUP, target=OTHER_TARGET)
    bad_path = state_path(repo, target=OTHER_TARGET, group=OTHER_GROUP)
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text(
        json.dumps(misplaced_state.model_dump(mode="json")),
        encoding="utf-8",
    )

    with pytest.raises(MonitoringIntegrityError):
        repo.rebuild_group_index(OTHER_GROUP)


def test_group_index_rebuild_rejects_state_target_path_mismatch(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    misplaced_state = make_state(group=GROUP, target=TARGET)
    bad_path = state_path(repo, target=OTHER_TARGET, group=GROUP)
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text(
        json.dumps(misplaced_state.model_dump(mode="json")),
        encoding="utf-8",
    )

    with pytest.raises(MonitoringIntegrityError):
        repo.rebuild_group_index(GROUP)


def test_duplicate_target_key_across_groups_is_ambiguous(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    repo.save_initial_target_state(make_state(group=OTHER_GROUP, target=TARGET))

    with pytest.raises(MonitoringIntegrityError, match="ambiguous"):
        repo.load_target_state(TARGET)

    candidate = make_candidate()
    with pytest.raises(MonitoringIntegrityError, match="ambiguous"):
        repo.load_candidate(candidate.candidate_id, TARGET)


def test_orphan_detection_does_not_adopt_unreferenced_documents(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    candidate = make_candidate()
    repo._save_immutable_document(candidate_path(repo, candidate.candidate_id), candidate)

    orphans = repo.find_orphan_documents(TARGET)

    assert [orphan.document_id for orphan in orphans] == [candidate.candidate_id]
    assert repo.load_target_state(TARGET).pending_candidate_ids == []  # type: ignore[union-attr]


def test_path_traversal_ids_are_rejected(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)

    for unsafe_id in ("../evil", "cand_/evil", "cand_\\evil", str(tmp_path / "evil")):
        with pytest.raises(MonitoringStorageError):
            repo.load_candidate(unsafe_id)

    with pytest.raises(MonitoringStorageError):
        repo.load_target_state("../evil")


def test_error_messages_and_indexes_do_not_leak_paths_or_raw_secret(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    secret_tool = make_tool(secret="VERY_SECRET")
    candidate = make_candidate(snapshot=make_snapshot(secret_tool))
    new_state = make_state(state_version=1, pending=[candidate.candidate_id])
    repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    with pytest.raises(MonitoringNotFoundError) as error_info:
        repo.load_candidate("cand_missing", TARGET)

    message = str(error_info.value)
    assert str(tmp_path) not in message
    assert "VERY_SECRET" not in message
    assert "VERY_SECRET" not in (repo.root / "index.json").read_text(encoding="utf-8")


def test_same_target_concurrent_commits_use_state_version_conflict(
    tmp_path: Path,
) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    results: list[str] = []

    def commit(candidate_id: str) -> None:
        candidate = make_candidate(candidate_id=candidate_id)
        new_state = make_state(state_version=1, pending=[candidate_id])
        try:
            repo.commit_candidate(CandidateCommit(0, candidate, new_state))
            results.append("success")
        except MonitoringConflictError:
            results.append("conflict")

    threads = [
        threading.Thread(target=commit, args=("cand_a",)),
        threading.Thread(target=commit, args=("cand_b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["conflict", "success"]
    assert repo.load_target_state(TARGET).state_version == 1  # type: ignore[union-attr]


def test_different_targets_commit_independently(tmp_path: Path) -> None:
    repo = FileMcpBaselineRepository(tmp_path)
    repo.save_initial_target_state(make_state())
    repo.save_initial_target_state(make_state(target=OTHER_TARGET))

    def commit(target: str, candidate_id: str) -> None:
        candidate = make_candidate(candidate_id=candidate_id, target=target)
        new_state = make_state(
            target=target,
            state_version=1,
            pending=[candidate_id],
        )
        repo.commit_candidate(CandidateCommit(0, candidate, new_state))

    threads = [
        threading.Thread(target=commit, args=(TARGET, "cand_a")),
        threading.Thread(target=commit, args=(OTHER_TARGET, "cand_b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert repo.load_target_state(TARGET).state_version == 1  # type: ignore[union-attr]
    assert repo.load_target_state(OTHER_TARGET).state_version == 1  # type: ignore[union-attr]


def test_state_model_validators() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        make_state(pending=["cand_one", "cand_one"])
    with pytest.raises(ValidationError, match="superseded"):
        make_state(approved="base_one", superseded=["base_one"])
    with pytest.raises(ValidationError, match="both pending and rejected"):
        make_state(pending=["cand_one"], rejected=["cand_one"])
    with pytest.raises(ValidationError, match="identity monitoring_group_key"):
        make_state(group=GROUP, identity=make_identity(group="mcpgrp_" + "9" * 32))

    naive_time = datetime(2026, 6, 24, 12, 0, 0)
    state = MonitoredServerState(
        monitoring_group_key=GROUP,
        monitoring_target_key=TARGET,
        identity=make_identity(),
        last_scan_at=naive_time,
        updated_at=naive_time,
    )
    assert state.last_scan_at.tzinfo is timezone.utc
    assert state.updated_at.tzinfo is timezone.utc

    with pytest.raises(ValidationError):
        MonitoredServerState.model_validate(
            {
                **state.model_dump(mode="json"),
                "extra": "x",
            }
        )
    with pytest.raises(ValidationError):
        state.state_version = 3  # type: ignore[misc]
