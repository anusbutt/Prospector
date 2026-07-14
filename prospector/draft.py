"""Drafting: locked §8 templates as code constants, one OpenRouter call per
company returning slot JSON only, deterministic assembly, then validation.

The LLM never sees or rewrites template prose (FR-015). It receives already-
gated slot inputs and returns {greeting_name, hook_phrase, subject_company}.
Honesty is enforced by the validator, not hoped for (Constitution IV/V).
"""

import json
import re

import httpx

from prospector.config import Settings
from prospector.models import Draft, Prospect, Variant

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

GENERIC_INBOX_PREFIXES = {
    "info", "office", "contact", "admin", "hello", "sales", "support",
    "team", "service", "bookings", "mail", "inquiries", "enquiries",
}

SIGNATURE = "Anas\nx.com/iamanusbutt\nlinkedin.com/in/anus-yousuf"

OPENER_GENERIC = (
    "Straight to it, and if this isn't your department, "
    "please forward it to whoever handles your bookings."
)
OPENER_DIRECT = "Straight to it."

SUBJECT_TEMPLATE = "free setup for {subject_company}, you keep the bookings"

# Offer (PRODUCT.md §8, updated 2026-07-14): Nestaro, free 10-day run for
# 5 duct-cleaning companies, set up entirely by Anas. The agnostic variant
# differs from the FB variant only in how paragraph two opens: product-fact
# ("Nestaro lives in your Facebook page inbox") vs their-activity ("When
# someone messages your page") — constitution v2.0.0 Principle V.
EMAIL_OFFER_PARAGRAPH = (
    "I'm giving 5 duct cleaning companies a free 10-day run of Nestaro, "
    "an AI assistant that answers your Facebook page messages for you. "
    "I set everything up; it costs you nothing for the ten days."
)

EMAIL_BODY_TAIL = """quotes your real prices (it never invents a number), and books them into a genuinely open slot on your calendar. You get the finished lead by email: name, phone, address, service, and time. Anything it shouldn't answer gets flagged to you instead of guessed.

Five spots, first come. Reply here and I'll have yours running this week.

{signature}"""

EMAIL_FB_TEMPLATE = (
    """Hi {greeting},

{opener}

"""
    + EMAIL_OFFER_PARAGRAPH
    + """

Here's what it does. When someone messages your page, it replies in seconds, day or night, in a normal human voice. It checks they're {hook_phrase}, """
    + EMAIL_BODY_TAIL
)

EMAIL_AGNOSTIC_TEMPLATE = (
    """Hi {greeting},

{opener}

"""
    + EMAIL_OFFER_PARAGRAPH
    + """

Here's what it does. Nestaro lives in your Facebook page inbox: when a customer messages, it replies in seconds, day or night, in a normal human voice. It checks they're {hook_phrase}, """
    + EMAIL_BODY_TAIL
)

MESSENGER_DM_TEMPLATE = (
    "Hey! I'm giving 5 duct cleaning companies a free 10-day run of Nestaro, "
    "an AI assistant that answers your page messages in seconds, day or night. "
    "It checks customers are real{city_clause}, quotes your real prices, and "
    "books them into open slots on your calendar. You just get the finished "
    "lead. I set it all up for you. Want one of the 5 spots? "
    "(My work: x.com/iamanusbutt)"
)

# Invariant template prose that must survive assembly byte-for-byte (FR-015)
AGNOSTIC_INVARIANTS = (
    EMAIL_OFFER_PARAGRAPH,
    "Here's what it does. Nestaro lives in your Facebook page inbox: when a customer messages, it replies in seconds, day or night, in a normal human voice.",
    "quotes your real prices (it never invents a number), and books them into a genuinely open slot on your calendar.",
    "Five spots, first come. Reply here and I'll have yours running this week.",
)

FB_INVARIANTS = (
    EMAIL_OFFER_PARAGRAPH,
    "Here's what it does. When someone messages your page, it replies in seconds, day or night, in a normal human voice.",
    "quotes your real prices (it never invents a number), and books them into a genuinely open slot on your calendar.",
    "Five spots, first come. Reply here and I'll have yours running this week.",
)

MESSENGER_INVARIANTS = (
    "Hey! I'm giving 5 duct cleaning companies a free 10-day run of Nestaro,",
    "quotes your real prices, and books them into open slots on your calendar.",
    "Want one of the 5 spots? (My work: x.com/iamanusbutt)",
)

# Ad-running is never observable and never claimed (Constitution V)
AD_CLAIM_SUBSTRINGS = ("your ads", "ad campaign", "running ads", "advertis", "your facebook ads", "ad spend")

DEFAULT_HOOK_PHRASE = "in your service area"

SYSTEM_PROMPT = """You fill three slots for a locked outreach email template. Reply with a JSON object only:
{"greeting_name": ..., "hook_phrase": ..., "subject_company": ...}

Rules (violations are rejected by a validator):
- greeting_name: repeat the provided name_or_team value EXACTLY. Never substitute another name.
- hook_phrase: a short locator phrase for mid-sentence use, e.g. "in your service area" or "around Boston". Start with "in" or "around". Max 8 words. Base it ONLY on the provided hook/city values; if they are empty, use "in your service area". Never invent facts.
- subject_company: a natural short form of the provided company name for a subject line. Only drop words (like LLC or Cleaning); never add or change words.
No other keys. No prose."""


class DraftError(Exception):
    """OpenRouter call failed; company is flagged, batch continues."""


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
    """Deterministic assembly from template constants + validated slot fills."""
    greeting = str(slots.get("greeting_name", "")).strip()
    hook_phrase = str(slots.get("hook_phrase", "")).strip() or DEFAULT_HOOK_PHRASE
    subject_company = str(slots.get("subject_company", "")).strip() or prospect.company.company

    opener = OPENER_GENERIC if is_generic_inbox(prospect.company.email) else OPENER_DIRECT
    template = EMAIL_FB_TEMPLATE if prospect.variant is Variant.EMAIL_FB else EMAIL_AGNOSTIC_TEMPLATE
    body = template.format(
        greeting=greeting, opener=opener, hook_phrase=hook_phrase, signature=SIGNATURE
    )
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
    return Draft(subject=None, body=body, model="deterministic", validated=not errors, validation_errors=errors)


def validate_email_draft(subject: str, body: str, prospect: Prospect, slots: dict) -> list[str]:
    errors: list[str] = []
    lowered = body.lower()

    if re.search(r"\[[^\]\n]{1,60}\]", body) or re.search(r"\[[^\]\n]{1,60}\]", subject):
        errors.append("unfilled [slot] remains")

    invariants = FB_INVARIANTS if prospect.variant is Variant.EMAIL_FB else AGNOSTIC_INVARIANTS
    for line in invariants:
        if line not in body:
            errors.append(f"template prose altered: missing {line[:40]!r}...")

    for banned in AD_CLAIM_SUBSTRINGS:
        if banned in lowered or banned in subject.lower():
            errors.append(f"ad-running claim detected: {banned!r}")

    if not body.rstrip().endswith(SIGNATURE):
        errors.append("signature altered or missing")

    # Constitution v2.0.0 Principle V: product-fact Facebook mentions are fine
    # in every variant; claims about the PROSPECT's page activity belong only
    # to the strong-signal variant — enforced structurally by template choice
    # (the agnostic variant contains no their-activity phrasing to alter).
    if prospect.variant is not Variant.EMAIL_FB and "messages your page" in lowered:
        errors.append("their-page-activity phrasing in a non-strong variant")

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

    hook_phrase = str(slots.get("hook_phrase", "")).strip() or DEFAULT_HOOK_PHRASE
    if len(hook_phrase) > 60 or "\n" in hook_phrase or "http" in hook_phrase or "—" in hook_phrase:
        errors.append("hook_phrase malformed")
    elif not hook_phrase.lower().startswith(("in ", "around ")):
        errors.append("hook_phrase must start with 'in' or 'around'")

    subject_company = str(slots.get("subject_company", "")).strip() or prospect.company.company
    company_tokens = {t for t in re.split(r"[^a-z0-9']+", prospect.company.company.lower()) if t}
    subject_tokens = [t for t in re.split(r"[^a-z0-9']+", subject_company.lower()) if t]
    if not subject_tokens or any(t not in company_tokens for t in subject_tokens):
        errors.append("subject_company contains words not in the company name")

    return errors


def build_email_draft(prospect: Prospect, settings: Settings) -> Draft:
    slots = request_slots(prospect, settings)
    draft = assemble_email(prospect, slots)
    draft.model = settings.openrouter_model
    return draft
