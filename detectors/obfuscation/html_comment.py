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


# tool metadata 안에 숨겨진 HTML/CSS/Script 계열 마크업을 찾는 패턴입니다.
HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
CSS_COMMENT_RE = re.compile(r"/\*(.*?)\*/", re.DOTALL)
SCRIPT_TAG_RE = re.compile(
    r"<script\b[^>]*>(.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
IE_CONDITIONAL_COMMENT_RE = re.compile(
    r"<!--\s*\[if\b(.*?)<!\s*\[endif\]\s*-->",
    re.IGNORECASE | re.DOTALL,
)

# 각 마크업 패턴마다 category, finding prefix, 제목, 권고문을 함께 정의합니다.
MARKUP_PATTERNS = (
    (
        "ie_conditional_comment",
        IE_CONDITIONAL_COMMENT_RE,
        "obfuscation.ie_conditional_comment",
        "mcp03-ie-conditional-comment",
        "IE conditional comment found in tool metadata",
        "Remove IE conditional comments from MCP tool metadata and review hidden conditional text.",
    ),
    (
        "html_comment",
        HTML_COMMENT_RE,
        "obfuscation.html_comment",
        "mcp03-html-comment",
        "HTML comment found in tool metadata",
        "Remove HTML comments from MCP tool metadata and review hidden comment text.",
    ),
    (
        "css_comment",
        CSS_COMMENT_RE,
        "obfuscation.css_comment",
        "mcp03-css-comment",
        "CSS comment found in tool metadata",
        "Remove CSS comments from MCP tool metadata and review hidden comment text.",
    ),
    (
        "script_tag",
        SCRIPT_TAG_RE,
        "obfuscation.script_tag",
        "mcp03-script-tag",
        "Script tag found in tool metadata",
        "Remove script tags from MCP tool metadata and keep metadata human-readable.",
    ),
)


class HtmlCommentDetector:
    name = "html_comment"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        # metadata의 숨겨진 마크업 본문을 추출하고, 그 안의 suspicious phrase를 검사합니다.
        findings: list[Finding] = []

        for field in iter_metadata_text(tool):
            seen_spans: set[tuple[int, int]] = set()

            for markup_type, pattern, category, prefix, title, recommendation in MARKUP_PATTERNS:
                for match in pattern.finditer(field.value):
                    if match.span() in seen_spans:
                        continue
                    seen_spans.add(match.span())

                    hidden_text = match.group(1).strip()
                    suspicious = contains_suspicious_phrase(hidden_text)
                    severity = "high" if suspicious else "medium"
                    confidence = "high" if suspicious else "medium"

                    evidence = json_evidence(
                        {
                            "markup_type": markup_type,
                            "hidden_text_excerpt": excerpt(hidden_text),
                            "full_match_excerpt": excerpt(match.group(0)),
                            "suspicious_instruction": suspicious,
                        }
                    )
                    findings.append(
                        make_finding(
                            prefix=prefix,
                            category=category,
                            severity=severity,
                            confidence=confidence,
                            title=title,
                            tool=tool,
                            location=field.location,
                            evidence=evidence,
                            recommendation=recommendation,
                        )
                    )

        return findings
