from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.models import ToolMetadata
from core.scan_result import ScanResult


class McpProduct(StrEnum):
    CODEX = "codex"
    CLAUDE = "claude"


class McpScope(StrEnum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class McpTransport(StrEnum):
    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"


class ServerEnabledState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class ServerSupportState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


class DiscoverySourceStatus(StrEnum):
    FOUND = "found"
    MISSING = "missing"
    INACCESSIBLE = "inaccessible"
    INVALID = "invalid"


class PolicySourceCoverage(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


class PermissionEffect(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ToolActivationStatus(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class DynamicScanStage(StrEnum):
    DISCOVERY = "discovery"
    SELECTION = "selection"
    CONFIGURATION = "configuration"
    CONNECT = "connect"
    INITIALIZE = "initialize"
    LIST_TOOLS = "list_tools"
    METADATA_VALIDATION = "metadata_validation"
    REMOTE_SESSION_TERMINATION = "remote_session_termination"
    LOCAL_CLEANUP = "local_cleanup"
    TOOL_POLICY = "tool_policy"
    SCAN = "scan"


class IssueLevel(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class DynamicScanStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class DynamicStageStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"


class LocalCleanupStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RemoteSessionTerminationStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    CONFIRMED = "confirmed"
    ATTEMPTED_UNCONFIRMED = "attempted_unconfirmed"


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        hide_input_in_errors=True,
    )


class DiscoveryContext(_StrictModel):
    current_working_directory: Path
    project_root: Path | None = None
    user_home: Path
    include_trusted_project_config: bool = False


class HttpConnectionPolicy(_StrictModel):
    verify_tls: Literal[True] = True
    follow_redirects: Literal[False] = False


class StdioConnectionConfig(_StrictModel):
    transport: Literal[McpTransport.STDIO] = McpTransport.STDIO
    server_name: str = Field(min_length=1)
    command: str = Field(min_length=1, repr=False, exclude=True)
    args: list[str] = Field(default_factory=list, repr=False, exclude=True)
    cwd: str | None = Field(default=None, repr=False, exclude=True)
    env_values: dict[str, str] = Field(
        default_factory=dict,
        repr=False,
        exclude=True,
    )
    env_references: dict[str, str] = Field(
        default_factory=dict,
        repr=False,
        exclude=True,
    )

    @field_validator("server_name", "command")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _required_text(value)


class StreamableHttpConnectionConfig(_StrictModel):
    transport: Literal[McpTransport.STREAMABLE_HTTP] = (
        McpTransport.STREAMABLE_HTTP
    )
    server_name: str = Field(min_length=1)
    url: str = Field(min_length=1, repr=False, exclude=True)
    static_headers: dict[str, str] = Field(
        default_factory=dict,
        repr=False,
        exclude=True,
    )
    environment_header_references: dict[str, str] = Field(
        default_factory=dict,
        repr=False,
        exclude=True,
    )
    bearer_token_environment_reference: str | None = Field(
        default=None,
        repr=False,
        exclude=True,
    )
    http_policy: HttpConnectionPolicy = Field(
        default_factory=HttpConnectionPolicy,
    )

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _http_url(value)


ConnectionConfig = Annotated[
    StdioConnectionConfig | StreamableHttpConnectionConfig,
    Field(discriminator="transport"),
]


class ResolvedStdioConnection(_StrictModel):
    transport: Literal[McpTransport.STDIO] = McpTransport.STDIO
    server_name: str = Field(min_length=1)
    command: str = Field(min_length=1, repr=False, exclude=True)
    args: list[str] = Field(default_factory=list, repr=False, exclude=True)
    cwd: str | None = Field(default=None, repr=False, exclude=True)
    environment: dict[str, str] = Field(
        default_factory=dict,
        repr=False,
        exclude=True,
    )

    @field_validator("server_name", "command")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _required_text(value)


class ResolvedStreamableHttpConnection(_StrictModel):
    transport: Literal[McpTransport.STREAMABLE_HTTP] = (
        McpTransport.STREAMABLE_HTTP
    )
    server_name: str = Field(min_length=1)
    url: str = Field(min_length=1, repr=False, exclude=True)
    headers: dict[str, str] = Field(
        default_factory=dict,
        repr=False,
        exclude=True,
    )
    http_policy: HttpConnectionPolicy = Field(
        default_factory=HttpConnectionPolicy,
    )

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _http_url(value)


ResolvedConnection = Annotated[
    ResolvedStdioConnection | ResolvedStreamableHttpConnection,
    Field(discriminator="transport"),
]


class DynamicScanIssue(_StrictModel):
    stage: DynamicScanStage
    code: str = Field(min_length=1)
    level: IssueLevel
    safe_message: str = Field(min_length=1)
    server_id: str | None = None
    tool_id: str | None = None
    item_index: int | None = Field(default=None, ge=0)
    tool_name: str | None = None


class ClaudePermissionRule(_StrictModel):
    effect: PermissionEffect
    tool_name_pattern: str = Field(
        min_length=1,
        repr=False,
        exclude=True,
    )
    source_label: str = Field(min_length=1)


class HostToolPolicy(_StrictModel):
    product: McpProduct
    source_coverage: PolicySourceCoverage = PolicySourceCoverage.INCOMPLETE
    codex_enabled_tools_configured: bool = False
    codex_enabled_tools: list[str] = Field(
        default_factory=list,
        repr=False,
        exclude=True,
    )
    codex_disabled_tools: list[str] = Field(
        default_factory=list,
        repr=False,
        exclude=True,
    )
    claude_permission_rules: list[ClaudePermissionRule] = Field(
        default_factory=list,
        repr=False,
        exclude=True,
    )
    parse_issues: list[DynamicScanIssue] = Field(default_factory=list)


class McpServerSummary(_StrictModel):
    selection_id: str = Field(min_length=1)
    product: McpProduct
    scope: McpScope
    source_label: str = Field(min_length=1)
    server_name: str = Field(min_length=1)
    transport: McpTransport
    enabled_state: ServerEnabledState
    support_state: ServerSupportState
    support_reason_code: str | None = None
    command_basename: str | None = None
    remote_origin: str | None = None
    argument_count: int = Field(default=0, ge=0)

    @field_validator("selection_id", "source_label", "server_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("required summary text must not be empty")

        return normalized

    @field_validator("support_reason_code")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("command_basename")
    @classmethod
    def keep_command_basename(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None

        return normalized.replace("\\", "/").rsplit("/", 1)[-1]

    @field_validator("remote_origin")
    @classmethod
    def keep_remote_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None

        parsed = urlsplit(value)

        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("remote_origin must be an HTTP origin")

        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"

        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("remote_origin contains an invalid port") from error

        port_suffix = f":{port}" if port is not None else ""
        return f"{parsed.scheme.lower()}://{host}{port_suffix}"


class DiscoveredMcpServer(McpServerSummary):
    connection: ConnectionConfig | None = None
    tool_policy: HostToolPolicy

    @model_validator(mode="after")
    def validate_discovered_server(self) -> DiscoveredMcpServer:
        if (
            self.support_state == ServerSupportState.SUPPORTED
            and self.connection is None
            and self.enabled_state != ServerEnabledState.DISABLED
        ):
            raise ValueError("supported server must include a connection")
        if (
            self.support_state != ServerSupportState.SUPPORTED
            and self.connection is not None
        ):
            raise ValueError(
                "unsupported or invalid server must not include a connection"
            )
        if (
            self.enabled_state == ServerEnabledState.DISABLED
            and self.connection is not None
        ):
            raise ValueError("disabled server must not include a connection")

        if self.connection is not None:
            if self.connection.transport != self.transport:
                raise ValueError("connection transport must match server transport")
            if self.connection.server_name != self.server_name:
                raise ValueError("connection server_name must match server_name")

        if self.tool_policy.product != self.product:
            raise ValueError("tool policy product must match server product")

        return self

    def to_summary(self) -> McpServerSummary:
        return McpServerSummary.model_validate(
            self.model_dump(
                exclude={"connection", "tool_policy"},
            )
        )


class McpDiscoveryResult(_StrictModel):
    servers: list[DiscoveredMcpServer] = Field(default_factory=list)
    issues: list[DynamicScanIssue] = Field(default_factory=list)
    source_statuses: dict[str, DiscoverySourceStatus] = Field(
        default_factory=dict,
    )

    @property
    def summaries(self) -> list[McpServerSummary]:
        return [server.to_summary() for server in self.servers]


class ToolActivationAssessment(_StrictModel):
    tool_name: str = Field(min_length=1)
    status: ToolActivationStatus
    product: McpProduct
    policy_source_labels: list[str] = Field(default_factory=list)
    safe_basis_code: str = Field(min_length=1)


def build_tool_id(
    *,
    server_selection_id: str,
    tool_name: str,
    snapshot_ordinal: int,
) -> str:
    normalized_server_id = _required_text(server_selection_id)
    normalized_tool_name = _required_text(tool_name)

    if snapshot_ordinal < 0:
        raise ValueError("snapshot_ordinal must be non-negative")

    payload = (
        f"{normalized_server_id}\0"
        f"{normalized_tool_name}\0"
        f"{snapshot_ordinal}"
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()[:20]


class CollectedTool(_StrictModel):
    tool_id: str = Field(pattern=r"^[0-9a-f]{20}$")
    metadata: ToolMetadata
    activation: ToolActivationAssessment

    @model_validator(mode="after")
    def validate_tool_pair(self) -> CollectedTool:
        if self.metadata.tool_name != self.activation.tool_name:
            raise ValueError(
                "activation tool_name must match metadata tool_name"
            )

        return self


class LocalCleanupResult(_StrictModel):
    status: LocalCleanupStatus
    issues: list[DynamicScanIssue] = Field(default_factory=list)


class RemoteSessionTerminationResult(_StrictModel):
    status: RemoteSessionTerminationStatus
    safe_basis_code: str | None = None
    issues: list[DynamicScanIssue] = Field(default_factory=list)


class CleanupResult(_StrictModel):
    local_cleanup: LocalCleanupResult
    remote_session_termination: RemoteSessionTerminationResult


class McpServerImplementation(_StrictModel):
    name: str = Field(min_length=1)
    version: str | None = None


class McpProtocolMetadata(_StrictModel):
    protocol_version: str | None = None
    server_implementation: McpServerImplementation | None = None


class McpSnapshotResult(_StrictModel):
    server_summary: McpServerSummary
    protocol_version: str | None = None
    server_implementation: McpServerImplementation | None = None
    tools: list[ToolMetadata] = Field(default_factory=list)
    issues: list[DynamicScanIssue] = Field(default_factory=list)
    cleanup: CleanupResult


class DynamicScanTimeouts(_StrictModel):
    stdio_start_seconds: float = Field(
        default=10.0,
        gt=0,
        allow_inf_nan=False,
    )
    connect_seconds: float = Field(
        default=30.0,
        gt=0,
        allow_inf_nan=False,
    )
    initialize_seconds: float = Field(
        default=30.0,
        gt=0,
        allow_inf_nan=False,
    )
    list_tools_page_seconds: float = Field(
        default=30.0,
        gt=0,
        allow_inf_nan=False,
    )
    remote_session_termination_seconds: float = Field(
        default=5.0,
        gt=0,
        allow_inf_nan=False,
    )
    local_cleanup_seconds: float = Field(
        default=5.0,
        gt=0,
        allow_inf_nan=False,
    )


class DynamicScanStageResult(_StrictModel):
    stage: DynamicScanStage
    status: DynamicStageStatus


class DynamicScanResult(_StrictModel):
    status: DynamicScanStatus
    target: McpServerSummary
    stages: list[DynamicScanStageResult] = Field(default_factory=list)
    issues: list[DynamicScanIssue] = Field(default_factory=list)
    protocol_metadata: McpProtocolMetadata | None = None
    collected_tools: list[CollectedTool] = Field(default_factory=list)
    cleanup: CleanupResult
    scan_result: ScanResult | None = None

    @model_validator(mode="after")
    def validate_dynamic_result(self) -> DynamicScanResult:
        stage_names = [stage.stage for stage in self.stages]
        if len(stage_names) != len(set(stage_names)):
            raise ValueError("dynamic scan stages must be unique")

        for item in self.collected_tools:
            if item.activation.product != self.target.product:
                raise ValueError(
                    "tool activation product must match target product"
                )
            if item.metadata.server_name != self.target.server_name:
                raise ValueError(
                    "tool metadata server_name must match target server_name"
                )

        if self.scan_result is not None:
            if self.scan_result.scan_type != "dynamic":
                raise ValueError("scan_result must use dynamic scan_type")
            if self.scan_result.source_type != "mcp_server":
                raise ValueError("scan_result must use mcp_server source_type")

            collected_metadata = [
                item.metadata for item in self.collected_tools
            ]
            if self.scan_result.tools != collected_metadata:
                raise ValueError(
                    "scan_result tools must match collected tool metadata"
                )

        return self


def _required_text(value: str) -> str:
    normalized = value.strip()

    if not normalized:
        raise ValueError("required text must not be empty")

    return normalized


def _http_url(value: str) -> str:
    normalized = _required_text(value)
    parsed = urlsplit(normalized)

    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("URL must use HTTP or HTTPS and include a host")

    return normalized
