from __future__ import annotations

import hashlib
import json

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Literal, Self

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


JsonDict = dict[str, Any]

Severity = Literal["critical", "high", "medium", "low", "info"]
Confidence = Literal["high", "medium", "low"]


class ToolMetadata(BaseModel):
    """
    MCP tool metadata를 MCP-AuditGuard 내부에서 분석하기 좋은 표준 형태로 담는 모델.

    역할:
    - tools.json 또는 MCP tools/list 응답에 들어있는 tool 1개를 표현한다.
    - detector들은 dict를 직접 뒤지지 않고 이 모델을 기준으로 분석한다.
    - baseline diff를 위해 안정적인 metadata_hash를 가진다.
    - 원본 정보 손실을 막기 위해 raw에 원본 tool dict를 보존한다.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        validate_by_name=True,
        validate_by_alias=True,
    )

    server_name: str = Field(
        ...,
        min_length=1,
        description="이 tool을 제공한 MCP server 이름",
    )

    tool_name: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("tool_name", "name"),
        serialization_alias="name",
        description="MCP tool의 실제 name",
    )

    title: str | None = Field(
        default=None,
        description="사용자에게 표시될 수 있는 tool 제목",
    )

    description: str | None = Field(
        default=None,
        description="tool 설명. MCP03 Tool Poisoning의 주요 분석 대상",
    )

    input_schema: JsonDict | None = Field(
        default=None,
        validation_alias=AliasChoices("input_schema", "inputSchema"),
        serialization_alias="inputSchema",
        description="tool 입력 JSON Schema",
    )

    output_schema: JsonDict | None = Field(
        default=None,
        validation_alias=AliasChoices("output_schema", "outputSchema"),
        serialization_alias="outputSchema",
        description="tool 출력 JSON Schema",
    )

    annotations: JsonDict | None = Field(
        default=None,
        description="MCP tool annotations",
    )

    meta: JsonDict | None = Field(
        default=None,
        validation_alias=AliasChoices("meta", "_meta"),
        serialization_alias="_meta",
        description="MCP 원본의 _meta 필드를 Python 내부에서 meta라는 이름으로 사용",
    )

    raw: JsonDict = Field(
        ...,
        description="원본 MCP tool dict 전체. 모델에 없는 필드까지 보존하기 위해 필요",
    )

    source: str | None = Field(
        default=None,
        description="이 metadata가 나온 파일 경로 또는 수집 위치",
    )

    metadata_hash: str = Field(
        default="",
        description="baseline diff를 위한 안정적인 SHA-256 hash",
    )

    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="metadata 수집 시각",
    )

    @field_validator("server_name", "tool_name")
    @classmethod
    def strip_required_names(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("server_name and tool_name must not be empty")

        return value

    @field_validator("title", "description", "source")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("collected_at")
    @classmethod
    def ensure_timezone_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    @field_validator("metadata_hash")
    @classmethod
    def validate_metadata_hash_format(cls, value: str) -> str:
        if not value:
            return value

        if len(value) != 64:
            raise ValueError("metadata_hash must be a SHA-256 hex string")

        try:
            int(value, 16)
        except ValueError as exc:
            raise ValueError("metadata_hash must be a SHA-256 hex string") from exc

        return value

    @model_validator(mode="after")
    def fill_metadata_hash(self) -> Self:
        if not self.metadata_hash:
            self.metadata_hash = self.build_metadata_hash()

        return self

    @property
    def target(self) -> str:
        """
        finding/report에서 사용할 표준 target 이름.

        예:
        - github.search_repo
        - filesystem.read_file
        - demo-server.search
        """
        return f"{self.server_name}.{self.tool_name}"

    def stable_hash_payload(self) -> JsonDict:
        """
        metadata_hash 계산에 사용할 안정적인 payload.

        source와 collected_at은 scan 시점마다 달라질 수 있으므로 제외한다.
        raw는 모델에 없는 커스텀 필드 변경까지 잡기 위해 포함한다.
        """
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "title": self.title,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "annotations": self.annotations,
            "meta": self.meta,
            "raw": self.raw,
        }

    def build_metadata_hash(self) -> str:
        canonical_json = json.dumps(
            self.stable_hash_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def to_mcp_tool_dict(self) -> JsonDict:
        """
        내부 모델을 MCP tools.json에 가까운 형태로 내보낼 때 사용한다.

        내부 Python 필드명:
        - tool_name
        - input_schema
        - output_schema
        - meta

        MCP 스타일 출력:
        - name
        - inputSchema
        - outputSchema
        - _meta
        """
        return self.model_dump(
            by_alias=True,
            exclude_none=True,
            exclude={
                "server_name",
                "source",
                "metadata_hash",
                "collected_at",
                "raw",
            },
        )

    @classmethod
    def from_mcp_tool(
        cls,
        raw_tool: JsonDict,
        *,
        server_name: str = "unknown-server",
        source: str | None = None,
        collected_at: datetime | None = None,
    ) -> Self:
        """
        MCP tools.json 안의 tool dict 하나를 ToolMetadata로 변환한다.

        tool_collector.py에서는 이 메서드를 사용하면 된다.
        """
        if not isinstance(raw_tool, dict):
            raise TypeError("raw_tool must be a dict")

        tool_name = raw_tool.get("name") or raw_tool.get("tool_name")

        if not tool_name:
            raise ValueError("MCP tool must contain 'name'")

        data: JsonDict = {
            "server_name": server_name,
            "tool_name": tool_name,
            "title": raw_tool.get("title"),
            "description": raw_tool.get("description"),
            "input_schema": _get_first_existing(raw_tool, "inputSchema", "input_schema"),
            "output_schema": _get_first_existing(raw_tool, "outputSchema", "output_schema"),
            "annotations": raw_tool.get("annotations"),
            "meta": _get_first_existing(raw_tool, "_meta", "meta"),
            "raw": dict(raw_tool),
            "source": source,
        }

        if collected_at is not None:
            data["collected_at"] = collected_at

        return cls.model_validate(data)


class Finding(BaseModel):
    """
    detector가 발견한 보안 이슈 1개를 표현하는 모델.

    역할:
    - detector는 suspicious pattern을 발견하면 Finding을 반환한다.
    - scanner는 여러 detector의 Finding을 모은다.
    - report/CLI/baseline diff는 Finding 목록을 기준으로 동작한다.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    id: str = Field(
        ...,
        min_length=1,
        description="Finding 종류를 식별하는 ID",
    )

    category: str = Field(
        ...,
        min_length=1,
        description="tool_poisoning, obfuscation, integrity 등 큰 분류",
    )

    owasp: str = Field(
        ...,
        min_length=1,
        description="OWASP MCP Top 10 항목. 예: MCP03",
    )

    severity: Severity = Field(
        ...,
        description="위험도",
    )

    confidence: Confidence = Field(
        ...,
        description="탐지 확신도",
    )

    title: str = Field(
        ...,
        min_length=1,
        description="사람이 읽을 수 있는 finding 제목",
    )

    tool_name: str | None = Field(
        default=None,
        description="Finding target MCP tool name",
    )

    target: str = Field(
        ...,
        min_length=1,
        description="문제가 발견된 대상. 보통 server_name.tool_name",
    )

    location: str = Field(
        ...,
        min_length=1,
        description="문제가 발견된 위치. 예: description, input_schema.properties.query.description",
    )

    evidence: str = Field(
        ...,
        description="탐지 근거 문자열. secret redaction 대상",
    )

    redacted: bool = Field(
        default=False,
        description="evidence에 redaction이 적용되었는지 여부",
    )

    recommendation: str = Field(
        ...,
        min_length=1,
        description="해결 또는 완화 방법",
    )

    fingerprint: str = Field(
        default="",
        description="같은 finding을 추적하기 위한 안정적인 fingerprint",
    )

    @field_validator("id", "category", "owasp", "title", "target", "location", "recommendation")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("required text fields must not be empty")

        return value

    @field_validator("evidence")
    @classmethod
    def normalize_evidence(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def fill_fingerprint(self) -> Self:
        if not self.fingerprint:
            self.fingerprint = self.build_fingerprint()

        return self

    def stable_fingerprint_payload(self) -> JsonDict:
        """
        같은 finding인지 판단하기 위한 payload.

        severity/confidence는 제외한다.
        이유:
        - rule tuning으로 severity/confidence가 바뀌어도 같은 위치의 같은 문제일 수 있음
        """
        return {
            "id": self.id,
            "category": self.category,
            "owasp": self.owasp,
            "target": self.target,
            "location": self.location,
            "evidence": self.evidence,
        }

    def build_fingerprint(self) -> str:
        canonical_json = json.dumps(
            self.stable_fingerprint_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class Detector(ABC):
    """
    모든 detector가 따라야 하는 공통 인터페이스.

    scanner는 detector 내부 구현을 몰라도 된다.
    scanner는 detect(tool)을 호출하고 list[Finding]만 받으면 된다.
    """

    id: str
    category: str

    @abstractmethod
    def detect(self, tool: ToolMetadata) -> list[Finding]:
        """
        ToolMetadata 1개를 분석하고 Finding 목록을 반환한다.

        finding이 없으면 빈 리스트를 반환한다.
        detector 내부에서 예외를 직접 삼킬지, scanner에서 처리할지는 scanner.py에서 정책을 정한다.
        """
        raise NotImplementedError


def _get_first_existing(data: JsonDict, *keys: str) -> Any:
    """
    여러 key 후보 중 실제로 존재하는 첫 번째 값을 반환한다.

    dict.get()만 사용하면 값이 None일 때와 key가 없을 때를 구분하기 어렵다.
    """
    for key in keys:
        if key in data:
            return data[key]

    return None
