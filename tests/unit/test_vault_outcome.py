"""Measurement fields: draft_source and outcome (006 US5, FR-331..FR-333).

`outcome` is the second human-owned frontmatter key. The tool writes it empty
on creation and never again — without that, the template-era baseline is gone
the moment the agent rollout completes and the comparison is unrecoverable.
"""

from prospector.vault import (
    DASHBOARD_CONTENT,
    FRONTMATTER_KEYS,
    HUMAN_OWNED_KEYS,
    merge_notes,
    parse_note,
    upsert_note,
)

BASE = """---
company: Acme Duct
email: scott@acmeduct.com
channel: email
status: {status}
name_used: team
name_confidence: none
name_candidate:
hook: 22 years
website: acmeduct.com
angle: offer-led
fb_signal: none
duplicate_of:
needs_review: false
draft_source: {source}
outcome: {outcome}
tags: [outreach, duct-cleaning, prospector]
---

## Draft
**Subject:** S

B

## Research
- Owner name: not found

## Log
-
"""


def note(status="to-send", source="agent", outcome=""):
    return BASE.format(status=status, source=source, outcome=outcome)


class TestKeys:
    def test_both_keys_present_and_before_tags(self):
        assert "draft_source" in FRONTMATTER_KEYS
        assert "outcome" in FRONTMATTER_KEYS
        assert FRONTMATTER_KEYS.index("draft_source") < FRONTMATTER_KEYS.index("tags")
        assert FRONTMATTER_KEYS.index("outcome") < FRONTMATTER_KEYS.index("tags")

    def test_outcome_is_human_owned(self):
        assert "outcome" in HUMAN_OWNED_KEYS
        assert "status" in HUMAN_OWNED_KEYS
        assert "draft_source" not in HUMAN_OWNED_KEYS


class TestOutcomePreservation:
    def test_outcome_preserved_across_rerun(self):
        """FR-332: the operator's record survives every re-run."""
        existing = note(outcome="replied")
        fresh = note(outcome="")
        merged = merge_notes(existing, fresh)
        assert parse_note(merged)[0]["outcome"] == "replied"

    def test_outcome_preserved_on_frozen_note_too(self):
        merged = merge_notes(note(status="sent", outcome="interested"), note(), freeze_draft=True)
        assert parse_note(merged)[0]["outcome"] == "interested"

    def test_unrecognized_outcome_value_is_preserved_not_corrected(self):
        """Values are a convention, not an enforced enum."""
        merged = merge_notes(note(outcome="called me back"), note())
        assert parse_note(merged)[0]["outcome"] == "called me back"

    def test_empty_outcome_stays_empty(self):
        merged = merge_notes(note(outcome=""), note(outcome=""))
        assert parse_note(merged)[0]["outcome"] == ""

    def test_outcome_survives_repeated_reruns(self, tmp_path):
        (tmp_path / "acme.md").write_text(note(outcome="replied"), encoding="utf-8")
        for _ in range(3):
            upsert_note(tmp_path, "acme", note(outcome=""))
        text = (tmp_path / "acme.md").read_text(encoding="utf-8")
        assert parse_note(text)[0]["outcome"] == "replied"


class TestDraftSourceIsMachineOwned:
    def test_draft_source_follows_fresh_when_not_frozen(self):
        merged = merge_notes(note(source="template"), note(source="agent"))
        assert parse_note(merged)[0]["draft_source"] == "agent"

    def test_draft_source_preserved_with_a_frozen_draft(self):
        """A preserved draft must keep the source that describes it."""
        merged = merge_notes(note(status="sent", source="template"), note(source="agent"), freeze_draft=True)
        assert parse_note(merged)[0]["draft_source"] == "template"


class TestDashboard:
    def test_dashboard_groups_by_draft_source(self):
        assert DASHBOARD_CONTENT.count("GROUP BY draft_source") == 2

    def test_dashboard_compares_outcome_by_source(self):
        """SC-308: reply rate per drafting path, answerable from the dashboard."""
        assert 'GROUP BY draft_source + " / " + outcome' in DASHBOARD_CONTENT
        assert "WHERE outcome" in DASHBOARD_CONTENT
