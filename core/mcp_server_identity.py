from __future__ import annotations

import os
import posixpath
import unicodedata

from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from core.dynamic_scan_models import (
    DiscoveryContext,
    DiscoveredMcpServer,
    HttpConnectionPolicy,
    McpScope,
    McpTransport,
    StdioConnectionConfig,
    StreamableHttpConnectionConfig,
)
from core.mcp_metadata_normalizer import canonical_json_bytes, calculate_sha256
from core.mcp_monitoring_models import (
    ConfigurationFingerprint,
    MonitoringIdentity,
    RegistrationIdentity,
)


GROUP_KEY_VERSION = "mcp-monitoring-group-v1"
TARGET_KEY_VERSION = "mcp-monitoring-target-v1"
CONTEXT_IDENTITY_VERSION = "mcp-monitoring-context-v1"
CONFIG_FINGERPRINT_VERSION = "mcp-config-fingerprint-v1"
HASH_PREFIX_LENGTH = 32


class McpServerIdentityError(ValueError):
    """Raised when MCP monitoring identity cannot be derived safely."""


def create_monitoring_identity(
    server: DiscoveredMcpServer,
    context: DiscoveryContext,
) -> MonitoringIdentity:
    """Create long-lived group and target identifiers for one discovered server."""
    _validate_server(server)
    if not isinstance(context, DiscoveryContext):
        raise McpServerIdentityError("context must be a DiscoveryContext instance")

    normalized_server_name = _normalize_server_name(server.server_name)
    group_key = _monitoring_group_key(
        product=server.product.value,
        normalized_server_name=normalized_server_name,
    )
    context_identity, context_label = _create_context_identity(
        server=server,
        context=context,
    )
    target_key = _monitoring_target_key(
        monitoring_group_key=group_key,
        context_identity=context_identity,
    )

    return MonitoringIdentity(
        monitoring_group_key=group_key,
        monitoring_target_key=target_key,
        product=server.product,
        normalized_server_name=normalized_server_name,
        display_server_name=server.server_name,
        context_identity=context_identity,
        context_label=context_label,
        registration_identity=RegistrationIdentity(
            selection_id=server.selection_id,
            scope=server.scope,
            safe_source_label=server.source_label,
            context_identity=context_identity,
        ),
    )


def create_configuration_fingerprint(
    server: DiscoveredMcpServer,
) -> ConfigurationFingerprint:
    """Create a secret-safe fingerprint for one discovered server connection."""
    _validate_server(server)

    connection = server.connection
    if isinstance(connection, StdioConnectionConfig):
        normalized_connection = _normalize_stdio_connection(connection)
        safe_summary = _stdio_safe_summary(connection)
        transport = McpTransport.STDIO
    elif isinstance(connection, StreamableHttpConnectionConfig):
        normalized_connection = _normalize_http_connection(connection)
        safe_summary = _http_safe_summary(connection)
        transport = McpTransport.STREAMABLE_HTTP
    else:
        raise McpServerIdentityError(
            "server connection is unavailable or unsupported"
        )

    payload = {
        "version": CONFIG_FINGERPRINT_VERSION,
        "transport": transport.value,
        "normalized_connection": normalized_connection,
    }

    return ConfigurationFingerprint(
        fingerprint=calculate_sha256(canonical_json_bytes(payload)),
        transport=transport,
        safe_summary=safe_summary,
    )


def _validate_server(server: DiscoveredMcpServer) -> None:
    if not isinstance(server, DiscoveredMcpServer):
        raise McpServerIdentityError(
            "server must be a DiscoveredMcpServer instance"
        )
    if not getattr(server, "product", None):
        raise McpServerIdentityError("server product is unavailable")
    if not isinstance(server.server_name, str) or not server.server_name:
        raise McpServerIdentityError("server name must not be empty")


def _normalize_server_name(server_name: str) -> str:
    if not isinstance(server_name, str) or not server_name:
        raise McpServerIdentityError("server name must not be empty")

    normalized = unicodedata.normalize("NFC", server_name)
    if not normalized:
        raise McpServerIdentityError("server name must not be empty")

    return normalized


def _monitoring_group_key(
    *,
    product: str,
    normalized_server_name: str,
) -> str:
    payload = {
        "version": GROUP_KEY_VERSION,
        "product": product,
        "normalized_server_name": normalized_server_name,
    }
    return f"mcpgrp_{_digest_prefix(payload)}"


def _monitoring_target_key(
    *,
    monitoring_group_key: str,
    context_identity: str,
) -> str:
    payload = {
        "version": TARGET_KEY_VERSION,
        "monitoring_group_key": monitoring_group_key,
        "context_identity": context_identity,
    }
    return f"mcptgt_{_digest_prefix(payload)}"


def _create_context_identity(
    *,
    server: DiscoveredMcpServer,
    context: DiscoveryContext,
) -> tuple[str, str]:
    if server.scope == McpScope.USER:
        payload = {
            "version": CONTEXT_IDENTITY_VERSION,
            "context_type": "user",
            "product": server.product.value,
        }
        return f"mcpctx_{_digest_prefix(payload)}", "User"

    if server.scope in {McpScope.PROJECT, McpScope.LOCAL}:
        project_path = _resolve_project_context(context)
        path_identity = _path_identity(project_path)
        context_type = (
            "local_project" if server.scope == McpScope.LOCAL else "project"
        )
        payload = {
            "version": CONTEXT_IDENTITY_VERSION,
            "context_type": context_type,
            "product": server.product.value,
            "path_identity_hash": calculate_sha256(
                canonical_json_bytes(
                    {
                        "version": "mcp-monitoring-path-identity-v1",
                        "path_identity": path_identity,
                    }
                )
            ),
        }
        label = "Local project" if server.scope == McpScope.LOCAL else "Project"
        return f"mcpctx_{_digest_prefix(payload)}", label

    raise McpServerIdentityError("server scope is unsupported")


def _resolve_project_context(context: DiscoveryContext) -> Path:
    project_root = getattr(context, "project_root", None)
    if project_root is not None:
        return Path(project_root).expanduser().resolve(strict=False)

    current = getattr(context, "current_working_directory", None)
    if current is None:
        raise McpServerIdentityError("project context is unavailable")

    resolved_current = Path(current).expanduser().resolve(strict=False)
    for candidate in (resolved_current, *resolved_current.parents):
        if (candidate / ".git").exists():
            return candidate

    return resolved_current


def _path_identity(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _normalize_stdio_connection(
    connection: StdioConnectionConfig,
) -> dict[str, object]:
    normalized_cwd = (
        _path_identity(Path(connection.cwd))
        if connection.cwd is not None
        else None
    )

    return {
        "transport": McpTransport.STDIO.value,
        "command": _normalize_command(
            connection.command,
            cwd=connection.cwd,
        ),
        "args": list(connection.args),
        "cwd": _presence(normalized_cwd),
        "env_literals": [
            {
                "target_name": name,
                "literal_present": True,
            }
            for name in sorted(connection.env_values)
        ],
        "env_references": [
            {
                "target_name": target_name,
                "source_name": source_name,
            }
            for target_name, source_name in sorted(
                connection.env_references.items()
            )
        ],
        "execution_policy": {
            "shell": False,
        },
    }


def _normalize_command(
    command: str,
    *,
    cwd: str | None,
) -> dict[str, object]:
    if _is_path_like(command):
        command_path = Path(command).expanduser()
        if command_path.is_absolute() or command.startswith("~"):
            return {
                "kind": "path",
                "value": _path_identity(command_path),
            }

        if cwd is not None:
            cwd_path = Path(cwd).expanduser().resolve(strict=False)
            return {
                "kind": "path",
                "value": _path_identity(cwd_path / command),
            }

        return {
            "kind": "relative_path",
            "value": _normalize_relative_command_path(command),
        }

    return {
        "kind": "executable",
        "value": command,
    }


def _is_path_like(value: str) -> bool:
    return (
        "/" in value
        or "\\" in value
        or Path(value).is_absolute()
        or value.startswith("~")
    )


def _normalize_relative_command_path(command: str) -> str:
    normalized = command.replace("\\", "/")
    parts = [
        segment
        for segment in normalized.split("/")
        if segment not in {"", "."}
    ]

    return "/".join(parts) or "."


def _stdio_safe_summary(
    connection: StdioConnectionConfig,
) -> dict[str, str | int | bool | None]:
    return {
        "transport": McpTransport.STDIO.value,
        "command_basename": _basename(connection.command),
        "argument_count": len(connection.args),
        "cwd_present": connection.cwd is not None,
        "env_key_count": (
            len(connection.env_values) + len(connection.env_references)
        ),
        "env_literal_key_count": len(connection.env_values),
        "env_reference_key_count": len(connection.env_references),
    }


def _normalize_http_connection(
    connection: StreamableHttpConnectionConfig,
) -> dict[str, object]:
    url = _normalize_url(connection.url)
    static_headers = _normalize_static_headers(connection.static_headers)
    env_headers = _normalize_env_headers(
        connection.environment_header_references
    )
    _ensure_header_names_do_not_collide(
        [
            *[header["name"] for header in static_headers],
            *[header["name"] for header in env_headers],
            (
                "authorization"
                if connection.bearer_token_environment_reference is not None
                else None
            ),
        ]
    )
    verify_tls, follow_redirects = _http_policy_values(connection.http_policy)

    return {
        "transport": McpTransport.STREAMABLE_HTTP.value,
        "url": url,
        "headers": {
            "static": static_headers,
            "environment_references": env_headers,
            "bearer_token_reference": _presence(
                connection.bearer_token_environment_reference
            ),
        },
        "http_policy": {
            "verify_tls": verify_tls,
            "follow_redirects": follow_redirects,
            "trust_env": False,
        },
    }


def _normalize_url(url: str) -> dict[str, object]:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise McpServerIdentityError("HTTP URL is invalid") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise McpServerIdentityError("HTTP URL scheme is unsupported")
    if parsed.hostname is None:
        raise McpServerIdentityError("HTTP URL host is unavailable")

    host = _normalize_host(parsed.hostname)
    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise McpServerIdentityError("HTTP URL port is invalid") from exc

    default_port = 443 if scheme == "https" else 80
    effective_port = explicit_port if explicit_port is not None else default_port

    return {
        "scheme": scheme,
        "host": host,
        "effective_port": effective_port,
        "path": _normalize_path(parsed.path),
        "query": _normalize_query(
            parsed.query,
            present=_query_delimiter_present(url),
        ),
        "userinfo_present": (
            parsed.username is not None or parsed.password is not None
        ),
    }


def _normalize_host(host: str) -> str:
    lowered = host.lower()
    if ":" in lowered:
        return lowered

    try:
        return lowered.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise McpServerIdentityError("HTTP URL host is invalid") from exc


def _normalize_path(path: str) -> str:
    if not path:
        return "/"

    return _normalize_url_path_text(path)


_UNRESERVED_URL_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "-._~"
)
_RESERVED_URL_CHARS = frozenset(":/?#[]@!$&'()*+,;=")
_HEX_CHARS = frozenset("0123456789ABCDEFabcdef")


def _normalize_url_path_text(path: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(path):
        char = path[index]
        if char == "%":
            if (
                index + 2 >= len(path)
                or path[index + 1] not in _HEX_CHARS
                or path[index + 2] not in _HEX_CHARS
            ):
                raise McpServerIdentityError(
                    "HTTP URL path contains invalid percent encoding"
                )

            encoded = path[index + 1 : index + 3].upper()
            decoded = chr(int(encoded, 16))
            if decoded in _UNRESERVED_URL_CHARS:
                result.append(decoded)
            else:
                result.append(f"%{encoded}")
            index += 3
            continue

        if char in _UNRESERVED_URL_CHARS or char in _RESERVED_URL_CHARS:
            result.append(char)
        else:
            result.append(quote(char, safe=""))
        index += 1

    return "".join(result)


def _normalize_query(
    query: str,
    *,
    present: bool,
) -> dict[str, object]:
    if not present:
        return {"presence": "missing"}
    if query == "":
        return {"presence": "empty", "pairs": []}

    pairs: list[dict[str, object]] = []
    for item in query.split("&"):
        if "=" in item:
            name, value = item.split("=", 1)
            value_payload = {
                "presence": "value",
                "value": _normalize_query_component(value),
            }
        else:
            name = item
            value_payload = {"presence": "missing"}

        pairs.append(
            {
                "name": _normalize_query_component(name),
                "value": value_payload,
            }
        )

    return {
        "presence": "value",
        "pairs": pairs,
    }


def _query_delimiter_present(url: str) -> bool:
    return "?" in url.split("#", 1)[0]


def _normalize_query_component(value: str) -> str:
    return quote(unquote(value), safe="-._~")


def _normalize_static_headers(
    headers: dict[str, str],
) -> list[dict[str, object]]:
    return [
        {
            "name": _normalize_header_name(name),
            "literal_present": True,
        }
        for name in sorted(headers, key=lambda item: item.lower())
    ]


def _normalize_env_headers(
    headers: dict[str, str],
) -> list[dict[str, str]]:
    return [
        {
            "name": _normalize_header_name(name),
            "source_name": source_name,
        }
        for name, source_name in sorted(
            headers.items(),
            key=lambda item: item[0].lower(),
        )
    ]


def _normalize_header_name(name: str) -> str:
    normalized = name.strip().lower()
    if not normalized:
        raise McpServerIdentityError("HTTP header name is invalid")
    return normalized


def _ensure_header_names_do_not_collide(
    names: list[str | None],
) -> None:
    present_names = [name for name in names if name is not None]
    if len(present_names) != len(set(present_names)):
        raise McpServerIdentityError("HTTP header names are ambiguous")


def _http_policy_values(
    policy: HttpConnectionPolicy,
) -> tuple[bool, bool]:
    verify_tls = getattr(policy, "verify_tls", None)
    follow_redirects = getattr(policy, "follow_redirects", None)
    if not isinstance(verify_tls, bool) or not isinstance(follow_redirects, bool):
        raise McpServerIdentityError("HTTP policy is invalid")

    return verify_tls, follow_redirects


def _http_safe_summary(
    connection: StreamableHttpConnectionConfig,
) -> dict[str, str | int | bool | None]:
    url = _normalize_url(connection.url)
    verify_tls, follow_redirects = _http_policy_values(connection.http_policy)
    return {
        "transport": McpTransport.STREAMABLE_HTTP.value,
        "origin": _safe_origin(url),
        "header_name_count": (
            len(connection.static_headers)
            + len(connection.environment_header_references)
        ),
        "token_reference_present": (
            connection.bearer_token_environment_reference is not None
        ),
        "verify_tls": verify_tls,
        "follow_redirects": follow_redirects,
        "trust_env": False,
    }


def _safe_origin(url: dict[str, object]) -> str:
    scheme = str(url["scheme"])
    host = str(url["host"])
    port = int(url["effective_port"])
    default_port = 443 if scheme == "https" else 80
    formatted_host = f"[{host}]" if ":" in host else host
    port_suffix = f":{port}" if port != default_port else ""
    return f"{scheme}://{formatted_host}{port_suffix}"


def _presence(value: object | None) -> dict[str, object]:
    if value is None:
        return {"presence": "missing"}

    return {
        "presence": "value",
        "value": value,
    }


def _basename(value: str) -> str:
    normalized = value.replace("\\", "/")
    return posixpath.basename(normalized) or normalized


def _digest_prefix(payload: object) -> str:
    return calculate_sha256(canonical_json_bytes(payload))[:HASH_PREFIX_LENGTH]
