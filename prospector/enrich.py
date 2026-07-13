"""Name enrichment: deterministic email-pattern inference against a bundled
first-names list, plus optional Hunter.io lookup (research.md R3).

Tiers mirror §7: unambiguous patterns (scottb@, john.smith@, johnsmith@) infer
a first name at high tier; ambiguous ones (derickson@ — surname-likely) only
produce a review candidate. Third-party enrichment is never trusted above
medium (Constitution IV: when unsure, score down).
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx

from prospector.config import Settings
from prospector.models import Evidence, EvidenceKind

HUNTER_URL = "https://api.hunter.io/v2/people/find"

# Inboxes that name a function, not a person
GENERIC_PREFIXES = {
    "info", "office", "contact", "admin", "hello", "sales", "support", "team",
    "service", "services", "bookings", "booking", "mail", "inquiries",
    "enquiries", "billing", "accounts", "schedule", "scheduling", "estimates",
    "quotes", "appointments", "dispatch", "frontdesk", "help", "careers",
    "jobs", "noreply", "no-reply", "webmaster", "postmaster", "system",
    "customerservice", "reception",
}

SURNAME_SUFFIXES = ("son", "sen", "man", "berg", "stein", "ford", "ston", "well", "worth")


@dataclass
class NameInference:
    first_name: str | None = None  # set -> high tier (§7 unambiguous pattern)
    candidate: str | None = None   # set -> medium tier (partial/ambiguous)
    evidence: Evidence | None = None


@lru_cache(maxsize=1)
def first_names() -> frozenset[str]:
    path = Path(__file__).parent / "data" / "first_names.txt"
    return frozenset(line.strip().lower() for line in path.read_text().splitlines() if line.strip())


def infer_from_email(email: str | None) -> NameInference:
    if not email or "@" not in email:
        return NameInference()
    local = email.split("@", 1)[0].lower()
    if local in GENERIC_PREFIXES:
        return NameInference()
    names = first_names()

    def evidence(value: str, note: str) -> Evidence:
        return Evidence(
            kind=EvidenceKind.EMAIL_PATTERN, value=value,
            source=f"email pattern: {email}", excerpt=note,
        )

    # first.last@ / first_last@ / first-last@
    parts = [p for p in re.split(r"[._-]", local) if p]
    if len(parts) == 2:
        first, second = parts
        if first in names and len(first) >= 3:
            name = first.capitalize()
            return NameInference(first_name=name, evidence=evidence(name, f"'{first}.{second}' -> first.last"))
        if len(first) == 1 and len(second) >= 4 and second not in names:
            # j.smith@ -> initial + surname: candidate only
            candidate = second.capitalize()
            return NameInference(candidate=candidate, evidence=evidence(candidate, f"'{local}' -> initial + surname?"))
        return NameInference()
    if len(parts) != 1 or not local.isalpha():
        return NameInference()

    # single token
    if local in names and len(local) >= 3:
        name = local.capitalize()
        return NameInference(first_name=name, evidence=evidence(name, f"'{local}' is a first name"))
    # scottb@ -> name + single initial (§7: unambiguous)
    if len(local) >= 5 and local[:-1] in names and len(local[:-1]) >= 4:
        name = local[:-1].capitalize()
        return NameInference(first_name=name, evidence=evidence(name, f"'{local}' -> first name + initial"))
    # johnsmith@ -> name + surname (§7: unambiguous when the name part is clear)
    for split_at in range(4, len(local) - 2):
        head, tail = local[:split_at], local[split_at:]
        if head in names and len(tail) >= 3:
            name = head.capitalize()
            return NameInference(first_name=name, evidence=evidence(name, f"'{local}' -> {head} + {tail}"))
    # derickson@ -> surname-likely, or opaque: candidate for human review only
    if 5 <= len(local) <= 15:
        surname_like = local.endswith(SURNAME_SUFFIXES) or (local[1:] in names)
        candidate = local.capitalize()
        note = "surname-likely local part" if surname_like else "opaque local part"
        return NameInference(candidate=candidate, evidence=evidence(candidate, f"'{local}': {note}"))
    return NameInference()


def hunter_lookup(email: str, settings: Settings) -> NameInference:
    """Optional Hunter.io people lookup. Result is candidate tier only —
    third-party enrichment never reaches §7 high. Skipped without a key."""
    if not settings.hunter_key or not email:
        return NameInference()
    try:
        response = httpx.get(
            HUNTER_URL, params={"email": email, "api_key": settings.hunter_key}, timeout=15.0
        )
        response.raise_for_status()
        data = response.json().get("data") or {}
    except (httpx.HTTPError, ValueError):
        return NameInference()
    name = (data.get("name") or {}).get("givenName") or data.get("first_name")
    if not name:
        return NameInference()
    candidate = str(name).strip().capitalize()
    return NameInference(
        candidate=candidate,
        evidence=Evidence(
            kind=EvidenceKind.HUNTER, value=candidate,
            source=f"hunter.io: {email}", excerpt="third-party enrichment (medium tier max)",
        ),
    )
