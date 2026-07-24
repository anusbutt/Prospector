"""CLI contract for `prospector source` (specs/002-company-sourcing/contracts/cli.md)."""

import pytest
from typer.testing import CliRunner

from prospector.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for var in ("OPENROUTER_API_KEY", "GOOGLE_PLACES_API_KEY", "HUNTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # no repo .env interference


def test_source_help_lists_options():
    result = runner.invoke(app, ["source", "--help"])
    assert result.exit_code == 0
    for option in ("--keyword", "--metros", "--out", "--all", "--max-queries", "--limit", "--verbose"):
        assert option in result.output


def test_missing_places_key_exits_1_nothing_written(tmp_path):
    result = runner.invoke(app, ["source", "--out", str(tmp_path / "c.csv")])
    assert result.exit_code == 1
    assert "GOOGLE_PLACES_API_KEY" in result.output
    assert not (tmp_path / "c.csv").exists()


def test_bad_metros_file_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "places-x")
    result = runner.invoke(app, ["source", "--metros", str(tmp_path / "nope.txt")])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_empty_metros_file_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "places-x")
    empty = tmp_path / "metros.txt"
    empty.write_text("# nothing\n")
    result = runner.invoke(app, ["source", "--metros", str(empty)])
    assert result.exit_code == 1
    assert "no metros" in result.output


def test_unwritable_out_dir_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "places-x")
    result = runner.invoke(app, ["source", "--out", str(tmp_path / "missing-dir" / "c.csv")])
    assert result.exit_code == 1
    assert "output directory" in result.output
