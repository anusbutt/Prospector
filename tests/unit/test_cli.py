import pytest
from typer.testing import CliRunner

import prospector.cli as cli
from prospector.cli import app
from prospector.models import RunSummary

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for var in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "GOOGLE_PLACES_API_KEY", "HUNTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # no repo .env interference


def make_csv(tmp_path):
    path = tmp_path / "list.csv"
    path.write_text("company,email\nAcme,info@acme.com\n")
    return path


class TestHelp:
    def test_app_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Obsidian vault" in result.output

    def test_run_help_lists_options(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        for option in ("--vault", "--limit", "--only", "--no-llm", "--verbose"):
            assert option in result.output

    def test_send_command_exists_and_is_dry_run_by_default(self):
        # Constitution v3.0.0 (Principle I): a guarded send command exists,
        # dry-run by default (real sends require --send).
        result = runner.invoke(app, ["send", "--help"])
        assert result.exit_code == 0
        for option in ("--send", "--limit", "--vault", "--yes"):
            assert option in result.output
        assert "dry-run" in result.output.lower() or "dry run" in result.output.lower()


class TestPreflight:
    def test_missing_key_without_no_llm_exits_1(self, tmp_path):
        result = runner.invoke(app, ["run", str(make_csv(tmp_path))])
        assert result.exit_code == 1
        assert "OPENROUTER_API_KEY" in result.output

    def test_missing_input_exits_1(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
        result = runner.invoke(app, ["run", "missing.csv"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestRunWiring:
    def test_no_llm_passes_through_and_skips_key_check(self, tmp_path, monkeypatch):
        calls = {}

        def fake_run_batch(input_path, settings, **kwargs):
            calls.update(kwargs, input_path=input_path)
            return RunSummary(total=1, processed=1)

        monkeypatch.setattr("prospector.pipeline.run_batch", fake_run_batch)
        result = runner.invoke(app, ["run", str(make_csv(tmp_path)), "--no-llm", "--limit", "2"])
        assert result.exit_code == 0, result.output
        assert calls["no_llm"] is True
        assert calls["limit"] == 2
        assert "processed: 1" in result.output

    def test_unexpected_error_exits_2(self, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("prospector.pipeline.run_batch", boom)
        result = runner.invoke(app, ["run", str(make_csv(tmp_path)), "--no-llm"])
        assert result.exit_code == 2
        assert "unexpected error" in result.output

    def test_summary_table_printed(self, tmp_path, monkeypatch):
        summary = RunSummary(total=2, processed=2, named_none=2, messenger=1)
        summary.per_company = [("acme", "ok", "drafted"), ("beta", "ok", "no draft")]
        monkeypatch.setattr("prospector.pipeline.run_batch", lambda *a, **k: summary)
        result = runner.invoke(app, ["run", str(make_csv(tmp_path)), "--no-llm"])
        assert result.exit_code == 0
        assert "acme" in result.output and "beta" in result.output
        assert "messenger: 1" in result.output
