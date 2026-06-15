from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from core.models import Confidence, Finding, ToolMetadata


ScanType = Literal["static", "dynamic", "hybrid"]
ScanSourceType = Literal["tools_json", "mcp_server"]


class SeveritySummary(BaseModel):
    """Finding 목록의 severity별 개수."""

    model_config = ConfigDict(extra="forbid")

    critical: int = Field(default=0, ge=0)
    high: int = Field(default=0, ge=0)
    medium: int = Field(default=0, ge=0)
    low: int = Field(default=0, ge=0)
    info: int = Field(default=0, ge=0)

    @computed_field
    @property
    def total(self) -> int:
        return (
            self.critical
            + self.high
            + self.medium
            + self.low
            + self.info
        )

    @classmethod
    def from_findings(
        cls,
        findings: list[Finding],
    ) -> SeveritySummary:
        counts = Counter(
            finding.severity for finding in findings
        )

        return cls(
            critical=counts["critical"],
            high=counts["high"],
            medium=counts["medium"],
            low=counts["low"],
            info=counts["info"],
        )


class ScanSummary(BaseModel):
    """웹이나 다른 UI에서 사용할 스캔 요약."""

    model_config = ConfigDict(extra="forbid")

    tool_count: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    affected_target_count: int = Field(ge=0)

    by_severity: SeveritySummary
    by_confidence: dict[Confidence, int] = Field(
        default_factory=dict
    )
    by_category: dict[str, int] = Field(
        default_factory=dict
    )

    @classmethod
    def from_scan_data(
        cls,
        tools: list[ToolMetadata],
        findings: list[Finding],
    ) -> ScanSummary:
        confidence_counts = Counter(
            finding.confidence for finding in findings
        )
        category_counts = Counter(
            finding.category for finding in findings
        )
        affected_targets = {
            finding.target for finding in findings
        }

        return cls(
            tool_count=len(tools),
            finding_count=len(findings),
            affected_target_count=len(affected_targets),
            by_severity=SeveritySummary.from_findings(findings),
            by_confidence=dict(confidence_counts),
            by_category=dict(category_counts),
        )


class ScanResult(BaseModel):
    """한 번의 스캔 실행으로 만들어진 구조화 결과."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    schema_version: str = "1.0"
    scan_id: UUID = Field(default_factory=uuid4)

    scan_type: ScanType = "static"
    source_type: ScanSourceType = "tools_json"
    source: str

    started_at: datetime
    completed_at: datetime

    tools: list[ToolMetadata]
    findings: list[Finding]

    baseline_compared: bool = False
    warnings: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def duration_ms(self) -> int:
        duration = self.completed_at - self.started_at
        return max(
            0,
            int(duration.total_seconds() * 1000),
        )

    @computed_field
    @property
    def summary(self) -> ScanSummary:
        return ScanSummary.from_scan_data(
            self.tools,
            self.findings,
        )