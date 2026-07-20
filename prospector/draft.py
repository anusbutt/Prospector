"""Drafting: locked §8 templates as code constants, one OpenRouter call per
company returning slot JSON only, deterministic assembly, then validation.

The LLM never sees or rewrites template prose (FR-015). It receives already-
gated slot inputs and returns {greeting_name, subject_company}.
Honesty is enforced by the validator, not hoped for (Constitution IV/V).
"""

import json
import re

import httpx

from prospector.config import Settings
from prospector.models import Draft, Prospect

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

GENERIC_INBOX_PREFIXES = {
    "info", "office", "contact", "admin", "hello", "sales", "support",
    "team", "service", "bookings", "mail", "inquiries", "enquiries",
}

# Founder-led, compact sign-off (PRODUCT.md §8, rev. 2 2026-07-17). The
# LinkedIn company link is deliberately omitted: it may only appear "when
# appropriate" and must never be forced into every email — a mechanical
# template cannot judge that, so the locked prose leaves it out (005 FR-204).
SIGNATURE = "Anas\nFounder, Omniveer"

# Link strategy (PRODUCT.md §8, 005 FR-202..205): exactly ONE promotional link
# per body — the product page (it hosts the explanation and the demo, so no
# separate video link and no attachment). Homepage is for Omniveer-broad
# messages only and never combined with the product link. No booking link
# unless one is explicitly configured later.
PRODUCT_URL = "https://www.omniveer.com/duct-lead-qualifier"
COMPANY_URL = "https://www.omniveer.com"
LINKEDIN_COMPANY_URL = "https://www.linkedin.com/company/omniveer/"

SUBJECT_TEMPLATE = "Free 10-day pilot for {subject_company}"

# Offer (PRODUCT.md §8, rev. 2 2026-07-17, operator-supplied copy): the
# Omniveer Duct Lead Qualifier, free 10-day pilot for 5 duct-cleaning
# companies. The copy is CHANNEL-NEUTRAL — it makes no claim about the
# prospect's channels (or Facebook at all), so both fb_signal levels share
# this one body and the §7.5 honesty gate is trivially satisfied (Principle V,
# v4.0.1: defaulting down is always allowed; the signal is still recorded).
# Ends with the single promotional link (the product page carries the demo)
# and a low-pressure close — no urgency, no guarantees. "Book a demo through
# the page" refers to the page already linked: no second URL.
EMAIL_OFFER_PARAGRAPH = (
    "I'm giving 5 duct-cleaning companies a free 10-day pilot of the "
    "Omniveer Duct Lead Qualifier."
)

EMAIL_TEMPLATE = (
    """Hi {greeting},

"""
    + EMAIL_OFFER_PARAGRAPH
    + """

It responds to new leads, qualifies them, books appointments when they're ready, sends the full details to your email, and keeps every lead organized in a dashboard.

You can see the short demo here:
"""
    + PRODUCT_URL
    + """

Reply to this email if you'd like one of the five pilot spots, or book a demo through the page.

{signature}"""
)

MESSENGER_DM_TEMPLATE = (
    "Hey! I'm giving 5 duct cleaning companies a free 10-day pilot of the "
    "Omniveer Duct Lead Qualifier. It answers your page messages in seconds, "
    "day or night. It checks customers are real{city_clause}, quotes your real "
    "prices, and books them into open slots on your calendar. You just get the "
    "finished lead. I set it all up for you. Want one of the 5 spots? "
    "(See it working: " + PRODUCT_URL + ")"
)

# Invariant template prose that must survive assembly byte-for-byte (FR-015)
EMAIL_INVARIANTS = (
    EMAIL_OFFER_PARAGRAPH,
    "It responds to new leads, qualifies them, books appointments when they're ready, sends the full details to your email, and keeps every lead organized in a dashboard.",
    "You can see the short demo here:\n" + PRODUCT_URL,
    "Reply to this email if you'd like one of the five pilot spots, or book a demo through the page.",
)

MESSENGER_INVARIANTS = (
    "Hey! I'm giving 5 duct cleaning companies a free 10-day pilot of the Omniveer Duct Lead Qualifier.",
    "quotes your real prices, and books them into open slots on your calendar.",
    "Want one of the 5 spots? (See it working: " + PRODUCT_URL + ")",
)

# Ad-running is never observable and never claimed (Constitution V)
AD_CLAIM_SUBSTRINGS = ("your ads", "ad campaign", "running ads", "advertis", "your facebook ads", "ad spend")

SYSTEM_PROMPT = """You fill two slots for a locked outreach email template. Reply with a JSON object only:
{"greeting_name": ..., "subject_company": ...}

Rules (violations are rejected by a validator):
- greeting_name: repeat the provided name_or_team value EXACTLY. Never substitute another name.
- subject_company: a natural short form of the provided company name for a subject line. Only drop words (like LLC or Cleaning); never add or change words.
No other keys. No prose."""


class DraftError(Exception):
    """OpenRouter call failed; company is flagged, batch continues."""


# Curly apostrophes are common in scraped company names ("Drew’s"), and a model
# almost always answers with the straight form ("Drew's"). Splitting on a
# straight-quote-only class made those two tokenize differently — "drew"+"s"
# versus "drew's" — so a correct subject was rejected as invented. Normalize the
# quote and drop it from tokens so both spellings agree.
_CURLY_QUOTES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'"})


def name_tokens(text: str) -> set[str]:
    """Apostrophe-insensitive word tokens, for company/subject comparison."""
    return {t for t in re.split(r"[^a-z0-9]+", text.translate(_CURLY_QUOTES).lower()) if t}


def _strip_code_fences(content: str) -> str:
    """Some providers ignore response_format and fence the JSON in ```blocks```."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def is_generic_inbox(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    return email.split("@", 1)[0].lower() in GENERIC_INBOX_PREFIXES


def expected_greeting(prospect: Prospect) -> str:
    if prospect.name_used != "team":
        return prospect.name_used
    return f"{prospect.company.company} team"


def request_slots(prospect: Prospect, settings: Settings) -> dict:
    """Single-shot LLM call. Returns slot dict. Raises DraftError on failure."""
    payload = {
        "model": settings.openrouter_model,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "company": prospect.company.company,
                        "name_or_team": expected_greeting(prospect),
                        "channel": prospect.company.channel.value,
                        "hook": prospect.research.hook or "",
                        "city": prospect.research.city or prospect.company.city or "",
                        "angle": prospect.angle,
                        "fb_signal": prospect.fb_signal.value,
                        "variant": prospect.variant.value,
                        "is_generic_inbox": is_generic_inbox(prospect.company.email),
                    }
                ),
            },
        ],
    }
    try:
        response = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {settings.openrouter_key}", "X-Title": "Prospector"},
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        slots = json.loads(_strip_code_fences(content))
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise DraftError(f"OpenRouter call failed: {exc}") from exc
    if not isinstance(slots, dict):
        raise DraftError("OpenRouter returned non-object slot JSON")
    return slots


def assemble_email(prospect: Prospect, slots: dict) -> Draft:
    """Deterministic assembly from template constants + validated slot fills.

    Rev. 2 (2026-07-17): one channel-neutral template for every fb_signal
    level — the copy makes no claims about the prospect's channels, so the
    §7.5 gate is trivially satisfied (the signal is still recorded)."""
    greeting = str(slots.get("greeting_name", "")).strip()
    subject_company = str(slots.get("subject_company", "")).strip() or prospect.company.company

    body = EMAIL_TEMPLATE.format(greeting=greeting, signature=SIGNATURE)
    subject = SUBJECT_TEMPLATE.format(subject_company=subject_company)
    errors = validate_email_draft(subject, body, prospect, slots)
    return Draft(subject=subject, body=body, model="", validated=not errors, validation_errors=errors)


def build_messenger_draft(prospect: Prospect) -> Draft:
    """Messenger DM (§8): fully deterministic — the only slot is the city,
    which comes from recorded research. No LLM call needed."""
    city = prospect.research.city or prospect.company.city
    city_clause = f", around {city}" if city else ""
    body = MESSENGER_DM_TEMPLATE.format(city_clause=city_clause)
    errors: list[str] = []
    for line in MESSENGER_INVARIANTS:
        if line not in body:
            errors.append(f"template prose altered: missing {line[:40]!r}...")
    for banned in AD_CLAIM_SUBSTRINGS:
        if banned in body.lower():
            errors.append(f"ad-running claim detected: {banned!r}")
    # Link strategy (005): one promotional link — the product page — and never
    # LinkedIn in the pitch. Same rules as the email validator.
    if body.count("http") != 1 or PRODUCT_URL not in body:
        errors.append("body must carry exactly one promotional link (the product page)")
    if "linkedin.com" in body.lower():
        errors.append("LinkedIn link may not appear in the pitch")
    return Draft(subject=None, body=body, model="deterministic", validated=not errors, validation_errors=errors)


def validate_email_draft(subject: str, body: str, prospect: Prospect, slots: dict) -> list[str]:
    errors: list[str] = []
    lowered = body.lower()

    if re.search(r"\[[^\]\n]{1,60}\]", body) or re.search(r"\[[^\]\n]{1,60}\]", subject):
        errors.append("unfilled [slot] remains")

    for line in EMAIL_INVARIANTS:
        if line not in body:
            errors.append(f"template prose altered: missing {line[:40]!r}...")

    for banned in AD_CLAIM_SUBSTRINGS:
        if banned in lowered or banned in subject.lower():
            errors.append(f"ad-running claim detected: {banned!r}")

    # Link strategy (005 FR-202..205): exactly one promotional link — the
    # product page (demo lives there). This structurally blocks a homepage+
    # product combo, second/video/booking links, and any link a slot smuggles in.
    if body.count("http") != 1 or PRODUCT_URL not in body:
        errors.append("body must carry exactly one promotional link (the product page)")
    if "linkedin.com" in lowered:
        errors.append("LinkedIn link may not appear in the pitch")

    if not body.rstrip().endswith(SIGNATURE):
        errors.append("signature altered or missing")

    # Constitution Principle V: the rev.-2 template is channel-neutral — no
    # claim about the prospect's channels may appear at ANY signal level, so
    # their-activity phrasing sneaking in via a slot is always rejected.
    if "messages your page" in lowered:
        errors.append("their-page-activity phrasing in the channel-neutral template")

    expected = expected_greeting(prospect)
    if not body.startswith(f"Hi {expected},"):
        errors.append(f"greeting must be {expected!r}")

    # Unsourced-name guard (Constitution IV): a real first name in the greeting
    # must trace to recorded evidence or the input owner_name column.
    if prospect.name_used != "team":
        sourced = {
            evidence.value.split()[0].lower()
            for evidence in prospect.research.name_evidence
            if evidence.value
        }
        if prospect.company.owner_name:
            sourced.add(prospect.company.owner_name.split()[0].lower())
        if prospect.name_used.lower() not in sourced:
            errors.append("greeting name does not trace to a recorded source")

    subject_company = str(slots.get("subject_company", "")).strip() or prospect.company.company
    company_tokens = name_tokens(prospect.company.company)
    subject_tokens = [t for t in name_tokens(subject_company)]
    if not subject_tokens or any(t not in company_tokens for t in subject_tokens):
        errors.append("subject_company contains words not in the company name")

    return errors


def build_email_draft(prospect: Prospect, settings: Settings) -> Draft:
    slots = request_slots(prospect, settings)
    draft = assemble_email(prospect, slots)
    draft.model = settings.openrouter_model
    return draft
