"""Company sourcing: Places discovery -> dedupe -> pixel signal -> candidate CSV.

Feature 002 (specs/002-company-sourcing/). Everything here is deterministic
Python — no LLM. All web fetches go through fetch.Fetcher (Constitution II);
the Meta Pixel signal is string inspection of already-fetched HTML, and
`ad_signal` is a targeting filter only — it never reaches draft copy
(Constitution V).
"""

import csv
import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from selectolax.parser import HTMLParser

import httpx

from prospector.config import ConfigError
from prospector.fetch import BlockedHostError, Fetcher, FetchError, is_blocked_host

BUNDLED_METROS = "data/us_metros.txt"

# Same endpoint/header pattern as resolve.py, but keyword discovery instead of
# company lookup: minimal field mask (extra fields risk a higher billing SKU),
# one page per metro (research.md R1).
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.websiteUri"
MAX_RESULTS_PER_METRO = 20


@dataclass
class Candidate:
    """One discovered business (data-model.md). Durable form: a CSV row."""

    place_id: str
    company: str
    city: str = ""
    website: str | None = None  # fetchable URL (scheme kept)
    domain: str | None = None  # lowercase host, www.-stripped (dedupe + CSV)
    ad_signal: str = "none"  # "pixel" | "none"; only detect_pixel may raise it
    email: str | None = None  # publicly listed only — never inferred
    metro: str = ""
    failures: list[str] = field(default_factory=list)


@dataclass
class SourcingSummary:
    """Per-run report printed to stdout (data-model.md)."""

    metros_total: int = 0
    metros_covered: int = 0
    queries_used: int = 0
    query_budget: int = 0
    discovered: int = 0
    duplicates_collapsed: int = 0
    kept_with_all: int = 0  # unique candidates (what --all would write)
    pixel_positive: int = 0
    emails_found: int = 0
    written: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (candidate/metro, reason)


def load_metros(path: Path | None = None) -> list[str]:
    """Load the metro list: bundled default, or a --metros override file.

    Lines are `City, ST`; blanks and #-comments ignored. Empty result or an
    unreadable override file is a pre-flight ConfigError (exit 1, nothing written).
    """
    if path is None:
        text = files("prospector").joinpath(BUNDLED_METROS).read_text(encoding="utf-8")
        source = "bundled metro list"
    else:
        if not Path(path).is_file():
            raise ConfigError(f"metros file not found: {path}")
        text = Path(path).read_text(encoding="utf-8")
        source = str(path)
    metros = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not metros:
        raise ConfigError(f"no metros found in {source}")
    return metros


class PlacesSearcher:
    """Places Text Search (New), one budget-counted query per metro."""

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=httpx.Timeout(15.0, connect=10.0))

    def search(self, keyword: str, metro: str) -> list[dict]:
        """Raises httpx.HTTPError / ValueError on failure; caller isolates per metro."""
        response = self._client.post(
            PLACES_URL,
            headers={"X-Goog-Api-Key": self._api_key, "X-Goog-FieldMask": FIELD_MASK},
            json={"textQuery": f"{keyword} in {metro}", "maxResultCount": MAX_RESULTS_PER_METRO},
        )
        response.raise_for_status()
        return response.json().get("places", [])


def discover(
    searcher: PlacesSearcher,
    keyword: str,
    metros: list[str],
    *,
    max_queries: int,
    limit: int | None,
    summary: SourcingSummary,
    log=None,
) -> list[Candidate]:
    """Query Places per metro under the budget; per-metro failures never abort."""
    candidates: list[Candidate] = []
    for metro in metros[: limit if limit is not None else len(metros)]:
        if summary.queries_used >= max_queries:
            break  # budget exhausted: stop issuing queries, keep what we have
        summary.queries_used += 1
        summary.metros_covered += 1
        try:
            places = searcher.search(keyword, metro)
        except (httpx.HTTPError, ValueError) as exc:
            summary.failures.append((metro, f"places query failed: {exc}"))
            continue
        if log:
            log(f"{metro}: {len(places)} results")
        summary.discovered += len(places)
        for place in places:
            candidate = candidate_from_place(place, metro)
            if candidate is None:
                summary.failures.append((metro, "result with empty company name dropped"))
                continue
            candidates.append(candidate)
    return candidates


def candidate_from_place(place: dict, metro: str) -> Candidate | None:
    """Places JSON -> Candidate. Returns None for a result with no usable name."""
    company = ((place.get("displayName") or {}).get("text") or "").strip()
    if not company:
        return None
    website = (place.get("websiteUri") or "").strip() or None
    if website and is_blocked_host(website):
        # A Facebook page listed as the "website" is a signal we never fetch:
        # treat as no website (Constitution II).
        website = None
    return Candidate(
        place_id=place.get("id") or "",
        company=company,
        city=_city_state(place.get("formattedAddress") or "") or metro,
        website=website,
        domain=_domain(website) if website else None,
        metro=metro,
    )


def dedupe(candidates: list[Candidate], summary: SourcingSummary) -> list[Candidate]:
    """Collapse duplicates by place_id, then website domain. First seen wins
    (metro-list order, so bigger metros win ties — research.md R6)."""
    unique: list[Candidate] = []
    seen_ids: set[str] = set()
    seen_domains: set[str] = set()
    for candidate in candidates:
        if candidate.place_id and candidate.place_id in seen_ids:
            summary.duplicates_collapsed += 1
            continue
        if candidate.domain and candidate.domain in seen_domains:
            summary.duplicates_collapsed += 1
            continue
        if candidate.place_id:
            seen_ids.add(candidate.place_id)
        if candidate.domain:
            seen_domains.add(candidate.domain)
        unique.append(candidate)
    return unique


def _city_state(address: str) -> str | None:
    # "123 Main St, Boston, MA 02101, USA" -> "Boston, MA"
    parts = [p.strip() for p in address.split(",")]
    if len(parts) < 3:
        return None
    city = parts[-3]
    state = (parts[-2].split() or [""])[0]
    if not city or not state:
        return None
    return f"{city}, {state}"


def _domain(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


# Meta's standard pixel install has three observable components (research.md R3):
# the loader host, the fbq() global, and the noscript image beacon URL. Any real
# install contains at least one. Detection is STRING INSPECTION ONLY — a URL
# found in a page is never fetched (Constitution II).
PIXEL_MARKERS = ("connect.facebook.net", "fbq(", "facebook.com/tr")


def detect_pixel(html: str) -> str:
    """'pixel' iff Meta Pixel markup is present in the page source, else 'none'.

    Pure function over an already-fetched string; no network capability.
    ad_signal is a targeting filter only and never reaches drafts (Constitution V).
    """
    lowered = html.lower()
    return "pixel" if any(marker in lowered for marker in PIXEL_MARKERS) else "none"


# Live validation (research.md R3 amendment): modern pixel installs are mostly
# GTM-mediated — the pixel config lives in the container's public JS, not the
# page HTML. googletagmanager.com is a Google host; Principle II untouched.
GTM_ID_RE = re.compile(r"\bGTM-[A-Z0-9]{4,}\b")
GTM_URL = "https://www.googletagmanager.com/gtm.js?id={id}"
MAX_GTM_CONTAINERS = 2


def extract_gtm_ids(html: str) -> list[str]:
    """Container ids, only when the page actually references Tag Manager."""
    if "googletagmanager.com" not in html.lower():
        return []
    seen: list[str] = []
    for match in GTM_ID_RE.finditer(html):
        if match.group() not in seen:
            seen.append(match.group())
        if len(seen) == MAX_GTM_CONTAINERS:
            break
    return seen


def classify_ad_signal(candidate: Candidate, html: str, fetcher: Fetcher) -> str:
    """Page markers first; else inspect referenced GTM containers the same way."""
    if detect_pixel(html) == "pixel":
        return "pixel"
    for gtm_id in extract_gtm_ids(html):
        try:
            response = fetcher.fetch(GTM_URL.format(id=gtm_id))
        except (BlockedHostError, FetchError, httpx.HTTPError) as exc:
            candidate.failures.append(f"gtm container {gtm_id} fetch failed: {exc}")
            continue  # classify down, never up
        if response.status_code < 400 and detect_pixel(response.text) == "pixel":
            return "pixel"
    return "none"


def fetch_homepage(candidate: Candidate, fetcher: Fetcher, summary: SourcingSummary) -> str | None:
    """Fetch a candidate's homepage politely; None on any failure (recorded).

    Homepage is fetched without a robots check, subpages with one — 001's
    convention. Failures classify DOWN: the candidate stays ad_signal 'none'.
    """
    if not candidate.website:
        candidate.failures.append("no website listed")
        return None
    try:
        response = fetcher.fetch(candidate.website)
    except (BlockedHostError, FetchError, httpx.HTTPError) as exc:
        candidate.failures.append(f"homepage fetch failed: {exc}")
        summary.failures.append((candidate.company, f"homepage fetch failed: {exc}"))
        return None
    if response.status_code >= 400:
        candidate.failures.append(f"homepage returned {response.status_code}")
        summary.failures.append((candidate.company, f"homepage returned {response.status_code}"))
        return None
    return response.text


# Conservative: word-ish local part, dotted domain, 2+ letter TLD. Misses exotic
# addresses on purpose — a missed email costs a messenger-bucket route, a wrong
# one costs a bounced send.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ASSET_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")


def extract_public_email(html: str) -> str | None:
    """First publicly listed email: mailto links beat plaintext (research.md R4).

    Deterministic, never constructed: document order within each tier,
    lowercased, mailto query params stripped, asset-name false positives dropped.
    """
    tree = HTMLParser(html)
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        if href.lower().startswith("mailto:"):
            address = unquote(href[7:]).split("?", 1)[0].strip().lower()
            if _plausible_email(address):
                return address
    text = tree.body.text(separator=" ") if tree.body else html
    for match in EMAIL_RE.finditer(text):
        address = match.group().lower()
        if _plausible_email(address):
            return address
    return None


def _plausible_email(address: str) -> bool:
    return bool(EMAIL_RE.fullmatch(address)) and not address.endswith(ASSET_SUFFIXES)


def find_contact_link(html: str, base_url: str) -> str | None:
    """First same-host nav link whose path mentions 'contact' (one hop max, R4)."""
    tree = HTMLParser(html)
    base_host = (urlparse(base_url).hostname or "").lower()
    for node in tree.css("a[href]"):
        absolute = urljoin(base_url, node.attributes.get("href") or "")
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if (parsed.hostname or "").lower() != base_host:
            continue  # cross-host "contact" links are somebody else's site
        if "contact" in parsed.path.lower():
            return absolute
    return None


def capture_email(candidate: Candidate, html: str, fetcher: Fetcher) -> None:
    """Homepage first; else at most one robots-checked contact-page hop."""
    candidate.email = extract_public_email(html)
    if candidate.email is not None:
        return
    contact_url = find_contact_link(html, candidate.website)
    if contact_url is None:
        return
    try:
        response = fetcher.fetch(contact_url, check_robots=True)
    except (BlockedHostError, FetchError, httpx.HTTPError) as exc:
        candidate.failures.append(f"contact page fetch failed: {exc}")
        return
    if response.status_code >= 400:
        candidate.failures.append(f"contact page returned {response.status_code}")
        return
    candidate.email = extract_public_email(response.text)


# Columns 1-4 are exactly feature 001's input format; ad_signal rides along as
# an audit trail that 001's ingest ignores (contracts/csv-format.md).
CSV_HEADER = ["company", "email", "website", "city", "ad_signal"]


def write_candidates_csv(candidates: list[Candidate], out: Path) -> int:
    """Write the candidate CSV (header always; zero rows -> header-only file)."""
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)
        for c in candidates:
            writer.writerow([c.company, c.email or "", c.domain or "", c.city, c.ad_signal])
    return len(candidates)


def run_sourcing(
    settings,
    *,
    keyword: str,
    metros: list[str],
    out: Path,
    keep_all: bool = False,
    max_queries: int = 60,
    limit: int | None = None,
    verbose: bool = False,
    searcher: PlacesSearcher | None = None,
    fetcher: Fetcher | None = None,
) -> SourcingSummary:
    """Full sourcing pipeline: search -> parse -> dedupe -> classify -> write CSV."""
    import sys

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else None
    summary = SourcingSummary(metros_total=len(metros), query_budget=max_queries)
    searcher = searcher or PlacesSearcher(settings.places_key)
    fetcher = fetcher or Fetcher()

    candidates = discover(
        searcher, keyword, metros, max_queries=max_queries, limit=limit, summary=summary, log=log
    )
    unique = dedupe(candidates, summary)
    summary.kept_with_all = len(unique)

    for candidate in unique:
        html = fetch_homepage(candidate, fetcher, summary)
        if html is not None:
            candidate.ad_signal = classify_ad_signal(candidate, html, fetcher)
            capture_email(candidate, html, fetcher)
        if log:
            log(f"{candidate.company}: ad_signal={candidate.ad_signal} email={candidate.email or '-'}")

    rows = unique if keep_all else [c for c in unique if c.ad_signal == "pixel"]
    summary.pixel_positive = sum(1 for c in unique if c.ad_signal == "pixel")
    summary.emails_found = sum(1 for c in unique if c.email)
    summary.written = write_candidates_csv(rows, out)
    return summary
