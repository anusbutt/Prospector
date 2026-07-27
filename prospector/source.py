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

from prospector import vault
from prospector.config import ConfigError
from prospector.extract import EMAIL_RE, _plausible_email, extract_public_email
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
    already_known: int = 0  # dropped at the gate: already in the vault
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


def dedupe(
    candidates: list[Candidate], summary: SourcingSummary, metros: list[str] | None = None
) -> list[Candidate]:
    """Collapse duplicates by place_id, then website domain. First seen wins
    (metro-list order, so bigger metros win ties — research.md R6).

    "First seen" is made explicit rather than inherited from the order Places
    happened to answer in: candidates are ranked by metro position, then by
    place_id, before the pass. Metro precedence is unchanged; what changes is
    that two runs over the same results now collapse to the same winner even if
    the API returned them in a different order."""
    order = {metro: i for i, metro in enumerate(metros or [])}
    ranked = sorted(
        candidates,
        key=lambda c: (order.get(c.metro, len(order)), c.place_id, c.company),
    )
    unique: list[Candidate] = []
    seen_ids: set[str] = set()
    seen_domains: set[str] = set()
    for candidate in ranked:
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


def known_companies(vault_dir: str | Path | None) -> tuple[set[str], set[str]]:
    """Slugs and website domains of every company already in the vault.

    Sourcing is for finding companies you do NOT have yet. Anything already in
    the vault has been researched, drafted, and possibly emailed, so re-finding
    it costs Places quota and a homepage fetch to produce a row you would throw
    away. A missing vault is not an error — it just means nothing is known yet.

    Matching is by company slug, with the website domain as a second key. Slug
    is the only one of the two available before the homepage fetch, which is why
    the gate can run early; domain catches a business whose Places display name
    has drifted since it was first sourced."""
    slugs: set[str] = set()
    domains: set[str] = set()
    if vault_dir is None:
        return slugs, domains
    vault_dir = Path(vault_dir)
    if not vault_dir.is_dir():
        return slugs, domains
    for path in sorted(vault_dir.glob("*.md")):
        if path.name.startswith("_"):  # _Dashboard.md and friends
            continue
        slugs.add(path.stem)
        try:
            frontmatter, _ = vault.parse_note(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        website = (frontmatter.get("website") or "").strip().lower()
        if not website:
            continue
        # Notes store a display form ("acme.com/about"), not a URL.
        domain = _domain(website if "//" in website else f"https://{website}")
        if domain:
            domains.add(domain)
    return slugs, domains


def drop_known(
    candidates: list[Candidate],
    known_slugs: set[str],
    known_domains: set[str],
    summary: SourcingSummary,
) -> list[Candidate]:
    """Keep only companies the vault has never seen (the sourcing gate).

    Runs before any homepage is fetched, so a repeat sweep costs Places queries
    and nothing else. Dropped companies are counted, never silently discarded."""
    fresh: list[Candidate] = []
    for candidate in candidates:
        if vault.slugify(candidate.company) in known_slugs:
            summary.already_known += 1
            continue
        if candidate.domain and candidate.domain in known_domains:
            summary.already_known += 1
            continue
        fresh.append(candidate)
    return fresh


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


def _row_sort_key(candidate: Candidate) -> tuple[str, str, str]:
    """Canonical row order: by company, then domain, then place_id.

    Places can return the same businesses in a different order on different
    days. Sorting on the candidate's own values means the output file depends on
    WHAT was found, not on the order it arrived in — so an unchanged result set
    produces an unchanged file. Company first because the CSV is read by a human
    before it is fed to `run`."""
    return (candidate.company.casefold(), candidate.domain or "", candidate.place_id)


def write_candidates_csv(candidates: list[Candidate], out: Path) -> int:
    """Write the candidate CSV (header always; zero rows -> header-only file)."""
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)
        for c in sorted(candidates, key=_row_sort_key):
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
    vault_dir: str | Path | None = None,
    include_known: bool = False,
) -> SourcingSummary:
    """Full sourcing pipeline: search -> dedupe -> drop known -> classify -> CSV."""
    import sys

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else None
    summary = SourcingSummary(metros_total=len(metros), query_budget=max_queries)
    searcher = searcher or PlacesSearcher(settings.places_key)
    fetcher = fetcher or Fetcher()

    candidates = discover(
        searcher, keyword, metros, max_queries=max_queries, limit=limit, summary=summary, log=log
    )
    unique = dedupe(candidates, summary, metros)

    # The gate sits BEFORE the fetch loop: a company already in the vault costs
    # a Places result and nothing more. Fetching its homepage again to classify
    # a row that would be discarded is the expensive mistake this avoids.
    if not include_known:
        known_slugs, known_domains = known_companies(vault_dir)
        before = len(unique)
        unique = drop_known(unique, known_slugs, known_domains, summary)
        if log and before != len(unique):
            log(f"gate: dropped {before - len(unique)} already in the vault")

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
