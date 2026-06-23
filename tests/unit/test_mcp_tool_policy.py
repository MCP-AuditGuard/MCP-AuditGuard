from __future__ import annotations

import pytest

from core.dynamic_scan_models import (
    ClaudePermissionRule,
    DynamicScanIssue,
    DynamicScanStage,
    HostToolPolicy,
    IssueLevel,
    McpProduct,
    PermissionEffect,
    PolicySourceCoverage,
    ToolActivationStatus,
)
from core.mcp_tool_policy import (
    evaluate_tool_activation,
    evaluate_tool_activations,
)
from core.models import ToolMetadata


def make_tool(
    tool_name: str,
    *,
    server_name: str = "docs",
) -> ToolMetadata:
    return ToolMetadata.from_mcp_tool(
        raw_tool={
            "name": tool_name,
            "description": f"{tool_name} description",
            "inputSchema": {"type": "object"},
        },
        server_name=server_name,
        source="mcp:test",
    )


def make_codex_policy(
    *,
    coverage: PolicySourceCoverage = PolicySourceCoverage.COMPLETE,
    enabled_tools_configured: bool = False,
    enabled_tools: list[str] | None = None,
    disabled_tools: list[str] | None = None,
    parse_issues: list[DynamicScanIssue] | None = None,
) -> HostToolPolicy:
    return HostToolPolicy(
        product=McpProduct.CODEX,
        source_coverage=coverage,
        codex_enabled_tools_configured=enabled_tools_configured,
        codex_enabled_tools=enabled_tools or [],
        codex_disabled_tools=disabled_tools or [],
        parse_issues=parse_issues or [],
    )


def make_claude_policy(
    *rules: ClaudePermissionRule,
    coverage: PolicySourceCoverage = PolicySourceCoverage.COMPLETE,
    parse_issues: list[DynamicScanIssue] | None = None,
) -> HostToolPolicy:
    return HostToolPolicy(
        product=McpProduct.CLAUDE,
        source_coverage=coverage,
        claude_permission_rules=list(rules),
        parse_issues=parse_issues or [],
    )


def claude_rule(
    effect: PermissionEffect,
    pattern: str,
    *,
    source_label: str = "Claude project settings",
) -> ClaudePermissionRule:
    return ClaudePermissionRule(
        effect=effect,
        tool_name_pattern=pattern,
        source_label=source_label,
    )


def policy_parse_issue() -> DynamicScanIssue:
    return DynamicScanIssue(
        stage=DynamicScanStage.DISCOVERY,
        code="policy_parse_error",
        level=IssueLevel.WARNING,
        safe_message="A policy source could not be parsed.",
    )


def test_codex_disabled_tools_take_precedence_over_allow_list() -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_codex_policy(
            enabled_tools_configured=True,
            enabled_tools=["search"],
            disabled_tools=["search"],
        ),
    )

    assert assessment.status == ToolActivationStatus.DISABLED
    assert assessment.safe_basis_code == "codex_disabled_match"


@pytest.mark.parametrize(
    ("configured", "enabled_tools", "expected_status", "basis_code"),
    [
        (
            True,
            [],
            ToolActivationStatus.DISABLED,
            "codex_enabled_allow_miss",
        ),
        (
            True,
            ["search"],
            ToolActivationStatus.ENABLED,
            "codex_enabled_allow_match",
        ),
        (
            False,
            [],
            ToolActivationStatus.ENABLED,
            "codex_policy_complete",
        ),
    ],
)
def test_codex_allow_list_presence_changes_the_result(
    configured: bool,
    enabled_tools: list[str],
    expected_status: ToolActivationStatus,
    basis_code: str,
) -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_codex_policy(
            enabled_tools_configured=configured,
            enabled_tools=enabled_tools,
        ),
    )

    assert assessment.status == expected_status
    assert assessment.safe_basis_code == basis_code


def test_codex_allow_miss_remains_explicitly_disabled_with_incomplete_sources(
) -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_codex_policy(
            coverage=PolicySourceCoverage.INCOMPLETE,
            enabled_tools_configured=True,
            enabled_tools=["read"],
        ),
    )

    assert assessment.status == ToolActivationStatus.DISABLED
    assert assessment.safe_basis_code == "codex_enabled_allow_miss"


def test_codex_allow_match_is_unknown_when_upper_sources_are_unchecked() -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_codex_policy(
            coverage=PolicySourceCoverage.INCOMPLETE,
            enabled_tools_configured=True,
            enabled_tools=["search"],
        ),
    )

    assert assessment.status == ToolActivationStatus.UNKNOWN
    assert assessment.safe_basis_code == "policy_coverage_incomplete"


def test_damaged_codex_allow_list_is_not_treated_as_explicitly_empty() -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_codex_policy(
            coverage=PolicySourceCoverage.INVALID,
            enabled_tools_configured=True,
            parse_issues=[policy_parse_issue()],
        ),
    )

    assert assessment.status == ToolActivationStatus.UNKNOWN
    assert assessment.safe_basis_code == "policy_coverage_invalid"


def test_claude_deny_takes_precedence_over_ask_and_allow() -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_claude_policy(
            claude_rule(
                PermissionEffect.ALLOW,
                "mcp__docs__search",
                source_label="Claude user settings",
            ),
            claude_rule(
                PermissionEffect.ASK,
                "mcp__docs__search",
                source_label="Claude project settings",
            ),
            claude_rule(
                PermissionEffect.DENY,
                "mcp__docs__*",
                source_label="Claude local settings",
            ),
        ),
    )

    assert assessment.status == ToolActivationStatus.DISABLED
    assert assessment.safe_basis_code == "claude_deny_match"
    assert assessment.policy_source_labels == ["Claude local settings"]


def test_claude_ask_is_enabled_when_policy_coverage_is_complete() -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("publish"),
        policy=make_claude_policy(
            claude_rule(
                PermissionEffect.ALLOW,
                "mcp__docs__publish",
                source_label="Claude user settings",
            ),
            claude_rule(
                PermissionEffect.ASK,
                "mcp__docs__publish",
                source_label="Claude project settings",
            ),
        ),
    )

    assert assessment.status == ToolActivationStatus.ENABLED
    assert assessment.safe_basis_code == "claude_ask_match"
    assert assessment.policy_source_labels == ["Claude project settings"]


@pytest.mark.parametrize(
    ("effect", "basis_code"),
    [
        (PermissionEffect.ASK, "claude_ask_match"),
        (PermissionEffect.ALLOW, "claude_allow_match"),
    ],
)
def test_claude_ask_and_allow_are_enabled_with_complete_coverage(
    effect: PermissionEffect,
    basis_code: str,
) -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_claude_policy(
            claude_rule(effect, "mcp__docs__search"),
        ),
    )

    assert assessment.status == ToolActivationStatus.ENABLED
    assert assessment.safe_basis_code == basis_code


@pytest.mark.parametrize(
    "effect",
    [PermissionEffect.ASK, PermissionEffect.ALLOW],
)
def test_claude_positive_match_is_unknown_with_unchecked_upper_deny_source(
    effect: PermissionEffect,
) -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_claude_policy(
            claude_rule(effect, "mcp__docs__search"),
            coverage=PolicySourceCoverage.INCOMPLETE,
        ),
    )

    assert assessment.status == ToolActivationStatus.UNKNOWN
    assert assessment.safe_basis_code == "policy_coverage_incomplete"
    assert assessment.policy_source_labels == [
        "Claude project settings"
    ]


def test_claude_global_and_server_tool_globs_match_conservatively() -> None:
    tools = [
        make_tool("search"),
        make_tool("get_issue", server_name="github"),
        make_tool("delete", server_name="other"),
    ]
    policy = make_claude_policy(
        claude_rule(PermissionEffect.DENY, "mcp__other__*"),
        claude_rule(PermissionEffect.ASK, "mcp__github__get_*"),
        claude_rule(PermissionEffect.ALLOW, "mcp__docs__*"),
    )

    assessments = evaluate_tool_activations(tools=tools, policy=policy)

    assert [item.status for item in assessments] == [
        ToolActivationStatus.ENABLED,
        ToolActivationStatus.ENABLED,
        ToolActivationStatus.DISABLED,
    ]
    assert [item.safe_basis_code for item in assessments] == [
        "claude_allow_match",
        "claude_ask_match",
        "claude_deny_match",
    ]


def test_claude_unanchored_allow_glob_does_not_auto_enable_mcp_tools() -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_claude_policy(
            claude_rule(PermissionEffect.ALLOW, "mcp__*"),
            coverage=PolicySourceCoverage.INCOMPLETE,
        ),
    )

    assert assessment.status == ToolActivationStatus.UNKNOWN
    assert assessment.safe_basis_code == "policy_coverage_incomplete"
    assert assessment.policy_source_labels == []


@pytest.mark.parametrize(
    "effect",
    [
        PermissionEffect.DENY,
        PermissionEffect.ASK,
        PermissionEffect.ALLOW,
    ],
)
def test_claude_bare_server_pattern_is_not_a_server_wide_tool_rule(
    effect: PermissionEffect,
) -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_claude_policy(
            claude_rule(effect, "mcp__docs"),
        ),
    )

    assert assessment.status == ToolActivationStatus.ENABLED
    assert assessment.safe_basis_code == "claude_policy_complete"
    assert assessment.policy_source_labels == []


def test_claude_global_deny_is_definitive_with_incomplete_coverage() -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_claude_policy(
            claude_rule(PermissionEffect.DENY, "*"),
            coverage=PolicySourceCoverage.INCOMPLETE,
        ),
    )

    assert assessment.status == ToolActivationStatus.DISABLED
    assert assessment.safe_basis_code == "claude_deny_match"


@pytest.mark.parametrize(
    ("coverage", "expected_status", "basis_code"),
    [
        (
            PolicySourceCoverage.COMPLETE,
            ToolActivationStatus.ENABLED,
            "claude_policy_complete",
        ),
        (
            PolicySourceCoverage.INCOMPLETE,
            ToolActivationStatus.UNKNOWN,
            "policy_coverage_incomplete",
        ),
        (
            PolicySourceCoverage.INVALID,
            ToolActivationStatus.UNKNOWN,
            "policy_coverage_invalid",
        ),
    ],
)
def test_claude_no_matching_rule_depends_on_policy_coverage(
    coverage: PolicySourceCoverage,
    expected_status: ToolActivationStatus,
    basis_code: str,
) -> None:
    assessment = evaluate_tool_activation(
        tool=make_tool("search"),
        policy=make_claude_policy(coverage=coverage),
    )

    assert assessment.status == expected_status
    assert assessment.safe_basis_code == basis_code


def test_assessment_list_preserves_every_tool_without_mutating_metadata() -> None:
    tools = [make_tool("enabled"), make_tool("disabled")]
    before = [tool.model_dump() for tool in tools]
    policy = make_codex_policy(
        enabled_tools_configured=True,
        enabled_tools=["enabled"],
    )

    assessments = evaluate_tool_activations(tools=tools, policy=policy)

    assert [item.tool_name for item in assessments] == [
        "enabled",
        "disabled",
    ]
    assert [item.status for item in assessments] == [
        ToolActivationStatus.ENABLED,
        ToolActivationStatus.DISABLED,
    ]
    assert [tool.model_dump() for tool in tools] == before
    assert len(assessments) == len(tools)
