"""008 US5: a note written under the pre-008 schema survives a re-run.

There is no migration pass (FR-024). A legacy note — carrying the now-removed
`fb_signal` / `facebook_url` keys, and very possibly `status: approved` — simply
converges on the current schema the next time its company is processed. What it
MUST NOT lose in doing so is human-owned value (FR-023): `status`, `outcome`,
the `## Log`, and any section the operator added themselves.

The removed keys are machine-owned observation, so convergence dropping them is
the specified outcome, not a regression — that distinction is what these tests
pin down. This is the vault half of SC-006; T038 checks it against real notes.
"""

from prospector import vault
from prospector.models import Company, Confidence, Prospect, ResearchResult

# A note exactly as feature 007 would have written it: fb_signal and
# facebook_url present, approved by a human, with an outcome, a real log and a
# hand-added section.
LEGACY_NOTE = """---
company: Summit Duct Care
email: info@summitduct.example.com
channel: email
status: approved
name_used: Scott
name_confidence: high
name_candidate:
hook: Denver service area
website: summitduct.example.com
angle: offer-led
fb_signal: strong
facebook_url: https://facebook.com/summitduct
duplicate_of:
needs_review: false
draft_source: agent
outcome: replied - wants a call in August
tags: [outreach, duct-cleaning, prospector]
---

## Draft
**Subject:** Free 10-day pilot for Summit Duct Care

Hi Scott,

The approved copy a human already read.

Anas
Founder, Omniveer

## Research
- Owner name: Scott (about page)

## Log
- 2026-07-18 approved by hand
- 2026-07-19 followed up

## Notes from the call
Scott asked about pricing tiers. Call back after Labor Day.
Do not lose this.
"""

CUSTOM_HEADING = "Notes from the call"


def legacy_prospect():
    company = Company(
        company="Summit Duct Care",
        email="info@summitduct.example.com",
        raw_email_field="info@summitduct.example.com",
        city="Denver",
    )
    company.slug = "summit-duct-care"
    research = ResearchResult(website="https://summitduct.example.com", hook="Denver service area")
    prospect = Prospect(company=company, research=research)
    prospect.name_used = "Scott"
    prospect.name_confidence = Confidence.HIGH
    return prospect


def rerun(vault_dir, *, freeze_draft=True) -> str:
    """Write the legacy note, then re-process the same company over it."""
    path = vault_dir / "summit-duct-care.md"
    path.write_text(LEGACY_NOTE, encoding="utf-8")
    fresh = vault.render_note(
        legacy_prospect(),
        "**Subject:** Regenerated subject\n\nRegenerated body.",
        "- Owner name: Scott (about page)",
        tags_line="[outreach, duct-cleaning, prospector]",
    )
    vault.upsert_note(vault_dir, "summit-duct-care", fresh, freeze_draft=freeze_draft)
    return path.read_text(encoding="utf-8")


class TestHumanOwnedContentSurvives:
    """FR-023: nothing the human owns may be lost."""

    def test_status_is_preserved(self, tmp_path):
        frontmatter, _ = vault.parse_note(rerun(tmp_path))
        assert frontmatter["status"] == "approved"

    def test_outcome_is_preserved(self, tmp_path):
        frontmatter, _ = vault.parse_note(rerun(tmp_path))
        assert frontmatter["outcome"] == "replied - wants a call in August"

    def test_log_is_preserved_verbatim(self, tmp_path):
        _, sections = vault.parse_note(rerun(tmp_path))
        log = dict(sections)["Log"].strip("\n")
        assert log == "- 2026-07-18 approved by hand\n- 2026-07-19 followed up"

    def test_custom_section_is_preserved_verbatim(self, tmp_path):
        _, sections = vault.parse_note(rerun(tmp_path))
        body = dict(sections)[CUSTOM_HEADING].strip("\n")
        assert "Scott asked about pricing tiers" in body
        assert "Do not lose this." in body

    def test_custom_section_stays_after_the_known_sections(self, tmp_path):
        _, sections = vault.parse_note(rerun(tmp_path))
        headings = [h for h, _ in sections]
        assert headings[-1] == CUSTOM_HEADING

    def test_approved_draft_is_not_regenerated(self, tmp_path):
        """An approved note is frozen: re-drafting would send unreviewed words."""
        text = rerun(tmp_path)
        assert "The approved copy a human already read." in text
        assert "Regenerated body." not in text
        assert "**Subject:** Free 10-day pilot for Summit Duct Care" in text


class TestConvergesOnTheCurrentSchema:
    """FR-024: the removed fields leave; no migration pass is involved."""

    def test_removed_facebook_keys_are_gone(self, tmp_path):
        text = rerun(tmp_path)
        frontmatter, _ = vault.parse_note(text)
        assert "fb_signal" not in frontmatter
        assert "facebook_url" not in frontmatter
        assert "facebook" not in text.lower()

    def test_frontmatter_is_exactly_the_current_schema(self, tmp_path):
        frontmatter, _ = vault.parse_note(rerun(tmp_path))
        assert tuple(frontmatter) == vault.FRONTMATTER_KEYS

    def test_research_still_refreshes(self, tmp_path):
        """Research is machine-owned observation, so it is not frozen."""
        _, sections = vault.parse_note(rerun(tmp_path))
        assert "Scott (about page)" in dict(sections)["Research"]

    def test_a_second_rerun_is_a_no_op(self, tmp_path):
        """Convergence is stable: once migrated, re-running changes no bytes."""
        first = rerun(tmp_path)
        fresh = vault.render_note(
            legacy_prospect(),
            "**Subject:** Regenerated subject\n\nRegenerated body.",
            "- Owner name: Scott (about page)",
            tags_line="[outreach, duct-cleaning, prospector]",
        )
        result = vault.upsert_note(tmp_path, "summit-duct-care", fresh, freeze_draft=True)
        assert result == "unchanged"
        assert (tmp_path / "summit-duct-care.md").read_text(encoding="utf-8") == first


class TestLegacyNoteStillSendable:
    """A legacy approved note must remain deliverable (FR-020 unchanged send)."""

    def test_send_can_still_parse_an_approved_legacy_note(self, tmp_path):
        rerun(tmp_path)
        text = (tmp_path / "summit-duct-care.md").read_text(encoding="utf-8")
        subject, body = vault.parse_draft(text)
        assert subject == "Free 10-day pilot for Summit Duct Care"
        assert "The approved copy a human already read." in body
