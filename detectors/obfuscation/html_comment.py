from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from core.models import Finding, ToolMetadata
from detectors.obfuscation.common import (
    excerpt,
    iter_spec_metadata_text,
    json_evidence,
    make_finding,
)
from detectors.obfuscation.derived_text import DerivedMetadataText


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
        "도구 메타데이터의 IE 조건부 주석",
        "MCP 도구 메타데이터는 사람이 읽을 수 있는 기능 설명을 제공하는 용도입니다. IE 조건부 주석 안에 실제 설명과 다른 지시문이 숨겨져 있는지 확인하세요. 실제 기능 설명과 무관한 주석이라면 제거하거나 명확한 설명으로 수정하세요.",
    ),
    (
        "html_comment",
        HTML_COMMENT_RE,
        "obfuscation.html_comment",
        "mcp03-html-comment",
        "도구 메타데이터의 HTML 주석",
        "MCP 도구 메타데이터는 사람이 읽을 수 있는 기능 설명을 제공하는 용도입니다. HTML 주석 안에 실제 설명과 다른 지시문이 숨겨져 있는지 확인하세요. 실제 기능 설명과 무관한 주석이라면 제거하거나 명확한 설명으로 수정하세요.",
    ),
    (
        "css_comment",
        CSS_COMMENT_RE,
        "obfuscation.css_comment",
        "mcp03-css-comment",
        "도구 메타데이터의 CSS 주석",
        "MCP 도구 메타데이터는 사람이 읽을 수 있는 기능 설명을 제공하는 용도입니다. CSS 주석 안에 실제 설명과 다른 지시문이 숨겨져 있는지 확인하세요. 실제 기능 설명과 무관한 주석이라면 제거하거나 명확한 설명으로 수정하세요.",
    ),
    (
        "script_tag",
        SCRIPT_TAG_RE,
        "obfuscation.script_tag",
        "mcp03-script-tag",
        "도구 메타데이터의 script 태그",
        "MCP 도구 메타데이터는 사람이 읽을 수 있는 기능 설명을 제공하는 용도입니다. script 태그 안에 실제 설명과 다른 지시문이나 실행성 내용이 포함되어 있는지 확인하세요. 실제 기능 설명과 무관한 script 태그라면 제거하거나 평문 설명으로 수정하세요.",
    ),
)


@dataclass(frozen=True)
class MarkupHiddenText:
    markup_type: str
    category: str
    prefix: str
    title: str
    recommendation: str
    hidden_text: str
    full_match: str
    span: tuple[int, int]


class HtmlCommentDetector:
    name = "html_comment"

    def detect(self, tool: ToolMetadata) -> list[Finding]:
        # metadata의 숨겨진 마크업 본문을 추출하되, MCP03 의도 판정은 별도 detector에 맡깁니다.
        findings: list[Finding] = []

        for field in iter_spec_metadata_text(tool):
            for hidden in find_markup_hidden_texts(field.value):
                evidence = json_evidence(
                    {
                        "markup_type": hidden.markup_type,
                        "hidden_text_excerpt": excerpt(hidden.hidden_text),
                        "full_match_excerpt": excerpt(hidden.full_match),
                    }
                )
                findings.append(
                    make_finding(
                        prefix=hidden.prefix,
                        category=hidden.category,
                        severity="medium",
                        confidence="medium",
                        title=hidden.title,
                        tool=tool,
                        location=field.location,
                        evidence=evidence,
                        recommendation=hidden.recommendation,
                        fingerprint_parts=(hidden.markup_type, hidden.hidden_text),
                    )
                )

        return findings


def derive_markup_hidden_texts(tool: ToolMetadata) -> list[DerivedMetadataText]:
    derived: list[DerivedMetadataText] = []

    for field in iter_spec_metadata_text(tool):
        for hidden in find_markup_hidden_texts(field.value):
            if not hidden.hidden_text:
                continue

            derived.append(
                DerivedMetadataText(
                    value=hidden.hidden_text,
                    source_location=field.location,
                    derived_location=f"{field.location}|hidden:{hidden.markup_type}",
                    transform=f"hidden:{hidden.markup_type}",
                    transformation_chain=(f"hidden:{hidden.markup_type}",),
                    original_excerpt=excerpt(hidden.full_match),
                    decode_confidence="high",
                )
            )

    return derived


@lru_cache(maxsize=2048)
def find_markup_hidden_texts(text: str) -> tuple[MarkupHiddenText, ...]:
    if not _has_markup_signature(text):
        return ()

    hidden_texts: list[MarkupHiddenText] = []
    seen_spans: set[tuple[int, int]] = set()

    for markup_type, pattern, category, prefix, title, recommendation in MARKUP_PATTERNS:
        for match in pattern.finditer(text):
            if match.span() in seen_spans:
                continue
            seen_spans.add(match.span())

            hidden_texts.append(
                MarkupHiddenText(
                    markup_type=markup_type,
                    category=category,
                    prefix=prefix,
                    title=title,
                    recommendation=recommendation,
                    hidden_text=match.group(1).strip(),
                    full_match=match.group(0),
                    span=match.span(),
                )
            )

    return tuple(hidden_texts)


def _has_markup_signature(text: str) -> bool:
    lowered = text.lower()
    return "<!--" in text or "/*" in text or "<script" in lowered
