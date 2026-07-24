import pytest

from prospector.enrich import NameInference, infer_from_email
from prospector.models import (
    Company,
    Confidence,
    Evidence,
    EvidenceKind,
    Prospect,
    ResearchResult,
)
from prospector.score import apply_name_scoring, first_name_of


def make_prospect(email=None, owner_name=None, name_evidence=()):
    company = Company(company="Acme Duct Cleaning", email=email, owner_name=owner_name)
    research = ResearchResult(name_evidence=list(name_evidence))
    return Prospect(company=company, research=research)


def evidence(kind, value, source="https://acmeduct.com/about"):
    return Evidence(kind=kind, value=value, source=source, excerpt=value)


NO_EMAIL = NameInference()


class TestHighTier:
    def test_scottb_email_high_greets_scott(self):
        prospect = make_prospect(email="scottb@acmeduct.com")
        apply_name_scoring(prospect, infer_from_email("scottb@acmeduct.com"))
        assert prospect.name_confidence is Confidence.HIGH
        assert prospect.name_used == "Scott"
        assert prospect.name_candidate is None
        assert not prospect.needs_review

    def test_about_page_evidence_high(self):
        prospect = make_prospect(name_evidence=[evidence(EvidenceKind.ABOUT_PAGE, "Scott Brown")])
        apply_name_scoring(prospect, NO_EMAIL)
        assert prospect.name_confidence is Confidence.HIGH
        assert prospect.name_used == "Scott"

    def test_owner_text_and_team_page_high(self):
        for kind in (EvidenceKind.OWNER_TEXT, EvidenceKind.TEAM_PAGE):
            prospect = make_prospect(name_evidence=[evidence(kind, "Jane Doe")])
            apply_name_scoring(prospect, NO_EMAIL)
            assert prospect.name_confidence is Confidence.HIGH, kind
            assert prospect.name_used == "Jane"

    def test_input_owner_name_wins_over_everything(self):
        prospect = make_prospect(
            email="derickson@x.com",
            owner_name="Maria Lopez",
            name_evidence=[evidence(EvidenceKind.FOOTER, "John Smith")],
        )
        apply_name_scoring(prospect, infer_from_email("derickson@x.com"))
        assert prospect.name_confidence is Confidence.HIGH
        assert prospect.name_used == "Maria"

    def test_site_evidence_beats_email_pattern(self):
        prospect = make_prospect(
            email="scott@acmeduct.com",
            name_evidence=[evidence(EvidenceKind.ABOUT_PAGE, "Jane Doe")],
        )
        apply_name_scoring(prospect, infer_from_email("scott@acmeduct.com"))
        assert prospect.name_used == "Jane"


class TestMediumTier:
    def test_derickson_medium_team_candidate_review(self):
        prospect = make_prospect(email="derickson@x.com")
        apply_name_scoring(prospect, infer_from_email("derickson@x.com"))
        assert prospect.name_confidence is Confidence.MEDIUM
        assert prospect.name_used == "team"
        assert prospect.name_candidate == "Derickson"
        assert prospect.needs_review

    def test_footer_name_is_medium_not_high(self):
        prospect = make_prospect(name_evidence=[evidence(EvidenceKind.FOOTER, "John Smith")])
        apply_name_scoring(prospect, NO_EMAIL)
        assert prospect.name_confidence is Confidence.MEDIUM
        assert prospect.name_used == "team"
        assert prospect.name_candidate == "John Smith"
        assert prospect.needs_review

    def test_hunter_candidate_is_medium(self):
        prospect = make_prospect(email="x@y.com")
        hunter = NameInference(candidate="Scott", evidence=evidence(EvidenceKind.HUNTER, "Scott", "hunter.io"))
        apply_name_scoring(prospect, NO_EMAIL, hunter)
        assert prospect.name_confidence is Confidence.MEDIUM
        assert prospect.name_candidate == "Scott"

    def test_footer_beats_email_candidate(self):
        prospect = make_prospect(
            email="derickson@x.com",
            name_evidence=[evidence(EvidenceKind.FOOTER, "John Smith")],
        )
        apply_name_scoring(prospect, infer_from_email("derickson@x.com"))
        assert prospect.name_candidate == "John Smith"


class TestNoneTier:
    def test_nothing_found_stays_team(self):
        prospect = make_prospect(email="info@acmeduct.com")
        apply_name_scoring(prospect, infer_from_email("info@acmeduct.com"))
        assert prospect.name_confidence is Confidence.NONE
        assert prospect.name_used == "team"
        assert prospect.name_candidate is None
        assert not prospect.needs_review


def fb_ev(kind):
    return Evidence(kind=kind, value="x", source="https://site.test")


class TestHelpers:
    def test_first_name_extraction(self):
        assert first_name_of("Scott Brown") == "Scott"
        assert first_name_of("maria lopez") == "Maria"
        assert first_name_of("Scott") == "Scott"
