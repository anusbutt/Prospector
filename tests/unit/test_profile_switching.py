"""008 US3: the same pipeline serves a different vertical by selecting a profile.

This is the test that makes the feature true rather than merely plumbed. Given
identical input, two profiles must produce different copy, signature,
promotional link and note tags — and the second profile must need no code
change to exist (Constitution v7.0.0, Principle VI).
"""

import pytest

from prospector.draft import assemble_email
from prospector.models import Company, Prospect, ResearchResult
from prospector.profiles import load
from prospector.vault import parse_note, render_note

# The greeting slot carries the WHOLE resolved greeting, not the bare fallback
# word: `request_slots` hands the model `expected_greeting(prospect)` and the
# validator re-derives the same string, so "team" alone would be rejected.
SLOTS = {"greeting_name": "Acme Services team", "subject_company": "Acme"}

HVAC_TOML = """tags = ["outreach", "hvac", "prospector"]
signature = "Dana\\nFounder, Warmly"
product_url = "https://warmly.example/hvac-assistant"
keywords = ["hvac repair", "furnace install"]
banned_claims = ["running ads", "your ads"]
"""

HVAC_FALLBACK = """## Subject
Two-week pilot for {subject_company}

## Template
Hi {greeting},

We run a two-week pilot for independent HVAC shops.

It answers after-hours calls and books the job.

See it here:
https://warmly.example/hvac-assistant

Reply if you would like a slot.

{signature}

## Invariants
- We run a two-week pilot for independent HVAC shops.
- It answers after-hours calls and books the job.
"""


@pytest.fixture
def hvac(tmp_path, monkeypatch):
    """A second vertical, created with files only — no code change."""
    root = tmp_path / "profiles" / "hvac"
    (root / "skills").mkdir(parents=True)
    (root / "IDENTITY.md").write_text("You are Dana of Warmly.", encoding="utf-8")
    (root / "OFFER.md").write_text("A two-week pilot for HVAC shops.", encoding="utf-8")
    (root / "CONSTRAINTS.md").write_text("Never invent facts.", encoding="utf-8")
    (root / "skills" / "write-cold-email.md").write_text("Be brief.", encoding="utf-8")
    (root / "fallback.md").write_text(HVAC_FALLBACK, encoding="utf-8")
    (root / "profile.toml").write_text(HVAC_TOML, encoding="utf-8")
    monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "profiles"))
    return load("hvac")


def prospect():
    company = Company(company="Acme Services", email="info@acme.com", raw_email_field="info@acme.com")
    return Prospect(company=company, research=ResearchResult(website="https://acme.com"))


class TestSameInputDifferentProfile:
    def test_bodies_differ(self, hvac, duct_profile):
        duct = assemble_email(prospect(), SLOTS, duct_profile)
        other = assemble_email(prospect(), SLOTS, hvac)
        assert duct.body != other.body

    def test_each_body_carries_its_own_offer_and_link(self, hvac, duct_profile):
        duct = assemble_email(prospect(), SLOTS, duct_profile)
        other = assemble_email(prospect(), SLOTS, hvac)
        assert duct_profile.product_url in duct.body
        assert hvac.product_url in other.body
        assert hvac.product_url not in duct.body
        assert duct_profile.product_url not in other.body

    def test_each_body_ends_with_its_own_signature(self, hvac, duct_profile):
        assert assemble_email(prospect(), SLOTS, duct_profile).body.rstrip().endswith(duct_profile.signature)
        assert assemble_email(prospect(), SLOTS, hvac).body.rstrip().endswith(hvac.signature)

    def test_subjects_differ(self, hvac, duct_profile):
        duct = assemble_email(prospect(), SLOTS, duct_profile)
        other = assemble_email(prospect(), SLOTS, hvac)
        assert duct.subject != other.subject
        assert "Acme" in duct.subject and "Acme" in other.subject

    def test_both_validate_against_their_own_invariants(self, hvac, duct_profile):
        """Each profile's copy is judged by its own locked prose, not the other's."""
        for profile in (duct_profile, hvac):
            draft = assemble_email(prospect(), SLOTS, profile)
            assert draft.validated, draft.validation_errors

    def test_note_tags_come_from_the_profile(self, hvac, duct_profile):
        for profile in (duct_profile, hvac):
            note = render_note(prospect(), "d", "r", tags_line=profile.tags_line)
            assert parse_note(note)[0]["tags"] == profile.tags_line

    def test_sourcing_keywords_come_from_the_profile(self, hvac, duct_profile):
        assert hvac.keywords[0] == "hvac repair"
        assert hvac.keywords[0] != duct_profile.keywords[0]
