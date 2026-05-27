from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


class ConfigLoadError(Exception):
    """
    MCP config 파일을 읽거나 파싱하거나 구조화하지 못했을 때 발생하는 예외.

    왜 별도 예외를 만들었나?
    - CLI에서 사용자에게 "config 파일 문제"라고 명확히 보여주기 위해서.
    - JSONDecodeError, OSError, TypeError 같은 내부 예외를 그대로 노출하지 않기 위해서.
    """


@dataclass(frozen=True)
class McpServerConfig:
    """
    MCP config 안의 서버 설정 1개를 표현하는 모델.

    예를 들어 config 파일에 이런 항목이 있다면:

        "filesystem": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Work"],
          "env": {"FILESYSTEM_ROOT": "C:\\Work"}
        }

    이것을 다음처럼 구조화한다:

        McpServerConfig(
            server_name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "C:\\Work"],
            env={"FILESYSTEM_ROOT": "C:\\Work"},
            raw={...},
            source="..."
        )

    이 모델은 ToolMetadata와 다르다.

    ToolMetadata:
        MCP tool 하나의 metadata를 표현한다.

    McpServerConfig:
        MCP server 실행/연결 설정 하나를 표현한다.
    """

    server_name: str

    # 로컬 MCP 서버를 실행할 때 사용할 command.
    # 예: "npx", "node", "python", "uvx"
    command: str | None = None

    # command에 넘길 인자 목록.
    # 예: ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Work"]
    args: list[str] = field(default_factory=list)

    # 환경변수.
    # Phase 2의 MCP01 Secret Exposure Scanner에서 중요한 분석 대상이 된다.
    env: dict[str, str] = field(default_factory=dict)

    # 작업 디렉터리. config에 cwd가 있을 수도 있고 없을 수도 있다.
    cwd: str | None = None

    # 원본 server config 전체를 보존한다.
    # 우리가 아직 모델링하지 않은 필드도 나중 detector가 분석할 수 있게 하기 위함.
    raw: JsonDict = field(default_factory=dict)

    # 이 설정이 나온 파일 경로.
    source: str | None = None

    @property
    def has_env(self) -> bool:
        """
        env 값이 하나라도 있는지 확인한다.

        MCP01 Secret Exposure Scanner에서 빠른 필터링용으로 쓸 수 있다.
        """
        return len(self.env) > 0

    @property
    def command_line(self) -> list[str]:
        """
        command와 args를 합쳐 실행 명령 형태로 보여준다.

        실제 실행하지 않는다.
        단지 report나 테스트에서 보기 좋게 쓰기 위한 값이다.

        예:
            command="npx"
            args=["-y", "server"]

            결과:
            ["npx", "-y", "server"]
        """
        if not self.command:
            return []

        return [self.command, *self.args]

    def to_safe_dict(self) -> JsonDict:
        """
        로그나 report에 안전하게 표시하기 위한 dict를 만든다.

        env 값은 민감할 수 있으므로 value를 그대로 내보내지 않는다.
        대신 env key 목록만 보여준다.

        예:
            {"GITHUB_TOKEN": "FAKE_..."}  -> ["GITHUB_TOKEN"]
        """
        return {
            "server_name": self.server_name,
            "command": self.command,
            "args": list(self.args),
            "env_keys": sorted(self.env.keys()),
            "cwd": self.cwd,
            "source": self.source,
        }


def load_mcp_config(
    path: str | Path,
) -> list[McpServerConfig]:
    """
    MCP config JSON 파일을 읽어서 list[McpServerConfig]로 변환한다.

    이 함수가 하는 일:
    1. 파일 존재 확인
    2. JSON 읽기
    3. mcpServers 항목 찾기
    4. 각 server 설정을 McpServerConfig로 변환

    이 함수가 하지 않는 일:
    - MCP 서버 실행
    - MCP 서버 연결
    - tools/list 호출
    - secret 탐지
    - redaction
    """
    file_path = Path(path)

    if not file_path.exists():
        raise ConfigLoadError(f"MCP config file not found: {file_path}")

    if not file_path.is_file():
        raise ConfigLoadError(f"MCP config path is not a file: {file_path}")

    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigLoadError(f"failed to read MCP config file: {file_path}") from exc

    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(
            f"invalid JSON MCP config: {file_path} "
            f"(line={exc.lineno}, column={exc.colno})"
        ) from exc

    return parse_mcp_config_document(
        document,
        source=str(file_path),
    )


def parse_mcp_config_document(
    document: Any,
    *,
    source: str | None = None,
) -> list[McpServerConfig]:
    """
    이미 JSON으로 파싱된 MCP config document를 list[McpServerConfig]로 변환한다.

    파일을 읽지 않기 때문에 unit test에서 쓰기 좋다.

    지원하는 기본 형태:
        {
          "mcpServers": {
            "server-name": {
              "command": "...",
              "args": [...],
              "env": {...}
            }
          }
        }
    """
    if not isinstance(document, Mapping):
        raise ConfigLoadError("MCP config root must be an object")

    document_dict = dict(document)

    raw_servers = _extract_mcp_servers(document_dict)

    configs: list[McpServerConfig] = []

    for server_name, raw_server_config in raw_servers.items():
        if not isinstance(server_name, str):
            raise ConfigLoadError("MCP server name must be a string")

        if not isinstance(raw_server_config, Mapping):
            raise ConfigLoadError(
                f"MCP server config must be an object. server={server_name}"
            )

        config = _to_mcp_server_config(
            server_name=server_name,
            raw_server_config=dict(raw_server_config),
            source=source,
        )

        configs.append(config)

    return configs


def _extract_mcp_servers(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    """
    MCP config 문서에서 mcpServers 항목을 찾는다.

    기본은 mcpServers만 지원한다.

    왜 mcp_servers도 같이 허용하나?
    - 테스트나 내부 fixture에서 snake_case로 작성하는 실수를 어느 정도 받아주기 위해서.
    - 하지만 팀 표준은 mcpServers로 잡는 것이 좋다.
    """
    raw_servers = document.get("mcpServers")

    if raw_servers is None:
        raw_servers = document.get("mcp_servers")

    if raw_servers is None:
        raise ConfigLoadError("MCP config must contain 'mcpServers'")

    if not isinstance(raw_servers, Mapping):
        raise ConfigLoadError("'mcpServers' must be an object")

    return raw_servers


def _to_mcp_server_config(
    *,
    server_name: str,
    raw_server_config: JsonDict,
    source: str | None,
) -> McpServerConfig:
    """
    server config dict 하나를 McpServerConfig로 변환한다.
    """
    normalized_server_name = server_name.strip()

    if not normalized_server_name:
        raise ConfigLoadError("MCP server name must not be empty")

    command = _optional_string(
        raw_server_config.get("command"),
        field_name=f"{normalized_server_name}.command",
    )

    args = _string_list(
        raw_server_config.get("args", []),
        field_name=f"{normalized_server_name}.args",
    )

    env = _string_dict(
        raw_server_config.get("env", {}),
        field_name=f"{normalized_server_name}.env",
    )

    cwd = _optional_string(
        raw_server_config.get("cwd"),
        field_name=f"{normalized_server_name}.cwd",
    )

    return McpServerConfig(
        server_name=normalized_server_name,
        command=command,
        args=args,
        env=env,
        cwd=cwd,
        raw=dict(raw_server_config),
        source=source,
    )


def _optional_string(
    value: Any,
    *,
    field_name: str,
) -> str | None:
    """
    None 또는 문자열만 허용한다.

    command/cwd 같은 필드는 없을 수도 있으므로 None을 허용한다.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise ConfigLoadError(f"{field_name} must be a string")

    normalized = value.strip()

    return normalized or None


def _string_list(
    value: Any,
    *,
    field_name: str,
) -> list[str]:
    """
    문자열 리스트인지 검증한다.

    args는 command 인자 목록이므로 list[str]이어야 한다.
    """
    if value is None:
        return []

    if not isinstance(value, list):
        raise ConfigLoadError(f"{field_name} must be an array")

    result: list[str] = []

    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigLoadError(f"{field_name}[{index}] must be a string")

        result.append(item)

    return result


def _string_dict(
    value: Any,
    *,
    field_name: str,
) -> dict[str, str]:
    """
    문자열 key/value dict인지 검증한다.

    env는 환경변수이므로 dict[str, str] 형태가 가장 안전하다.
    """
    if value is None:
        return {}

    if not isinstance(value, Mapping):
        raise ConfigLoadError(f"{field_name} must be an object")

    result: dict[str, str] = {}

    for key, item in value.items():
        if not isinstance(key, str):
            raise ConfigLoadError(f"{field_name} keys must be strings")

        if not isinstance(item, str):
            raise ConfigLoadError(f"{field_name}.{key} must be a string")

        result[key] = item

    return result