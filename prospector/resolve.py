"""Website + Google Business resolution when the input row has no URL.

Order (research.md R1): Google Places when a key is configured, then DuckDuckGo
HTML search (no key). A candidate is accepted only if the domain plausibly
matches the company and the homepage mentions it. Never raises on network
errors — failures are recorded and the pipeline moves on.
"""

from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
from selectolax.parser import HTMLParser

from prospector.config import Settings
from prospector.fetch import FetchError, Fetcher, is_blocked_host
from prospector.models import Company, Evidence, EvidenceKind

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
DDG_URL = "https://html.duckduckgo.com/html/"

# Domains that are never a company's own website
NON_COMPANY_DOMAINS = (
    "yelp.com", "yellowpages.com", "bbb.org", "angi.com", "angieslist.com",
    "homeadvisor.com", "thumbtack.com", "houzz.com", "mapquest.com",
    "linkedin.com", "instagram.com", "twitter.com", "x.com", "youtube.com",
    "google.com", "duckduckgo.com", "wikipedia.org", "nextdoor.com",
)

GENERIC_TOKENS = {
    "the", "and", "of", "a", "llc", "inc", "co", "corp", "company", "companies",
    "services", "service", "cleaning", "cleaners", "group", "home", "pro", "pros",
}


@dataclass
class ResolveInfo:
    website: str | None = None
    gbp_city: str | None = None
    sources_consulted: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def resolve(company: Company, settings: Settings, fetcher: Fetcher) -> ResolveInfo:
    info = ResolveInfo()
    if company.website:
        info.website = company.website
        return info
    if settings.places_key:
        _try_places(company, settings, info)
    if not info.website:
        _try_ddg(company, fetcher, info)
    if not info.website:
        info.failures.append("website could not be resolved")
    return info


def _try_places(company: Company, settings: Settings, info: ResolveInfo) -> None:
    query = company.company if not company.city else f"{company.company} {company.city}"
    info.sources_consulted.append("google-places")
    try:
        response = httpx.post(
            PLACES_URL,
            headers={
                "X-Goog-Api-Key": settings.places_key,
                "X-Goog-FieldMask": "places.websiteUri,places.formattedAddress,places.displayName",
            },
            json={"textQuery": query},
            timeout=15.0,
        )
        response.raise_for_status()
        places = response.json().get("places", [])
    except (httpx.HTTPError, ValueError) as exc:
        info.failures.append(f"google-places failed: {exc}")
        return
    if not places:
        return
    place = places[0]
    website = place.get("websiteUri")
    if website and not is_blocked_host(website):
        info.website = website.rstrip("/")
    info.gbp_city = _city_from_address(place.get("formattedAddress", ""))


def _city_from_address(address: str) -> str | None:
    # "123 Main St, Boston, MA 02101, USA" -> "Boston"
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 3:
        return parts[-3] or None
    return None


def _try_ddg(company: Company, fetcher: Fetcher, info: ResolveInfo) -> None:
    query = company.company if not company.city else f"{company.company} {company.city}"
    url = f"{DDG_URL}?q={quote_plus(query)}"
    info.sources_consulted.append(f"ddg-search: {query}")
    try:
        response = fetcher.fetch(url)
    except FetchError as exc:
        info.failures.append(f"ddg search failed: {exc}")
        return
    for candidate in _ddg_result_urls(response.text)[:5]:
        if is_blocked_host(candidate) or _is_non_company(candidate):
            continue
        if not _domain_plausible(company.company, candidate):
            continue
        if _homepage_mentions(company.company, candidate, fetcher, info):
            info.website = candidate.rstrip("/")
            return


def _ddg_result_urls(html: str) -> list[str]:
    urls: list[str] = []
    for node in HTMLParser(html).css("a.result__a"):
        href = node.attributes.get("href") or ""
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
            # redirect link: //duckduckgo.com/l/?uddg=<encoded>
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                urls.append(target)
        elif href.startswith("http"):
            urls.append(href)
    return urls


# Cues in a search snippet suggesting an actively used FB page (§7.5).
FB_ACTIVITY_CUES = (
    "review", "rating", "followers", "likes", "posted", "hours ago",
    "days ago", "open now", "updated",
)


def fb_search_evidence(company: Company, fetcher: Fetcher, info: ResolveInfo) -> Evidence | None:
    """DDG search for the company's Facebook presence. Only search-result
    snippets are read — the Facebook page itself is never fetched
    (Constitution II). Returns Evidence only for an active-looking page;
    anything less defaults down to nothing (§7.5)."""
    query = f'"{company.company}" facebook'
    url = f"{DDG_URL}?q={quote_plus(query)}"
    info.sources_consulted.append(f"ddg-search: {query}")
    try:
        response = fetcher.fetch(url)
    except FetchError as exc:
        info.failures.append(f"ddg fb search failed: {exc}")
        return None
    for result_url, snippet in _ddg_results_with_snippets(response.text):
        host = (urlparse(result_url).hostname or "").lower()
        if not (host == "facebook.com" or host.endswith(".facebook.com")):
            continue
        haystack = snippet.lower()
        if any(cue in haystack for cue in FB_ACTIVITY_CUES):
            return Evidence(
                kind=EvidenceKind.FB_SEARCH_ACTIVE, value=result_url,
                source=f"ddg-search: {query}", excerpt=snippet[:200],
            )
        return None  # FB page found but no activity cues: default down
    return None


def _ddg_results_with_snippets(html: str) -> list[tuple[str, str]]:
    tree = HTMLParser(html)
    titles = tree.css("a.result__a")
    snippets = tree.css("a.result__snippet, div.result__snippet")
    results: list[tuple[str, str]] = []
    for i, node in enumerate(titles):
        href = node.attributes.get("href") or ""
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
            href = parse_qs(parsed.query).get("uddg", [""])[0]
        snippet = snippets[i].text(separator=" ").strip() if i < len(snippets) else ""
        title = node.text(separator=" ").strip()
        if href:
            results.append((href, f"{title} {snippet}".strip()))
    return results


def _is_non_company(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in NON_COMPANY_DOMAINS)


def _company_tokens(company_name: str) -> tuple[list[str], list[str]]:
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in company_name.lower()).split() if t]
    specific = [t for t in tokens if t not in GENERIC_TOKENS and len(t) >= 4]
    return tokens, specific


def _domain_plausible(company_name: str, url: str) -> bool:
    domain = (urlparse(url).hostname or "").lower().replace("-", "")
    tokens, specific = _company_tokens(company_name)
    if any(t in domain for t in specific):
        return True
    non_generic = [t for t in tokens if t not in GENERIC_TOKENS and len(t) >= 3]
    return len([t for t in non_generic if t in domain]) >= 2


def _homepage_mentions(company_name: str, url: str, fetcher: Fetcher, info: ResolveInfo) -> bool:
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    info.sources_consulted.append(origin)
    try:
        response = fetcher.fetch(origin)
    except FetchError as exc:
        info.failures.append(f"candidate homepage fetch failed: {exc}")
        return False
    if response.status_code != 200:
        return False
    text = (HTMLParser(response.text).body or HTMLParser(response.text).root).text().lower()
    _, specific = _company_tokens(company_name)
    if specific:
        return any(t in text for t in specific)
    return company_name.lower() in text
