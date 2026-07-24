import httpx
import respx

from prospector.config import Settings
from prospector.fetch import Fetcher
from prospector.models import Company, EvidenceKind
from prospector.resolve import ResolveInfo, fb_search_evidence, resolve

from pathlib import Path


def settings(places_key=None):
    return Settings(
        openrouter_key="sk-test", openrouter_model="m", places_key=places_key,
        hunter_key=None, vault_dir=Path("Vault/Outreach"),
    )


def instant_fetcher():
    return Fetcher(clock=lambda: 0.0, sleep=lambda s: None)


def ddg_html(*results):
    links = "".join(f'<a class="result__a" href="{href}">{title}</a>' for href, title in results)
    return f"<html><body><div class='results'>{links}</div></body></html>"


ACME = Company(company="Acme Duct Cleaning", email="info@acmeduct.com", city="Boston")


class TestInputWebsiteWins:
    def test_given_website_used_directly(self):
        company = Company(company="Acme", email=None, website="https://acme.com")
        info = resolve(company, settings(), instant_fetcher())
        assert info.website == "https://acme.com"
        assert info.sources_consulted == []


class TestPlacesPath:
    @respx.mock
    def test_places_resolves_website_and_city(self):
        respx.post("https://places.googleapis.com/v1/places:searchText").mock(
            return_value=httpx.Response(200, json={
                "places": [{
                    "websiteUri": "https://acmeduct.com/",
                    "formattedAddress": "12 Main St, Boston, MA 02101, USA",
                    "displayName": {"text": "Acme Duct Cleaning"},
                }]
            })
        )
        info = resolve(ACME, settings(places_key="g-key"), instant_fetcher())
        assert info.website == "https://acmeduct.com"
        assert info.gbp_city == "Boston"
        assert "google-places" in info.sources_consulted

    @respx.mock
    def test_places_error_falls_through_to_ddg(self):
        respx.post("https://places.googleapis.com/v1/places:searchText").mock(return_value=httpx.Response(500))
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text=ddg_html(("https://acmeduct.com", "Acme Duct Cleaning")))
        )
        respx.get("https://acmeduct.com").mock(
            return_value=httpx.Response(200, text="<html><body>Acme Duct Cleaning of Boston</body></html>")
        )
        info = resolve(ACME, settings(places_key="g-key"), instant_fetcher())
        assert info.website == "https://acmeduct.com"
        assert any("google-places failed" in f for f in info.failures)


class TestDdgPath:
    @respx.mock
    def test_ddg_resolves_with_homepage_validation(self):
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text=ddg_html(
                ("https://yelp.com/biz/acme-duct", "Acme on Yelp"),
                ("//duckduckgo.com/l/?uddg=https%3A%2F%2Facmeduct.com%2F", "Acme Duct Cleaning"),
            ))
        )
        respx.get("https://acmeduct.com").mock(
            return_value=httpx.Response(200, text="<html><body>Welcome to Acme Duct Cleaning</body></html>")
        )
        info = resolve(ACME, settings(), instant_fetcher())
        assert info.website == "https://acmeduct.com"

    @respx.mock
    def test_implausible_domain_rejected(self):
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text=ddg_html(("https://unrelated-plumbing.com", "Plumbing")))
        )
        info = resolve(ACME, settings(), instant_fetcher())
        assert info.website is None
        assert any("could not be resolved" in f for f in info.failures)

    @respx.mock
    def test_homepage_not_mentioning_company_rejected(self):
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text=ddg_html(("https://acmeduct.com", "Acme")))
        )
        respx.get("https://acmeduct.com").mock(
            return_value=httpx.Response(200, text="<html><body>Domain for sale</body></html>")
        )
        info = resolve(ACME, settings(), instant_fetcher())
        assert info.website is None

    @respx.mock
    def test_facebook_results_never_fetched(self):
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text=ddg_html(
                ("https://www.facebook.com/acmeduct", "Acme Duct | Facebook"),
                ("https://acmeduct.com", "Acme Duct Cleaning"),
            ))
        )
        homepage = respx.get("https://acmeduct.com").mock(
            return_value=httpx.Response(200, text="<html><body>Acme Duct Cleaning</body></html>")
        )
        fb = respx.get(url__startswith="https://www.facebook.com").mock(return_value=httpx.Response(200))
        info = resolve(ACME, settings(), instant_fetcher())
        assert info.website == "https://acmeduct.com"
        assert fb.call_count == 0
        assert homepage.call_count == 1

    @respx.mock
    def test_network_error_never_raises(self):
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            side_effect=httpx.ConnectTimeout("down")
        )
        info = resolve(ACME, settings(), instant_fetcher())
        assert info.website is None
        assert any("ddg search failed" in f for f in info.failures)


def ddg_html_with_snippets(*results):
    blocks = "".join(
        f'<div class="result"><a class="result__a" href="{href}">{title}</a>'
        f'<a class="result__snippet" href="{href}">{snippet}</a></div>'
        for href, title, snippet in results
    )
    return f"<html><body>{blocks}</body></html>"


class TestFbSearchEvidence:
    @respx.mock
    def test_active_fb_page_in_snippets_yields_evidence_without_fetching_fb(self):
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text=ddg_html_with_snippets(
                ("https://www.facebook.com/acmeduct", "Acme Duct Cleaning | Facebook",
                 "Acme Duct Cleaning. 312 likes. Posted 3 days ago: fall specials"),
            ))
        )
        fb = respx.get(url__startswith="https://www.facebook.com").mock(return_value=httpx.Response(200))
        info = ResolveInfo()
        evidence = fb_search_evidence(ACME, instant_fetcher(), info)
        assert evidence is not None
        assert evidence.kind is EvidenceKind.FB_SEARCH_ACTIVE
        assert evidence.value == "https://www.facebook.com/acmeduct"
        assert fb.call_count == 0, "the FB page itself must never be fetched"

    @respx.mock
    def test_fb_page_without_activity_cues_defaults_down_to_nothing(self):
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text=ddg_html_with_snippets(
                ("https://www.facebook.com/acmeduct", "Acme Duct", "A page on Facebook"),
            ))
        )
        assert fb_search_evidence(ACME, instant_fetcher(), ResolveInfo()) is None

    @respx.mock
    def test_no_fb_result_yields_nothing(self):
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text=ddg_html_with_snippets(
                ("https://acmeduct.com", "Acme Duct Cleaning", "official site, 500 reviews"),
            ))
        )
        assert fb_search_evidence(ACME, instant_fetcher(), ResolveInfo()) is None

    @respx.mock
    def test_search_failure_recorded_not_raised(self):
        respx.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            side_effect=httpx.ConnectTimeout("down")
        )
        info = ResolveInfo()
        assert fb_search_evidence(ACME, instant_fetcher(), info) is None
        assert any("ddg fb search failed" in f for f in info.failures)
