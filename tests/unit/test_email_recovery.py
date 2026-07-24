"""008 US2: recovering a published address instead of bucketing the company.

A company with no supplied address is not discarded — the pages already fetched
for research are searched for a published address. Selection must be
deterministic (research.md R2) and the adopted address must be recorded as
evidence with its source, like every other fact (FR-007).

No page is fetched here: recovery only reads what research already has (FR-011).
"""

from prospector.extract import PageContent, recover_email
from prospector.models import EvidenceKind


def page(kind, html, url=None):
    return PageContent(kind, url or f"https://acme.com/{kind}", html)


def mailto(addr):
    return f'<html><body><a href="mailto:{addr}">write us</a></body></html>'


class TestPagePriority:
    """Contact page beats about/team, which beat the homepage (R2)."""

    def test_contact_page_wins_over_homepage(self):
        pages = [
            page("homepage", mailto("home@acme.com"), "https://acme.com"),
            page("contact", mailto("contact@acme.com")),
        ]
        found, _ = recover_email(pages)
        assert found == "contact@acme.com"

    def test_about_beats_homepage(self):
        pages = [
            page("homepage", mailto("home@acme.com"), "https://acme.com"),
            page("about", mailto("about@acme.com")),
        ]
        found, _ = recover_email(pages)
        assert found == "about@acme.com"

    def test_contact_beats_about(self):
        pages = [
            page("about", mailto("about@acme.com")),
            page("contact", mailto("contact@acme.com")),
        ]
        found, _ = recover_email(pages)
        assert found == "contact@acme.com"

    def test_homepage_used_when_it_is_all_there_is(self):
        found, _ = recover_email([page("homepage", mailto("home@acme.com"), "https://acme.com")])
        assert found == "home@acme.com"


class TestDeterminism:
    def test_same_pages_yield_same_address(self):
        pages = [
            page("homepage", mailto("a@acme.com"), "https://acme.com"),
            page("contact", mailto("b@acme.com")),
            page("about", mailto("c@acme.com")),
        ]
        assert recover_email(pages)[0] == recover_email(pages)[0]

    def test_page_order_does_not_change_the_choice(self):
        a = page("homepage", mailto("home@acme.com"), "https://acme.com")
        b = page("contact", mailto("contact@acme.com"))
        assert recover_email([a, b])[0] == recover_email([b, a])[0]


class TestRejection:
    def test_no_address_anywhere_returns_none(self):
        found, evidence = recover_email([page("homepage", "<html><body>no mail here</body></html>")])
        assert found is None and evidence is None

    def test_asset_filename_is_not_an_address(self):
        html = "<html><body>logo@2x.png sprite@3x.jpg</body></html>"
        assert recover_email([page("homepage", html)])[0] is None

    def test_no_pages_at_all(self):
        assert recover_email([]) == (None, None)


class TestEvidence:
    def test_adopted_address_is_recorded_with_its_source(self):
        found, evidence = recover_email([page("contact", mailto("info@acme.com"))])
        assert found == "info@acme.com"
        assert evidence is not None
        assert evidence.kind is EvidenceKind.EMAIL_PUBLISHED
        assert evidence.value == "info@acme.com"
        assert evidence.source == "https://acme.com/contact"
        assert evidence.excerpt

    def test_no_evidence_when_nothing_found(self):
        assert recover_email([page("homepage", "<html><body>nope</body></html>")])[1] is None


class TestDomainMatchGuard:
    """An address is adopted only if it belongs to the site publishing it.

    Website resolution can land on the wrong company. A wrong `website` field is
    cosmetic; a wrong ADDRESS is something we would actually mail — so recovery
    defaults down (research.md R2, live finding 2026-07-25)."""

    def test_matching_domain_is_adopted(self):
        found, _ = recover_email(
            [page("contact", mailto("cliff@ductsunlimited.com"), "https://ductsunlimited.com/contact")]
        )
        assert found == "cliff@ductsunlimited.com"

    def test_subdomain_still_counts_as_the_same_organisation(self):
        found, _ = recover_email(
            [page("contact", mailto("info@acme.com"), "https://www.acme.com/contact")]
        )
        assert found == "info@acme.com"

    def test_stranger_gmail_on_an_unrelated_site_is_rejected(self):
        """The live regression: a DDG-resolved wrong site offered a personal Gmail."""
        found, evidence = recover_email(
            [page("homepage", mailto("christiancorrea26@gmail.com"), "https://auroramessenger.com/")]
        )
        assert found is None and evidence is None

    def test_other_companys_address_is_rejected(self):
        found, _ = recover_email(
            [page("contact", mailto("sales@someoneelse.com"), "https://acme.com/contact")]
        )
        assert found is None

    def test_a_matching_address_on_a_later_page_still_wins_over_nothing(self):
        pages = [
            page("contact", mailto("stranger@gmail.com"), "https://acme.com/contact"),
            page("homepage", mailto("info@acme.com"), "https://acme.com/"),
        ]
        assert recover_email(pages)[0] == "info@acme.com"
