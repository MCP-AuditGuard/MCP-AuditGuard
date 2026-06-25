from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache


MAX_TOKEN_GAP = 2

LEET_TRANSLATION = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
        "$": "s",
    }
)


@dataclass(frozen=True)
class PreparedText:
    normalized: str
    tokens: tuple[str, ...]


@lru_cache(maxsize=2048)
def prepare_text_for_match(text: str) -> PreparedText:
    normalized_text = _normalize_text(text)
    tokens = tuple(_tokenize_normalized_text(normalized_text))
    return PreparedText(
        normalized="".join(char for char in normalized_text if char.isalnum()),
        tokens=tokens,
    )


def normalize_for_match(text: str) -> str:
    normalized = _normalize_text(text)
    return "".join(char for char in normalized if char.isalnum())


def tokenize_for_match(text: str) -> list[str]:
    normalized = _normalize_text(text)
    return _tokenize_normalized_text(normalized)


def _tokenize_normalized_text(normalized: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []

    for char in normalized:
        if char.isalnum():
            current.append(char)
            continue

        if current:
            tokens.append("".join(current))
            current = []

    if current:
        tokens.append("".join(current))

    return tokens


def keyword_matches(
    text: str,
    keyword: str,
    *,
    max_gap: int = MAX_TOKEN_GAP,
) -> bool:
    return keyword_matches_prepared(
        prepare_text_for_match(text),
        keyword,
        max_gap=max_gap,
    )


def keyword_matches_prepared(
    prepared_text: PreparedText,
    keyword: str,
    *,
    max_gap: int = MAX_TOKEN_GAP,
) -> bool:
    normalized_keyword, keyword_tokens = _keyword_match_parts(keyword)
    if not normalized_keyword:
        return False

    if normalized_keyword in prepared_text.normalized:
        return True

    if len(keyword_tokens) <= 1:
        return False

    return tokens_match_with_gap(
        list(prepared_text.tokens),
        list(keyword_tokens),
        max_gap=max_gap,
    )


def contains_any_keyword(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    return any(keyword_matches(text, keyword) for keyword in keywords)


def tokens_match_with_gap(
    text_tokens: list[str],
    keyword_tokens: list[str],
    *,
    max_gap: int = MAX_TOKEN_GAP,
) -> bool:
    if not text_tokens or not keyword_tokens:
        return False

    for start_index, token in enumerate(text_tokens):
        if token != keyword_tokens[0]:
            continue

        text_index = start_index + 1
        matched_tokens = 1

        while matched_tokens < len(keyword_tokens):
            next_keyword_token = keyword_tokens[matched_tokens]
            search_end = min(len(text_tokens), text_index + max_gap + 1)

            for candidate_index in range(text_index, search_end):
                if text_tokens[candidate_index] == next_keyword_token:
                    text_index = candidate_index + 1
                    matched_tokens += 1
                    break
            else:
                break

        if matched_tokens == len(keyword_tokens):
            return True

    return False


def regex_trigger_matches(text: str, triggers: list[str] | tuple[str, ...]) -> bool:
    return not triggers or contains_any_keyword(text, list(triggers))


def regex_trigger_matches_prepared(
    prepared_text: PreparedText,
    triggers: list[str] | tuple[str, ...],
) -> bool:
    return not triggers or any(
        keyword_matches_prepared(prepared_text, trigger)
        for trigger in triggers
    )


@lru_cache(maxsize=1024)
def _keyword_match_parts(keyword: str) -> tuple[str, tuple[str, ...]]:
    normalized_keyword = normalize_for_match(keyword)
    keyword_tokens = tuple(tokenize_for_match(keyword))
    return normalized_keyword, keyword_tokens


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return normalized.translate(LEET_TRANSLATION)
