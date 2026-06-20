from __future__ import annotations

"""
MCP tool metadata baseline 저장 모듈.

baseline은 "현재 정상으로 판단한 MCP tool metadata 상태"를 JSON으로 저장한다.
나중에 같은 tool을 다시 스캔했을 때 description, schema, annotations 등이
바뀌었는지 hash로 비교할 수 있다.

Member5 담당 관점:
- metadata를 안정적인 dict로 정규화한다.
- 정규화된 metadata를 SHA-256 hash로 변환한다.
- baseline JSON을 저장/로드한다.

보안적 의미:
- MCP Tool Poisoning은 tool 설명이나 schema가 나중에 바뀌며 발생할 수 있다.
- baseline은 이런 metadata rug-pull 시나리오를 탐지하기 위한 기준점이다.
- embedding vector 같은 큰 파생 데이터는 저장하지 않고, 실제 비교 대상인
  metadata와 hash만 저장해 재현성과 관리 용이성을 유지한다.
"""

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models import ToolMetadata


BASELINE_VERSION = 1


def normalize_tool(tool: "ToolMetadata") -> dict[str, Any]:
    """
    baseline hash에 사용할 ToolMetadata 필드를 안정적인 dict로 정규화한다.

    Args:
        tool: baseline에 포함할 MCP ToolMetadata 객체 또는 테스트용 mock 객체

    Returns:
        hash 계산과 baseline 저장에 사용할 metadata dict

    Security Note:
        description, input_schema, output_schema, annotations는 Tool Poisoning 문구가
        숨어들기 쉬운 핵심 metadata 영역이다. 이 필드들이 바뀌면 같은 tool이라도
        다른 hash가 생성되어 diff 단계에서 변경 finding을 만들 수 있다.

    유지보수 포인트:
        baseline 비교 범위를 넓히려면 이 함수에 필드를 추가해야 한다. 예를 들어
        `_meta`나 `title`까지 rug-pull 탐지 대상으로 삼고 싶다면 이곳과 관련 테스트를
        함께 수정한다.
    """
    return {
        "server_name": tool.server_name,
        "tool_name": tool.tool_name,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "output_schema": tool.output_schema,
        "annotations": tool.annotations,
    }


def hash_tool_metadata(tool: "ToolMetadata") -> str:
    """
    정규화된 tool metadata의 안정적인 SHA-256 hash를 생성한다.

    Args:
        tool: hash를 생성할 MCP ToolMetadata 객체

    Returns:
        `normalize_tool` 결과를 기반으로 생성한 SHA-256 hex 문자열

    Security Note:
        `sort_keys=True`를 사용해 dict key 순서 차이 때문에 hash가 달라지는 문제를
        방지한다. `ensure_ascii=False`는 한국어 등 비ASCII metadata가 들어와도 사람이
        읽을 수 있는 형태를 유지하며, 동일 문자열에 대해 안정적인 hash를 만든다.
    """
    normalized = normalize_tool(tool)
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_baseline(tools: list["ToolMetadata"]) -> dict[str, Any]:
    """
    ToolMetadata 목록으로 baseline JSON 구조를 생성한다.

    Args:
        tools: 현재 스캔에서 수집된 MCP tool metadata 목록

    Returns:
        version과 tools map을 포함한 baseline dict

    구조:
        {
          "version": 1,
          "tools": {
            "server:tool": {
              "hash": "...",
              "metadata": {...}
            }
          }
        }

    보안적 의미:
        key를 `server_name:tool_name`으로 고정하면 같은 이름의 tool이 다른 서버에서
        제공되는 경우를 구분할 수 있다. 이는 tool shadowing이나 metadata 변경 추적에서
        중요한 기준이다.
    """
    baseline: dict[str, Any] = {
        "version": BASELINE_VERSION,
        "tools": {},
    }

    for tool in tools:
        # baseline diff는 이 key를 기준으로 added/removed/modified를 판단한다.
        key = f"{tool.server_name}:{tool.tool_name}"
        baseline["tools"][key] = {
            "hash": hash_tool_metadata(tool),
            "metadata": normalize_tool(tool),
        }

    return baseline


def save_baseline(tools: list["ToolMetadata"], path: str) -> None:
    """
    현재 tool metadata 상태를 baseline JSON 파일로 저장한다.

    Args:
        tools: 저장할 MCP tool metadata 목록
        path: baseline JSON을 쓸 파일 경로

    예외:
        파일 쓰기 권한 문제나 경로 오류는 `Path.write_text`의 OSError로 전파된다.
        CLI/service 계층에서 사용자 친화적인 메시지로 변환한다.
    """
    baseline_path = Path(path)
    baseline = create_baseline(tools)
    baseline_path.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_baseline(path: str) -> dict[str, Any]:
    """
    baseline JSON 파일을 읽어 dict로 반환한다.

    Args:
        path: 이전에 저장한 baseline JSON 경로

    Returns:
        baseline document dict

    예외:
        파일이 없거나 JSON 파싱에 실패하면 상위 service 계층에서 잡아
        `ScanServiceError`로 변환한다.
    """
    baseline_path = Path(path)
    return json.loads(baseline_path.read_text(encoding="utf-8"))
