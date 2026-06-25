from __future__ import annotations

"""
MCP tool metadata baseline 저장 모듈.

baseline은 "정상으로 판단한 특정 시점의 MCP tool metadata 상태"를 저장한다.
이후 같은 tool을 다시 스캔했을 때 metadata hash를 비교해 추가/삭제/변경 여부를
확인할 수 있다.

Member5 담당 관점:
- ToolMetadata를 안정적인 dict로 정규화한다.
- 정규화된 metadata를 SHA-256 hash로 변환한다.
- baseline JSON을 저장하고 다시 로드한다.

보안적 의미:
- Tool Poisoning은 최초 등록 시점이 아니라 이후 metadata 변경으로 발생할 수 있다.
- baseline은 이런 metadata rug-pull 시나리오를 탐지하기 위한 기준점이다.
- embedding vector 같은 파생 데이터는 저장하지 않고, 비교 대상 metadata와 hash만
  저장해 용량/재현성/민감정보 노출 위험을 줄인다.
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
        description, schema, annotations는 Tool Poisoning 지시문이 숨어들기 쉬운 영역이다.
        이 필드들이 바뀌면 hash가 달라지고 diff_engine에서 변경 finding을 만들 수 있다.

    유지보수 포인트:
        `_meta`나 `title`까지 baseline 변경 감지 대상으로 삼으려면 이 함수와 관련
        테스트를 함께 수정해야 한다.
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

    `sort_keys=True`는 JSON key 순서 차이로 hash가 흔들리는 것을 막는다.
    `ensure_ascii=False`는 한국어 등 비ASCII metadata를 있는 그대로 직렬화해
    사람이 읽기 쉬운 baseline JSON을 유지한다.
    """
    normalized = normalize_tool(tool)
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_baseline(tools: list["ToolMetadata"]) -> dict[str, Any]:
    """
    ToolMetadata 목록으로 baseline document를 생성한다.

    baseline key는 `server_name:tool_name` 형식이다. 같은 tool 이름이라도 다른 MCP
    서버에서 제공될 수 있으므로 server_name을 함께 넣어 충돌을 줄인다.

    Returns:
        {
          "version": 1,
          "tools": {
            "server:tool": {"hash": "...", "metadata": {...}}
          }
        }
    """
    baseline: dict[str, Any] = {
        "version": BASELINE_VERSION,
        "tools": {},
    }

    for tool in tools:
        # diff_engine은 이 key 집합을 비교해 added/removed/modified를 판단한다.
        key = f"{tool.server_name}:{tool.tool_name}"
        baseline["tools"][key] = {
            "hash": hash_tool_metadata(tool),
            "metadata": normalize_tool(tool),
        }

    return baseline


def save_baseline(tools: list["ToolMetadata"], path: str) -> None:
    """
    현재 tool metadata 상태를 baseline JSON 파일로 저장한다.

    파일 쓰기 권한 문제나 경로 오류는 OSError로 전파된다. CLI/service 계층에서
    이 예외를 잡아 사용자 친화적인 메시지로 변환한다.
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

    파일 없음 또는 JSON 파싱 오류는 상위 service 계층에서 처리한다.
    """
    baseline_path = Path(path)
    return json.loads(baseline_path.read_text(encoding="utf-8"))
