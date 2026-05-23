from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["critical", "high", "medium", "low", "info"]
Confidence = Literal["high", "medium", "low"]


class ToolMetadata(BaseModel):
    server_name: str
    tool_name: str
    title: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    metadata_hash: str = ""
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Finding(BaseModel):
    id: str
    category: str
    owasp: str
    severity: Severity
    confidence: Confidence
    title: str
    tool_name: str | None = None
    target: str
    location: str
    evidence: str
    redacted: bool
    recommendation: str
    fingerprint: str
