from __future__ import annotations

import json
import os
import re
import sys
import threading

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from core.mcp_baseline_repository import (
    ApprovalCommit,
    BaselineHistoryDeletionCommit,
    BaselineRevocationCommit,
    CandidateCommit,
    McpBaselineRepository,
    MonitoringConflictError,
    MonitoringIntegrityError,
    MonitoringNotFoundError,
    MonitoringSchemaError,
    MonitoringStorageError,
    RejectionCommit,
    StateCommit,
)
from core.mcp_metadata_normalizer import canonical_json_bytes, calculate_sha256
from core.mcp_monitoring_models import (
    ApprovedBaseline,
    BaselineLifecycleStatus,
    BaselineHistoryRecord,
    ComparisonStatus,
    MONITORING_STORAGE_SCHEMA_VERSION,
    MonitoringCandidate,
    MonitoringGroupIndex,
    MonitoringRootIndex,
    MonitoringTargetIndexEntry,
    MonitoredServerState,
    NormalizedToolMetadata,
    OrphanDocument,
    RepositoryCommitResult,
    ToolSnapshot,
    VerificationStatus,
)


_GROUP_RE = re.compile(r"^mcpgrp_[0-9a-f]{32}$")
_TARGET_RE = re.compile(r"^mcptgt_[0-9a-f]{32}$")
_CANDIDATE_RE = re.compile(r"^cand_[A-Za-z0-9_-]{1,128}$")
_BASELINE_RE = re.compile(r"^base_[A-Za-z0-9_-]{1,128}$")
_HISTORY_RE = re.compile(r"^hist_[A-Za-z0-9_-]{1,128}$")


class FileMcpBaselineRepository(McpBaselineRepository):
    """File-backed MCP monitoring repository.

    Root and group indexes are non-authoritative caches. Target state documents
    are the source of truth.
    """

    _registry_lock = threading.Lock()
    _target_locks: dict[str, threading.RLock] = {}
    _group_locks: dict[str, threading.RLock] = {}
    _root_lock = threading.RLock()

    def __init__(self, root: Path | str) -> None:
        base_root = Path(root).expanduser().resolve(strict=False)
        self.root = (
            base_root
            if base_root.name == "mcp-monitoring"
            else base_root / "mcp-monitoring"
        )

    def load_target_state(
        self,
        monitoring_target_key: str,
    ) -> MonitoredServerState | None:
        target_key = self._safe_target_key(monitoring_target_key)
        path = self._find_target_state_path(target_key)
        if path is None:
            return None

        state = self._read_model(
            path=path,
            model_type=MonitoredServerState,
            document_type="monitored_server_state",
        )
        if state.monitoring_target_key != target_key:
            raise MonitoringIntegrityError("stored target state identity mismatch")
        self._validate_document_location(state, path)

        return state

    def save_initial_target_state(
        self,
        state: MonitoredServerState,
    ) -> MonitoredServerState:
        if state.state_version != 0:
            raise MonitoringConflictError("initial state version must be zero")

        self._safe_group_key(state.monitoring_group_key)
        self._safe_target_key(state.monitoring_target_key)
        with self._lock_for_target(state.monitoring_target_key):
            path = self._target_dir(
                state.monitoring_group_key,
                state.monitoring_target_key,
            ) / "state.json"
            self._ensure_target_dirs(
                state.monitoring_group_key,
                state.monitoring_target_key,
            )
            if path.exists():
                existing = self._read_model(
                    path=path,
                    model_type=MonitoredServerState,
                    document_type="monitored_server_state",
                )
                if self._model_bytes(existing) == self._model_bytes(state):
                    return existing
                raise MonitoringConflictError("initial state already exists")

            self._write_model_atomic(path, state)
            self._rebuild_indexes_best_effort(state.monitoring_group_key)
            return state

    def load_candidate(
        self,
        candidate_id: str,
        monitoring_target_key: str | None = None,
    ) -> MonitoringCandidate:
        candidate_key = self._safe_candidate_id(candidate_id)
        path = self._find_document_path(
            document_id=candidate_key,
            directory_name="candidates",
            suffix=".json",
            monitoring_target_key=monitoring_target_key,
        )
        candidate = self._read_model(
            path=path,
            model_type=MonitoringCandidate,
            document_type="monitoring_candidate",
        )
        self._validate_document_id(candidate.candidate_id, candidate_key)
        self._validate_document_location(candidate, path)
        self._validate_document_target(candidate, monitoring_target_key)
        self._verify_snapshot(candidate.snapshot)
        return candidate

    def load_approved_baseline(
        self,
        baseline_id: str,
        monitoring_target_key: str | None = None,
    ) -> ApprovedBaseline:
        baseline_key = self._safe_baseline_id(baseline_id)
        path = self._find_document_path(
            document_id=baseline_key,
            directory_name="approved",
            suffix=".json",
            monitoring_target_key=monitoring_target_key,
        )
        approved = self._read_model(
            path=path,
            model_type=ApprovedBaseline,
            document_type="approved_baseline",
        )
        self._validate_document_id(approved.baseline_id, baseline_key)
        self._validate_document_location(approved, path)
        self._validate_document_target(approved, monitoring_target_key)
        self._verify_snapshot(approved.snapshot)
        return approved

    def load_history_record(
        self,
        history_id: str,
        monitoring_target_key: str | None = None,
    ) -> BaselineHistoryRecord:
        history_key = self._safe_history_id(history_id)
        path = self._find_document_path(
            document_id=history_key,
            directory_name="history",
            suffix=".json",
            monitoring_target_key=monitoring_target_key,
        )
        history = self._read_model(
            path=path,
            model_type=BaselineHistoryRecord,
            document_type="baseline_history",
        )
        self._validate_document_id(history.history_id, history_key)
        self._validate_document_location(history, path)
        self._validate_document_target(history, monitoring_target_key)
        return history

    def commit_candidate(
        self,
        command: CandidateCommit,
    ) -> RepositoryCommitResult:
        new_state = command.new_state
        self._validate_candidate_commit(command)
        with self._lock_for_target(new_state.monitoring_target_key):
            old_state = self._load_existing_state_for_commit(new_state)
            self._validate_state_transition(
                old_state=old_state,
                new_state=new_state,
                expected_state_version=command.expected_state_version,
            )
            self._validate_candidate_state_references(command)
            self._save_immutable_document(
                self._candidate_path(command.candidate),
                command.candidate,
            )
            self._write_state_commit(new_state)
            warnings = self._rebuild_indexes_best_effort(
                new_state.monitoring_group_key
            )
            return RepositoryCommitResult(
                committed_state=new_state,
                document_ids=[command.candidate.candidate_id],
                warnings=warnings,
            )

    def commit_approval(
        self,
        command: ApprovalCommit,
    ) -> RepositoryCommitResult:
        new_state = command.new_state
        self._validate_approval_commit(command)
        with self._lock_for_target(new_state.monitoring_target_key):
            old_state = self._load_existing_state_for_commit(new_state)
            self._validate_state_transition(
                old_state=old_state,
                new_state=new_state,
                expected_state_version=command.expected_state_version,
            )
            self._validate_approval_state_references(command)
            self._save_immutable_document(
                self._approved_path(command.approved_baseline),
                command.approved_baseline,
            )
            self._save_immutable_document(
                self._history_path(command.history_record),
                command.history_record,
            )
            self._write_state_commit(new_state)
            warnings = self._rebuild_indexes_best_effort(
                new_state.monitoring_group_key
            )
            return RepositoryCommitResult(
                committed_state=new_state,
                document_ids=[
                    command.approved_baseline.baseline_id,
                    command.history_record.history_id,
                ],
                warnings=warnings,
            )

    def commit_rejection(
        self,
        command: RejectionCommit,
    ) -> RepositoryCommitResult:
        new_state = command.new_state
        self._validate_rejection_commit(command)
        with self._lock_for_target(new_state.monitoring_target_key):
            old_state = self._load_existing_state_for_commit(new_state)
            self._validate_state_transition(
                old_state=old_state,
                new_state=new_state,
                expected_state_version=command.expected_state_version,
            )
            self._validate_rejection_state_references(command, old_state)
            self._save_immutable_document(
                self._history_path(command.history_record),
                command.history_record,
            )
            self._write_state_commit(new_state)
            warnings = self._rebuild_indexes_best_effort(
                new_state.monitoring_group_key
            )
            return RepositoryCommitResult(
                committed_state=new_state,
                document_ids=[command.history_record.history_id],
                warnings=warnings,
            )

    def commit_baseline_revocation(
        self,
        command: BaselineRevocationCommit,
    ) -> RepositoryCommitResult:
        new_state = command.new_state
        self._validate_baseline_revocation_commit(command)
        with self._lock_for_target(new_state.monitoring_target_key):
            old_state = self._load_existing_state_for_commit(new_state)
            self._validate_state_transition(
                old_state=old_state,
                new_state=new_state,
                expected_state_version=command.expected_state_version,
            )
            self._validate_baseline_revocation_state_references(
                command,
                old_state,
            )
            self.load_approved_baseline(
                command.expected_current_approved_id,
                monitoring_target_key=new_state.monitoring_target_key,
            )
            self._save_immutable_document(
                self._history_path(command.history_record),
                command.history_record,
            )
            self._write_state_commit(new_state)
            warnings = self._rebuild_indexes_best_effort(
                new_state.monitoring_group_key
            )
            return RepositoryCommitResult(
                committed_state=new_state,
                document_ids=[command.history_record.history_id],
                warnings=warnings,
            )

    def commit_history_deletion(
        self,
        command: BaselineHistoryDeletionCommit,
    ) -> RepositoryCommitResult:
        new_state = command.new_state
        with self._lock_for_target(new_state.monitoring_target_key):
            old_state = self._load_existing_state_for_commit(new_state)
            self._validate_state_transition(
                old_state=old_state,
                new_state=new_state,
                expected_state_version=command.expected_state_version,
            )
            self._validate_history_deletion_state(command, old_state)
            deleted_history_ids = list(old_state.history_ids)
            self._write_state_commit(new_state)
            delete_warnings = self._delete_history_documents(
                new_state,
                deleted_history_ids,
            )
            warnings = [
                *delete_warnings,
                *self._rebuild_indexes_best_effort(
                    new_state.monitoring_group_key
                ),
            ]
            return RepositoryCommitResult(
                committed_state=new_state,
                document_ids=deleted_history_ids,
                warnings=warnings,
            )

    def commit_state(
        self,
        command: StateCommit,
    ) -> RepositoryCommitResult:
        new_state = command.new_state
        with self._lock_for_target(new_state.monitoring_target_key):
            old_state = self._load_existing_state_for_commit(new_state)
            self._validate_state_transition(
                old_state=old_state,
                new_state=new_state,
                expected_state_version=command.expected_state_version,
            )
            self._write_state_commit(new_state)
            warnings = self._rebuild_indexes_best_effort(
                new_state.monitoring_group_key
            )
            return RepositoryCommitResult(
                committed_state=new_state,
                document_ids=[],
                warnings=warnings,
            )

    def list_group_targets(
        self,
        monitoring_group_key: str,
    ) -> list[str]:
        group_key = self._safe_group_key(monitoring_group_key)
        try:
            target_keys: list[str] = []
            for state_path in self._iter_group_state_paths(group_key):
                state = self._read_model(
                    path=state_path,
                    model_type=MonitoredServerState,
                    document_type="monitored_server_state",
                )
                self._validate_document_location(state, state_path)
                target_keys.append(state.monitoring_target_key)

            return sorted(target_keys)
        except MonitoringStorageError:
            raise
        except ValidationError as exc:
            raise MonitoringSchemaError("could not list group targets") from exc
        except OSError as exc:
            raise MonitoringStorageError("could not list group targets") from exc

    def list_target_history(
        self,
        monitoring_target_key: str,
    ) -> list[BaselineHistoryRecord]:
        state = self.load_target_state(monitoring_target_key)
        if state is None:
            raise MonitoringNotFoundError("target state was not found")

        return [
            self.load_history_record(
                history_id,
                monitoring_target_key=state.monitoring_target_key,
            )
            for history_id in state.history_ids
        ]

    def rebuild_group_index(
        self,
        monitoring_group_key: str,
    ) -> MonitoringGroupIndex:
        group_key = self._safe_group_key(monitoring_group_key)
        with self._lock_for_group(group_key):
            try:
                states: list[MonitoredServerState] = []
                for state_path in self._iter_group_state_paths(group_key):
                    state = self._read_model(
                        path=state_path,
                        model_type=MonitoredServerState,
                        document_type="monitored_server_state",
                    )
                    self._validate_document_location(state, state_path)
                    states.append(state)

                states = sorted(states, key=lambda state: state.monitoring_target_key)
                if states:
                    first = states[0]
                    product = first.identity.product
                    display_name = first.identity.display_server_name
                else:
                    product = None
                    display_name = "unknown"

                if product is None:
                    # Empty group indexes are useful as cache rebuild artifacts in
                    # tests, but normal groups are created from target state.
                    from core.dynamic_scan_models import McpProduct

                    product = McpProduct.CODEX

                index = MonitoringGroupIndex(
                    monitoring_group_key=group_key,
                    product=product,
                    display_server_name=display_name,
                    targets=[
                        MonitoringTargetIndexEntry(
                            monitoring_target_key=state.monitoring_target_key,
                            context_label=state.identity.context_label,
                            last_scan_status=state.last_scan_status,
                            baseline_lifecycle=state.baseline_lifecycle,
                            comparison_status=state.comparison_status,
                            verification_status=state.verification_status,
                            last_seen_at=state.last_scan_at or state.updated_at,
                        )
                        for state in states
                    ],
                )
                self._write_model_atomic(self._group_index_path(group_key), index)
                return index
            except MonitoringStorageError:
                raise
            except ValidationError as exc:
                raise MonitoringSchemaError("could not rebuild group index") from exc
            except OSError as exc:
                raise MonitoringStorageError("could not rebuild group index") from exc

    def rebuild_root_index(self) -> MonitoringRootIndex:
        with self._root_lock:
            try:
                group_indexes = (
                    [
                        self.rebuild_group_index(group_dir.name)
                        for group_dir in self._groups_dir().iterdir()
                        if group_dir.is_dir() and _GROUP_RE.fullmatch(group_dir.name)
                    ]
                    if self._groups_dir().exists()
                    else []
                )
                index = MonitoringRootIndex(
                    groups=sorted(
                        group_indexes,
                        key=lambda group: group.monitoring_group_key,
                    ),
                )
                self._write_model_atomic(self._root_index_path(), index)
                return index
            except MonitoringStorageError:
                raise
            except ValidationError as exc:
                raise MonitoringSchemaError("could not rebuild root index") from exc
            except OSError as exc:
                raise MonitoringStorageError("could not rebuild root index") from exc

    def find_orphan_documents(
        self,
        monitoring_target_key: str | None = None,
    ) -> list[OrphanDocument]:
        targets = (
            [self._target_dir_from_key(self._safe_target_key(monitoring_target_key))]
            if monitoring_target_key is not None
            else list(self._iter_target_dirs())
        )
        orphans: list[OrphanDocument] = []
        for target_dir in targets:
            state_path = target_dir / "state.json"
            if not state_path.exists():
                continue
            state = self._read_model(
                path=state_path,
                model_type=MonitoredServerState,
                document_type="monitored_server_state",
            )
            refs = self._reachable_document_ids(state)

            for document_type, directory_name, regex, referenced_ids in (
                (
                    "monitoring_candidate",
                    "candidates",
                    _CANDIDATE_RE,
                    refs["candidates"],
                ),
                (
                    "approved_baseline",
                    "approved",
                    _BASELINE_RE,
                    refs["approved"],
                ),
                (
                    "baseline_history",
                    "history",
                    _HISTORY_RE,
                    refs["history"],
                ),
            ):
                directory = target_dir / directory_name
                if not directory.exists():
                    continue
                for path in sorted(directory.glob("*.json")):
                    document_id = path.stem
                    if not regex.fullmatch(document_id):
                        continue
                    if document_id not in referenced_ids:
                        orphans.append(
                            OrphanDocument(
                                document_type=document_type,  # type: ignore[arg-type]
                                document_id=document_id,
                                monitoring_target_key=state.monitoring_target_key,
                            )
                        )

        return sorted(orphans, key=lambda item: (item.monitoring_target_key, item.document_type, item.document_id))

    def _validate_candidate_commit(self, command: CandidateCommit) -> None:
        candidate = command.candidate
        state = command.new_state
        if candidate.monitoring_group_key != state.monitoring_group_key:
            raise MonitoringConflictError("candidate group does not match state")
        if candidate.monitoring_target_key != state.monitoring_target_key:
            raise MonitoringConflictError("candidate target does not match state")
        if candidate.state_version_at_creation != command.expected_state_version:
            raise MonitoringConflictError("candidate state version does not match")
        self._verify_snapshot(candidate.snapshot)

    def _validate_candidate_state_references(self, command: CandidateCommit) -> None:
        candidate_id = command.candidate.candidate_id
        state = command.new_state
        if candidate_id not in state.pending_candidate_ids:
            raise MonitoringConflictError("candidate is not referenced as pending")
        if candidate_id in state.rejected_candidate_ids:
            raise MonitoringConflictError("candidate cannot be rejected in candidate commit")

    def _validate_approval_commit(self, command: ApprovalCommit) -> None:
        approved = command.approved_baseline
        history = command.history_record
        state = command.new_state
        for document in (approved, history):
            if document.monitoring_group_key != state.monitoring_group_key:
                raise MonitoringConflictError("document group does not match state")
            if document.monitoring_target_key != state.monitoring_target_key:
                raise MonitoringConflictError("document target does not match state")
        self._verify_snapshot(approved.snapshot)

    def _validate_approval_state_references(self, command: ApprovalCommit) -> None:
        approved = command.approved_baseline
        history = command.history_record
        state = command.new_state
        if approved.baseline_id != state.current_approved_id:
            raise MonitoringConflictError("approved baseline is not current in state")
        if history.history_id not in state.history_ids:
            raise MonitoringConflictError("approval history is not referenced by state")
        if (
            approved.approved_from_candidate_id is not None
            and approved.approved_from_candidate_id in state.pending_candidate_ids
        ):
            raise MonitoringConflictError("approved candidate is still pending")
        if history.new_approved_id != approved.baseline_id:
            raise MonitoringConflictError("approval history does not reference baseline")
        if (
            history.candidate_id is not None
            and approved.approved_from_candidate_id is not None
            and history.candidate_id != approved.approved_from_candidate_id
        ):
            raise MonitoringConflictError("approval history candidate mismatch")
        if (
            history.previous_approved_id is not None
            and history.previous_approved_id not in state.superseded_baseline_ids
        ):
            raise MonitoringConflictError("previous approved baseline was not superseded")

    def _validate_rejection_commit(self, command: RejectionCommit) -> None:
        history = command.history_record
        state = command.new_state
        if history.monitoring_group_key != state.monitoring_group_key:
            raise MonitoringConflictError("history group does not match state")
        if history.monitoring_target_key != state.monitoring_target_key:
            raise MonitoringConflictError("history target does not match state")

    def _validate_rejection_state_references(
        self,
        command: RejectionCommit,
        old_state: MonitoredServerState,
    ) -> None:
        history = command.history_record
        state = command.new_state
        if history.history_id not in state.history_ids:
            raise MonitoringConflictError("rejection history is not referenced by state")
        if history.candidate_id is None:
            raise MonitoringConflictError("rejection history must reference a candidate")
        if history.candidate_id not in state.rejected_candidate_ids:
            raise MonitoringConflictError("rejected candidate is not rejected in state")
        if history.candidate_id in state.pending_candidate_ids:
            raise MonitoringConflictError("rejected candidate is still pending")
        if state.current_approved_id != old_state.current_approved_id:
            raise MonitoringConflictError("rejection cannot change current approved baseline")

    def _validate_baseline_revocation_commit(
        self,
        command: BaselineRevocationCommit,
    ) -> None:
        history = command.history_record
        state = command.new_state
        if history.monitoring_group_key != state.monitoring_group_key:
            raise MonitoringConflictError("history group does not match state")
        if history.monitoring_target_key != state.monitoring_target_key:
            raise MonitoringConflictError("history target does not match state")

    def _validate_baseline_revocation_state_references(
        self,
        command: BaselineRevocationCommit,
        old_state: MonitoredServerState,
    ) -> None:
        history = command.history_record
        state = command.new_state
        expected_baseline_id = command.expected_current_approved_id
        if old_state.current_approved_id is None:
            raise MonitoringConflictError("current approved baseline is missing")
        if old_state.current_approved_id != expected_baseline_id:
            raise MonitoringConflictError("current approved baseline conflict")
        if state.current_approved_id is not None:
            raise MonitoringConflictError("revoked baseline must clear current approved baseline")
        if expected_baseline_id not in state.superseded_baseline_ids:
            raise MonitoringConflictError("revoked baseline was not superseded")
        if state.pending_candidate_ids != old_state.pending_candidate_ids:
            raise MonitoringConflictError("revocation cannot change pending candidates")
        if state.rejected_candidate_ids != old_state.rejected_candidate_ids:
            raise MonitoringConflictError("revocation cannot change rejected candidates")
        if history.history_id not in state.history_ids:
            raise MonitoringConflictError("revocation history is not referenced by state")
        if history.event_type.value != "baseline_revoked":
            raise MonitoringConflictError("history event is not a baseline revocation")
        if history.candidate_id is not None:
            raise MonitoringConflictError("revocation history cannot reference a candidate")
        if history.baseline_id != expected_baseline_id:
            raise MonitoringConflictError("revocation history baseline mismatch")
        if history.previous_approved_id != expected_baseline_id:
            raise MonitoringConflictError("revocation history previous baseline mismatch")
        if history.new_approved_id is not None:
            raise MonitoringConflictError("revocation history cannot set a new baseline")
        if state.last_scan_status != old_state.last_scan_status:
            raise MonitoringConflictError("revocation cannot change last scan status")
        if state.last_scan_at != old_state.last_scan_at:
            raise MonitoringConflictError("revocation cannot change last scan time")
        if state.last_seen_selection_id != old_state.last_seen_selection_id:
            raise MonitoringConflictError("revocation cannot change last seen selection")

    def _validate_history_deletion_state(
        self,
        command: BaselineHistoryDeletionCommit,
        old_state: MonitoredServerState,
    ) -> None:
        new_state = command.new_state
        if new_state.history_ids:
            raise MonitoringConflictError("history deletion must clear history ids")
        if new_state.current_approved_id is not None:
            raise MonitoringConflictError("history deletion must clear current baseline")
        if new_state.pending_candidate_ids:
            raise MonitoringConflictError("history deletion must clear pending candidates")
        if new_state.rejected_candidate_ids:
            raise MonitoringConflictError("history deletion must clear rejected candidates")
        if new_state.superseded_baseline_ids:
            raise MonitoringConflictError("history deletion must clear superseded baselines")
        if new_state.comparison_status != ComparisonStatus.NOT_COMPARED:
            raise MonitoringConflictError("history deletion must reset comparison status")
        if new_state.verification_status != VerificationStatus.UNVERIFIED:
            raise MonitoringConflictError("history deletion must reset verification status")
        if new_state.last_comparison is not None:
            raise MonitoringConflictError("history deletion must clear comparison result")

        if new_state.baseline_lifecycle != BaselineLifecycleStatus.NONE:
            raise MonitoringConflictError("history deletion has invalid lifecycle")

        old_payload = old_state.model_dump(mode="python")
        new_payload = new_state.model_dump(mode="python")
        for ignored_field in (
            "state_version",
            "current_approved_id",
            "pending_candidate_ids",
            "rejected_candidate_ids",
            "superseded_baseline_ids",
            "history_ids",
            "baseline_lifecycle",
            "comparison_status",
            "verification_status",
            "last_comparison",
            "updated_at",
        ):
            old_payload.pop(ignored_field, None)
            new_payload.pop(ignored_field, None)

        if old_payload != new_payload:
            raise MonitoringConflictError("history deletion cannot change monitoring state")

    def _load_existing_state_for_commit(
        self,
        new_state: MonitoredServerState,
    ) -> MonitoredServerState:
        old_state = self.load_target_state(new_state.monitoring_target_key)
        if old_state is None:
            raise MonitoringNotFoundError("target state was not found")
        return old_state

    def _validate_state_transition(
        self,
        *,
        old_state: MonitoredServerState,
        new_state: MonitoredServerState,
        expected_state_version: int,
    ) -> None:
        if old_state.state_version != expected_state_version:
            raise MonitoringConflictError("state version conflict")
        if old_state.monitoring_group_key != new_state.monitoring_group_key:
            raise MonitoringConflictError("state group cannot change")
        if old_state.monitoring_target_key != new_state.monitoring_target_key:
            raise MonitoringConflictError("state target cannot change")
        if new_state.state_version != old_state.state_version + 1:
            raise MonitoringConflictError("new state version must increase by one")

    def _write_state_commit(self, state: MonitoredServerState) -> None:
        self._write_model_atomic(
            self._target_dir(
                state.monitoring_group_key,
                state.monitoring_target_key,
            )
            / "state.json",
            state,
        )

    def _save_immutable_document(self, path: Path, model: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = self._read_json(path)
            existing_bytes = canonical_json_bytes(existing)
            new_bytes = self._model_bytes(model)
            if existing_bytes == new_bytes:
                return
            raise MonitoringConflictError("immutable document already exists")

        self._write_model_atomic(path, model)

    def _delete_history_documents(
        self,
        state: MonitoredServerState,
        history_ids: list[str],
    ) -> list[str]:
        warnings: list[str] = []
        target_dir = self._target_dir(
            state.monitoring_group_key,
            state.monitoring_target_key,
        )
        for history_id in history_ids:
            safe_history_id = self._safe_history_id(history_id)
            path = target_dir / "history" / f"{safe_history_id}.json"
            if not path.exists():
                continue
            try:
                path.unlink()
            except OSError:
                if "history_delete_pending" not in warnings:
                    warnings.append("history_delete_pending")

        return warnings

    def _rebuild_indexes_best_effort(self, monitoring_group_key: str) -> list[str]:
        warnings: list[str] = []
        try:
            self.rebuild_group_index(monitoring_group_key)
        except MonitoringStorageError:
            warnings.append("index_rebuild_pending")
        try:
            self.rebuild_root_index()
        except MonitoringStorageError:
            if "index_rebuild_pending" not in warnings:
                warnings.append("index_rebuild_pending")
        return warnings

    def _reachable_document_ids(
        self,
        state: MonitoredServerState,
    ) -> dict[str, set[str]]:
        candidate_ids = set(state.pending_candidate_ids) | set(state.rejected_candidate_ids)
        approved_ids = set(state.superseded_baseline_ids)
        if state.current_approved_id is not None:
            approved_ids.add(state.current_approved_id)
        history_ids = set(state.history_ids)

        for history_id in state.history_ids:
            try:
                history = self.load_history_record(
                    history_id,
                    monitoring_target_key=state.monitoring_target_key,
                )
            except MonitoringStorageError:
                continue
            if history.candidate_id is not None:
                candidate_ids.add(history.candidate_id)
            for baseline_id in (
                history.baseline_id,
                history.previous_approved_id,
                history.new_approved_id,
            ):
                if baseline_id is not None:
                    approved_ids.add(baseline_id)

        return {
            "candidates": candidate_ids,
            "approved": approved_ids,
            "history": history_ids,
        }

    def _verify_snapshot(self, snapshot: ToolSnapshot) -> None:
        if snapshot.tool_count != len(snapshot.tools):
            raise MonitoringIntegrityError("snapshot tool count mismatch")
        keys = [tool.tool_key for tool in snapshot.tools]
        if len(keys) != len(set(keys)):
            raise MonitoringIntegrityError("duplicate tool key")
        for tool in snapshot.tools:
            if tool.normalization_version != snapshot.normalization_version:
                raise MonitoringIntegrityError("tool normalization version mismatch")
            self._verify_tool_hash(tool)

        sorted_tools = sorted(snapshot.tools, key=lambda item: item.tool_key)
        payload = {
            "version": snapshot.normalization_version,
            "tools": [
                {
                    "tool_key": tool.tool_key,
                    "tool_hash": tool.tool_hash,
                }
                for tool in sorted_tools
            ],
        }
        expected_hash = calculate_sha256(canonical_json_bytes(payload))
        if expected_hash != snapshot.snapshot_hash:
            raise MonitoringIntegrityError("snapshot hash mismatch")
        if snapshot.snapshot_id != f"snap_{snapshot.snapshot_hash[:20]}":
            raise MonitoringIntegrityError("snapshot id mismatch")

    def _verify_tool_hash(self, tool: NormalizedToolMetadata) -> None:
        payload = {
            "normalization_version": tool.normalization_version,
            "tool_key": tool.tool_key,
            "server_name": tool.server_name,
            "tool_name": tool.tool_name,
            "fields": tool.fields.to_hash_payload(),
        }
        expected_hash = calculate_sha256(canonical_json_bytes(payload))
        if expected_hash != tool.tool_hash:
            raise MonitoringIntegrityError("tool hash mismatch")

    def _read_model(
        self,
        *,
        path: Path,
        model_type: type,
        document_type: str,
    ):
        data = self._read_json(path)
        if not isinstance(data, dict):
            raise MonitoringSchemaError("stored document must be a JSON object")
        if data.get("schema_version") != MONITORING_STORAGE_SCHEMA_VERSION:
            raise MonitoringSchemaError("unsupported monitoring schema version")
        if data.get("document_type") != document_type:
            raise MonitoringSchemaError("unexpected monitoring document type")
        try:
            return model_type.model_validate(data)
        except ValidationError as exc:
            raise MonitoringSchemaError("stored monitoring document is invalid") from exc

    def _read_json(self, path: Path) -> object:
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text)
        except FileNotFoundError as exc:
            raise MonitoringNotFoundError("monitoring document was not found") from exc
        except json.JSONDecodeError as exc:
            raise MonitoringSchemaError("stored monitoring document is not valid JSON") from exc
        except OSError as exc:
            raise MonitoringStorageError("could not read monitoring document") from exc

    def _write_model_atomic(self, path: Path, model: object) -> None:
        try:
            data = model.model_dump(mode="json")  # type: ignore[attr-defined]
            text = json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
        except (TypeError, ValueError, PydanticSerializationError) as exc:
            raise MonitoringStorageError(
                "could not serialize monitoring document"
            ) from exc

        self._write_text_atomic(path, f"{text}\n")

    def _write_text_atomic(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            self._replace(temp_path, path)
        except OSError as exc:
            raise MonitoringStorageError("could not write monitoring document") from exc
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass

        try:
            self._fsync_directory(path.parent)
        except OSError:
            pass

    def _replace(self, source: Path, target: Path) -> None:
        os.replace(source, target)

    def _fsync_directory(self, directory: Path) -> None:
        if os.name == "nt":
            return
        try:
            fd = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            try:
                os.fsync(fd)
            except OSError:
                return
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

    def _model_bytes(self, model: object) -> bytes:
        data = model.model_dump(mode="json")  # type: ignore[attr-defined]
        return canonical_json_bytes(data)

    def _validate_document_id(self, actual: str, expected: str) -> None:
        if actual != expected:
            raise MonitoringIntegrityError("document id does not match file name")

    def _validate_document_target(
        self,
        document: object,
        monitoring_target_key: str | None,
    ) -> None:
        if monitoring_target_key is None:
            return
        target_key = self._safe_target_key(monitoring_target_key)
        if getattr(document, "monitoring_target_key") != target_key:
            raise MonitoringIntegrityError("document target does not match request")

    def _validate_document_location(self, document: object, path: Path) -> None:
        group_key, target_key = self._group_target_from_path(path)
        if getattr(document, "monitoring_group_key") != group_key:
            raise MonitoringIntegrityError("document group does not match path")
        if getattr(document, "monitoring_target_key") != target_key:
            raise MonitoringIntegrityError("document target does not match path")

    def _group_target_from_path(self, path: Path) -> tuple[str, str]:
        try:
            relative_path = path.resolve(strict=False).relative_to(
                self.root.resolve(strict=False)
            )
        except ValueError as exc:
            raise MonitoringStorageError("monitoring path escaped storage root") from exc

        parts = relative_path.parts
        if len(parts) < 4 or parts[0] != "groups" or parts[2] != "targets":
            raise MonitoringStorageError("unexpected monitoring document path")

        return self._safe_group_key(parts[1]), self._safe_target_key(parts[3])

    def _find_document_path(
        self,
        *,
        document_id: str,
        directory_name: str,
        suffix: str,
        monitoring_target_key: str | None,
    ) -> Path:
        if monitoring_target_key is not None:
            target_dir = self._target_dir_from_key(
                self._safe_target_key(monitoring_target_key)
            )
            path = target_dir / directory_name / f"{document_id}{suffix}"
            if not path.exists():
                raise MonitoringNotFoundError("monitoring document was not found")
            return path

        matches = [
            target_dir / directory_name / f"{document_id}{suffix}"
            for target_dir in self._iter_target_dirs()
            if (target_dir / directory_name / f"{document_id}{suffix}").exists()
        ]
        if not matches:
            raise MonitoringNotFoundError("monitoring document was not found")
        if len(matches) > 1:
            raise MonitoringIntegrityError("monitoring document id is ambiguous")
        return matches[0]

    def _find_target_state_path(self, monitoring_target_key: str) -> Path | None:
        target_key = self._safe_target_key(monitoring_target_key)
        matches: list[Path] = []
        for target_dir in self._iter_target_dirs():
            if target_dir.name != target_key:
                continue
            path = target_dir / "state.json"
            if path.exists():
                matches.append(path)
        if not matches:
            return None
        if len(matches) > 1:
            raise MonitoringIntegrityError("target key is ambiguous")
        return matches[0]

    def _target_dir_from_key(self, monitoring_target_key: str) -> Path:
        target_key = self._safe_target_key(monitoring_target_key)
        matches = [
            target_dir
            for target_dir in self._iter_target_dirs()
            if target_dir.name == target_key
        ]
        if not matches:
            raise MonitoringNotFoundError("target state was not found")
        if len(matches) > 1:
            raise MonitoringIntegrityError("target key is ambiguous")
        return matches[0]

    def _iter_group_state_paths(self, monitoring_group_key: str) -> list[Path]:
        group_dir = self._group_dir(monitoring_group_key)
        targets_dir = group_dir / "targets"
        if not targets_dir.exists():
            return []
        return [
            path / "state.json"
            for path in sorted(targets_dir.iterdir())
            if path.is_dir()
            and _TARGET_RE.fullmatch(path.name)
            and (path / "state.json").exists()
        ]

    def _iter_target_dirs(self) -> list[Path]:
        groups_dir = self._groups_dir()
        if not groups_dir.exists():
            return []
        target_dirs: list[Path] = []
        for group_dir in sorted(groups_dir.iterdir()):
            if not group_dir.is_dir() or not _GROUP_RE.fullmatch(group_dir.name):
                continue
            targets_dir = group_dir / "targets"
            if not targets_dir.exists():
                continue
            for target_dir in sorted(targets_dir.iterdir()):
                if target_dir.is_dir() and _TARGET_RE.fullmatch(target_dir.name):
                    target_dirs.append(target_dir)
        return target_dirs

    def _ensure_target_dirs(
        self,
        monitoring_group_key: str,
        monitoring_target_key: str,
    ) -> None:
        target_dir = self._target_dir(monitoring_group_key, monitoring_target_key)
        for directory in (
            target_dir,
            target_dir / "approved",
            target_dir / "candidates",
            target_dir / "history",
            target_dir / "quarantine",
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _candidate_path(self, candidate: MonitoringCandidate) -> Path:
        self._ensure_target_dirs(
            candidate.monitoring_group_key,
            candidate.monitoring_target_key,
        )
        return (
            self._target_dir(
                candidate.monitoring_group_key,
                candidate.monitoring_target_key,
            )
            / "candidates"
            / f"{candidate.candidate_id}.json"
        )

    def _approved_path(self, approved: ApprovedBaseline) -> Path:
        self._ensure_target_dirs(
            approved.monitoring_group_key,
            approved.monitoring_target_key,
        )
        return (
            self._target_dir(
                approved.monitoring_group_key,
                approved.monitoring_target_key,
            )
            / "approved"
            / f"{approved.baseline_id}.json"
        )

    def _history_path(self, history: BaselineHistoryRecord) -> Path:
        self._ensure_target_dirs(
            history.monitoring_group_key,
            history.monitoring_target_key,
        )
        return (
            self._target_dir(
                history.monitoring_group_key,
                history.monitoring_target_key,
            )
            / "history"
            / f"{history.history_id}.json"
        )

    def _target_dir(
        self,
        monitoring_group_key: str,
        monitoring_target_key: str,
    ) -> Path:
        group_key = self._safe_group_key(monitoring_group_key)
        target_key = self._safe_target_key(monitoring_target_key)
        return self._safe_child(
            self._group_dir(group_key) / "targets",
            target_key,
        )

    def _group_dir(self, monitoring_group_key: str) -> Path:
        group_key = self._safe_group_key(monitoring_group_key)
        return self._safe_child(self._groups_dir(), group_key)

    def _groups_dir(self) -> Path:
        return self.root / "groups"

    def _root_index_path(self) -> Path:
        return self.root / "index.json"

    def _group_index_path(self, monitoring_group_key: str) -> Path:
        return self._group_dir(monitoring_group_key) / "index.json"

    def _safe_child(self, parent: Path, child: str) -> Path:
        if (
            "\x00" in child
            or "/" in child
            or "\\" in child
            or child in {"", ".", ".."}
            or Path(child).is_absolute()
        ):
            raise MonitoringStorageError("unsafe monitoring document id")
        path = (parent / child).resolve(strict=False)
        root = self.root.resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise MonitoringStorageError("unsafe monitoring path") from exc
        return path

    def _safe_group_key(self, value: str) -> str:
        if not _GROUP_RE.fullmatch(value):
            raise MonitoringStorageError("invalid monitoring group key")
        return value

    def _safe_target_key(self, value: str) -> str:
        if not _TARGET_RE.fullmatch(value):
            raise MonitoringStorageError("invalid monitoring target key")
        return value

    def _safe_candidate_id(self, value: str) -> str:
        if not _CANDIDATE_RE.fullmatch(value):
            raise MonitoringStorageError("invalid candidate id")
        return value

    def _safe_baseline_id(self, value: str) -> str:
        if not _BASELINE_RE.fullmatch(value):
            raise MonitoringStorageError("invalid baseline id")
        return value

    def _safe_history_id(self, value: str) -> str:
        if not _HISTORY_RE.fullmatch(value):
            raise MonitoringStorageError("invalid history id")
        return value

    @classmethod
    def _lock_for_target(cls, target_key: str) -> threading.RLock:
        with cls._registry_lock:
            return cls._target_locks.setdefault(target_key, threading.RLock())

    @classmethod
    def _lock_for_group(cls, group_key: str) -> threading.RLock:
        with cls._registry_lock:
            return cls._group_locks.setdefault(group_key, threading.RLock())


def get_default_monitoring_root(
    *,
    platform_name: str | None = None,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    env = environ if environ is not None else os.environ
    platform_value = platform_name if platform_name is not None else sys.platform
    home_path = home if home is not None else Path.home()

    configured = env.get("AUDITGUARD_MCP_MONITORING_DIR")
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            raise MonitoringStorageError("monitoring root must be an absolute path")
        return configured_path.resolve(strict=False)

    if platform_value.startswith("win"):
        local_app_data = env.get("LOCALAPPDATA")
        if local_app_data:
            return (
                Path(local_app_data).expanduser().resolve(strict=False)
                / "AuditGuard"
                / "mcp-monitoring"
            )
    elif platform_value == "darwin":
        return (
            home_path.expanduser().resolve(strict=False)
            / "Library"
            / "Application Support"
            / "AuditGuard"
            / "mcp-monitoring"
        )
    else:
        xdg_data_home = env.get("XDG_DATA_HOME")
        if xdg_data_home:
            xdg_path = Path(xdg_data_home).expanduser()
            if xdg_path.is_absolute():
                return (
                    xdg_path.resolve(strict=False)
                    / "auditguard"
                    / "mcp-monitoring"
                )
        return (
            home_path.expanduser().resolve(strict=False)
            / ".local"
            / "share"
            / "auditguard"
            / "mcp-monitoring"
        )

    return (
        home_path.expanduser().resolve(strict=False)
        / ".auditguard"
        / "mcp-monitoring"
    )
