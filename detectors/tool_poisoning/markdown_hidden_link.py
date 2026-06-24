from __future__ import annotations

import re
from urllib.parse import unquote

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import (
    contains_suspicious_phrase,
    excerpt,
    iter_spec_metadata_text,
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

        for field in iter_spec_metadata_text(tool):
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
                        title="도구 메타데이터의 의심스러운 Markdown 링크",
                        tool=tool,
                        location=field.location,
                        evidence=evidence,
                        recommendation=(
                            "MCP 도구 메타데이터의 Markdown 링크는 관련 문서나 리소스를 안내하는 용도입니다. "
                            "링크 라벨, URL, title 속성에 숨겨진 지시문이나 위험한 URL이 포함되어 있는지 확인하세요. "
                            "실제 문서 안내와 무관한 지시나 위험한 링크라면 제거하거나 안전한 링크 설명으로 수정하세요."
                        ),
                        fingerprint_parts=("markdown_link", label, decoded_url, title),
                    )
                )

        return findings
