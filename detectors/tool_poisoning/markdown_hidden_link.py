from __future__ import annotations

import re
from urllib.parse import unquote

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import (
    contains_suspicious_phrase,
    excerpt,
    iter_metadata_text,
    json_evidence,
    make_finding,
)


MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]*)\]\(\s*([^\s)]+)(?:\s+['\"]([^'\"]+)['\"])?\s*\)"
)
DANGEROUS_SCHEMES = ("javascript:", "data:")


class MarkdownHiddenLinkDetector:
    name = "markdown_hidden_link"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        findings: list[Finding] = []

        for field in iter_metadata_text(tool):
            for match in MARKDOWN_LINK_RE.finditer(field.value):
                label, url, title = match.group(1), match.group(2), match.group(3) or ""
                decoded_url = unquote(url)
                suspicious = any(
                    contains_suspicious_phrase(value)
                    for value in (label, url, decoded_url, title)
                    if value
                )
                dangerous_scheme = decoded_url.lower().startswith(DANGEROUS_SCHEMES)

                if not suspicious and not dangerous_scheme:
                    continue

                severity = "high" if suspicious else "medium"
                confidence = "high" if suspicious or dangerous_scheme else "medium"
                evidence = json_evidence(
                    {
                        "label_excerpt": excerpt(label),
                        "url_excerpt": excerpt(url),
                        "decoded_url_excerpt": excerpt(decoded_url),
                        "title_excerpt": excerpt(title),
                        "suspicious_instruction": suspicious,
                        "dangerous_scheme": dangerous_scheme,
                    }
                )

                findings.append(
                    make_finding(
                        prefix="mcp03-md-link",
                        category="tool_poisoning.markdown_hidden_link",
                        severity=severity,
                        confidence=confidence,
                        title="Suspicious Markdown link found in tool metadata",
                        tool=tool,
                        location=field.location,
                        evidence=evidence,
                        recommendation=(
                            "Remove hidden instructions or dangerous URLs from Markdown links "
                            "in MCP tool metadata."
                        ),
                    )
                )

        return findings
