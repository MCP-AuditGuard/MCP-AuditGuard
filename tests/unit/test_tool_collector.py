import json
from pathlib import Path

import pytest

from core.tool_collector import (
    ToolCollectionError,
    load_tools_json,
    parse_tools_document,
)


def test_parse_recommended_fixture_shape():
    document = {
        "server_name": "demo-server",
        "tools": [
            {
                "name": "search_file",
                "title": "Search File",
                "description": "Search files",
                "inputSchema": {"type": "object"},
                "_meta": {"version": "1.0"},
            }
        ],
    }

    tools = parse_tools_document(
        document,
        source="tests/fixtures/benign_tools.json",
    )

    assert len(tools) == 1

    tool = tools[0]
    assert tool.server_name == "demo-server"
    assert tool.tool_name == "search_file"
    assert tool.title == "Search File"
    assert tool.description == "Search files"
    assert tool.input_schema == {"type": "object"}
    assert tool.meta == {"version": "1.0"}
    assert tool.source == "tests/fixtures/benign_tools.json"
    assert tool.target == "demo-server.search_file"
    assert len(tool.metadata_hash) == 64


def test_parse_tools_without_server_name_uses_default():
    document = {
        "tools": [
            {
                "name": "search_file",
                "description": "Search files",
            }
        ]
    }

    tools = parse_tools_document(
        document,
        default_server_name="default-server",
    )

    assert len(tools) == 1
    assert tools[0].server_name == "default-server"
    assert tools[0].tool_name == "search_file"


def test_parse_json_rpc_tools_list_response():
    document = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": [
                {
                    "name": "read_file",
                    "description": "Read file content",
                    "inputSchema": {"type": "object"},
                }
            ]
        },
    }

    tools = parse_tools_document(
        document,
        default_server_name="jsonrpc-server",
    )

    assert len(tools) == 1
    assert tools[0].server_name == "jsonrpc-server"
    assert tools[0].tool_name == "read_file"
    assert tools[0].input_schema == {"type": "object"}


def test_parse_array_shape():
    document = [
        {
            "name": "search_file",
            "description": "Search files",
        },
        {
            "name": "read_file",
            "description": "Read files",
        },
    ]

    tools = parse_tools_document(
        document,
        default_server_name="array-server",
    )

    assert len(tools) == 2
    assert tools[0].server_name == "array-server"
    assert tools[0].tool_name == "search_file"
    assert tools[1].tool_name == "read_file"


def test_parse_document_requires_tools_array():
    document = {
        "server_name": "demo-server"
    }

    with pytest.raises(ToolCollectionError):
        parse_tools_document(document)


def test_parse_document_rejects_non_array_tools():
    document = {
        "server_name": "demo-server",
        "tools": {
            "name": "search_file"
        },
    }

    with pytest.raises(ToolCollectionError):
        parse_tools_document(document)


def test_parse_document_rejects_tool_without_name():
    document = {
        "server_name": "demo-server",
        "tools": [
            {
                "description": "Missing tool name"
            }
        ],
    }

    with pytest.raises(ToolCollectionError):
        parse_tools_document(document)


def test_load_tools_json_reads_file(tmp_path: Path):
    tools_json = tmp_path / "tools.json"

    tools_json.write_text(
        json.dumps(
            {
                "server_name": "file-server",
                "tools": [
                    {
                        "name": "search_file",
                        "description": "Search files",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tools = load_tools_json(tools_json)

    assert len(tools) == 1
    assert tools[0].server_name == "file-server"
    assert tools[0].tool_name == "search_file"
    assert tools[0].source == str(tools_json)


def test_load_tools_json_rejects_missing_file(tmp_path: Path):
    missing_file = tmp_path / "missing-tools.json"

    with pytest.raises(ToolCollectionError):
        load_tools_json(missing_file)


def test_load_tools_json_rejects_invalid_json(tmp_path: Path):
    invalid_json = tmp_path / "invalid-tools.json"
    invalid_json.write_text("{ invalid json", encoding="utf-8")

    with pytest.raises(ToolCollectionError):
        load_tools_json(invalid_json)


def test_metadata_hash_is_stable_for_same_tool_content():
    document_1 = {
        "server_name": "demo-server",
        "tools": [
            {
                "name": "search_file",
                "description": "Search files",
                "inputSchema": {"type": "object"},
            }
        ],
    }

    document_2 = {
        "tools": [
            {
                "inputSchema": {"type": "object"},
                "description": "Search files",
                "name": "search_file",
            }
        ],
        "server_name": "demo-server",
    }

    tool_1 = parse_tools_document(document_1)[0]
    tool_2 = parse_tools_document(document_2)[0]

    assert tool_1.metadata_hash == tool_2.metadata_hash