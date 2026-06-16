from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from reports.artifact_store import get_report_artifact


router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
)


@router.get(
    "/{scan_id}/markdown",
    response_class=FileResponse,
)
def download_markdown_report(
    scan_id: UUID,
) -> FileResponse:
    try:
        report_path = get_report_artifact(
            scan_id,
            "markdown",
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Markdown report was not found.",
        ) from error

    return FileResponse(
        path=report_path,
        media_type="text/markdown; charset=utf-8",
        filename=f"auditguard-{scan_id}.md",
    )


@router.get(
    "/{scan_id}/json",
    response_class=FileResponse,
)
def download_json_report(
    scan_id: UUID,
) -> FileResponse:
    try:
        report_path = get_report_artifact(
            scan_id,
            "json",
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="JSON report was not found.",
        ) from error

    return FileResponse(
        path=report_path,
        media_type="application/json",
        filename=f"auditguard-{scan_id}.json",
    )