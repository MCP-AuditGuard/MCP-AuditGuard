from __future__ import annotations

import re

from collections.abc import Sequence

from core.dynamic_scan_models import (
    ClaudePermissionRule,
    HostToolPolicy,
    McpProduct,
    PermissionEffect,
    PolicySourceCoverage,
    ToolActivationAssessment,
    ToolActivationStatus,
)
from core.models import ToolMetadata


def evaluate_tool_activation(
    *,
    tool: ToolMetadata,
    policy: HostToolPolicy,
) -> ToolActivationAssessment:
    """Evaluate host policy without filtering or mutating tool metadata."""
    if policy.product == McpProduct.CODEX:
        return _evaluate_codex_tool(tool=tool, policy=policy)

    return _evaluate_claude_tool(tool=tool, policy=policy)


def evaluate_tool_activations(
    *,
    tools: Sequence[ToolMetadata],
    policy: HostToolPolicy,
) -> list[ToolActivationAssessment]:
    """Return one assessment per input tool in the original order."""
    return [
        evaluate_tool_activation(tool=tool, policy=policy)
        for tool in tools
    ]


def _evaluate_codex_tool(
    *,
    tool: ToolMetadata,
    policy: HostToolPolicy,
) -> ToolActivationAssessment:
    if tool.tool_name in policy.codex_disabled_tools:
        return _assessment(
            tool=tool,
            policy=policy,
            status=ToolActivationStatus.DISABLED,
            safe_basis_code="codex_disabled_match",
        )

    if _policy_is_invalid(policy):
        return _unknown_assessment(tool=tool, policy=policy)

    if (
        policy.codex_enabled_tools_configured
        and tool.tool_name not in policy.codex_enabled_tools
    ):
        return _assessment(
            tool=tool,
            policy=policy,
            status=ToolActivationStatus.DISABLED,
            safe_basis_code="codex_enabled_allow_miss",
        )

    if policy.source_coverage != PolicySourceCoverage.COMPLETE:
        return _unknown_assessment(tool=tool, policy=policy)

    return _assessment(
        tool=tool,
        policy=policy,
        status=ToolActivationStatus.ENABLED,
        safe_basis_code=(
            "codex_enabled_allow_match"
            if policy.codex_enabled_tools_configured
            else "codex_policy_complete"
        ),
    )


def _evaluate_claude_tool(
    *,
    tool: ToolMetadata,
    policy: HostToolPolicy,
) -> ToolActivationAssessment:
    matching_rules = {
        effect: _matching_claude_rules(
            tool=tool,
            rules=policy.claude_permission_rules,
            effect=effect,
        )
        for effect in PermissionEffect
    }

    deny_rules = matching_rules[PermissionEffect.DENY]
    if deny_rules:
        return _assessment(
            tool=tool,
            policy=policy,
            status=ToolActivationStatus.DISABLED,
            safe_basis_code="claude_deny_match",
            source_labels=_source_labels(deny_rules),
        )

    ask_rules = matching_rules[PermissionEffect.ASK]
    allow_rules = matching_rules[PermissionEffect.ALLOW]

    if _policy_is_invalid(policy):
        return _unknown_assessment(
            tool=tool,
            policy=policy,
            source_labels=_source_labels(ask_rules or allow_rules),
        )

    if ask_rules:
        if policy.source_coverage != PolicySourceCoverage.COMPLETE:
            return _unknown_assessment(
                tool=tool,
                policy=policy,
                source_labels=_source_labels(ask_rules),
            )
        return _assessment(
            tool=tool,
            policy=policy,
            status=ToolActivationStatus.ENABLED,
            safe_basis_code="claude_ask_match",
            source_labels=_source_labels(ask_rules),
        )

    if allow_rules:
        if policy.source_coverage != PolicySourceCoverage.COMPLETE:
            return _unknown_assessment(
                tool=tool,
                policy=policy,
                source_labels=_source_labels(allow_rules),
            )
        return _assessment(
            tool=tool,
            policy=policy,
            status=ToolActivationStatus.ENABLED,
            safe_basis_code="claude_allow_match",
            source_labels=_source_labels(allow_rules),
        )

    if policy.source_coverage != PolicySourceCoverage.COMPLETE:
        return _unknown_assessment(tool=tool, policy=policy)

    return _assessment(
        tool=tool,
        policy=policy,
        status=ToolActivationStatus.ENABLED,
        safe_basis_code="claude_policy_complete",
    )


def _matching_claude_rules(
    *,
    tool: ToolMetadata,
    rules: Sequence[ClaudePermissionRule],
    effect: PermissionEffect,
) -> list[ClaudePermissionRule]:
    return [
        rule
        for rule in rules
        if rule.effect == effect
        and _claude_rule_matches(
            rule.tool_name_pattern,
            server_name=tool.server_name,
            tool_name=tool.tool_name,
            effect=effect,
        )
    ]


def _claude_rule_matches(
    pattern: str,
    *,
    server_name: str,
    tool_name: str,
    effect: PermissionEffect,
) -> bool:
    normalized_pattern = pattern.strip()
    canonical_name = f"mcp__{server_name}__{tool_name}"
    server_tool_prefix = f"mcp__{server_name}__"

    if "(" in normalized_pattern or ")" in normalized_pattern:
        return False

    if effect == PermissionEffect.ALLOW:
        if not normalized_pattern.startswith(server_tool_prefix):
            return False

    return _star_pattern_matches(normalized_pattern, canonical_name)


def _star_pattern_matches(pattern: str, value: str) -> bool:
    expression = re.escape(pattern).replace(r"\*", ".*")
    return re.fullmatch(expression, value) is not None


def _policy_is_invalid(policy: HostToolPolicy) -> bool:
    return (
        policy.source_coverage == PolicySourceCoverage.INVALID
        or bool(policy.parse_issues)
    )


def _unknown_assessment(
    *,
    tool: ToolMetadata,
    policy: HostToolPolicy,
    source_labels: list[str] | None = None,
) -> ToolActivationAssessment:
    return _assessment(
        tool=tool,
        policy=policy,
        status=ToolActivationStatus.UNKNOWN,
        safe_basis_code=(
            "policy_coverage_invalid"
            if _policy_is_invalid(policy)
            else "policy_coverage_incomplete"
        ),
        source_labels=source_labels,
    )


def _assessment(
    *,
    tool: ToolMetadata,
    policy: HostToolPolicy,
    status: ToolActivationStatus,
    safe_basis_code: str,
    source_labels: list[str] | None = None,
) -> ToolActivationAssessment:
    return ToolActivationAssessment(
        tool_name=tool.tool_name,
        status=status,
        product=policy.product,
        policy_source_labels=source_labels or [],
        safe_basis_code=safe_basis_code,
    )


def _source_labels(
    rules: Sequence[ClaudePermissionRule],
) -> list[str]:
    return list(dict.fromkeys(rule.source_label for rule in rules))
