from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.models import ToolMetadata


DerivedConfidence = Literal["high", "medium", "low"]

MAX_DERIVED_TEXTS_PER_TOOL = 50
MAX_DERIVED_TEXT_CHARS = 4096
MAX_TOTAL_DERIVED_CHARS_PER_TOOL = 20000
MAX_TRANSFORMATION_CHAIN_LENGTH = 4


@dataclass(frozen=True)
class DerivedMetadataText:
    value: str
    source_location: str
    derived_location: str
    transform: str
    transformation_chain: tuple[str, ...]
    original_excerpt: str
    decode_confidence: DerivedConfidence


def collect_obfuscation_derived_texts(tool: ToolMetadata) -> list[DerivedMetadataText]:
    from detectors.obfuscation.encoded_payload import derive_encoded_texts
    from detectors.obfuscation.homoglyph import derive_homoglyph_texts
    from detectors.obfuscation.html_comment import derive_markup_hidden_texts
    from detectors.obfuscation.unicode_obfuscation import derive_unicode_normalized_texts

    candidates: list[DerivedMetadataText] = []
    candidates.extend(derive_encoded_texts(tool))
    candidates.extend(derive_unicode_normalized_texts(tool))
    candidates.extend(derive_markup_hidden_texts(tool))
    candidates.extend(derive_homoglyph_texts(tool))

    return _limit_and_deduplicate(candidates)


def _limit_and_deduplicate(candidates: list[DerivedMetadataText]) -> list[DerivedMetadataText]:
    limited: list[DerivedMetadataText] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    total_chars = 0

    for candidate in candidates:
        if len(limited) >= MAX_DERIVED_TEXTS_PER_TOOL:
            break
        if len(candidate.value) > MAX_DERIVED_TEXT_CHARS:
            continue
        if len(candidate.transformation_chain) > MAX_TRANSFORMATION_CHAIN_LENGTH:
            continue

        key = (
            candidate.source_location,
            candidate.value,
            candidate.transformation_chain,
        )
        if key in seen:
            continue

        if total_chars + len(candidate.value) > MAX_TOTAL_DERIVED_CHARS_PER_TOOL:
            break

        limited.append(candidate)
        seen.add(key)
        total_chars += len(candidate.value)

    return limited
