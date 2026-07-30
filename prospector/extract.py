"""Deterministic extraction from fetched pages: name candidates (with Evidence),
city/service area, one personalization hook. Never invents anything — every
extracted datum carries its source and excerpt (research.md R3).
"""

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urljoin, urlparse

import trafilatura
from selectolax.parser import HTMLParser

from prospector.enrich import first_names
from prospector.models import Company, Evidence, EvidenceKind

PAGE_KEYWORDS = {
    "about": ("about", "our-story", "our_story", "who-we-are"),
    "team": ("team", "staff", "our-people", "meet-"),
    "contact": ("contact",),
}
MAX_EXTRA_PAGES = 3

TITLE_WORDS = r"(?:owner(?:[- ]operator)?|founder|president|proprietor|founded by|owned(?: and operated)? by)"
NAME = r"([A-Z][a-z]+(?: [A-Z]\.)? [A-Z][a-z]+)"
TITLE_THEN_NAME = re.compile(TITLE_WORDS + r"[^.\n]{0,60}?" + NAME)
NAME_THEN_TITLE = re.compile(NAME + r"[^.\n]{0,60}?\b" + TITLE_WORDS, re.IGNORECASE)
TITLE_THEN_NAME_I = re.compile(TITLE_WORDS, re.IGNORECASE)
COPYRIGHT_NAME = re.compile(r"(?:©|&copy;|copyright)\s*(?:\d{4})?\s*" + NAME, re.IGNORECASE)
HEADING_NAME = re.compile(r"^[A-Z][a-z]+(?: [A-Z]\.)? [A-Z][a-z]+$")

US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"
)
CITY_STATE = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?),\s*(?:" + US_STATES + r")\b")
# city stays case-sensitive (capitalized) so "area"/"metro" never lands in the capture
SERVING_AREA = re.compile(r"\b[Ss]erv(?:ing|e|es)\s+(?:[Tt]he\s+)?([A-Z][a-z]+(?: [A-Z][a-z]+)?)(?:\s+(?:metro\s+)?area)?")
YEARS = re.compile(r"\b(\d{1,2}\+?)\s*years\b", re.IGNORECASE)

# Words that disqualify a "name" candidate (page furniture + trade vocabulary)
NON_NAME_WORDS = {
    "about", "contact", "our", "team", "home", "services", "service", "why",
    "choose", "free", "call", "today", "quote", "estimate", "duct", "ducts",
    "vent", "vents", "air", "clean", "cleaning", "master", "pro", "pros",
    "heating", "cooling", "hvac", "quality", "trusted", "local", "family",
    "meet", "staff", "crew", "reviews", "faq", "areas", "pricing", "book",
    "any", "main", "quick", "whether", "owner", "operated", "office", "links",
    "time", "response", "satisfaction", "guaranteed", "your", "you", "the",
    # Pronouns and determiners. "Serving We Clean Ducts customers..." captured
    # "We" as a city, producing `city: We` and `hook: We service area` — junk
    # that reached the note and then made every sentence containing the word
    # "we" look like a claim about the prospect. Filter at the source.
    "we", "us", "our", "ours", "they", "them", "their", "it", "its", "this",
    "that", "these", "those", "all", "some", "most", "many", "each", "every",
    "other", "others", "same", "more", "less", "here", "there", "when", "where",
}


@dataclass
class PageContent:
    kind: str  # homepage | about | team | contact
    url: str
    html: str


@dataclass
class ExtractOutcome:
    name_evidence: list[Evidence] = field(default_factory=list)
    city: str | None = None
    hook: str | None = None
    hook_evidence: Evidence | None = None


def discover_extra_pages(homepage_html: str, base_url: str) -> list[tuple[str, str]]:
    """Find about/team/contact links in the homepage nav. Returns [(kind, url)], <=3."""
    found: dict[str, str] = {}
    base_host = urlparse(base_url).hostname
    for node in HTMLParser(homepage_html).css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            absolute = urljoin(base_url.rstrip("/") + "/", href)
            if urlparse(absolute).hostname != base_host:
                continue
            path = urlparse(absolute).path.lower()
        except ValueError:
            # A malformed href is the page author's mistake, not a reason to
            # lose the company. An unfilled template placeholder such as
            # "http://[BookingLink]" reads as an IPv6 literal to urlsplit
            # (3.11.4+), which then raises from ipaddress. Skip the link.
            continue
        for kind, keywords in PAGE_KEYWORDS.items():
            if kind not in found and any(k in path for k in keywords):
                found[kind] = absolute
    return list(found.items())[:MAX_EXTRA_PAGES]


def extract(company: Company, pages: list[PageContent]) -> ExtractOutcome:
    outcome = ExtractOutcome()
    for page in pages:
        text = _page_text(page.html)
        _collect_names(company, page, text, outcome)
        if outcome.city is None:
            outcome.city = _find_city(text)
        if outcome.hook is None:
            _find_hook(page, text, outcome)
    _dedupe_names(outcome)
    return outcome


def _page_text(html: str) -> str:
    extracted = trafilatura.extract(html)
    if extracted:
        return extracted
    tree = HTMLParser(html)
    node = tree.body or tree.root
    return node.text(separator="\n") if node else ""


def _page_evidence_kind(page_kind: str) -> EvidenceKind:
    if page_kind == "about":
        return EvidenceKind.ABOUT_PAGE
    if page_kind == "team":
        return EvidenceKind.TEAM_PAGE
    return EvidenceKind.OWNER_TEXT


def _collect_names(company: Company, page: PageContent, text: str, outcome: ExtractOutcome) -> None:
    kind = _page_evidence_kind(page.kind)

    for pattern in (TITLE_THEN_NAME, NAME_THEN_TITLE):
        for match in pattern.finditer(text):
            candidate = match.group(1)
            if _plausible_person_name(candidate, company):
                outcome.name_evidence.append(
                    Evidence(kind=kind, value=candidate, source=page.url, excerpt=_excerpt(text, match.start()))
                )

    if page.kind in ("about", "team"):
        for node in HTMLParser(page.html).css("h1,h2,h3,h4"):
            heading = node.text(strip=True)
            if HEADING_NAME.fullmatch(heading) and _plausible_person_name(heading, company):
                outcome.name_evidence.append(
                    Evidence(kind=kind, value=heading, source=page.url, excerpt=f"heading: {heading}")
                )

    footer = HTMLParser(page.html).css_first("footer")
    footer_text = footer.text(separator=" ") if footer else text[-300:]
    for match in COPYRIGHT_NAME.finditer(footer_text):
        candidate = match.group(1)
        if _plausible_person_name(candidate, company):
            outcome.name_evidence.append(
                Evidence(kind=EvidenceKind.FOOTER, value=candidate, source=page.url, excerpt=_excerpt(footer_text, match.start()))
            )


def _plausible_person_name(candidate: str, company: Company) -> bool:
    words = [w for w in candidate.replace(".", "").split() if w]
    if len(words) < 2:
        return False
    lowered = [w.lower() for w in words]
    if any(w in NON_NAME_WORDS for w in lowered):
        return False
    # Fabrication guard (Constitution IV): the first word must be a known US
    # first name. Real sites produce capitalized bigrams like "Quick Links"
    # near owner-keywords; a rare real name lost here beats a fake one greeted.
    if lowered[0] not in first_names():
        return False
    company_tokens = {t for t in re.split(r"[^a-z0-9]+", company.company.lower()) if t}
    if any(w in company_tokens for w in lowered):
        return False
    if company.city and company.city.lower() in lowered:
        return False
    return all(w.isalpha() or (len(w) == 1) for w in [x.rstrip(".") for x in words])


def _find_city(text: str) -> str | None:
    match = CITY_STATE.search(text)
    if match:
        return match.group(1)
    match = SERVING_AREA.search(text)
    if match:
        candidate = match.group(1)
        if candidate.lower() not in NON_NAME_WORDS:
            return candidate
    return None


def _find_hook(page: PageContent, text: str, outcome: ExtractOutcome) -> None:
    match = SERVING_AREA.search(text)
    if match:
        area = match.group(1)
        if area.lower() not in NON_NAME_WORDS:
            outcome.hook = f"{area} service area"
            outcome.hook_evidence = Evidence(
                kind=EvidenceKind.HOOK_SOURCE, value=outcome.hook, source=page.url, excerpt=_excerpt(text, match.start())
            )
            return
    match = YEARS.search(text)
    if match:
        outcome.hook = f"{match.group(1)} years in business"
        outcome.hook_evidence = Evidence(
            kind=EvidenceKind.HOOK_SOURCE, value=outcome.hook, source=page.url, excerpt=_excerpt(text, match.start())
        )


def _excerpt(text: str, position: int, width: int = 100) -> str:
    start = max(0, position - width // 2)
    return " ".join(text[start : position + width].split())[:200]


def _dedupe_names(outcome: ExtractOutcome) -> None:
    seen: set[str] = set()
    unique: list[Evidence] = []
    for evidence in outcome.name_evidence:
        key = evidence.value.lower()
        if key not in seen:
            seen.add(key)
            unique.append(evidence)
    outcome.name_evidence = unique


# Conservative: word-ish local part, dotted domain, 2+ letter TLD. Misses exotic
# addresses on purpose — a missed email costs a reported skip, a wrong one
# costs a bounced send.
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


# Page priority for address recovery (008 research.md R2): an address published
# on a contact page is the intended point of contact; the homepage is the last
# resort. Ranking pages rather than trusting fetch order makes the choice
# deterministic — identical research always adopts the same address (FR-006).
_RECOVERY_PAGE_PRIORITY = ("contact", "about", "team", "homepage")


def _registrable(host: str) -> str:
    """Last two labels of a host — a cheap same-organisation key.

    Deliberately naive (it treats "co.uk" as registrable); it only has to be
    consistent, because it is used to compare a page's host with an address's
    domain, not to parse the public suffix list."""
    parts = [p for p in (host or "").lower().split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else ".".join(parts)


def recover_email(pages: list[PageContent]) -> tuple[str | None, Evidence | None]:
    """Find a published address on pages ALREADY fetched for research.

    Returns (address, evidence) or (None, None). Reads only what it is given —
    it issues no request, so recovery costs no extra traffic and cannot reach a
    blocked host (FR-011). The adopted address is returned with an
    EMAIL_PUBLISHED evidence record naming the page it came from, so a wrong
    adoption is auditable in the note rather than invisible (FR-007).

    An address is adopted ONLY when its domain matches the host of the page it
    was found on. Website resolution can land on the wrong site (a DuckDuckGo
    fallback resolved an invented company to an unrelated domain and offered a
    stranger's personal Gmail), and unlike a wrong `website` field a wrong
    address is something we would actually mail. Defaulting down is the standing
    rule here: a missed address costs a reported skip, a wrong one costs
    contacting someone who never published themselves as a business."""
    ranked = sorted(
        pages,
        key=lambda p: (
            _RECOVERY_PAGE_PRIORITY.index(p.kind)
            if p.kind in _RECOVERY_PAGE_PRIORITY
            else len(_RECOVERY_PAGE_PRIORITY)
        ),
    )
    for page in ranked:
        address = extract_public_email(page.html)
        if address is None:
            continue
        page_domain = _registrable(urlparse(page.url).hostname or "")
        if page_domain and _registrable(address.rsplit("@", 1)[-1]) != page_domain:
            continue  # published on this page, but not this organisation's address
        return address, Evidence(
            kind=EvidenceKind.EMAIL_PUBLISHED,
            value=address,
            source=page.url,
            excerpt=f"published on the {page.kind}" if page.kind == "homepage" else f"published on the {page.kind} page",
        )
    return None, None
