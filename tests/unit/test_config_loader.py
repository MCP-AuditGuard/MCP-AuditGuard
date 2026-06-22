import json
from dataclasses import fields
from pathlib import Path

import pytest

from core import config_loader
from core.config_loader import (
    ConfigLoadError,
    McpServerConfig,
    load_mcp_config,
    parse_mcp_config_document,
    parse_mcp_server_entry,
)


def test_parse_mcp_server_entry_loads_single_stdio_server():
    raw_entry = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        "env": {"FILESYSTEM_ROOT": "C:\\Work"},
        "cwd": "C:\\Work",
        "customField": {"preserved": True},
    }

    config = parse_mcp_server_entry(
        " filesystem ",
        raw_entry,
        source="codex:user",
    )

    assert config == McpServerConfig(
        server_name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem"],
        env={"FILESYSTEM_ROOT": "C:\\Work"},
        cwd="C:\\Work",
        raw=raw_entry,
        source="codex:user",
    )
    assert config.raw is not raw_entry


def test_parse_mcp_server_entry_preserves_existing_model_contract():
    config = parse_mcp_server_entry(
        "remote-shaped-entry",
        {
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer TEST_TOKEN"},
            "transport": "streamable-http",
            "enabled_tools": ["search"],
        },
    )

    assert [field.name for field in fields(McpServerConfig)] == [
        "server_name",
        "command",
        "args",
        "env",
        "cwd",
        "raw",
        "source",
    ]
    assert config.command is None
    assert config.raw["url"] == "https://example.com/mcp"
    assert not hasattr(config, "url")
    assert not hasattr(config, "headers")
    assert not hasattr(config, "transport")
    assert not hasattr(config, "tool_policy")


def test_parse_mcp_server_entry_allows_discovery_to_isolate_entry_errors():
    entries = {
        "valid-before": {"command": "python", "args": ["before.py"]},
        "invalid": {"command": 123},
        "valid-after": {"command": "node", "args": ["after.js"]},
    }
    configs = []
    errors = []

    for server_name, raw_entry in entries.items():
        try:
            configs.append(
                parse_mcp_server_entry(server_name, raw_entry)
            )
        except ConfigLoadError as error:
            errors.append((server_name, str(error)))

    assert [config.server_name for config in configs] == [
        "valid-before",
        "valid-after",
    ]
    assert errors == [
        ("invalid", "invalid.command must be a string"),
    ]


def test_parse_mcp_config_document_reuses_public_entry_parser(monkeypatch):
    parsed_server_names = []
    original_parser = config_loader.parse_mcp_server_entry

    def recording_parser(server_name, raw_server_config, *, source=None):
        parsed_server_names.append(server_name)
        return original_parser(
            server_name,
            raw_server_config,
            source=source,
        )

    monkeypatch.setattr(
        config_loader,
        "parse_mcp_server_entry",
        recording_parser,
    )

    configs = config_loader.parse_mcp_config_document(
        {
            "mcpServers": {
                "first": {"command": "python"},
                "second": {"command": "node"},
            }
        },
        source="manual.json",
    )

    assert parsed_server_names == ["first", "second"]
    assert [config.source for config in configs] == [
        "manual.json",
        "manual.json",
    ]


@pytest.mark.parametrize(
    ("server_name", "raw_entry", "message"),
    [
        (123, {}, "server name must be a string"),
        ("   ", {}, "server name must not be empty"),
        ("bad", "not-an-object", "config must be an object"),
        ("bad", {"args": "not-an-array"}, "args must be an array"),
    ],
)
def test_parse_mcp_server_entry_rejects_invalid_entry(
    server_name,
    raw_entry,
    message,
):
    with pytest.raises(ConfigLoadError, match=message):
        parse_mcp_server_entry(server_name, raw_entry)


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
