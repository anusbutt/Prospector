"""Failure isolation + double-send prevention + duplicate-inbox collapse (T025).
Feature 004: exercised through the provider-neutral sender interface."""

import os
from datetime import date

import pytest

from prospector import ledger, send as send_mod
from prospector.config import Settings
from prospector.models import LedgerRecord, SendOutcome


def make_settings(tmp_path, caps=None):
    return Settings(
        openrouter_key=None, openrouter_model="m", places_key=None, hunter_key=None,
        vault_dir=tmp_path / "vault", send_from="outreach@omniveer.com",
        send_caps=caps or [100], send_delay=(0, 0),
        ledger_path=tmp_path / "ledger.jsonl",
    )


def write_note(vault, slug, *, status="approved", email="x@y.com", mtime=None):
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
    p = vault / f"{slug}.md"
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


class FailingSender:
    """Fake EmailSender that fails for chosen recipients (transport-agnostic)."""

    def __init__(self, fail_on):
        self.fail_on = set(fail_on)
        self.calls = []
        self._n = 0

    def verify_identity(self):
        return "outreach@omniveer.com"

    def send_message(self, from_addr, to_addr, subject, body):
        self.calls.append(to_addr)
        if to_addr in self.fail_on:
            raise RuntimeError("smtp boom")
        self._n += 1
        return f"msg-{self._n}"


def test_mid_batch_failure_isolated(tmp_path):
    vault = tmp_path / "vault"
    p0 = write_note(vault, "c0", email="c0@x.com", mtime=1000)
    p1 = write_note(vault, "c1", email="c1@x.com", mtime=1001)
    p2 = write_note(vault, "c2", email="c2@x.com", mtime=1002)
    sender = FailingSender(fail_on={"c1@x.com"})
    settings = make_settings(tmp_path)

    report = send_mod.run_send(settings, dry_run=False, sender=sender, today=date(2026, 7, 16))

    assert report.sent == 2
    assert report.failed == 1
    # 1 and 3 sent, 2 stays approved
    assert "status: sent" in p0.read_text()
    assert "status: approved" in p1.read_text()  # failed → unchanged
    assert "status: sent" in p2.read_text()
    # ledger has 2 sent + 1 failed
    rows = ledger.read_all(settings.ledger_path)
    assert sum(r.result == "sent" for r in rows) == 2
    assert sum(r.result == "failed" for r in rows) == 1


def test_already_sent_in_ledger_is_skipped(tmp_path):
    vault = tmp_path / "vault"
    write_note(vault, "acme", email="a@acme.com")
    settings = make_settings(tmp_path)
    # pre-seed the ledger with a prior successful send of the same recipient
    ledger.append(settings.ledger_path, LedgerRecord(
        ts="2026-07-10T10:00:00", slug="acme", recipient="a@acme.com", company="Acme",
        message_id="old", result="sent", error=None, from_account="outreach@omniveer.com",
    ))
    sender = FailingSender(fail_on=set())

    report = send_mod.run_send(settings, dry_run=False, sender=sender, today=date(2026, 7, 16))

    assert sender.calls == []  # never re-sent
    assert report.count(SendOutcome.SKIPPED_ALREADY_SENT) == 1


def test_already_sent_by_slug_even_if_status_reset(tmp_path):
    vault = tmp_path / "vault"
    write_note(vault, "acme", email="new@acme.com")  # different email, same slug
    settings = make_settings(tmp_path)
    ledger.append(settings.ledger_path, LedgerRecord(
        ts="2026-07-10T10:00:00", slug="acme", recipient="old@acme.com", company="Acme",
        message_id="old", result="sent", error=None, from_account="outreach@omniveer.com",
    ))
    sender = FailingSender(fail_on=set())

    report = send_mod.run_send(settings, dry_run=False, sender=sender, today=date(2026, 7, 16))

    assert sender.calls == []  # slug already sent → skipped
    assert report.count(SendOutcome.SKIPPED_ALREADY_SENT) == 1


def test_duplicate_inbox_collapses_to_one_send(tmp_path):
    vault = tmp_path / "vault"
    write_note(vault, "acme-1", email="shared@acme.com", mtime=1000)
    write_note(vault, "acme-2", email="shared@acme.com", mtime=1001)
    settings = make_settings(tmp_path)
    sender = FailingSender(fail_on=set())

    report = send_mod.run_send(settings, dry_run=False, sender=sender, today=date(2026, 7, 16))

    assert len(sender.calls) == 1  # one send for the shared inbox
    assert report.sent == 1
    assert report.count(SendOutcome.SKIPPED_ALREADY_SENT) == 1
