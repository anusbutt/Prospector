"""Frozen-note semantics (006 US3, FR-326 / contracts/note-format.md §3).

Copy the human approved, or copy that already went out, must survive a re-run
byte-for-byte. These tests are the guard on 27 live sent notes.
"""

from prospector.vault import (
    DRAFTABLE_STATUS,
    is_frozen,
    merge_notes,
    parse_note,
    read_status,
    upsert_note,
)

EXISTING = """---
company: Acme Duct
email: scott@acmeduct.com
channel: email
status: {status}
name_used: Scott
name_confidence: high
name_candidate:
hook: 22 years in business
website: acmeduct.com
angle: offer-led
fb_signal: weak
duplicate_of:
needs_review: false
tags: [outreach, duct-cleaning, prospector]
---

## Draft
**Subject:** THE APPROVED SUBJECT

THE APPROVED BODY the human actually read.

## Research
- Owner name: Scott Brenner (about_page: https://acmeduct.com/about)
- Hook: 22 years in business

## Log
- 2026-07-19 approved by hand
"""

FRESH = """---
company: Acme Duct
email: scott@acmeduct.com
channel: email
status: to-send
name_used: Scott
name_confidence: high
name_candidate:
hook: 25 years in business
website: acmeduct.com
angle: offer-led
fb_signal: strong
duplicate_of:
needs_review: false
tags: [outreach, duct-cleaning, prospector]
---

## Draft
**Subject:** A REGENERATED SUBJECT

A REGENERATED BODY nobody has reviewed.

## Research
- Owner name: Scott Brenner (about_page: https://acmeduct.com/about)
- Hook: 25 years in business

## Log
-
"""


def section(note: str, heading: str) -> str:
    return dict(parse_note(note)[1])[heading]


class TestIsFrozen:
    def test_new_note_is_draftable(self):
        assert not is_frozen(None)

    def test_to_send_is_draftable(self):
        assert not is_frozen(DRAFTABLE_STATUS)
        assert not is_frozen("to-send")

    def test_approved_is_frozen(self):
        assert is_frozen("approved")

    def test_sent_is_frozen(self):
        assert is_frozen("sent")

    def test_is_frozen_defaults_down(self):
        """Unknown statuses are FROZEN, not draftable — uncertainty ranks down.

        An operator who invents `status: hold` gets protection, not a surprise
        rewrite of copy they were deliberately holding."""
        for invented in ("hold", "paused", "do-not-send", "", "TO-SEND", "Approved"):
            assert is_frozen(invented), f"{invented!r} should be frozen"


class TestReadStatus:
    def test_missing_note_returns_none(self, tmp_path):
        assert read_status(tmp_path, "nobody") is None

    def test_reads_existing_status(self, tmp_path):
        (tmp_path / "acme.md").write_text(EXISTING.format(status="approved"), encoding="utf-8")
        assert read_status(tmp_path, "acme") == "approved"

    def test_does_not_write(self, tmp_path):
        path = tmp_path / "acme.md"
        content = EXISTING.format(status="sent")
        path.write_text(content, encoding="utf-8")
        read_status(tmp_path, "acme")
        assert path.read_text(encoding="utf-8") == content


class TestMergeFreeze:
    def test_frozen_draft_is_preserved_byte_for_byte(self):
        merged = merge_notes(EXISTING.format(status="approved"), FRESH, freeze_draft=True)
        assert section(merged, "Draft") == section(EXISTING.format(status="approved"), "Draft")
        assert "REGENERATED" not in merged

    def test_frozen_note_still_refreshes_research(self):
        """Research is machine-owned observation, not approved copy."""
        merged = merge_notes(EXISTING.format(status="sent"), FRESH, freeze_draft=True)
        assert "25 years in business" in section(merged, "Research")

    def test_frozen_note_refreshes_other_machine_frontmatter(self):
        merged = merge_notes(EXISTING.format(status="sent"), FRESH, freeze_draft=True)
        frontmatter, _ = parse_note(merged)
        assert frontmatter["fb_signal"] == "strong"  # machine-owned, from fresh
        assert frontmatter["status"] == "sent"  # human-owned, preserved

    def test_unfrozen_draft_is_replaced(self):
        merged = merge_notes(EXISTING.format(status="to-send"), FRESH)
        assert "REGENERATED" in section(merged, "Draft")
        assert "APPROVED BODY" not in merged

    def test_log_preserved_either_way(self):
        for freeze in (True, False):
            merged = merge_notes(EXISTING.format(status="approved"), FRESH, freeze_draft=freeze)
            assert "approved by hand" in section(merged, "Log")

    def test_preexisting_key_order_is_preserved(self):
        """006 appends draft_source/outcome rather than inserting them.

        A pre-006 note gains the two keys on first re-run — that is expected —
        but every key it already had must keep its relative position, so the
        first re-run produces content diffs rather than 130 reorderings."""
        merged = merge_notes(EXISTING.format(status="approved"), FRESH, freeze_draft=True)
        before = list(parse_note(EXISTING.format(status="approved"))[0])
        after = list(parse_note(merged)[0])

        assert [k for k in after if k in before] == before, "existing keys reordered"
        # 006 appended draft_source/outcome; 007 appended facebook_url — all
        # before tags, none reordering the keys the note already had.
        assert set(after) - set(before) == {"draft_source", "outcome", "facebook_url"}
        assert after.index("draft_source") < after.index("tags")
        assert after.index("outcome") < after.index("tags")
        assert after.index("facebook_url") < after.index("tags")


class TestUpsertFreeze:
    def test_frozen_note_draft_survives_upsert(self, tmp_path):
        (tmp_path / "acme.md").write_text(EXISTING.format(status="approved"), encoding="utf-8")
        upsert_note(tmp_path, "acme", FRESH, freeze_draft=True)
        written = (tmp_path / "acme.md").read_text(encoding="utf-8")
        assert "THE APPROVED BODY" in written
        assert "REGENERATED" not in written

    def test_byte_idempotent_when_nothing_changed(self, tmp_path):
        (tmp_path / "acme.md").write_text(EXISTING.format(status="approved"), encoding="utf-8")
        upsert_note(tmp_path, "acme", FRESH, freeze_draft=True)
        first = (tmp_path / "acme.md").read_text(encoding="utf-8")
        result = upsert_note(tmp_path, "acme", FRESH, freeze_draft=True)
        assert result == "unchanged"
        assert (tmp_path / "acme.md").read_text(encoding="utf-8") == first
