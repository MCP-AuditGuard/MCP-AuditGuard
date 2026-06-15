from __future__ import annotations

from web.sample_catalog import discover_samples


def test_discover_samples_finds_nested_tools_json(tmp_path) -> None:
    sample_dir = tmp_path / "expanded-52" / "LAB-001-plain-env-secret"
    sample_dir.mkdir(parents=True)
    (sample_dir / "tools.json").write_text(
        '{"tools": []}',
        encoding="utf-8",
    )

    samples = discover_samples(tmp_path)

    assert len(samples) == 1
    assert samples[0].id == "expanded-52/LAB-001-plain-env-secret"
    assert samples[0].title == "Plain Env Secret"
    assert samples[0].json_files == (sample_dir.resolve() / "tools.json",)


def test_discover_samples_keeps_direct_child_samples(tmp_path) -> None:
    sample_dir = tmp_path / "01-hidden-description"
    sample_dir.mkdir()
    (sample_dir / "tools.json").write_text(
        '{"tools": []}',
        encoding="utf-8",
    )

    samples = discover_samples(tmp_path)

    assert len(samples) == 1
    assert samples[0].id == "01-hidden-description"
    assert samples[0].title == "Hidden Description"


def test_discover_samples_ignores_hidden_directories(tmp_path) -> None:
    sample_dir = tmp_path / ".drafts" / "LAB-999-hidden"
    sample_dir.mkdir(parents=True)
    (sample_dir / "tools.json").write_text(
        '{"tools": []}',
        encoding="utf-8",
    )

    assert discover_samples(tmp_path) == []
