from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from detectors.text_matching import (
    PreparedText,
    keyword_matches_prepared,
    prepare_text_for_match,
    regex_trigger_matches_prepared,
)


DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "tool_poisoning.yaml"
MAX_REGEX_TEXT_CHARS = 4096


@dataclass(frozen=True)
class RuleMatch:
    rule: dict[str, Any]
    pattern: str
    evidence: str
    match_type: str

    @property
    def rule_id(self) -> str:
        return str(self.rule.get("id", "tool_poisoning"))

    @property
    def category(self) -> str:
        return str(self.rule.get("category", "hidden_instruction"))

    @property
    def severity(self) -> str:
        return str(self.rule.get("severity", "medium"))

    @property
    def confidence(self) -> str:
        return str(self.rule.get("confidence", "medium"))


def load_rules(path: str | Path | None = None, category: str | None = None) -> list[dict[str, Any]]:
    rules_path = str(Path(path) if path else DEFAULT_RULES_PATH)
    rules = _load_rules_cached(rules_path)

    if category is not None:
        rules = tuple(rule for rule in rules if rule.get("category") == category)

    return [_copy_rule(rule) for rule in rules]


def find_rule_matches(
    *,
    text: str,
    rules: list[dict[str, Any]],
) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    prepared_text = prepare_text_for_match(text)

    for rule in rules:
        match = match_rule(text=text, prepared_text=prepared_text, rule=rule)
        if match is not None:
            matches.append(match)

    return matches


def match_rule(
    *,
    text: str,
    rule: dict[str, Any],
    prepared_text: PreparedText | None = None,
) -> RuleMatch | None:
    match_type = str(rule.get("type", "keyword"))
    compiled_patterns = list(rule.get("_compiled_patterns", []))

    for index, pattern in enumerate(rule.get("patterns", [])):
        pattern_text = str(pattern)
        evidence = match_pattern(
            text=text,
            pattern=pattern_text,
            match_type=match_type,
            triggers=rule.get("triggers", []),
            prepared_text=prepared_text,
            compiled_pattern=(
                compiled_patterns[index]
                if match_type == "regex" and index < len(compiled_patterns)
                else None
            ),
        )
        if evidence is None:
            continue

        return RuleMatch(
            rule=rule,
            pattern=pattern_text,
            evidence=evidence,
            match_type=match_type,
        )

    return None


def match_pattern(
    *,
    text: str,
    pattern: str,
    match_type: str,
    triggers: list[str] | tuple[str, ...] | None = None,
    prepared_text: PreparedText | None = None,
    compiled_pattern: re.Pattern[str] | None = None,
) -> str | None:
    if match_type == "regex":
        active_triggers = list(triggers or [])
        active_prepared = prepared_text or prepare_text_for_match(text)
        if active_triggers and not regex_trigger_matches_prepared(active_prepared, active_triggers):
            return None

        match_text = text[:MAX_REGEX_TEXT_CHARS]
        match = (
            compiled_pattern.search(match_text)
            if compiled_pattern is not None
            else re.search(pattern, match_text, flags=re.IGNORECASE)
        )
        return match.group(0) if match else None

    active_prepared = prepared_text or prepare_text_for_match(text)
    if keyword_matches_prepared(active_prepared, pattern):
        return pattern

    return None


@lru_cache(maxsize=None)
def _load_rules_cached(rules_path: str) -> tuple[dict[str, Any], ...]:
    with Path(rules_path).open("r", encoding="utf-8") as rule_file:
        data = yaml.safe_load(rule_file) or {}

    return tuple(_copy_rule(rule) for rule in data.get("rules", []))


def _copy_rule(rule: dict[str, Any]) -> dict[str, Any]:
    copied = dict(rule)

    if "patterns" in copied:
        copied["patterns"] = list(copied["patterns"])
        if copied.get("type", "keyword") == "regex":
            if "_compiled_patterns" in copied:
                copied["_compiled_patterns"] = list(copied["_compiled_patterns"])
            else:
                copied["_compiled_patterns"] = [
                    re.compile(str(pattern), flags=re.IGNORECASE)
                    for pattern in copied["patterns"]
                ]
    if "triggers" in copied:
        copied["triggers"] = list(copied["triggers"])

    return copied
