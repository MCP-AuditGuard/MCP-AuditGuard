from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.exceptions import ScanServiceError
from core.runtime_paths import (
    web_static_directory,
    web_templates_directory,
)
from core.mcp_baseline_repository import (
    MonitoringConflictError,
    MonitoringIntegrityError,
    MonitoringNotFoundError,
    MonitoringSchemaError,
    MonitoringStorageError,
)
from core.mcp_monitoring_service import (
    MonitoringDiscoveryError,
    MonitoringScanError,
    MonitoringServiceError,
)
from reports.artifact_store import ReportArtifactError
from web.mcp_schemas import ErrorResponse
from web.routers.security import router as security_router
from web.routers.mcp_servers import router as mcp_servers_router
from web.routers.scans import router as scans_router
from web.routers.samples import router as samples_router
from web.routers.reports import router as reports_router
from web.security import LocalWebSecurityMiddleware

TEMPLATES_DIR = web_templates_directory()
STATIC_DIR = web_static_directory()

app = FastAPI(
    title="MCP-AuditGuard Local API",
    version="0.1.0",
    description="Local Web API for MCP tool metadata security scans.",
)

templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
)

app.add_middleware(LocalWebSecurityMiddleware)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)

app.include_router(scans_router)
app.include_router(samples_router)
app.include_router(reports_router)
app.include_router(mcp_servers_router)
app.include_router(security_router)


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


@app.exception_handler(MonitoringNotFoundError)
async def handle_monitoring_not_found_error(
    request: Request,
    error: MonitoringNotFoundError,
) -> JSONResponse:
    return _monitoring_error_response(
        status.HTTP_404_NOT_FOUND,
        "monitoring_not_found",
        "The requested MCP monitoring resource was not found.",
    )


@app.exception_handler(MonitoringConflictError)
async def handle_monitoring_conflict_error(
    request: Request,
    error: MonitoringConflictError,
) -> JSONResponse:
    return _monitoring_error_response(
        status.HTTP_409_CONFLICT,
        "monitoring_conflict",
        "The MCP monitoring resource changed before the request could be applied.",
    )


@app.exception_handler(MonitoringDiscoveryError)
async def handle_monitoring_discovery_error(
    request: Request,
    error: MonitoringDiscoveryError,
) -> JSONResponse:
    return _monitoring_error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "monitoring_discovery_unavailable",
        "MCP server discovery is unavailable.",
    )


@app.exception_handler(MonitoringScanError)
async def handle_monitoring_scan_error(
    request: Request,
    error: MonitoringScanError,
) -> JSONResponse:
    return _monitoring_error_response(
        status.HTTP_502_BAD_GATEWAY,
        "monitoring_scan_failed",
        "MCP dynamic scan failed before a scan result could be returned.",
    )


@app.exception_handler(MonitoringSchemaError)
async def handle_monitoring_schema_error(
    request: Request,
    error: MonitoringSchemaError,
) -> JSONResponse:
    return _monitoring_error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "monitoring_storage_invalid",
        "MCP monitoring storage contains an invalid document.",
    )


@app.exception_handler(MonitoringIntegrityError)
async def handle_monitoring_integrity_error(
    request: Request,
    error: MonitoringIntegrityError,
) -> JSONResponse:
    return _monitoring_error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "monitoring_storage_integrity_error",
        "MCP monitoring storage integrity check failed.",
    )


@app.exception_handler(MonitoringStorageError)
async def handle_monitoring_storage_error(
    request: Request,
    error: MonitoringStorageError,
) -> JSONResponse:
    return _monitoring_error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "monitoring_storage_error",
        "MCP monitoring storage is unavailable.",
    )


@app.exception_handler(MonitoringServiceError)
async def handle_monitoring_service_error(
    request: Request,
    error: MonitoringServiceError,
) -> JSONResponse:
    return _monitoring_error_response(
        status.HTTP_400_BAD_REQUEST,
        "monitoring_service_error",
        "MCP monitoring request could not be completed.",
    )


def _monitoring_error_response(
    status_code: int,
    error_code: str,
    message: str,
    *,
    details: dict[str, str | int | bool | None] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error_code=error_code,
            message=message,
            details=details,
        ).model_dump(mode="json"),
    )
