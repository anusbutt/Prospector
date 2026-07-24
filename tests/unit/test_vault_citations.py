"""Per-paragraph citation trace in the note (SC-302).

The validator can only prove a cited record EXISTS for this company. Whether it
actually SUPPORTS the sentence is the operator's check — and that check is
impossible unless the note shows which record each paragraph claimed. These
tests guard the interface that makes the human layer performable.
"""

from prospector.models import Draft, EvidenceRef
from prospector.vault import (
    DRAFT_OWNED_SECTIONS,
    KNOWN_SECTIONS,
    build_citations_markdown,
    merge_notes,
    parse_note,
)

REFS = [
    EvidenceRef(
        id="hook_source_1",
        kind="hook_source",
        value="20 years in business",
        source="https://allproductcleaningnw.com/about-us/",
        excerpt="over 20 years of experience. All Pro Duct Cleaning is locally owned",
    ),
    EvidenceRef(
        id="fb_widget_1",
        kind="fb_widget",
        value="connect.facebook.net",
        source="https://drewsdryerventcleaning.com",
        excerpt="Messenger/FB chat widget markup on site",
    ),
]


def agent_draft(citations):
    return Draft(subject="S", body="B", model="m", source="agent", citations=citations)


class TestRendering:
    def test_evidence_citation_shows_excerpt_and_source(self):
        md = build_citations_markdown(agent_draft([["hook_source_1"]]), REFS)
        assert "hook_source_1" in md
        assert "over 20 years of experience" in md
        assert "https://allproductcleaningnw.com/about-us/" in md

    def test_offer_citation_is_labelled_as_not_about_them(self):
        md = build_citations_markdown(agent_draft([["offer"]]), REFS)
        assert "`offer`" in md
        assert "not a claim about them" in md

    def test_numbering_matches_body_paragraphs(self):
        md = build_citations_markdown(
            agent_draft([["hook_source_1"], ["offer"], ["offer"], ["offer"]]), REFS
        )
        for n in (1, 2, 3, 4):
            assert f"\n{n}. " in "\n" + md

    def test_multiple_citations_on_one_paragraph(self):
        md = build_citations_markdown(agent_draft([["hook_source_1", "fb_widget_1"]]), REFS)
        assert "hook_source_1" in md and "fb_widget_1" in md

    def test_preamble_states_the_limit_of_machine_checking(self):
        """The operator must know what the tool did and did not verify."""
        md = build_citations_markdown(agent_draft([["offer"]]), REFS)
        assert "only you can confirm" in md.lower()

    def test_template_draft_gets_no_citations_section(self):
        assert build_citations_markdown(Draft(subject="S", body="B", model="m"), REFS) == ""

    def test_no_draft_gets_no_citations_section(self):
        assert build_citations_markdown(None, REFS) == ""

    def test_unresolved_id_is_marked_not_silently_dropped(self):
        md = build_citations_markdown(agent_draft([["ghost_9"]]), REFS)
        assert "ghost_9" in md and "unresolved" in md


class TestSectionOwnership:
    def test_citations_is_a_known_section(self):
        assert "Citations" in KNOWN_SECTIONS

    def test_citations_sits_directly_under_draft(self):
        assert KNOWN_SECTIONS.index("Citations") == KNOWN_SECTIONS.index("Draft") + 1

    def test_citations_travels_with_the_draft_when_frozen(self):
        assert set(DRAFT_OWNED_SECTIONS) == {"Draft", "Citations"}


NOTE = """---
company: Acme Duct
email: a@b.com
channel: email
status: {status}
name_used: team
name_confidence: none
name_candidate:
hook: h
website: w
angle: offer-led
fb_signal: none
duplicate_of:
needs_review: false
draft_source: agent
outcome:
tags: [outreach, duct-cleaning, prospector]
---

## Draft
{draft}

## Citations
{citations}

## Research
- Owner name: not found

## Log
-
"""


def note(status="to-send", draft="OLD DRAFT", citations="1. `hook_source_1` — OLD"):
    return NOTE.format(status=status, draft=draft, citations=citations)


class TestMergeBehaviour:
    def test_citations_refresh_with_the_draft_when_not_frozen(self):
        merged = merge_notes(note(), note(draft="NEW DRAFT", citations="1. `offer` — NEW"))
        sections = dict(parse_note(merged)[1])
        assert "NEW" in sections["Citations"]
        assert "NEW DRAFT" in sections["Draft"]

    def test_frozen_note_keeps_the_citations_that_justify_its_draft(self):
        """A preserved draft with refreshed citations would be a lie."""
        merged = merge_notes(
            note(status="sent"),
            note(draft="NEW DRAFT", citations="1. `offer` — NEW"),
            freeze_draft=True,
        )
        sections = dict(parse_note(merged)[1])
        assert "OLD DRAFT" in sections["Draft"]
        assert "OLD" in sections["Citations"]
        assert "NEW" not in sections["Citations"]

    def test_citations_dropped_when_a_rerun_falls_back_to_template(self):
        """Template drafts make no per-paragraph claims, so the trace must go."""
        fresh = """---
company: Acme Duct
email: a@b.com
channel: email
status: to-send
name_used: team
name_confidence: none
name_candidate:
hook: h
website: w
angle: offer-led
fb_signal: none
duplicate_of:
needs_review: false
draft_source: template
outcome:
tags: [outreach, duct-cleaning, prospector]
---

## Draft
TEMPLATE DRAFT

## Research
- Owner name: not found

## Log
-
"""
        merged = merge_notes(note(), fresh)
        assert "Citations" not in dict(parse_note(merged)[1])

    def test_operator_sections_still_preserved_alongside_citations(self):
        existing = note().replace("## Log\n-", "## My notes\nleft a voicemail\n\n## Log\n-")
        merged = merge_notes(existing, note(draft="NEW", citations="1. `offer` — NEW"))
        sections = dict(parse_note(merged)[1])
        assert "left a voicemail" in sections["My notes"]
