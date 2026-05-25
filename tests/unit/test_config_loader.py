import json
from pathlib import Path

import pytest

from core.config_loader import (
    ConfigLoadError,
    load_mcp_config,
    parse_mcp_config_document,
)


def test_parse_mcp_config_document_loads_servers():
    document = {
        "mcpServers": {
            "filesystem": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    "C:\\Work",
                ],
                "env": {
                    "FILESYSTEM_ROOT": "C:\\Work",
                },
            },
            "github": {
                "command": "node",
                "args": [
                    "server.js",
                ],
                "env": {
                    "GITHUB_TOKEN": "FAKE_GITHUB_TOKEN_FOR_TEST",
                },
            },
        }
    }

    configs = parse_mcp_config_document(
        document,
        source="tests/fixtures/mcp_config.json",
    )

    assert len(configs) == 2

    filesystem = configs[0]
    github = configs[1]

    assert filesystem.server_name == "filesystem"
    assert filesystem.command == "npx"
    assert filesystem.args == [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "C:\\Work",
    ]
    assert filesystem.env == {
        "FILESYSTEM_ROOT": "C:\\Work",
    }
    assert filesystem.command_line == [
        "npx",
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "C:\\Work",
    ]
    assert filesystem.source == "tests/fixtures/mcp_config.json"

    assert github.server_name == "github"
    assert github.command == "node"
    assert github.args == ["server.js"]
    assert github.env == {
        "GITHUB_TOKEN": "FAKE_GITHUB_TOKEN_FOR_TEST",
    }


def test_parse_mcp_config_document_accepts_empty_args_and_env():
    document = {
        "mcpServers": {
            "simple": {
                "command": "python",
            }
        }
    }

    configs = parse_mcp_config_document(document)

    assert len(configs) == 1
    assert configs[0].server_name == "simple"
    assert configs[0].command == "python"
    assert configs[0].args == []
    assert configs[0].env == {}
    assert configs[0].has_env is False


def test_parse_mcp_config_document_requires_object_root():
    with pytest.raises(ConfigLoadError):
        parse_mcp_config_document([])


def test_parse_mcp_config_document_requires_mcp_servers():
    document = {
        "notMcpServers": {}
    }

    with pytest.raises(ConfigLoadError):
        parse_mcp_config_document(document)


def test_parse_mcp_config_document_rejects_non_object_mcp_servers():
    document = {
        "mcpServers": []
    }

    with pytest.raises(ConfigLoadError):
        parse_mcp_config_document(document)


def test_parse_mcp_config_document_rejects_non_object_server_config():
    document = {
        "mcpServers": {
            "bad-server": "not-object"
        }
    }

    with pytest.raises(ConfigLoadError):
        parse_mcp_config_document(document)


def test_parse_mcp_config_document_rejects_non_string_command():
    document = {
        "mcpServers": {
            "bad-server": {
                "command": 123
            }
        }
    }

    with pytest.raises(ConfigLoadError):
        parse_mcp_config_document(document)


def test_parse_mcp_config_document_rejects_non_list_args():
    document = {
        "mcpServers": {
            "bad-server": {
                "command": "node",
                "args": "server.js"
            }
        }
    }

    with pytest.raises(ConfigLoadError):
        parse_mcp_config_document(document)


def test_parse_mcp_config_document_rejects_non_string_arg_item():
    document = {
        "mcpServers": {
            "bad-server": {
                "command": "node",
                "args": ["server.js", 123]
            }
        }
    }

    with pytest.raises(ConfigLoadError):
        parse_mcp_config_document(document)


def test_parse_mcp_config_document_rejects_non_object_env():
    document = {
        "mcpServers": {
            "bad-server": {
                "command": "node",
                "env": ["TOKEN=abc"]
            }
        }
    }

    with pytest.raises(ConfigLoadError):
        parse_mcp_config_document(document)


def test_parse_mcp_config_document_rejects_non_string_env_value():
    document = {
        "mcpServers": {
            "bad-server": {
                "command": "node",
                "env": {
                    "TOKEN": 123
                }
            }
        }
    }

    with pytest.raises(ConfigLoadError):
        parse_mcp_config_document(document)


def test_to_safe_dict_does_not_expose_env_values():
    document = {
        "mcpServers": {
            "github": {
                "command": "node",
                "args": ["server.js"],
                "env": {
                    "GITHUB_TOKEN": "FAKE_GITHUB_TOKEN_FOR_TEST"
                },
            }
        }
    }

    config = parse_mcp_config_document(document)[0]

    safe = config.to_safe_dict()

    assert safe["server_name"] == "github"
    assert safe["env_keys"] == ["GITHUB_TOKEN"]

    # 값이 노출되면 안 된다.
    assert "FAKE_GITHUB_TOKEN_FOR_TEST" not in str(safe)


def test_load_mcp_config_reads_file(tmp_path: Path):
    config_file = tmp_path / "mcp_config.json"

    config_file.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "server"],
                        "env": {
                            "TEST_TOKEN": "FAKE_TEST_TOKEN"
                        },
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    configs = load_mcp_config(config_file)

    assert len(configs) == 1
    assert configs[0].server_name == "filesystem"
    assert configs[0].command == "npx"
    assert configs[0].args == ["-y", "server"]
    assert configs[0].env == {
        "TEST_TOKEN": "FAKE_TEST_TOKEN"
    }
    assert configs[0].source == str(config_file)


def test_load_mcp_config_rejects_missing_file(tmp_path: Path):
    missing_file = tmp_path / "missing_config.json"

    with pytest.raises(ConfigLoadError):
        load_mcp_config(missing_file)


def test_load_mcp_config_rejects_invalid_json(tmp_path: Path):
    config_file = tmp_path / "invalid_config.json"
    config_file.write_text("{ invalid json", encoding="utf-8")

    with pytest.raises(ConfigLoadError):
        load_mcp_config(config_file)