from __future__ import annotations

import inspect

from core.mcp_baseline_repository import (
    ApprovalCommit,
    CandidateCommit,
    McpBaselineRepository,
    RejectionCommit,
    StateCommit,
)


def test_repository_boundary_is_abstract() -> None:
    assert inspect.isabstract(McpBaselineRepository)


def test_commit_commands_are_immutable_dataclasses() -> None:
    assert CandidateCommit.__dataclass_params__.frozen is True
    assert ApprovalCommit.__dataclass_params__.frozen is True
    assert RejectionCommit.__dataclass_params__.frozen is True
    assert StateCommit.__dataclass_params__.frozen is True
