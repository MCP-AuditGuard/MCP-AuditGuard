from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.exceptions import ScanServiceError
from reports.artifact_store import ReportArtifactError
from web.routers.scans import router as scans_router
from web.routers.samples import router as samples_router
from web.routers.reports import router as reports_router

WEB_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_ROOT / "templates"
STATIC_DIR = WEB_ROOT / "static"

app = FastAPI(
    title="MCP-AuditGuard Local API",
    version="0.1.0",
    description="Local Web API for MCP tool metadata security scans.",
)

templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)

app.include_router(scans_router)
app.include_router(samples_router)
app.include_router(reports_router)


@app.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def show_home_page(
    request: Request,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.get(
    "/health",
    tags=["system"],
)
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "mcp-auditguard",
    }


@app.exception_handler(ScanServiceError)
async def handle_scan_service_error(
    request: Request,
    error: ScanServiceError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "scan_failed",
            "detail": str(error),
        },
    )

@app.exception_handler(ReportArtifactError)
async def handle_report_artifact_error(
    request: Request,
    error: ReportArtifactError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "report_save_failed",
            "detail": str(error),
        },
    )