from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.models import ToolMetadata


JsonDict = dict[str, Any]


class ToolCollectionError(Exception):
    """
    tools.json 문서를 ToolMetadata 목록으로 변환하지 못했을 때 발생하는 예외.

    CLI나 scanner 쪽에서는 이 예외를 잡아서 사용자에게
    어떤 입력 파일이 잘못되었는지 명확히 보여주면 된다.
    """


def load_tools_json(
    path: str | Path,
    *,
    default_server_name: str = "unknown-server",
) -> list[ToolMetadata]:
    """
    tools.json 파일을 읽어서 list[ToolMetadata]로 변환한다.

    이 함수는 파일 I/O까지 담당한다.

    지원하는 대표 입력 형태:

    1. 권장 fixture 형태
       {
         "server_name": "demo-server",
         "tools": [
           {"name": "search", "description": "..."}
         ]
       }

    2. MCP tools/list 결과에 가까운 형태
       {
         "tools": [
           {"name": "search", "description": "..."}
         ]
       }

    3. JSON-RPC tools/list 응답을 저장한 형태
       {
         "jsonrpc": "2.0",
         "id": 1,
         "result": {
           "tools": [
             {"name": "search", "description": "..."}
           ]
         }
       }

    4. 도구 배열만 있는 단순 형태
       [
         {"name": "search", "description": "..."}
       ]
    """
    file_path = Path(path)

    if not file_path.exists():
        raise ToolCollectionError(f"tools.json file not found: {file_path}")

    if not file_path.is_file():
        raise ToolCollectionError(f"path is not a file: {file_path}")

    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ToolCollectionError(f"failed to read tools.json: {file_path}") from exc

    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ToolCollectionError(
            f"invalid JSON file: {file_path} "
            f"(line={exc.lineno}, column={exc.colno})"
        ) from exc

    return parse_tools_document(
        document,
        source=str(file_path),
        default_server_name=default_server_name,
    )


def collect_from_tools_json(
    path: str | Path,
    *,
    default_server_name: str = "unknown-server",
) -> list[ToolMetadata]:
    """
    CLI가 기대하는 이름으로 tools.json collector를 노출한다.

    load_tools_json이 실제 구현이고, 이 함수는 호출부 호환성을 위한 얇은 alias다.
    """
    return load_tools_json(
        path,
        default_server_name=default_server_name,
    )


def parse_tools_document(
    document: Any,
    *,
    source: str | None = None,
    default_server_name: str = "unknown-server",
) -> list[ToolMetadata]:
    """
    이미 JSON으로 파싱된 document를 list[ToolMetadata]로 변환한다.

    파일을 읽지 않기 때문에 unit test에서 사용하기 좋다.

    예:
        tools = parse_tools_document(
            {
                "server_name": "demo-server",
                "tools": [
                    {"name": "search", "description": "Search documents"}
                ],
            },
            source="tests/fixtures/benign_tools.json",
        )
    """
    extraction = _extract_tools_document(
        document,
        default_server_name=default_server_name,
    )

    server_name = extraction["server_name"]
    raw_tools = extraction["tools"]

    tools: list[ToolMetadata] = []

    for index, raw_tool in enumerate(raw_tools):
        if not isinstance(raw_tool, Mapping):
            raise ToolCollectionError(
                f"tool item must be an object. "
                f"source={source or '<memory>'}, index={index}"
            )

        raw_tool_dict = dict(raw_tool)

        try:
            tool = ToolMetadata.from_mcp_tool(
                raw_tool=raw_tool_dict,
                server_name=server_name,
                source=source,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            tool_name = raw_tool_dict.get("name") or raw_tool_dict.get("tool_name") or "<missing>"
            raise ToolCollectionError(
                f"invalid tool metadata. "
                f"source={source or '<memory>'}, "
                f"index={index}, "
                f"tool={tool_name}"
            ) from exc

        tools.append(tool)

    return tools


def _extract_tools_document(
    document: Any,
    *,
    default_server_name: str,
) -> JsonDict:
    """
    다양한 tools.json 형태에서 server_name과 tools 배열을 추출한다.

    반환:
        {
            "server_name": "...",
            "tools": [...]
        }
    """
    if isinstance(document, list):
        return {
            "server_name": default_server_name,
            "tools": document,
        }

    if not isinstance(document, Mapping):
        raise ToolCollectionError(
            "tools document root must be an object or an array"
        )

    document_dict = dict(document)

    # JSON-RPC tools/list 응답을 파일로 저장한 경우:
    #
    # {
    #   "jsonrpc": "2.0",
    #   "id": 1,
    #   "result": {
    #     "tools": [...]
    #   }
    # }
    if isinstance(document_dict.get("result"), Mapping):
        result = dict(document_dict["result"])

        if "tools" in result:
            server_name = _extract_server_name(
                document_dict,
                default_server_name=default_server_name,
            )

            return {
                "server_name": server_name,
                "tools": _ensure_tools_list(result.get("tools")),
            }

    # 일반 fixture 형태:
    #
    # {
    #   "server_name": "demo-server",
    #   "tools": [...]
    # }
    if "tools" in document_dict:
        server_name = _extract_server_name(
            document_dict,
            default_server_name=default_server_name,
        )

        return {
            "server_name": server_name,
            "tools": _ensure_tools_list(document_dict.get("tools")),
        }

    raise ToolCollectionError(
        "tools document must contain a 'tools' array "
        "or a JSON-RPC 'result.tools' array"
    )


def _extract_server_name(
    document: Mapping[str, Any],
    *,
    default_server_name: str,
) -> str:
    """
    document에서 server 이름 후보를 찾는다.

    우선순위:
    1. server_name
    2. serverName
    3. server
    4. name
    5. default_server_name
    """
    candidates = (
        document.get("server_name"),
        document.get("serverName"),
        document.get("server"),
        document.get("name"),
        default_server_name,
    )

    for candidate in candidates:
        if candidate is None:
            continue

        server_name = str(candidate).strip()

        if server_name:
            return server_name

    return "unknown-server"


def _ensure_tools_list(value: Any) -> list[Any]:
    """
    tools 값이 list인지 검증한다.
    """
    if value is None:
        raise ToolCollectionError("'tools' field is required")

    if not isinstance(value, list):
        raise ToolCollectionError("'tools' must be an array")

    return value
