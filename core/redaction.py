from __future__ import annotations

import re


REDACTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"sk-[A-Za-z0-9_\-]{8,}", "[REDACTED_OPENAI_KEY]"),
    (r"ghp_[A-Za-z0-9_]{16,}", "[REDACTED_GITHUB_TOKEN]"),
    (r"github_pat_[A-Za-z0-9_]{16,}", "[REDACTED_GITHUB_PAT]"),
    (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
    (
        r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?)([^'\"\s,\}]+)",
        r"\1[REDACTED_SECRET]",
    ),
)


def redact_text(text: str) -> str:
    redacted = text
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted
