"""Send pipeline: selection (T012), real-send loop (T014), cap enforcement (T020),
pacing (T021). Feature 004: the pipeline is provider-blind — tests inject a fake
EmailSender; no provider module is touched, no network."""

import os
from datetime import date

import pytest

from prospector import send as send_mod
from prospector.config import Settings
from prospector.models import SendOutcome


def make_settings(tmp_path, caps=None, delay=(0, 0)):
    return Settings(
        openrouter_key=None,
        openrouter_model="m",
        places_key=None,
        hunter_key=None,
        vault_dir=tmp_path / "vault",
        send_from="outreach@omniveer.com",
        send_caps=caps or [100],
        send_delay=delay,
        ledger_path=tmp_path / "ledger.jsonl",
    )


def write_note(vault, slug, *, status="approved", email="x@y.com", channel="email",
               subject="Hi there", body="Body text.", mtime=None):
    vault.mkdir(parents=True, exist_ok=True)
    subj_line = f"**Subject:** {subject}\n\n" if subject is not None else ""
    body_block = f"{body}\n" if body is not None else ""
    text = (
        "---\n"
        f"company: {slug.title()}\n"
        f"email: {email}\n"
        f"channel: {channel}\n"
        f"status: {status}\n"
        "tags: [outreach]\n"
        "---\n\n"
        "## Draft\n"
        f"{subj_line}{body_block}\n"
        "## Research\n- x\n\n"
        "## Log\n-\n"
    )
    p = vault / f"{slug}.md"
    p.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


class FakeSender:
    """Provider-neutral fake EmailSender (contracts/email-sender.md)."""

    def __init__(self, fail_on=None, identity="outreach@omniveer.com"):
        self.calls = []
        self.fail_on = fail_on or set()
        self.identity = identity
        self._n = 0

    def verify_identity(self):
        return self.identity

    def send_message(self, from_addr, to_addr, subject, body):
        self.calls.append(to_addr)
        if to_addr in self.fail_on:
            raise RuntimeError("smtp boom")
        self._n += 1
        return f"msg-{self._n}"


class ExplodingSender:
    """Any use proves the pipeline touched the transport when it must not
    (dry-run makes no network requests — SC-102)."""

    def verify_identity(self):
        raise AssertionError("dry-run must never authenticate")

    def send_message(self, *a, **k):
        raise AssertionError("dry-run must never open a connection or send")


@pytest.fixture
def fake_sender():
    return FakeSender()


# --- T012 selection ---

def test_only_approved_are_collected(tmp_path):
    vault = tmp_path / "vault"
    write_note(vault, "yes", status="approved")
    write_note(vault, "no", status="to-send")
    cands, skipped = send_mod.collect_candidates(vault)
    slugs = {c.slug for c in cands}
    assert slugs == {"yes"}


def test_messenger_and_bad_email_are_skipped_not_sendable(tmp_path):
    vault = tmp_path / "vault"
    write_note(vault, "msg", status="approved", channel="messenger", email="")
    write_note(vault, "bademail", status="approved", email="notanemail")
    write_note(vault, "nosubj", status="approved", subject=None)
    cands, skipped = send_mod.collect_candidates(vault)
    assert cands == []
    reasons = {r.slug: r.outcome for r in skipped}
    assert reasons["msg"] == SendOutcome.SKIPPED_NOT_SENDABLE
    assert reasons["bademail"] == SendOutcome.SKIPPED_NOT_SENDABLE
    assert reasons["nosubj"] == SendOutcome.SKIPPED_NOT_SENDABLE


# --- T014 real-send loop ---

def test_two_approved_are_sent_status_flipped_and_ledgered(tmp_path, fake_sender):
    vault = tmp_path / "vault"
    p1 = write_note(vault, "acme", email="a@acme.com")
    p2 = write_note(vault, "beta", email="b@beta.com")
    write_note(vault, "later", status="to-send", email="c@later.com")
    settings = make_settings(tmp_path)

    report = send_mod.run_send(settings, dry_run=False, sender=fake_sender, today=date(2026, 7, 15))

    assert report.sent == 2
    assert set(fake_sender.calls) == {"a@acme.com", "b@beta.com"}
    # statuses flipped
    assert "status: sent" in p1.read_text()
    assert "status: sent" in p2.read_text()
    # non-approved untouched
    assert "status: to-send" in (vault / "later.md").read_text()
    # ledger has 2 sent rows
    from prospector import ledger
    rows = ledger.read_all(settings.ledger_path)
    assert len([r for r in rows if r.result == "sent"]) == 2


# --- T020 cap enforcement ---

def test_cap_limits_sends_and_defers_rest(tmp_path, fake_sender):
    vault = tmp_path / "vault"
    for i in range(5):
        write_note(vault, f"c{i}", email=f"c{i}@x.com", mtime=1000 + i)
    settings = make_settings(tmp_path, caps=[2])

    report = send_mod.run_send(settings, dry_run=False, sender=fake_sender, today=date(2026, 7, 15))

    assert report.sent == 2
    assert report.deferred == 3
    assert len(fake_sender.calls) == 2
    # oldest-approved-first: c0, c1 sent
    assert set(fake_sender.calls) == {"c0@x.com", "c1@x.com"}


def test_repeated_runs_never_exceed_daily_cap(tmp_path, fake_sender):
    vault = tmp_path / "vault"
    for i in range(5):
        write_note(vault, f"c{i}", email=f"c{i}@x.com", mtime=1000 + i)
    settings = make_settings(tmp_path, caps=[2])
    today = date(2026, 7, 15)

    send_mod.run_send(settings, dry_run=False, sender=fake_sender, today=today)
    r2 = send_mod.run_send(settings, dry_run=False, sender=fake_sender, today=today)

    from prospector import ledger
    assert ledger.daily_count(settings.ledger_path, today) == 2  # cap held across runs
    assert r2.sent == 0


def test_cap_zero_sends_nothing(tmp_path, fake_sender):
    vault = tmp_path / "vault"
    write_note(vault, "a", email="a@x.com")
    settings = make_settings(tmp_path, caps=[0])
    report = send_mod.run_send(settings, dry_run=False, sender=fake_sender, today=date(2026, 7, 15))
    assert report.sent == 0
    assert fake_sender.calls == []


# --- T021 pacing ---

def test_pacing_sleeps_between_sends_only(tmp_path, fake_sender):
    vault = tmp_path / "vault"
    for i in range(3):
        write_note(vault, f"c{i}", email=f"c{i}@x.com", mtime=1000 + i)
    settings = make_settings(tmp_path, caps=[10], delay=(30, 90))
    sleeps = []
    send_mod.run_send(
        settings, dry_run=False, sender=fake_sender, today=date(2026, 7, 15),
        sleep=lambda s: sleeps.append(s),
    )
    assert len(sleeps) == 2  # n-1 for 3 sends
    assert all(30 <= s <= 90 for s in sleeps)


def test_no_pacing_in_dry_run(tmp_path):
    vault = tmp_path / "vault"
    for i in range(3):
        write_note(vault, f"c{i}", email=f"c{i}@x.com", mtime=1000 + i)
    settings = make_settings(tmp_path, caps=[10], delay=(30, 90))
    sleeps = []
    # even a sender that explodes on any use is safe in dry-run (SC-102)
    report = send_mod.run_send(
        settings, dry_run=True, sender=ExplodingSender(), today=date(2026, 7, 15),
        sleep=lambda s: sleeps.append(s),
    )
    assert sleeps == []
    assert report.sent == 3  # "would send" count


# --- 004: dry-run never touches the transport ---

def test_dry_run_never_uses_the_sender(tmp_path):
    vault = tmp_path / "vault"
    write_note(vault, "acme", email="a@acme.com")
    settings = make_settings(tmp_path)
    report = send_mod.run_send(
        settings, dry_run=True, sender=ExplodingSender(), today=date(2026, 7, 15)
    )
    assert report.sent == 1  # previewed, not sent
    assert not settings.ledger_path.exists()


# --- 004: identity policy over the neutral interface ---

def test_verified_sender_accepts_matching_identity_case_insensitively(tmp_path):
    settings = make_settings(tmp_path)
    sender = FakeSender(identity="Outreach@Omniveer.com")
    assert send_mod.verified_sender(settings, sender=sender) is sender


def test_verified_sender_rejects_mismatched_identity(tmp_path):
    settings = make_settings(tmp_path)
    sender = FakeSender(identity="personal@gmail.com")
    with pytest.raises(send_mod.IdentityError):
        send_mod.verified_sender(settings, sender=sender)
    assert sender.calls == []  # nothing was sent
