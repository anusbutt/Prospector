"""`prospector send` CLI: dry-run default (US2), --send real path, identity
guard, and feature 004 provider selection / SMTP pre-flight. No network —
senders are injected or built on fake SMTP factories."""

import os

import pytest
from typer.testing import CliRunner

import prospector.cli as cli
from prospector.cli import app
from prospector import send as send_mod
from prospector import transport

runner = CliRunner()

PASSWORD = "sentinel-secret-123"

ALL_SEND_ENV = (
    "OPENROUTER_API_KEY", "GOOGLE_PLACES_API_KEY", "HUNTER_API_KEY",
    "PROSPECTOR_SEND_FROM", "PROSPECTOR_SEND_CAPS", "PROSPECTOR_SEND_DELAY",
    "PROSPECTOR_LEDGER", "PROSPECTOR_VAULT", "PROSPECTOR_SEND_PROVIDER",
    "PROSPECTOR_SEND_NAME", "PROSPECTOR_REPLY_TO", "PROSPECTOR_SMTP_HOST",
    "PROSPECTOR_SMTP_PORT", "PROSPECTOR_SMTP_SECURITY",
    "PROSPECTOR_SMTP_USERNAME", "PROSPECTOR_SMTP_PASSWORD",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for var in ALL_SEND_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


def _note(vault, slug, status="approved", email="a@acme.com"):
    vault.mkdir(parents=True, exist_ok=True)
    (vault / f"{slug}.md").write_text(
        "---\n"
        f"company: {slug.title()}\n"
        f"email: {email}\n"
        "channel: email\n"
        f"status: {status}\n"
        "tags: [outreach]\n"
        "---\n\n"
        "## Draft\n**Subject:** Hi\n\nBody.\n\n## Research\n- x\n\n## Log\n-\n",
        encoding="utf-8",
    )


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("PROSPECTOR_SEND_CAPS", "100")
    monkeypatch.setenv("PROSPECTOR_SEND_DELAY", "0,0")
    monkeypatch.setenv("PROSPECTOR_SEND_FROM", "outreach@omniveer.com")
    monkeypatch.setenv("PROSPECTOR_LEDGER", str(tmp_path / "ledger.jsonl"))


def _smtp_env(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("PROSPECTOR_SEND_PROVIDER", "smtp")
    monkeypatch.setenv("PROSPECTOR_SEND_FROM", "anas@omniveer.com")
    monkeypatch.setenv("PROSPECTOR_SEND_NAME", "Anas from Omniveer")
    monkeypatch.setenv("PROSPECTOR_SMTP_HOST", "smtp.zoho.com")
    monkeypatch.setenv("PROSPECTOR_SMTP_USERNAME", "anas@omniveer.com")
    monkeypatch.setenv("PROSPECTOR_SMTP_PASSWORD", PASSWORD)


class FakeSender:
    def __init__(self, identity="outreach@omniveer.com", fail=False):
        self.identity = identity
        self.fail = fail
        self.calls = []
        self._n = 0

    def verify_identity(self):
        return self.identity

    def send_message(self, from_addr, to_addr, subject, body):
        self.calls.append(to_addr)
        if self.fail:
            raise RuntimeError("boom")
        self._n += 1
        return f"msg-{self._n}"


# --- dry-run default (US2) ---

def test_dry_run_default_sends_nothing(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    _env(tmp_path, monkeypatch)

    def explode(settings):  # dry-run must never even construct a sender
        raise AssertionError("dry-run constructed a sender")

    monkeypatch.setattr(transport, "create_sender", explode)

    result = runner.invoke(app, ["send", "--vault", str(vault)])

    assert result.exit_code == 0
    assert not (tmp_path / "ledger.jsonl").exists()  # no ledger write
    assert "status: approved" in (vault / "acme.md").read_text()  # unchanged
    assert "WOULD SEND" in result.output


def test_dry_run_smtp_opens_no_connection(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    _smtp_env(tmp_path, monkeypatch)

    import smtplib

    def explode(*a, **k):
        raise AssertionError("dry-run opened an SMTP connection")

    monkeypatch.setattr(smtplib, "SMTP", explode)
    monkeypatch.setattr(smtplib, "SMTP_SSL", explode)

    result = runner.invoke(app, ["send", "--vault", str(vault)])

    assert result.exit_code == 0
    assert "WOULD SEND" in result.output
    assert not (tmp_path / "ledger.jsonl").exists()


# --- real send path ---

def test_send_flag_performs_real_send(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    _env(tmp_path, monkeypatch)
    fake = FakeSender()
    monkeypatch.setattr(send_mod, "verified_sender", lambda settings, **k: fake)

    result = runner.invoke(app, ["send", "--send", "--yes", "--vault", str(vault)])

    assert result.exit_code == 0
    assert fake.calls == ["a@acme.com"]
    assert "status: sent" in (vault / "acme.md").read_text()
    from prospector import ledger
    rows = ledger.read_all(tmp_path / "ledger.jsonl")
    assert len(rows) == 1 and rows[0].result == "sent"


def test_identity_mismatch_refuses_with_exit_2(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    _env(tmp_path, monkeypatch)
    fake = FakeSender(identity="someoneelse@gmail.com")
    monkeypatch.setattr(transport, "create_sender", lambda settings: fake)

    result = runner.invoke(app, ["send", "--send", "--yes", "--vault", str(vault)])

    assert result.exit_code == 2
    assert fake.calls == []  # nothing sent
    assert "status: approved" in (vault / "acme.md").read_text()


# --- 004: SMTP through the CLI ---

def _fake_factory(fail_login=False):
    """Minimal fake smtplib classes for SmtpSender injection via create_sender."""
    import smtplib

    log = []

    class Conn:
        def login(self, u, p):
            log.append(("login", u))
            if fail_login:
                raise smtplib.SMTPAuthenticationError(535, b"auth failed")

        def send_message(self, msg, from_addr=None, to_addrs=None):
            log.append(("send", from_addr, tuple(to_addrs), msg))
            return {}

        def starttls(self, context=None):
            log.append(("starttls",))

        def quit(self):
            log.append(("quit",))

    factory = {"ssl": lambda *a, **k: Conn(), "starttls": lambda *a, **k: Conn()}
    return factory, log


def test_smtp_send_updates_ledger_and_note_status(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    _smtp_env(tmp_path, monkeypatch)
    factory, log = _fake_factory()

    from prospector.smtp_send import SmtpSender

    monkeypatch.setattr(
        transport, "create_sender", lambda settings: SmtpSender(settings, smtp_factory=factory)
    )

    result = runner.invoke(app, ["send", "--send", "--yes", "--vault", str(vault)])

    assert result.exit_code == 0
    sends = [e for e in log if e[0] == "send"]
    assert len(sends) == 1
    msg = sends[0][3]
    assert msg["From"] == "Anas from Omniveer <anas@omniveer.com>"
    assert "status: sent" in (vault / "acme.md").read_text()
    from prospector import ledger
    rows = ledger.read_all(tmp_path / "ledger.jsonl")
    assert len(rows) == 1 and rows[0].result == "sent"
    assert rows[0].message_id == msg["Message-ID"]


def test_smtp_failed_send_leaves_note_approved(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    _smtp_env(tmp_path, monkeypatch)
    fake = FakeSender(identity="anas@omniveer.com", fail=True)
    monkeypatch.setattr(send_mod, "verified_sender", lambda settings, **k: fake)

    result = runner.invoke(app, ["send", "--send", "--yes", "--vault", str(vault)])

    assert result.exit_code == 0  # per-message failures are non-fatal
    assert "status: approved" in (vault / "acme.md").read_text()
    from prospector import ledger
    rows = ledger.read_all(tmp_path / "ledger.jsonl")
    assert len(rows) == 1 and rows[0].result == "failed"


def test_smtp_auth_failure_exits_3_without_leaking_password(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    _smtp_env(tmp_path, monkeypatch)
    factory, _ = _fake_factory(fail_login=True)

    from prospector.smtp_send import SmtpSender

    monkeypatch.setattr(
        transport, "create_sender", lambda settings: SmtpSender(settings, smtp_factory=factory)
    )

    result = runner.invoke(app, ["send", "--send", "--yes", "--vault", str(vault)])

    assert result.exit_code == 3
    assert PASSWORD not in result.output
    assert "status: approved" in (vault / "acme.md").read_text()


# --- 004: pre-flight failures (exit 1, before anything) ---

def test_missing_send_from_fails_preflight(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    monkeypatch.setenv("PROSPECTOR_LEDGER", str(tmp_path / "ledger.jsonl"))

    result = runner.invoke(app, ["send", "--vault", str(vault)])

    assert result.exit_code == 1
    assert "PROSPECTOR_SEND_FROM" in result.output


def test_missing_smtp_password_fails_preflight(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    _smtp_env(tmp_path, monkeypatch)
    monkeypatch.delenv("PROSPECTOR_SMTP_PASSWORD")

    result = runner.invoke(app, ["send", "--send", "--yes", "--vault", str(vault)])

    assert result.exit_code == 1
    assert "PROSPECTOR_SMTP_PASSWORD" in result.output


def test_from_spoofing_fails_preflight(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _note(vault, "acme")
    _smtp_env(tmp_path, monkeypatch)
    monkeypatch.setenv("PROSPECTOR_SEND_FROM", "ceo@bigcorp.com")

    result = runner.invoke(app, ["send", "--send", "--yes", "--vault", str(vault)])

    assert result.exit_code == 1
    assert "spoof" in result.output.lower()
    assert PASSWORD not in result.output
