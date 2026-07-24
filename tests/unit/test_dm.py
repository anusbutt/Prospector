"""Assisted-manual Messenger walk (007): candidate collection, the confirm loop,
ledger dedupe, status flip, and graceful no-link handling. Clipboard/browser/
confirm are injected — no real clipboard, no browser, no network."""

import os

from prospector import dm as dm_mod
from prospector import ledger, vault
from prospector.config import Settings
from prospector.models import DmOutcome


def make_settings(tmp_path):
    return Settings(
        openrouter_key=None,
        openrouter_model="m",
        places_key=None,
        hunter_key=None,
        vault_dir=tmp_path / "vault",
        dm_ledger_path=tmp_path / "dm_ledger.jsonl",
    )


def write_messenger_note(vault_dir, slug, *, status="approved", channel="messenger",
                         facebook_url="https://www.facebook.com/AcmeDucts/",
                         body="Hey! Free 10-day pilot. (https://www.omniveer.com/duct-lead-qualifier)",
                         mtime=None):
    vault_dir.mkdir(parents=True, exist_ok=True)
    fb_line = f'facebook_url: "{facebook_url}"\n' if facebook_url is not None else "facebook_url:\n"
    body_block = f"{body}\n" if body is not None else ""
    text = (
        "---\n"
        f"company: {slug.replace('-', ' ').title()}\n"
        "email:\n"
        f"channel: {channel}\n"
        f"status: {status}\n"
        f"{fb_line}"
        "tags: [outreach]\n"
        "---\n\n"
        "## Draft\n"
        f"{body_block}\n"
        "## Research\n- x\n\n"
        "## Log\n-\n"
    )
    p = vault_dir / f"{slug}.md"
    p.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


class Confirm:
    """Injected confirm stub returning a scripted decision per call."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.seen = []

    def __call__(self, cand, *, copied, opened):
        self.seen.append((cand.slug, copied, opened))
        return self.answers.pop(0) if self.answers else "n"


# --- collection ---

def test_collect_only_approved_messenger(tmp_path):
    v = tmp_path / "vault"
    write_messenger_note(v, "acme-ducts", status="approved")
    write_messenger_note(v, "not-approved", status="to-send")
    write_messenger_note(v, "an-email-note", channel="email")
    cands, skipped = dm_mod.collect_dm_candidates(v)
    assert [c.slug for c in cands] == ["acme-ducts"]
    assert skipped == []


def test_collect_flags_missing_body(tmp_path):
    v = tmp_path / "vault"
    write_messenger_note(v, "no-body", body=None)
    cands, skipped = dm_mod.collect_dm_candidates(v)
    assert cands == []
    assert len(skipped) == 1
    assert skipped[0].outcome is DmOutcome.SKIPPED_NOT_SENDABLE
    assert "no body" in skipped[0].detail


def test_collect_unquotes_facebook_url(tmp_path):
    v = tmp_path / "vault"
    write_messenger_note(v, "acme-ducts", facebook_url="https://www.facebook.com/AcmeDucts/")
    cands, _ = dm_mod.collect_dm_candidates(v)
    assert cands[0].facebook_url == "https://www.facebook.com/AcmeDucts/"


# --- confirm loop / status + ledger (US1) ---

def test_confirm_yes_ledgers_and_flips_status(tmp_path):
    s = make_settings(tmp_path)
    note = write_messenger_note(s.vault_dir, "acme-ducts")
    copies, opens = [], []
    report = dm_mod.run_dm(
        s, dry_run=False,
        confirm=Confirm("y"),
        opener=lambda url: opens.append(url) or True,
        copier=lambda text: copies.append(text) or True,
    )
    assert report.delivered == 1
    assert opens == ["https://www.facebook.com/AcmeDucts/"]
    assert copies and copies[0].startswith("Hey!")
    # ledger row written
    recs = ledger.read_all(s.dm_ledger_path)
    assert len(recs) == 1
    assert recs[0].result == "dm_sent_manual" and recs[0].message_id is None
    assert recs[0].slug == "acme-ducts"
    # status flipped + log bullet
    fm, _ = vault.parse_note(note.read_text(encoding="utf-8"))
    assert fm["status"] == "sent"
    assert "messenger delivered manually" in note.read_text(encoding="utf-8")


def test_decline_records_nothing(tmp_path):
    s = make_settings(tmp_path)
    note = write_messenger_note(s.vault_dir, "acme-ducts")
    report = dm_mod.run_dm(
        s, dry_run=False,
        confirm=Confirm("n"),
        opener=lambda url: True,
        copier=lambda text: True,
    )
    assert report.declined == 1 and report.delivered == 0
    assert ledger.read_all(s.dm_ledger_path) == []
    fm, _ = vault.parse_note(note.read_text(encoding="utf-8"))
    assert fm["status"] == "approved"


def test_quit_stops_the_walk(tmp_path):
    s = make_settings(tmp_path)
    write_messenger_note(s.vault_dir, "a-ducts", mtime=1)
    write_messenger_note(s.vault_dir, "b-ducts", mtime=2)
    report = dm_mod.run_dm(
        s, dry_run=False,
        confirm=Confirm("q"),
        opener=lambda url: True, copier=lambda text: True,
    )
    assert report.delivered == 0
    assert ledger.read_all(s.dm_ledger_path) == []


# --- dedupe (US3) ---

def test_ledgered_slug_is_skipped(tmp_path):
    s = make_settings(tmp_path)
    write_messenger_note(s.vault_dir, "acme-ducts")
    # first confirmed delivery
    dm_mod.run_dm(s, dry_run=False, confirm=Confirm("y"),
                  opener=lambda u: True, copier=lambda t: True)
    # reset status back to approved and run again
    note = s.vault_dir / "acme-ducts.md"
    vault.set_status(note, "approved", "reopened")
    opens = []
    report = dm_mod.run_dm(s, dry_run=False, confirm=Confirm("y"),
                           opener=lambda u: opens.append(u) or True, copier=lambda t: True)
    assert report.skipped_already == 1 and report.delivered == 0
    assert opens == []  # no browser opened for an already-delivered note


def test_duplicate_target_within_run(tmp_path):
    s = make_settings(tmp_path)
    url = "https://www.facebook.com/Shared/"
    write_messenger_note(s.vault_dir, "a-ducts", facebook_url=url, mtime=1)
    write_messenger_note(s.vault_dir, "b-ducts", facebook_url=url, mtime=2)
    report = dm_mod.run_dm(s, dry_run=False, confirm=Confirm("y", "y"),
                           opener=lambda u: True, copier=lambda t: True)
    assert report.delivered == 1 and report.skipped_already == 1


# --- graceful no-link (US5) ---

def test_no_facebook_link_does_not_open_but_still_offers(tmp_path):
    s = make_settings(tmp_path)
    note = write_messenger_note(s.vault_dir, "no-link", facebook_url=None)
    opens, copies = [], []
    confirm = Confirm("y")
    report = dm_mod.run_dm(
        s, dry_run=False, confirm=confirm,
        opener=lambda u: opens.append(u) or True,
        copier=lambda t: copies.append(t) or True,
    )
    assert opens == []  # opener never called without a link
    assert copies  # draft still copied
    assert confirm.seen and confirm.seen[0][2] is False  # opened=False presented
    assert report.delivered == 1  # y still ledgers + flips
    fm, _ = vault.parse_note(note.read_text(encoding="utf-8"))
    assert fm["status"] == "sent"
