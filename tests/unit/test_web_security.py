from __future__ import annotations

import pytest

from web import security as web_security
from web.security import (
    LocalWebSecurityError,
    LocalWebSecuritySettings,
    ParsedHost,
    is_state_changing_api_request,
    validate_host_header_values,
    validate_origin_header_values,
    validate_request_token_header_values,
)


SETTINGS = LocalWebSecuritySettings(
    allowed_hostnames=frozenset({"localhost", "127.0.0.1", "::1"}),
    request_token="SECRET_REQUEST_TOKEN",
    request_token_header="X-AuditGuard-Request-Token",
)


@pytest.mark.parametrize(
    ("header_value", "hostname", "port"),
    [
        ("localhost", "localhost", None),
        ("localhost:8000", "localhost", 8000),
        ("127.0.0.1", "127.0.0.1", None),
        ("127.0.0.1:8000", "127.0.0.1", 8000),
        ("[::1]", "::1", None),
        ("[::1]:8000", "::1", 8000),
    ],
)
def test_host_validation_allows_loopback_hosts(
    header_value: str,
    hostname: str,
    port: int | None,
) -> None:
    parsed = validate_host_header_values([header_value], SETTINGS)

    assert parsed == ParsedHost(hostname=hostname, port=port)


@pytest.mark.parametrize(
    "values",
    [
        ["evil.example"],
        ["localhost.evil.example"],
        ["127.0.0.1.evil.example"],
        ["localhost@evil.example"],
        ["0.0.0.0"],
        ["192.168.0.10"],
        [""],
        ["localhost:not-a-port"],
        ["localhost:99999"],
        ["::1"],
        [],
        ["localhost", "127.0.0.1"],
        ["SECRET_HOST_VALUE"],
    ],
)
def test_host_validation_rejects_untrusted_or_malformed_hosts(
    values: list[str],
) -> None:
    with pytest.raises(LocalWebSecurityError) as error:
        validate_host_header_values(values, SETTINGS)

    assert error.value.status_code == 400
    assert error.value.error_code == "host_not_allowed"
    assert "SECRET_HOST_VALUE" not in error.value.message


def test_origin_validation_allows_same_origin() -> None:
    validate_origin_header_values(
        ["http://127.0.0.1:8000"],
        request_host=ParsedHost("127.0.0.1", 8000),
        request_scheme="http",
        settings=SETTINGS,
    )
    validate_origin_header_values(
        ["http://localhost"],
        request_host=ParsedHost("localhost"),
        request_scheme="http",
        settings=SETTINGS,
    )
    validate_origin_header_values(
        ["http://localhost"],
        request_host=ParsedHost("localhost", 80),
        request_scheme="http",
        settings=SETTINGS,
    )


@pytest.mark.parametrize(
    "values",
    [
        [],
        ["null"],
        ["http://evil.example"],
        ["http://localhost:8000"],
        ["http://127.0.0.1:9000"],
        ["https://127.0.0.1:8000"],
        ["http://user@127.0.0.1:8000"],
        ["http://127.0.0.1:8000/path"],
        ["http://127.0.0.1:8000?query=1"],
        ["http://127.0.0.1:8000#fragment"],
        ["http://[::1"],
        ["http://["],
        ["http://127.0.0.1:invalid"],
        ["http://127.0.0.1:99999"],
        ["http://127.0.0.1:8000", "http://127.0.0.1:8000"],
        ["SECRET_ORIGIN_VALUE"],
        ["http://[SECRET_MALFORMED_ORIGIN"],
    ],
)
def test_origin_validation_rejects_cross_origin_or_malformed_values(
    values: list[str],
) -> None:
    with pytest.raises(LocalWebSecurityError) as error:
        validate_origin_header_values(
            values,
            request_host=ParsedHost("127.0.0.1", 8000),
            request_scheme="http",
            settings=SETTINGS,
        )

    assert error.value.status_code == 403
    assert error.value.error_code == "origin_not_allowed"
    assert "SECRET_ORIGIN_VALUE" not in error.value.message
    assert "SECRET_MALFORMED_ORIGIN" not in error.value.message


def test_origin_validation_converts_unicode_errors_to_security_errors(
    monkeypatch,
) -> None:
    def raise_unicode_error(origin: str):
        raise UnicodeError("SECRET_MALFORMED_ORIGIN")

    monkeypatch.setattr(web_security, "urlsplit", raise_unicode_error)

    with pytest.raises(LocalWebSecurityError) as error:
        validate_origin_header_values(
            ["http://127.0.0.1:8000"],
            request_host=ParsedHost("127.0.0.1", 8000),
            request_scheme="http",
            settings=SETTINGS,
        )

    assert error.value.status_code == 403
    assert error.value.error_code == "origin_not_allowed"
    assert "SECRET_MALFORMED_ORIGIN" not in error.value.message


def test_request_token_validation_accepts_exact_token() -> None:
    validate_request_token_header_values(["SECRET_REQUEST_TOKEN"], SETTINGS)


@pytest.mark.parametrize(
    "values",
    [
        [],
        ["wrong"],
        [""],
        ["   "],
        ["SECRET_REQUEST_TOKEN "],
        ["SECRET_REQUEST_TOKEN", "SECRET_REQUEST_TOKEN"],
    ],
)
def test_request_token_validation_rejects_missing_wrong_or_duplicate_tokens(
    values: list[str],
) -> None:
    with pytest.raises(LocalWebSecurityError) as error:
        validate_request_token_header_values(values, SETTINGS)

    assert error.value.status_code == 403
    assert error.value.error_code == "request_token_invalid"
    assert "SECRET_REQUEST_TOKEN" not in error.value.message


def test_request_token_validation_uses_compare_digest(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_compare_digest(left: str, right: str) -> bool:
        calls.append((left, right))
        return True

    monkeypatch.setattr(
        web_security.secrets,
        "compare_digest",
        fake_compare_digest,
    )

    validate_request_token_header_values(["provided"], SETTINGS)

    assert calls == [("provided", "SECRET_REQUEST_TOKEN")]


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/api/scans/upload", True),
        ("PUT", "/api/example", True),
        ("PATCH", "/api/example", True),
        ("DELETE", "/api/example", True),
        ("GET", "/api/example", False),
        ("HEAD", "/api/example", False),
        ("OPTIONS", "/api/example", False),
        ("POST", "/health", False),
    ],
)
def test_state_changing_api_detection(
    method: str,
    path: str,
    expected: bool,
) -> None:
    assert is_state_changing_api_request(method=method, path=path) is expected
