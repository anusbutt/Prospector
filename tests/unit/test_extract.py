from pathlib import Path

import httpx
import respx

from prospector.extract import PageContent, detect_fb_evidence, discover_extra_pages, extract
from prospector.models import Company, EvidenceKind

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sites"


def fixture(site, page):
    return (FIXTURES / site / page).read_text()


class TestDiscoverExtraPages:
    def test_finds_about_and_contact_from_nav(self):
        pages = discover_extra_pages(fixture("acme", "index.html"), "https://acmeduct.com")
        kinds = dict(pages)
        assert kinds["about"] == "https://acmeduct.com/about"
        assert kinds["contact"] == "https://acmeduct.com/contact"
        assert "services" not in [k for k, _ in pages]

    def test_external_links_ignored(self):
        html = '<a href="https://other.com/about">About</a>'
        assert discover_extra_pages(html, "https://acmeduct.com") == []

    def test_capped_at_three(self):
        html = (
            '<a href="/about">a</a><a href="/team">t</a>'
            '<a href="/contact">c</a><a href="/about-more">m</a>'
        )
        assert len(discover_extra_pages(html, "https://x.com")) <= 3


class TestNameExtraction:
    def test_owner_found_on_about_page_with_evidence(self):
        company = Company(company="Acme Duct Cleaning", email="info@acmeduct.com")
        outcome = extract(
            company,
            [
                PageContent("homepage", "https://acmeduct.com", fixture("acme", "index.html")),
                PageContent("about", "https://acmeduct.com/about", fixture("acme", "about.html")),
            ],
        )
        assert outcome.name_evidence, "expected a name candidate"
        best = outcome.name_evidence[0]
        assert best.value == "Scott Brown"
        assert best.kind is EvidenceKind.ABOUT_PAGE
        assert best.source == "https://acmeduct.com/about"
        assert "Scott Brown" in best.excerpt

    def test_footer_copyright_name(self):
        company = Company(company="Beta Air Systems", email=None)
        outcome = extract(
            company,
            [PageContent("homepage", "https://betaair.com", fixture("footer-name", "index.html"))],
        )
        values = {(e.value, e.kind) for e in outcome.name_evidence}
        assert ("John Smith", EvidenceKind.FOOTER) in values

    def test_generic_and_company_words_rejected(self):
        company = Company(company="Duct Master Pros", email=None)
        outcome = extract(
            company,
            [PageContent("about", "https://ductmaster.com/about", fixture("generic", "about.html"))],
        )
        assert outcome.name_evidence == []

    def test_real_world_page_furniture_never_becomes_a_name(self):
        # Regression: live sites produced "Whether You", "Quick Links",
        # "Main Office", "Any Time", "Owner Operated" near owner-keywords
        # and they were greeted at high confidence (T027 live catch).
        html = """<html><body>
        <p>Whether You need duct work, our owner is ready.</p>
        <p>Quick Links for the owner operated business.</p>
        <p>Main Office: founded by Any Time Duct Services.</p>
        <p>Owner Operated since 1999.</p>
        </body></html>"""
        company = Company(company="Some Duct Co", email=None)
        outcome = extract(company, [PageContent("about", "https://x.com/about", html)])
        assert outcome.name_evidence == [], [e.value for e in outcome.name_evidence]

    def test_rare_unlisted_name_dropped_not_fabricated(self):
        # a bigram whose first word is not a known first name is dropped:
        # losing a rare real name beats greeting a fake one
        html = "<html><body><p>Founded by Zorblat Smith, owner.</p></body></html>"
        company = Company(company="Some Duct Co", email=None)
        outcome = extract(company, [PageContent("about", "https://x.com/about", html)])
        assert outcome.name_evidence == []

    def test_company_copyright_not_a_name(self):
        company = Company(company="Acme Duct Cleaning", email=None)
        outcome = extract(
            company,
            [PageContent("homepage", "https://acmeduct.com", fixture("acme", "index.html"))],
        )
        # homepage alone: footer says "© 2025 Acme Duct Cleaning" -> not a person
        assert all(e.value != "Acme Duct" for e in outcome.name_evidence)
        assert outcome.name_evidence == []


class TestFbEvidence:
    def page(self, site):
        return [PageContent("homepage", f"https://{site}.test", fixture(site, "index.html"))]

    @respx.mock
    def test_widget_site_yields_widget_and_link(self):
        catch_all = respx.route().mock(return_value=httpx.Response(200))
        evidence = detect_fb_evidence(self.page("fb-widget"))
        kinds = {e.kind for e in evidence}
        assert EvidenceKind.FB_WIDGET in kinds
        assert EvidenceKind.FB_LINK in kinds
        assert catch_all.call_count == 0, "fb detection must never fetch"

    @respx.mock
    def test_embed_site_yields_embed_not_link(self):
        catch_all = respx.route().mock(return_value=httpx.Response(200))
        evidence = detect_fb_evidence(self.page("fb-embed"))
        kinds = {e.kind for e in evidence}
        assert kinds == {EvidenceKind.FB_EMBED}
        assert catch_all.call_count == 0

    @respx.mock
    def test_bare_footer_link_yields_single_soft_signal(self):
        catch_all = respx.route().mock(return_value=httpx.Response(200))
        evidence = detect_fb_evidence(self.page("fb-link"))
        assert [e.kind for e in evidence] == [EvidenceKind.FB_LINK]
        assert evidence[0].value == "https://www.facebook.com/zetavents"
        assert catch_all.call_count == 0

    @respx.mock
    def test_no_fb_site_yields_nothing(self):
        catch_all = respx.route().mock(return_value=httpx.Response(200))
        assert detect_fb_evidence(self.page("plain")) == []
        assert catch_all.call_count == 0

    def test_one_evidence_per_kind_across_pages(self):
        pages = self.page("fb-link") + [
            PageContent("about", "https://zeta.test/about", fixture("fb-link", "index.html"))
        ]
        evidence = detect_fb_evidence(pages)
        assert len([e for e in evidence if e.kind is EvidenceKind.FB_LINK]) == 1


class TestCityAndHook:
    def test_city_from_city_state_pattern(self):
        company = Company(company="Beta Air Systems", email=None)
        outcome = extract(
            company,
            [PageContent("homepage", "https://betaair.com", fixture("footer-name", "index.html"))],
        )
        assert outcome.city == "Denver"

    def test_hook_from_serving_area(self):
        company = Company(company="Plain Ducts", email=None)
        outcome = extract(
            company,
            [PageContent("homepage", "https://plainducts.com", fixture("plain", "index.html"))],
        )
        assert outcome.hook == "Springfield service area"
        assert outcome.hook_evidence is not None
        assert outcome.hook_evidence.kind is EvidenceKind.HOOK_SOURCE
        assert "serving the Springfield area" in outcome.hook_evidence.excerpt

    def test_years_hook_fallback(self):
        company = Company(company="Beta Air Systems", email=None)
        html = "<html><body><p>Trusted for 12 years and counting.</p></body></html>"
        outcome = extract(company, [PageContent("homepage", "https://betaair.com", html)])
        assert outcome.hook == "12 years in business"

    def test_no_hook_when_nothing_found(self):
        company = Company(company="X Co", email=None)
        html = "<html><body><p>Welcome.</p></body></html>"
        outcome = extract(company, [PageContent("homepage", "https://x.com", html)])
        assert outcome.hook is None
        assert outcome.city is None
