from __future__ import annotations

import secrets

from dataclasses import dataclass
from functools import lru_cache
from collections.abc import Callable
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from web.mcp_schemas import ErrorResponse


REQUEST_TOKEN_HEADER = "X-AuditGuard-Request-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True, slots=True)
class LocalWebSecuritySettings:
    allowed_hostnames: frozenset[str]
    request_token: str
    request_token_header: str


@dataclass(frozen=True, slots=True)
class ParsedHost:
    hostname: str
    port: int | None = None


class LocalWebSecurityError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


class LocalWebSecurityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        settings_provider: Callable[
            [],
            LocalWebSecuritySettings,
        ] | None = None,
    ) -> None:
        self.app = app
        self._settings_provider = (
            settings_provider or get_local_web_security_settings
        )

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = self._settings_provider()
        try:
            request_host = validate_host_header_values(
                _header_values(scope, "host"),
                settings,
            )
            if is_state_changing_api_request(
                method=str(scope.get("method", "")),
                path=str(scope.get("path", "")),
            ):
                validate_origin_header_values(
                    _header_values(scope, "origin"),
                    request_host=request_host,
                    request_scheme=str(scope.get("scheme", "http")),
                    settings=settings,
                )
                validate_request_token_header_values(
                    _header_values(scope, settings.request_token_header),
                    settings,
                )
        except LocalWebSecurityError as error:
            await _send_security_error(send, error)
            return

        await self.app(scope, receive, send)


@lru_cache(maxsize=1)
def get_local_web_security_settings() -> LocalWebSecuritySettings:
    return LocalWebSecuritySettings(
        allowed_hostnames=frozenset({"localhost", "127.0.0.1", "::1"}),
        request_token=secrets.token_urlsafe(32),
        request_token_header=REQUEST_TOKEN_HEADER,
    )


def is_state_changing_api_request(
    *,
    method: str,
    path: str,
) -> bool:
    return method.upper() in UNSAFE_METHODS and path.startswith("/api/")


def validate_host_header_values(
    values: list[str],
    settings: LocalWebSecuritySettings,
) -> ParsedHost:
    if len(values) != 1:
        raise _host_not_allowed()

    parsed = parse_host_header(values[0])
    allowed = {hostname.lower() for hostname in settings.allowed_hostnames}
    if parsed is None or parsed.hostname not in allowed:
        raise _host_not_allowed()

    return parsed


def validate_origin_header_values(
    values: list[str],
    *,
    request_host: ParsedHost,
    request_scheme: str,
    settings: LocalWebSecuritySettings,
) -> None:
    if len(values) != 1:
        raise _origin_not_allowed()

    origin = values[0]
    if not origin or origin == "null" or _contains_disallowed_char(origin):
        raise _origin_not_allowed()

    try:
        parsed = urlsplit(origin)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query
        fragment = parsed.fragment
        username = parsed.username
        password = parsed.password
        hostname = parsed.hostname
        origin_port = parsed.port
    except (ValueError, UnicodeError) as error:
        raise _origin_not_allowed() from error

    if (
        not scheme
        or not netloc
        or path
        or query
        or fragment
        or username is not None
        or password is not None
    ):
        raise _origin_not_allowed()

    if scheme != request_scheme.lower():
        raise _origin_not_allowed()

    if hostname is None:
        raise _origin_not_allowed()

    normalized_hostname = hostname.lower()
    allowed = {hostname.lower() for hostname in settings.allowed_hostnames}
    if (
        normalized_hostname not in allowed
        or normalized_hostname != request_host.hostname
    ):
        raise _origin_not_allowed()

    if _effective_port(scheme, origin_port) != _effective_port(
        request_scheme,
        request_host.port,
    ):
        raise _origin_not_allowed()


def validate_request_token_header_values(
    values: list[str],
    settings: LocalWebSecuritySettings,
) -> None:
    if len(values) != 1:
        raise _request_token_invalid()

    provided = values[0]
    if not provided or not provided.strip():
        raise _request_token_invalid()

    if not secrets.compare_digest(provided, settings.request_token):
        raise _request_token_invalid()


def parse_host_header(value: str) -> ParsedHost | None:
    if not value or _contains_disallowed_char(value):
        return None
    if any(marker in value for marker in ("/", "?", "#", "@")):
        return None

    if value.startswith("["):
        return _parse_bracketed_host(value)

    if "[" in value or "]" in value or value.count(":") > 1:
        return None

    if ":" in value:
        hostname, port_text = value.rsplit(":", 1)
        port = _parse_port(port_text)
        if port is None:
            return None
    else:
        hostname = value
        port = None

    hostname = hostname.lower()
    if not hostname:
        return None

    return ParsedHost(hostname=hostname, port=port)


def _parse_bracketed_host(value: str) -> ParsedHost | None:
    closing_index = value.find("]")
    if closing_index <= 1:
        return None

    hostname = value[1:closing_index].lower()
    remainder = value[closing_index + 1 :]
    if not hostname or "[" in hostname or "]" in remainder:
        return None

    if not remainder:
        return ParsedHost(hostname=hostname)

    if not remainder.startswith(":"):
        return None

    port = _parse_port(remainder[1:])
    if port is None:
        return None

    return ParsedHost(hostname=hostname, port=port)


def _parse_port(value: str) -> int | None:
    if not value or not value.isdecimal():
        return None

    port = int(value)
    if port < 1 or port > 65535:
        return None

    return port


def _effective_port(scheme: str, port: int | None) -> int | None:
    if port is not None:
        return port
    if scheme.lower() == "http":
        return 80
    if scheme.lower() == "https":
        return 443
    return None


def _contains_disallowed_char(value: str) -> bool:
    return any(ord(character) <= 32 or ord(character) == 127 for character in value)


def _header_values(scope: Scope, header_name: str) -> list[str]:
    target = header_name.lower().encode("ascii")
    return [
        value.decode("latin-1")
        for name, value in scope.get("headers", [])
        if name.lower() == target
    ]


async def _send_security_error(
    send: Send,
    error: LocalWebSecurityError,
) -> None:
    body = ErrorResponse(
        error_code=error.error_code,
        message=error.message,
        details=None,
    ).model_dump_json().encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": error.status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
        }
    )


def _host_not_allowed() -> LocalWebSecurityError:
    return LocalWebSecurityError(
        status_code=400,
        error_code="host_not_allowed",
        message="The request host is not allowed.",
    )


def _origin_not_allowed() -> LocalWebSecurityError:
    return LocalWebSecurityError(
        status_code=403,
        error_code="origin_not_allowed",
        message="The request origin is not allowed.",
    )


def _request_token_invalid() -> LocalWebSecurityError:
    return LocalWebSecurityError(
        status_code=403,
        error_code="request_token_invalid",
        message="A valid local request token is required.",
    )
