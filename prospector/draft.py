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

# The offer — signature, promotional link, locked fallback copy, invariants and
# banned-claim vocabulary — is per-vertical CONTENT supplied by the selected
# profile (008, Constitution v7.0.0 Principle VI). Nothing about a specific
# offer is hardcoded here; this module only knows how to assemble and validate.

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
                        "channel": prospect.company.channel,
                        "hook": prospect.research.hook or "",
                        "city": prospect.research.city or prospect.company.city or "",
                        "angle": prospect.angle,
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


def assemble_email(prospect: Prospect, slots: dict, profile) -> Draft:
    """Deterministic assembly from the profile's locked copy + validated slots.

    The template is channel-neutral: it makes no claim about the prospect, so
    nothing in it requires evidence (Constitution v7.0.0, Principle IV). Only
    bracketed slots are filled — the prose is never paraphrased."""
    greeting = str(slots.get("greeting_name", "")).strip()
    subject_company = str(slots.get("subject_company", "")).strip() or prospect.company.company

    body = profile.fallback_template.format(greeting=greeting, signature=profile.signature)
    subject = profile.fallback_subject.format(subject_company=subject_company)
    errors = validate_email_draft(subject, body, prospect, slots, profile)
    return Draft(subject=subject, body=body, model="", validated=not errors, validation_errors=errors)


def validate_email_draft(subject: str, body: str, prospect: Prospect, slots: dict, profile) -> list[str]:
    errors: list[str] = []
    lowered = body.lower()

    if re.search(r"\[[^\]\n]{1,60}\]", body) or re.search(r"\[[^\]\n]{1,60}\]", subject):
        errors.append("unfilled [slot] remains")

    for line in profile.fallback_invariants:
        if line not in body:
            errors.append(f"template prose altered: missing {line[:40]!r}...")

    for banned in profile.banned_claims:
        if banned in lowered or banned in subject.lower():
            errors.append(f"ad-running claim detected: {banned!r}")

    # Link strategy (005 FR-202..205): exactly one promotional link — the
    # product page (demo lives there). This structurally blocks a homepage+
    # product combo, second/video/booking links, and any link a slot smuggles in.
    if body.count("http") != 1 or profile.product_url not in body:
        errors.append("body must carry exactly one promotional link (the product page)")
    if "linkedin.com" in lowered:
        errors.append("LinkedIn link may not appear in the pitch")

    if not body.rstrip().endswith(profile.signature):
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


def build_email_draft(prospect: Prospect, settings: Settings, profile) -> Draft:
    slots = request_slots(prospect, settings)
    draft = assemble_email(prospect, slots, profile)
    draft.model = settings.openrouter_model
    return draft
