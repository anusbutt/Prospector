"""CLI `prospector dm` (007): preview is the default and mutates nothing; flags
are accepted. The real-send confirm loop is covered directly in test_dm.py (which
injects clipboard/browser); here we keep the browser out of the process by only
exercising preview + argument parsing."""

from typer.testing import CliRunner

from prospector import vault
from prospector.cli import app
from test_dm import write_messenger_note

runner = CliRunner()


def _prep(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    dm_ledger = tmp_path / "dm_ledger.jsonl"
    monkeypatch.setenv("PROSPECTOR_DM_LEDGER", str(dm_ledger))
    write_messenger_note(v, "acme-ducts", status="approved")
    write_messenger_note(v, "pending", status="to-send")
    return v, dm_ledger


def test_preview_is_default_and_inert(tmp_path, monkeypatch):
    v, dm_ledger = _prep(tmp_path, monkeypatch)
    note = v / "acme-ducts.md"
    before = note.read_text(encoding="utf-8")

    result = runner.invoke(app, ["dm", "--vault", str(v)])

    assert result.exit_code == 0
    assert "WOULD WALK (preview)" in result.output
    assert "to walk: 1" in result.output
    assert not dm_ledger.exists()  # nothing recorded
    assert note.read_text(encoding="utf-8") == before  # note byte-identical
    fm, _ = vault.parse_note(note.read_text(encoding="utf-8"))
    assert fm["status"] == "approved"


def test_flags_accepted(tmp_path, monkeypatch):
    v, _ = _prep(tmp_path, monkeypatch)
    result = runner.invoke(app, ["dm", "--vault", str(v), "--limit", "1"])
    assert result.exit_code == 0


def test_missing_vault_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("PROSPECTOR_DM_LEDGER", str(tmp_path / "dm.jsonl"))
    result = runner.invoke(app, ["dm", "--vault", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "vault folder not found" in result.output
