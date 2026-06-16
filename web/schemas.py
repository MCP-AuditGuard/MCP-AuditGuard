from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from core.models import Finding
from core.scan_result import ScanResult, ScanSummary, ScanType
from web.sample_catalog import SampleDefinition

class ScanResponse(BaseModel):
    """
    Web API가 외부에 반환하는 스캔 응답.

    내부 ScanResult에서 웹에 필요한 데이터만 선택해서 반환한다.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    scan_id: UUID
    scan_type: ScanType
    source: str

    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)

    summary: ScanSummary
    findings: list[Finding]

    baseline_compared: bool
    warnings: list[str]

    downloads: ReportDownloadLinks

    @classmethod
    def from_result(
        cls,
        result: ScanResult,
    ) -> "ScanResponse":
        scan_id = str(result.scan_id)

        return cls(
            schema_version=result.schema_version,
            scan_id=result.scan_id,
            scan_type=result.scan_type,
            source=result.source,
            started_at=result.started_at,
            completed_at=result.completed_at,
            duration_ms=result.duration_ms,
            summary=result.summary,
            findings=result.findings,
            baseline_compared=result.baseline_compared,
            warnings=result.warnings,
            downloads=ReportDownloadLinks(
                markdown_report=(
                    f"/api/reports/{scan_id}/markdown"
                ),
                json_report=(
                    f"/api/reports/{scan_id}/json"
                ),
            ),
        )
    
class ReportDownloadLinks(BaseModel):
    """저장된 리포트 다운로드 주소."""

    model_config = ConfigDict(
        extra="forbid",
        serialize_by_alias=True,
    )

    markdown_report: str = Field(serialization_alias="markdown")
    json_report: str = Field(serialization_alias="json")


class SampleResponse(BaseModel):
    """
    샘플 목록 API가 반환하는 최소 정보.

    실제 파일 경로나 JSON 파일 목록은 아직 외부에 공개하지 않는다.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    id: str
    title: str

    @classmethod
    def from_definition(
        cls,
        sample: SampleDefinition,
    ) -> "SampleResponse":
        return cls(
            id=sample.id,
            title=sample.title,
        )
