"""
AuditGuard baseline storage utilities.

이 모듈은 MCP tool metadata의 현재 상태를 baseline JSON으로 저장하고,
나중에 metadata 변경 여부를 비교할 수 있도록 안정적인 hash를 생성한다.

팀원 5 담당 영역:
- ToolMetadata 정규화
- metadata SHA-256 hash 생성
- baseline JSON 생성
- baseline 파일 저장 및 로드

보안적 의미:
MCP Tool Poisoning은 처음에는 정상처럼 보이다가 나중에 description, schema,
annotations 같은 metadata에 악성 지시문이 추가되는 방식으로 발생할 수 있다.
baseline은 이런 metadata rug-pull 시나리오를 추적하기 위한 기준점이다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models import ToolMetadata


# baseline 파일 구조의 버전이다.
# 나중에 JSON 구조가 바뀌면 version 값을 올려서 이전 baseline과 구분할 수 있다.
BASELINE_VERSION = 1


def normalize_tool(tool: "ToolMetadata") -> dict[str, Any]:
    """
    baseline hash 계산에 사용할 tool metadata만 안정적인 dict로 정리한다.

    Args:
        tool: baseline에 포함할 MCP ToolMetadata 객체.

    Returns:
        hash 계산과 baseline 저장에 사용할 정규화된 metadata dict.

    Security Note:
        description, input_schema, output_schema, annotations는 악성 지시문이 숨겨질 수 있는
        주요 metadata 위치다. 이 필드를 baseline에 포함해야 나중에 변경을 감지할 수 있다.

    왜 normalize 단계가 필요한가?
    - ToolMetadata에는 수집 시각, source 같은 실행 시점마다 달라질 수 있는 값이 있을 수 있다.
    - 그런 값까지 hash에 포함하면 실제 보안상 의미 있는 변경이 없어도 hash가 매번 바뀐다.
    - 그래서 baseline 비교에 필요한 핵심 metadata만 골라 같은 순서의 dict로 만든다.

    포함하는 값:
    - server_name: MCP server 이름
    - tool_name: MCP tool 이름
    - description: Tool Poisoning이 가장 자주 숨겨지는 설명 필드
    - input_schema/output_schema: schema poisoning 또는 응답 구조 변경 확인용
    - annotations: 권한 힌트나 부가 metadata 변경 확인용

    포함하지 않는 값:
    - embedding vector 또는 semantic detector의 내부 계산 결과

    embedding vector를 baseline에 저장하지 않는 이유:
    - vector는 용량이 크다.
    - 모델 버전에 따라 같은 텍스트도 다른 vector가 나올 수 있다.
    - baseline diff의 목적은 metadata 변경 감지이지 embedding cache 저장이 아니다.
    - metadata 원문이나 민감정보가 vector 저장 정책과 섞이지 않도록 경계를 둔다.
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
    정규화된 tool metadata를 SHA-256 hash로 변환한다.

    Args:
        tool: 해시를 생성할 MCP ToolMetadata 객체.

    Returns:
        정규화된 tool metadata를 기반으로 생성한 SHA-256 hash 문자열.

    Security Note:
        metadata hash는 baseline diff 기능의 핵심 기준값이다.
        동일 tool의 description/schema/annotations가 바뀌면 hash가 달라지므로
        metadata rug-pull 또는 후속 Tool Poisoning 가능성을 추적할 수 있다.

    핵심 포인트:
    - json.dumps(..., sort_keys=True)를 사용해 dict key 순서가 달라도 같은 문자열이 나오게 한다.
    - ensure_ascii=False를 사용해 한글 등 비 ASCII 문자를 그대로 보존한다.
    - 이렇게 만든 canonical JSON 문자열을 sha256으로 계산한다.

    결과:
    - 동일 metadata는 동일 hash
    - description/schema/annotations 등이 바뀌면 다른 hash
    """
    normalized = normalize_tool(tool)
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_baseline(tools: list["ToolMetadata"]) -> dict[str, Any]:
    """
    현재 tool 목록을 baseline JSON 구조로 만든다.

    Args:
        tools: 현재 수집된 ToolMetadata 목록.

    Returns:
        version과 tools map을 포함한 baseline dict.

    Security Note:
        baseline은 "현재 승인 가능한 MCP tool metadata 상태"를 저장한다.
        이후 scan에서 같은 key의 hash가 달라지면 사용자가 metadata 변경을 검토할 수 있다.

    baseline 구조:
    {
      "version": 1,
      "tools": {
        "server:tool": {
          "hash": "...",
          "metadata": {...}
        }
      }
    }

    key를 "{server_name}:{tool_name}" 형식으로 만드는 이유:
    - 서로 다른 서버가 같은 tool 이름을 쓸 수 있다.
    - 서버명과 tool명을 합치면 baseline diff에서 tool을 안정적으로 식별할 수 있다.
    """
    baseline: dict[str, Any] = {
        "version": BASELINE_VERSION,
        "tools": {},
    }

    for tool in tools:
        # baseline diff engine이 added/removed/modified를 비교할 때 사용하는 고유 key다.
        key = f"{tool.server_name}:{tool.tool_name}"
        baseline["tools"][key] = {
            "hash": hash_tool_metadata(tool),
            "metadata": normalize_tool(tool),
        }

    return baseline


def save_baseline(tools: list["ToolMetadata"], path: str) -> None:
    """
    현재 tool metadata baseline을 JSON 파일로 저장한다.

    Args:
        tools: baseline으로 저장할 현재 ToolMetadata 목록.
        path: baseline JSON 파일을 저장할 경로.

    Returns:
        없음.

    Security Note:
        로컬 baseline 저장은 scan 결과를 외부로 전송하지 않고도 이후 변경 감지를 가능하게 한다.
        실제 API key나 token 값을 저장하지 않도록 metadata 수집/리포트 단계의 redaction 정책과 함께 사용해야 한다.

    CLI의 --save-baseline 옵션에서 호출된다.
    pathlib.Path를 사용해 macOS/Linux 환경에서 경로 처리를 단순하게 유지한다.
    """
    baseline_path = Path(path)
    baseline = create_baseline(tools)
    baseline_path.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_baseline(path: str) -> dict[str, Any]:
    """
    저장된 baseline JSON 파일을 읽어서 dict로 반환한다.

    Args:
        path: 이전에 저장한 baseline JSON 파일 경로.

    Returns:
        JSON에서 읽은 baseline dict.

    Security Note:
        이전 baseline을 정확히 로드해야 현재 metadata와의 차이를 비교할 수 있다.
        이 비교는 정상 상태 이후 악성 metadata가 삽입되는 rug-pull 흐름을 찾는 데 유용하다.

    CLI의 --baseline 옵션에서 호출된다.
    여기서는 JSON 구조 검증을 깊게 하지 않고, 파일 읽기와 JSON parsing만 담당한다.
    실제 비교 로직은 core.diff_engine.diff_baseline에서 수행한다.
    """
    baseline_path = Path(path)
    return json.loads(baseline_path.read_text(encoding="utf-8"))
