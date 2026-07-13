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
from prospector.models import Draft, FbSignal, Prospect, Variant

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

# fb_signal weak -> conditional clause; none -> empty (FR-014)
WEAK_FB_CLAUSE = ", or Facebook if you use it"

EMAIL_AGNOSTIC_TEMPLATE = """Hi {greeting},

{opener}

I'll set up an AI assistant that answers your new leads for free, and you keep every job it books. No contract, no cost.

Here's what it does. However a lead reaches you — a form, a message{channel_clause} — it replies in seconds, day or night, figures out whether they're a real customer {hook_phrase}, and hands the good ones straight to you. The junk never touches your phone.

I'm doing this with a small group of duct cleaning companies to build real case studies. That's the whole catch: it works for you, and if it does, I get to point to the results. If it doesn't, you've lost nothing.

Open to it? Reply here and I'll have you running this week.

{signature}"""

EMAIL_FB_TEMPLATE = """Hi {greeting},

{opener}

I'll set up an AI assistant on your Facebook page for free, and you keep every job it books. No contract, no cost.

Here's what it does. The moment a lead messages or fills out a form, it replies day or night, figures out whether they're a real customer {hook_phrase}, and hands the good ones straight to you. The junk never touches your phone.

I'm doing this with a small group of duct cleaning companies to build real case studies. That's the whole catch: it works for you, and if it does, I get to point to the results. If it doesn't, you've lost nothing.

Open to it? Reply here and I'll have you running this week.

{signature}"""

MESSENGER_DM_TEMPLATE = (
    "Hey! I build AI assistants for duct cleaning companies. This one answers every "
    "new lead on your page in seconds, filters out the time-wasters, and flags the "
    "ready-to-book ones for you{city_clause}. I'm setting it up free for a few "
    "companies right now to build case studies. Want me to run yours? "
    "(My work: x.com/iamanusbutt)"
)

# Invariant template prose that must survive assembly byte-for-byte (FR-015)
AGNOSTIC_INVARIANTS = (
    "I'll set up an AI assistant that answers your new leads for free, and you keep every job it books. No contract, no cost.",
    "I'm doing this with a small group of duct cleaning companies to build real case studies.",
    "Open to it? Reply here and I'll have you running this week.",
)

FB_INVARIANTS = (
    "I'll set up an AI assistant on your Facebook page for free, and you keep every job it books. No contract, no cost.",
    "The moment a lead messages or fills out a form, it replies day or night,",
    "I'm doing this with a small group of duct cleaning companies to build real case studies.",
    "Open to it? Reply here and I'll have you running this week.",
)

MESSENGER_INVARIANTS = (
    "Hey! I build AI assistants for duct cleaning companies.",
    "I'm setting it up free for a few companies right now to build case studies.",
    "Want me to run yours? (My work: x.com/iamanusbutt)",
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
    if prospect.variant is Variant.EMAIL_FB:
        body = EMAIL_FB_TEMPLATE.format(
            greeting=greeting, opener=opener, hook_phrase=hook_phrase, signature=SIGNATURE
        )
    else:
        channel_clause = WEAK_FB_CLAUSE if prospect.fb_signal is FbSignal.WEAK else ""
        body = EMAIL_AGNOSTIC_TEMPLATE.format(
            greeting=greeting,
            opener=opener,
            channel_clause=channel_clause,
            hook_phrase=hook_phrase,
            signature=SIGNATURE,
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

    if prospect.fb_signal is FbSignal.NONE and "facebook" in lowered:
        errors.append("facebook mentioned without a supporting signal")

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
