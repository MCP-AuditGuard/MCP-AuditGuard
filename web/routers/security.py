from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from web.security import (
    LocalWebSecuritySettings,
    get_local_web_security_settings,
)


router = APIRouter(prefix="/api/security", tags=["security"])


class RequestTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header_name: str
    request_token: str


@router.get(
    "/request-token",
    include_in_schema=False,
)
def get_request_token(
    settings: LocalWebSecuritySettings = Depends(
        get_local_web_security_settings
    ),
) -> JSONResponse:
    return JSONResponse(
        content=RequestTokenResponse(
            header_name=settings.request_token_header,
            request_token=settings.request_token,
        ).model_dump(mode="json"),
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Cross-Origin-Resource-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
        },
    )
