from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.dynamic_scan_models import (
    DiscoveryContext,
    DiscoveredMcpServer,
    HostToolPolicy,
    HttpConnectionPolicy,
    McpProduct,
    McpScope,
    McpTransport,
    PolicySourceCoverage,
    ServerEnabledState,
    ServerSupportState,
    StdioConnectionConfig,
    StreamableHttpConnectionConfig,
)
from core.mcp_monitoring_models import (
    ConfigurationFingerprint,
    MonitoringIdentity,
)
from core.mcp_server_identity import (
    McpServerIdentityError,
    _normalize_stdio_connection,
    create_configuration_fingerprint,
    create_monitoring_identity,
)


def make_context(
    tmp_path: Path,
    *,
    project_root: Path | None = None,
    current_working_directory: Path | None = None,
) -> DiscoveryContext:
    user_home = tmp_path / "home"
    user_home.mkdir(parents=True, exist_ok=True)

    if project_root is None and current_working_directory is None:
        project_root = tmp_path / "project"

    if project_root is not None:
        project_root.mkdir(parents=True, exist_ok=True)

    current = current_working_directory or project_root or tmp_path
    current.mkdir(parents=True, exist_ok=True)

    return DiscoveryContext(
        current_working_directory=current,
        project_root=project_root,
        user_home=user_home,
        include_trusted_project_config=True,
    )


def make_policy(product: McpProduct) -> HostToolPolicy:
    return HostToolPolicy(
        product=product,
        source_coverage=PolicySourceCoverage.COMPLETE,
    )


def make_stdio_connection(
    *,
    server_name: str = "github",
    command: str = "python",
    args: list[str] | None = None,
    cwd: str | None = None,
    env_values: dict[str, str] | None = None,
    env_references: dict[str, str] | None = None,
) -> StdioConnectionConfig:
    return StdioConnectionConfig(
        server_name=server_name,
        command=command,
        args=args or ["server.py"],
        cwd=cwd,
        env_values=env_values or {},
        env_references=env_references or {},
    )


def make_http_connection(
    *,
    server_name: str = "remote",
    url: str = "https://example.com/mcp",
    static_headers: dict[str, str] | None = None,
    environment_header_references: dict[str, str] | None = None,
    bearer_token_environment_reference: str | None = None,
    http_policy: HttpConnectionPolicy | None = None,
    construct: bool = False,
) -> StreamableHttpConnectionConfig:
    values = {
        "transport": McpTransport.STREAMABLE_HTTP,
        "server_name": server_name,
        "url": url,
        "static_headers": static_headers or {},
        "environment_header_references": (
            environment_header_references or {}
        ),
        "bearer_token_environment_reference": (
            bearer_token_environment_reference
        ),
        "http_policy": http_policy or HttpConnectionPolicy(),
    }
    if construct:
        return StreamableHttpConnectionConfig.model_construct(**values)

    return StreamableHttpConnectionConfig(**values)


def make_server(
    *,
    product: McpProduct = McpProduct.CODEX,
    scope: McpScope = McpScope.USER,
    server_name: str = "github",
    selection_id: str = "codex:user:github",
    source_label: str = "User config",
    connection: StdioConnectionConfig | StreamableHttpConnectionConfig | None = None,
) -> DiscoveredMcpServer:
    connection = connection or make_stdio_connection(server_name=server_name)
    transport = connection.transport
    is_stdio = isinstance(connection, StdioConnectionConfig)

    return DiscoveredMcpServer(
        selection_id=selection_id,
        product=product,
        scope=scope,
        source_label=source_label,
        server_name=server_name,
        transport=transport,
        enabled_state=ServerEnabledState.ENABLED,
        support_state=ServerSupportState.SUPPORTED,
        command_basename="python" if is_stdio else None,
        remote_origin="https://example.com" if not is_stdio else None,
        argument_count=len(connection.args) if is_stdio else 0,
        connection=connection,
        tool_policy=make_policy(product),
    )


def fingerprint_for(
    connection: StdioConnectionConfig | StreamableHttpConnectionConfig,
) -> ConfigurationFingerprint:
    return create_configuration_fingerprint(
        make_server(server_name=connection.server_name, connection=connection)
    )


def test_monitoring_identity_model_contract_is_serializable_and_strict(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    identity = create_monitoring_identity(make_server(), context)

    serialized = identity.model_dump(mode="json")
    restored = MonitoringIdentity.model_validate(serialized)

    assert restored == identity
    assert identity.monitoring_group_key.startswith("mcpgrp_")
    assert identity.monitoring_target_key.startswith("mcptgt_")
    assert identity.context_identity.startswith("mcpctx_")
    assert identity.registration_identity.selection_id == "codex:user:github"
    assert identity.registration_identity.context_identity == identity.context_identity

    with pytest.raises(ValidationError):
        MonitoringIdentity.model_validate({**serialized, "unexpected": "x"})

    with pytest.raises(ValidationError):
        identity.context_label = "Other"  # type: ignore[misc]


def test_configuration_fingerprint_model_contract_is_secret_safe_and_strict() -> None:
    connection = make_stdio_connection(
        command="C:/tools/server.py",
        args=["--token", "SUPER_SECRET_ARG"],
        env_values={"TOKEN": "SUPER_SECRET_ENV"},
        env_references={"API_KEY": "API_KEY_SOURCE"},
    )

    fingerprint = fingerprint_for(connection)
    serialized = fingerprint.model_dump(mode="json")
    dumped_json = fingerprint.model_dump_json()

    assert ConfigurationFingerprint.model_validate(serialized) == fingerprint
    assert fingerprint.algorithm == "sha256"
    assert fingerprint.version == "mcp-config-fingerprint-v1"
    assert len(fingerprint.fingerprint) == 64
    assert fingerprint.secret_value_included is False
    assert "SUPER_SECRET_ARG" not in dumped_json
    assert "SUPER_SECRET_ENV" not in dumped_json

    with pytest.raises(ValidationError):
        ConfigurationFingerprint.model_validate({**serialized, "extra": "x"})

    with pytest.raises(ValidationError):
        fingerprint.fingerprint = "0" * 64  # type: ignore[misc]


def test_group_key_uses_product_and_nfc_server_name_only(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    base = create_monitoring_identity(
        make_server(server_name="GitHub"),
        context,
    )
    changed_selection = create_monitoring_identity(
        make_server(server_name="GitHub", selection_id="different"),
        context,
    )
    changed_connection = create_monitoring_identity(
        make_server(
            server_name="GitHub",
            connection=make_stdio_connection(
                server_name="GitHub",
                command="node",
            ),
        ),
        context,
    )
    changed_product = create_monitoring_identity(
        make_server(product=McpProduct.CLAUDE, server_name="GitHub"),
        context,
    )
    changed_case = create_monitoring_identity(
        make_server(server_name="github"),
        context,
    )
    changed_spacing = create_monitoring_identity(
        make_server(server_name="my server"),
        context,
    )
    internal_spacing = create_monitoring_identity(
        make_server(server_name="my  server"),
        context,
    )
    composed = create_monitoring_identity(
        make_server(server_name="Caf\u00e9"),
        context,
    )
    decomposed = create_monitoring_identity(
        make_server(server_name="Cafe\u0301"),
        context,
    )

    assert changed_selection.monitoring_group_key == base.monitoring_group_key
    assert changed_connection.monitoring_group_key == base.monitoring_group_key
    assert changed_product.monitoring_group_key != base.monitoring_group_key
    assert changed_case.monitoring_group_key != base.monitoring_group_key
    assert internal_spacing.monitoring_group_key != changed_spacing.monitoring_group_key
    assert decomposed.monitoring_group_key == composed.monitoring_group_key
    assert decomposed.normalized_server_name == "Caf\u00e9"


def test_target_key_uses_context_not_selection_or_connection(
    tmp_path: Path,
) -> None:
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    context_a = make_context(tmp_path, project_root=project_a)
    context_b = make_context(tmp_path, project_root=project_b)

    base = create_monitoring_identity(
        make_server(scope=McpScope.PROJECT),
        context_a,
    )
    changed_selection = create_monitoring_identity(
        make_server(scope=McpScope.PROJECT, selection_id="new-selection-id"),
        context_a,
    )
    changed_connection = create_monitoring_identity(
        make_server(
            scope=McpScope.PROJECT,
            connection=make_stdio_connection(command="node"),
        ),
        context_a,
    )
    other_project = create_monitoring_identity(
        make_server(scope=McpScope.PROJECT),
        context_b,
    )

    assert changed_selection.monitoring_group_key == base.monitoring_group_key
    assert changed_selection.monitoring_target_key == base.monitoring_target_key
    assert changed_connection.monitoring_group_key == base.monitoring_group_key
    assert changed_connection.monitoring_target_key == base.monitoring_target_key
    assert other_project.monitoring_group_key == base.monitoring_group_key
    assert other_project.context_identity != base.context_identity
    assert other_project.monitoring_target_key != base.monitoring_target_key


def test_user_and_project_shadowing_share_group_but_split_target(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)
    user_identity = create_monitoring_identity(
        make_server(scope=McpScope.USER),
        context,
    )
    project_identity = create_monitoring_identity(
        make_server(
            scope=McpScope.PROJECT,
            selection_id="codex:project:github",
            source_label="Project config",
        ),
        context,
    )

    assert project_identity.monitoring_group_key == user_identity.monitoring_group_key
    assert project_identity.monitoring_target_key != user_identity.monitoring_target_key
    assert user_identity.registration_identity.scope == McpScope.USER
    assert project_identity.registration_identity.scope == McpScope.PROJECT


def test_context_identity_does_not_serialize_raw_project_path(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "private-project"
    context = make_context(tmp_path, project_root=project_root)

    identity = create_monitoring_identity(
        make_server(
            scope=McpScope.PROJECT,
            selection_id="safe-selection",
            source_label="Project config",
        ),
        context,
    )

    assert str(project_root.resolve()) not in identity.model_dump_json()
    assert identity.context_label == "Project"


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows path case normalization is platform-specific.",
)
def test_windows_context_path_case_is_normalized(tmp_path: Path) -> None:
    project_root = tmp_path / "ProjectCase"
    lower_context = make_context(tmp_path, project_root=project_root)
    upper_context = make_context(
        tmp_path,
        project_root=Path(str(project_root).upper()),
    )

    lower = create_monitoring_identity(
        make_server(scope=McpScope.PROJECT),
        lower_context,
    )
    upper = create_monitoring_identity(
        make_server(scope=McpScope.PROJECT),
        upper_context,
    )

    assert upper.context_identity == lower.context_identity
    assert upper.monitoring_target_key == lower.monitoring_target_key


def test_stdio_fingerprint_tracks_execution_meaning_but_not_secret_values(
    tmp_path: Path,
) -> None:
    cwd_a = tmp_path / "cwd-a"
    cwd_b = tmp_path / "cwd-b"
    cwd_a.mkdir()
    cwd_b.mkdir()

    base = fingerprint_for(
        make_stdio_connection(
            command="python",
            args=["server.py", "--mode", "read"],
            cwd=str(cwd_a),
            env_values={"TOKEN": "first-secret"},
            env_references={"API_KEY": "SOURCE_A"},
        )
    )
    same_secret_key_changed_value = fingerprint_for(
        make_stdio_connection(
            command="python",
            args=["server.py", "--mode", "read"],
            cwd=str(cwd_a),
            env_values={"TOKEN": "second-secret"},
            env_references={"API_KEY": "SOURCE_A"},
        )
    )

    assert same_secret_key_changed_value.fingerprint == base.fingerprint
    assert (
        fingerprint_for(make_stdio_connection(command="node")).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_stdio_connection(args=["server.py", "--mode", "write"])
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_stdio_connection(args=["--mode", "read", "server.py"])
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(make_stdio_connection(cwd=str(cwd_b))).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_stdio_connection(env_values={"OTHER_TOKEN": "first-secret"})
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_stdio_connection(env_references={"API_KEY": "SOURCE_B"})
        ).fingerprint
        != base.fingerprint
    )

    dumped_json = base.model_dump_json()
    assert "first-secret" not in dumped_json
    assert "server.py" not in dumped_json
    assert base.safe_summary == {
        "transport": "stdio",
        "command_basename": "python",
        "argument_count": 3,
        "cwd_present": True,
        "env_key_count": 2,
        "env_literal_key_count": 1,
        "env_reference_key_count": 1,
    }


def test_stdio_relative_command_with_cwd_ignores_process_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process_a = tmp_path / "process-a"
    process_b = tmp_path / "process-b"
    server_cwd = tmp_path / "server-cwd"
    process_a.mkdir()
    process_b.mkdir()
    server_cwd.mkdir()

    connection = make_stdio_connection(
        command="./server.py",
        cwd=str(server_cwd),
    )

    monkeypatch.chdir(process_a)
    first = fingerprint_for(connection)
    monkeypatch.chdir(process_b)
    second = fingerprint_for(connection)

    assert second.fingerprint == first.fingerprint


def test_stdio_relative_command_changes_when_cwd_changes(tmp_path: Path) -> None:
    cwd_a = tmp_path / "server-a"
    cwd_b = tmp_path / "server-b"
    cwd_a.mkdir()
    cwd_b.mkdir()

    first = fingerprint_for(
        make_stdio_connection(command="./server.py", cwd=str(cwd_a))
    )
    second = fingerprint_for(
        make_stdio_connection(command="./server.py", cwd=str(cwd_b))
    )

    assert second.fingerprint != first.fingerprint


def test_stdio_relative_command_without_cwd_ignores_process_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process_a = tmp_path / "process-a"
    process_b = tmp_path / "process-b"
    process_a.mkdir()
    process_b.mkdir()
    connection = make_stdio_connection(command="./server.py", cwd=None)

    monkeypatch.chdir(process_a)
    first = fingerprint_for(connection)
    monkeypatch.chdir(process_b)
    second = fingerprint_for(connection)

    assert second.fingerprint == first.fingerprint


def test_stdio_executable_command_is_not_joined_with_cwd(tmp_path: Path) -> None:
    cwd_a = tmp_path / "server-a"
    cwd_b = tmp_path / "server-b"
    cwd_a.mkdir()
    cwd_b.mkdir()

    first = make_stdio_connection(command="python", cwd=str(cwd_a))
    second = make_stdio_connection(command="python", cwd=str(cwd_b))

    assert _normalize_stdio_connection(first)["command"] == {
        "kind": "executable",
        "value": "python",
    }
    assert _normalize_stdio_connection(second)["command"] == {
        "kind": "executable",
        "value": "python",
    }
    assert fingerprint_for(second).fingerprint != fingerprint_for(first).fingerprint


def test_http_fingerprint_tracks_url_header_and_policy_meaning() -> None:
    base = fingerprint_for(
        make_http_connection(
            url="https://EXAMPLE.com:443/mcp?b=2&a=1",
            static_headers={"X-Client": "first-secret"},
            environment_header_references={"X-API-Key": "API_KEY_SOURCE"},
            bearer_token_environment_reference="TOKEN_SOURCE",
        )
    )

    assert (
        fingerprint_for(
            make_http_connection(
                url="HTTPS://example.com/mcp?b=2&a=1",
                static_headers={"x-client": "second-secret"},
                environment_header_references={"x-api-key": "API_KEY_SOURCE"},
                bearer_token_environment_reference="TOKEN_SOURCE",
            )
        ).fingerprint
        == base.fingerprint
    )
    assert (
        fingerprint_for(
            make_http_connection(url="http://example.com/mcp?b=2&a=1")
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_http_connection(url="https://api.example.com/mcp?b=2&a=1")
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_http_connection(url="https://example.com:444/mcp?b=2&a=1")
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_http_connection(url="https://example.com/other?b=2&a=1")
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_http_connection(url="https://example.com/mcp?a=1&b=2")
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_http_connection(
                url="https://example.com/mcp?b=2&a=1",
                static_headers={"X-Other": "first-secret"},
                environment_header_references={"X-API-Key": "API_KEY_SOURCE"},
                bearer_token_environment_reference="TOKEN_SOURCE",
            )
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_http_connection(
                url="https://example.com/mcp?b=2&a=1",
                static_headers={"X-Client": "first-secret"},
                environment_header_references={"X-API-Key": "OTHER_SOURCE"},
                bearer_token_environment_reference="TOKEN_SOURCE",
            )
        ).fingerprint
        != base.fingerprint
    )
    assert (
        fingerprint_for(
            make_http_connection(
                url="https://example.com/mcp?b=2&a=1",
                static_headers={"X-Client": "first-secret"},
                environment_header_references={"X-API-Key": "API_KEY_SOURCE"},
                bearer_token_environment_reference="OTHER_TOKEN_SOURCE",
            )
        ).fingerprint
        != base.fingerprint
    )


def test_http_fragment_is_ignored_and_safe_summary_excludes_path_query_and_secrets() -> None:
    base = fingerprint_for(
        make_http_connection(
            url=(
                "https://api.example.com/v1/super-secret-path"
                "?token=super-secret-query#first"
            ),
            static_headers={"Authorization": "super-secret-header"},
        )
    )
    changed_fragment = fingerprint_for(
        make_http_connection(
            url=(
                "https://api.example.com/v1/super-secret-path"
                "?token=super-secret-query#second"
            ),
            static_headers={"Authorization": "another-secret-header"},
        )
    )

    dumped_json = base.model_dump_json()

    assert changed_fragment.fingerprint == base.fingerprint
    assert base.safe_summary["origin"] == "https://api.example.com"
    assert "super-secret-path" not in dumped_json
    assert "super-secret-query" not in dumped_json
    assert "super-secret-header" not in dumped_json


def test_http_policy_changes_are_fingerprinted() -> None:
    base = fingerprint_for(make_http_connection())
    tls_disabled = fingerprint_for(
        make_http_connection(
            http_policy=HttpConnectionPolicy.model_construct(
                verify_tls=False,
                follow_redirects=False,
            ),
            construct=True,
        )
    )
    redirects_enabled = fingerprint_for(
        make_http_connection(
            http_policy=HttpConnectionPolicy.model_construct(
                verify_tls=True,
                follow_redirects=True,
            ),
            construct=True,
        )
    )

    assert tls_disabled.fingerprint != base.fingerprint
    assert redirects_enabled.fingerprint != base.fingerprint
    assert base.safe_summary["verify_tls"] is True
    assert base.safe_summary["follow_redirects"] is False
    assert base.safe_summary["trust_env"] is False


def test_http_path_unreserved_percent_encoding_is_normalized() -> None:
    encoded = fingerprint_for(make_http_connection(url="https://example.com/%7Euser"))
    literal = fingerprint_for(make_http_connection(url="https://example.com/~user"))

    assert encoded.fingerprint == literal.fingerprint


def test_http_path_reserved_percent_encoding_is_preserved() -> None:
    encoded = fingerprint_for(make_http_connection(url="https://example.com/a%3Bb"))
    literal = fingerprint_for(make_http_connection(url="https://example.com/a;b"))

    assert encoded.fingerprint != literal.fingerprint


def test_http_path_percent_encoding_hex_case_is_normalized() -> None:
    lower = fingerprint_for(make_http_connection(url="https://example.com/a%3bb"))
    upper = fingerprint_for(make_http_connection(url="https://example.com/a%3Bb"))

    assert lower.fingerprint == upper.fingerprint


def test_http_path_encoded_slash_is_not_treated_as_path_separator() -> None:
    encoded = fingerprint_for(make_http_connection(url="https://example.com/a%2Fb"))
    literal = fingerprint_for(make_http_connection(url="https://example.com/a/b"))

    assert encoded.fingerprint != literal.fingerprint


def test_http_empty_path_and_root_path_share_fingerprint() -> None:
    empty_path = fingerprint_for(make_http_connection(url="https://example.com"))
    root_path = fingerprint_for(make_http_connection(url="https://example.com/"))

    assert empty_path.fingerprint == root_path.fingerprint


def test_http_invalid_path_percent_encoding_is_rejected_without_leaking_path() -> None:
    connection = make_http_connection(url="https://example.com/%GG")

    with pytest.raises(McpServerIdentityError) as error_info:
        fingerprint_for(connection)

    message = str(error_info.value)
    assert "percent encoding" in message
    assert "%GG" not in message
    assert "https://example.com" not in message


def test_identity_errors_are_domain_errors_and_do_not_leak_secrets(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path)

    with pytest.raises(McpServerIdentityError, match="DiscoveredMcpServer"):
        create_monitoring_identity(object(), context)  # type: ignore[arg-type]

    with pytest.raises(McpServerIdentityError, match="DiscoveredMcpServer"):
        create_configuration_fingerprint(object())  # type: ignore[arg-type]

    unsupported = make_server().model_copy(update={"connection": None})
    with pytest.raises(McpServerIdentityError, match="connection"):
        create_configuration_fingerprint(unsupported)

    missing_project_context = DiscoveryContext.model_construct(
        current_working_directory=None,
        project_root=None,
        user_home=tmp_path,
        include_trusted_project_config=True,
    )
    with pytest.raises(McpServerIdentityError, match="project context"):
        create_monitoring_identity(
            make_server(scope=McpScope.PROJECT),
            missing_project_context,
        )

    invalid_url = make_http_connection(
        url="https://example.com:bad/mcp?token=SUPER_SECRET",
        construct=True,
    )
    with pytest.raises(McpServerIdentityError) as error_info:
        fingerprint_for(invalid_url)

    assert "SUPER_SECRET" not in str(error_info.value)


def test_http_header_name_collisions_are_rejected() -> None:
    with pytest.raises(McpServerIdentityError, match="ambiguous"):
        fingerprint_for(
            make_http_connection(
                static_headers={"X-Test": "value"},
                environment_header_references={"x-test": "SOURCE"},
            )
        )

    with pytest.raises(McpServerIdentityError, match="ambiguous"):
        fingerprint_for(
            make_http_connection(
                static_headers={"Authorization": "value"},
                bearer_token_environment_reference="TOKEN_SOURCE",
            )
        )
