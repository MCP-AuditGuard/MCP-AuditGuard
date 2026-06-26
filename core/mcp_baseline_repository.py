from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.mcp_monitoring_models import (
    ApprovedBaseline,
    BaselineHistoryRecord,
    MonitoringCandidate,
    MonitoringGroupIndex,
    MonitoringRootIndex,
    MonitoredServerState,
    OrphanDocument,
    RepositoryCommitResult,
)


class MonitoringStorageError(Exception):
    """Base error for MCP monitoring repository failures."""


class MonitoringSchemaError(MonitoringStorageError):
    """Raised when a stored monitoring document has an unsupported schema."""


class MonitoringConflictError(MonitoringStorageError):
    """Raised when a repository commit conflicts with current state."""


class MonitoringIntegrityError(MonitoringStorageError):
    """Raised when stored monitoring document integrity checks fail."""


class MonitoringNotFoundError(MonitoringStorageError):
    """Raised when a referenced monitoring document cannot be found."""


@dataclass(frozen=True, slots=True)
class CandidateCommit:
    expected_state_version: int
    candidate: MonitoringCandidate
    new_state: MonitoredServerState


@dataclass(frozen=True, slots=True)
class ApprovalCommit:
    expected_state_version: int
    approved_baseline: ApprovedBaseline
    history_record: BaselineHistoryRecord
    new_state: MonitoredServerState


@dataclass(frozen=True, slots=True)
class RejectionCommit:
    expected_state_version: int
    history_record: BaselineHistoryRecord
    new_state: MonitoredServerState


@dataclass(frozen=True, slots=True)
class BaselineRevocationCommit:
    expected_state_version: int
    expected_current_approved_id: str
    history_record: BaselineHistoryRecord
    new_state: MonitoredServerState


@dataclass(frozen=True, slots=True)
class BaselineHistoryDeletionCommit:
    expected_state_version: int
    new_state: MonitoredServerState


@dataclass(frozen=True, slots=True)
class StateCommit:
    expected_state_version: int
    new_state: MonitoredServerState


class McpBaselineRepository(ABC):
    """Repository boundary for MCP monitoring baseline storage."""

    @abstractmethod
    def load_target_state(
        self,
        monitoring_target_key: str,
    ) -> MonitoredServerState | None:
        raise NotImplementedError

    @abstractmethod
    def save_initial_target_state(
        self,
        state: MonitoredServerState,
    ) -> MonitoredServerState:
        raise NotImplementedError

    @abstractmethod
    def load_candidate(
        self,
        candidate_id: str,
        monitoring_target_key: str | None = None,
    ) -> MonitoringCandidate:
        raise NotImplementedError

    @abstractmethod
    def load_approved_baseline(
        self,
        baseline_id: str,
        monitoring_target_key: str | None = None,
    ) -> ApprovedBaseline:
        raise NotImplementedError

    @abstractmethod
    def load_history_record(
        self,
        history_id: str,
        monitoring_target_key: str | None = None,
    ) -> BaselineHistoryRecord:
        raise NotImplementedError

    @abstractmethod
    def commit_candidate(
        self,
        command: CandidateCommit,
    ) -> RepositoryCommitResult:
        raise NotImplementedError

    @abstractmethod
    def commit_approval(
        self,
        command: ApprovalCommit,
    ) -> RepositoryCommitResult:
        raise NotImplementedError

    @abstractmethod
    def commit_rejection(
        self,
        command: RejectionCommit,
    ) -> RepositoryCommitResult:
        raise NotImplementedError

    @abstractmethod
    def commit_baseline_revocation(
        self,
        command: BaselineRevocationCommit,
    ) -> RepositoryCommitResult:
        raise NotImplementedError

    @abstractmethod
    def commit_history_deletion(
        self,
        command: BaselineHistoryDeletionCommit,
    ) -> RepositoryCommitResult:
        raise NotImplementedError

    @abstractmethod
    def commit_state(
        self,
        command: StateCommit,
    ) -> RepositoryCommitResult:
        raise NotImplementedError

    @abstractmethod
    def list_group_targets(
        self,
        monitoring_group_key: str,
    ) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def list_target_history(
        self,
        monitoring_target_key: str,
    ) -> list[BaselineHistoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def rebuild_group_index(
        self,
        monitoring_group_key: str,
    ) -> MonitoringGroupIndex:
        raise NotImplementedError

    @abstractmethod
    def rebuild_root_index(self) -> MonitoringRootIndex:
        raise NotImplementedError

    @abstractmethod
    def find_orphan_documents(
        self,
        monitoring_target_key: str | None = None,
    ) -> list[OrphanDocument]:
        raise NotImplementedError
