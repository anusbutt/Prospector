"""Agent drafting with automatic template fallback (006).

The model writes prose but never facts: each block declares the evidence it
rests on, and every citation is resolved deterministically against records
actually captured for THIS company before the copy reaches a note
(Constitution v5.0.0, Principle IV).

Two structural guarantees, both cheaper than validating after the fact:

  * The model never writes the greeting or the signature — code owns both — so
    a fabricated name has no channel to enter through (research R3).
  * Every block MUST carry a citation, so no code has to judge which sentences
    are claims. There is no uncited category to classify (research R2).

`draft_email()` never raises. Any failure returns the locked-template draft,
which is why `draft.py` is left byte-unchanged as the honesty floor (FR-316).
"""

import json
import re

import httpx

from prospector.config import Settings
from prospector.draft import (
    AD_CLAIM_SUBSTRINGS,
    OPENROUTER_URL,
    PRODUCT_URL,
    SIGNATURE,
    DraftError,
    _strip_code_fences,
    build_email_draft,
    expected_greeting,
)
from prospector.models import (
    OFFER_CITE,
    AgentResponse,
    Draft,
    DraftBlock,
    EvidenceRef,
    Prospect,
    ResearchResult,
)
from prospector.resolve import GENERIC_TOKENS

# Variation across the batch is now a GOAL (SC-301): identical bodies across a
# ramping domain are themselves a spam signal. The honesty floor no longer
# depends on determinism, so sampling is free to serve copy quality.
AGENT_TEMPERATURE = 0.7
REQUEST_TIMEOUT = 60.0

MIN_BLOCKS = 3
MAX_BLOCKS = 6

# Trade vocabulary that is not distinctive to any one prospect. "5 duct-cleaning
# companies" appears in the offer itself, so these must never trip the
# offer-only leakage check (V3).
TRADE_TOKENS = {
    "duct", "ducts", "vent", "vents", "dryer", "air", "clean", "cleaning",
    "cleaners", "heating", "cooling", "hvac", "chimney", "restoration",
    "carpet", "quality", "master", "masters", "solutions",
}
NON_DISTINCTIVE = GENERIC_TOKENS | TRADE_TOKENS


class AgentDraftError(Exception):
    """Agent path could not produce a usable draft. Always caught internally."""


# --- Evidence catalogue -----------------------------------------------------


def build_evidence_refs(research: ResearchResult) -> list[EvidenceRef]:
    """Assign stable `<kind>_<ordinal>` ids over this company's evidence.

    Order follows the research result, so identical research yields identical
    ids and therefore byte-identical notes on re-run (FR-329). Readable ids
    matter: the operator reviewing a citation should be able to tell where it
    points without a lookup table."""
    records = list(research.name_evidence) + list(research.fb_evidence)
    if research.hook_evidence is not None:
        records.append(research.hook_evidence)

    refs: list[EvidenceRef] = []
    counters: dict[str, int] = {}
    for evidence in records:
        kind = evidence.kind.value
        counters[kind] = counters.get(kind, 0) + 1
        refs.append(
            EvidenceRef(
                id=f"{kind}_{counters[kind]}",
                kind=kind,
                value=evidence.value,
                source=evidence.source,
                excerpt=evidence.excerpt,
            )
        )
    return refs


def build_payload(prospect: Prospect, refs: list[EvidenceRef]) -> dict:
    """The per-company user message.

    Carries ONLY extracted evidence fields — never raw fetched HTML (FR-302).
    The greeting is already resolved here: the model is told what it will be,
    not asked to choose it."""
    return {
        "company": prospect.company.company,
        "greeting": f"Hi {expected_greeting(prospect)},",
        "city": prospect.research.city or prospect.company.city or "",
        "evidence": [
            {
                "id": ref.id,
                "kind": ref.kind,
                "value": ref.value,
                "source": ref.source,
                "excerpt": ref.excerpt,
            }
            for ref in refs
        ],
        "offer_id": OFFER_CITE,
    }


# --- Request / parse --------------------------------------------------------


def request_draft(prospect: Prospect, settings: Settings, instructions, refs: list[EvidenceRef]) -> AgentResponse:
    """One request. No retry, no repair, no second call (FR-307)."""
    payload = {
        "model": settings.openrouter_model,
        "temperature": AGENT_TEMPERATURE,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": instructions.text},
            {"role": "user", "content": json.dumps(build_payload(prospect, refs))},
        ],
    }
    try:
        response = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {settings.openrouter_key}", "X-Title": "Prospector"},
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise AgentDraftError(f"agent call failed: {exc}") from exc
    return parse_response(content)


def parse_response(content: str) -> AgentResponse:
    """Parse and shape-check the model reply (contracts/agent-draft.md §3)."""
    try:
        data = json.loads(_strip_code_fences(content))
    except (ValueError, TypeError) as exc:
        raise AgentDraftError(f"agent response malformed: not JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise AgentDraftError("agent response malformed: not a JSON object")

    subject = data.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise AgentDraftError("agent response malformed: missing subject")

    raw_blocks = data.get("blocks")
    if not isinstance(raw_blocks, list):
        raise AgentDraftError("agent response malformed: blocks is not a list")
    if not MIN_BLOCKS <= len(raw_blocks) <= MAX_BLOCKS:
        raise AgentDraftError(
            f"agent returned {len(raw_blocks)} blocks (expected {MIN_BLOCKS}-{MAX_BLOCKS})"
        )

    blocks: list[DraftBlock] = []
    for i, raw in enumerate(raw_blocks):
        if not isinstance(raw, dict):
            raise AgentDraftError(f"agent response malformed: block {i + 1} is not an object")
        text = raw.get("text")
        cites = raw.get("cites")
        if not isinstance(text, str) or not text.strip():
            raise AgentDraftError(f"agent response malformed: block {i + 1} has no text")
        if not isinstance(cites, list) or not all(isinstance(c, str) for c in cites):
            raise AgentDraftError(f"agent response malformed: block {i + 1} cites is not a list of strings")
        blocks.append(DraftBlock(text=text.strip(), cites=[c.strip() for c in cites]))

    return AgentResponse(subject=subject.strip(), blocks=blocks)


# --- Assembly ---------------------------------------------------------------


def assemble_body(prospect: Prospect, response: AgentResponse) -> str:
    """Greeting + blocks + signature, all in code (FR-306).

    The model's prose is never edited here — only accepted whole or rejected
    whole."""
    parts = [f"Hi {expected_greeting(prospect)},"]
    parts.extend(block.text for block in response.blocks)
    parts.append(SIGNATURE)
    return "\n\n".join(parts)


# --- Validation -------------------------------------------------------------


def _prospect_tokens(prospect: Prospect) -> list[str]:
    """Values that mark a sentence as being about THIS prospect (V3).

    Distinctive company tokens only: "5 duct-cleaning companies" appears in the
    offer itself, so trade and generic words must never count as leakage."""
    tokens: list[str] = []
    company = prospect.company.company
    tokens.append(company.lower())
    for token in re.split(r"[^a-z0-9]+", company.lower()):
        if len(token) >= 4 and token not in NON_DISTINCTIVE:
            tokens.append(token)

    city = prospect.research.city or prospect.company.city
    if city:
        tokens.append(city.lower())
    if prospect.name_used and prospect.name_used != "team":
        tokens.append(prospect.name_used.lower())
    if prospect.name_candidate:
        tokens.append(prospect.name_candidate.lower())
    if prospect.research.hook:
        tokens.append(prospect.research.hook.lower())
    return [t for t in dict.fromkeys(tokens) if t]


def validate_citations(response: AgentResponse, prospect: Prospect, refs: list[EvidenceRef]) -> list[str]:
    """Rules V1-V4 (contracts/agent-draft.md §5.1). Deterministic; no model."""
    errors: list[str] = []
    known = {ref.id for ref in refs}
    prospect_tokens = _prospect_tokens(prospect)
    cited_real_evidence = False

    for i, block in enumerate(response.blocks, start=1):
        # V1 — no block may be uncited. This is what removes the need for any
        # "is this a claim?" classifier: there is no uncited category.
        if not block.cites:
            errors.append(f"block {i} carries no citation")
            continue

        # V2 — every citation resolves to a record captured for THIS company.
        for cite in block.cites:
            if cite != OFFER_CITE and cite not in known:
                errors.append(f"block {i} cites unknown id {cite!r}")

        non_offer = [c for c in block.cites if c != OFFER_CITE]
        if non_offer:
            cited_real_evidence = True
            continue

        # V3 — anti-laundering: an offer-only block may not describe the
        # prospect. Substring match over values already in hand, not a judgment.
        lowered = block.text.lower()
        for token in prospect_tokens:
            if token in lowered:
                errors.append(
                    f"block {i} cites only {OFFER_CITE!r} but mentions the prospect ({token!r})"
                )
                break

    # V4 — an all-offer draft is template-equivalent; the template is cheaper.
    if not cited_real_evidence:
        errors.append("no block cites real evidence (draft is not personalized)")

    return errors


def validate_retained(subject: str, body: str, prospect: Prospect) -> list[str]:
    """Rules V5-V12 (§5.2): the checks that survive free prose, reusing
    `draft.py`'s existing predicates and constants."""
    errors: list[str] = []
    lowered = body.lower()

    if re.search(r"\[[^\]\n]{1,60}\]", body) or re.search(r"\[[^\]\n]{1,60}\]", subject):
        errors.append("unfilled [slot] remains")

    for banned in AD_CLAIM_SUBSTRINGS:
        if banned in lowered or banned in subject.lower():
            errors.append(f"ad-running claim detected: {banned!r}")

    if body.count("http") != 1 or PRODUCT_URL not in body:
        errors.append("body must carry exactly one promotional link (the product page)")
    if "linkedin.com" in lowered:
        errors.append("LinkedIn link may not appear in the pitch")

    if not body.rstrip().endswith(SIGNATURE):
        errors.append("signature altered or missing")

    expected = expected_greeting(prospect)
    if not body.startswith(f"Hi {expected},"):
        errors.append(f"greeting must be {expected!r}")

    # Unsourced-name guard: identical rule to the template path, now applied to
    # model-written prose. Code owns the greeting, so this is a backstop against
    # a block greeting again inside its own text.
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

    company_tokens = {t for t in re.split(r"[^a-z0-9']+", prospect.company.company.lower()) if t}
    subject_tokens = [t for t in re.split(r"[^a-z0-9']+", subject.lower()) if t]
    unknown = [t for t in subject_tokens if t not in company_tokens]
    if not subject_tokens:
        errors.append("subject is empty")
    elif not any(t in company_tokens for t in subject_tokens):
        errors.append("subject_company contains words not in the company name")
    else:
        # Offer vocabulary is permitted alongside the company's own words.
        allowed = {"free", "day", "10", "pilot", "for", "spots", "duct", "lead", "qualifier", "a", "the"}
        stray = [t for t in unknown if t not in allowed]
        if stray:
            errors.append(f"subject contains words not in the company name: {stray}")

    return errors


def validate(response: AgentResponse, body: str, prospect: Prospect, refs: list[EvidenceRef]) -> list[str]:
    """All rules. Every failure is collected so the operator sees each one
    (FR-314) — no short-circuiting."""
    return validate_citations(response, prospect, refs) + validate_retained(
        response.subject, body, prospect
    )


# --- Entry point ------------------------------------------------------------


def draft_email(prospect: Prospect, settings: Settings, instructions=None) -> Draft:
    """Agent path with automatic fallback. NEVER raises (G1).

    Returns an agent-sourced Draft when the model produced validated, cited
    copy; otherwise the locked-template Draft carrying the rejection reasons."""
    reason: str
    refs = build_evidence_refs(prospect.research)

    if instructions is None:
        reason = "no instructions loaded"
    elif not refs:
        # G3/FR-317: nothing to cite means nothing to personalize. Skipping the
        # request entirely is both cheaper and more honest than asking for copy
        # that could only cite the offer.
        reason = "no evidence to cite"
    else:
        try:
            response = request_draft(prospect, settings, instructions, refs)
            body = assemble_body(prospect, response)
            errors = validate(response, body, prospect, refs)
            if not errors:
                return Draft(
                    subject=response.subject,
                    body=body,
                    model=settings.openrouter_model,
                    validated=True,
                    source="agent",
                )
            reason = "; ".join(errors)
        except AgentDraftError as exc:
            reason = str(exc)

    # The locked template still needs its own (much smaller) slot-filling call,
    # so a total OpenRouter outage takes BOTH paths down. That is not a
    # regression: it is exactly today's behavior, and SC-305 asks for
    # equivalence with today, not for offline drafting. Returning an
    # unvalidated Draft rather than raising keeps `draft_email` to one contract
    # (G1) — the pipeline already flags unvalidated drafts for review.
    try:
        fallback = build_email_draft(prospect, settings)
    except DraftError as exc:
        return Draft(
            subject=None,
            body="",
            model=settings.openrouter_model,
            validated=False,
            validation_errors=[f"agent fallback: {reason}", f"template fallback failed: {exc}"],
            source="template",
        )
    fallback.source = "template"
    fallback.validation_errors = [*fallback.validation_errors, f"agent fallback: {reason}"]
    return fallback
