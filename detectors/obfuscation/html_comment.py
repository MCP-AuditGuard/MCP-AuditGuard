from __future__ import annotations

import re

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import (
    contains_suspicious_phrase,
    excerpt,
    iter_metadata_text,
    json_evidence,
    make_finding,
)


HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)


class HtmlCommentDetector:
    name = "html_comment"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        findings: list[Finding] = []

        for field in iter_metadata_text(tool):
            for match in HTML_COMMENT_RE.finditer(field.value):
                comment = match.group(1).strip()
                suspicious = contains_suspicious_phrase(comment)
                severity = "high" if suspicious else "medium"
                confidence = "high" if suspicious else "medium"

                evidence = json_evidence(
                    {
                        "comment_excerpt": excerpt(comment),
                        "suspicious_instruction": suspicious,
                    }
                )
                findings.append(
                    make_finding(
                        prefix="mcp03-html-comment",
                        category="obfuscation.html_comment",
                        severity=severity,
                        confidence=confidence,
                        title="HTML comment found in tool metadata",
                        tool=tool,
                        location=field.location,
                        evidence=evidence,
                        recommendation=(
                            "Remove HTML comments from MCP tool metadata and review hidden "
                            "comment text for tool poisoning instructions."
                        ),
                    )
                )

        return findings
