"""Deterministic scoring: name confidence per PRODUCT.md §7.

Precedence (strongest first):
  1. input owner_name column          -> high (the human said so)
  2. site owner/about/team evidence   -> high
  3. unambiguous email pattern        -> high
  4. footer copyright name            -> medium (candidate)
  5. ambiguous email pattern          -> medium (candidate)
  6. Hunter.io enrichment             -> medium (candidate)
  7. nothing                          -> none

high  -> greet by first name.  medium -> "team" + name_candidate +
needs_review.  none -> "team".  Never fabricate (Constitution IV).

fb_signal classification (§7.5) arrives in US3 (T018).
"""

from prospector.enrich import NameInference
from prospector.models import (
    Channel,
    Company,
    Confidence,
    Evidence,
    EvidenceKind,
    FbSignal,
    Prospect,
    ResearchResult,
    Variant,
)

HIGH_SITE_KINDS = (EvidenceKind.OWNER_TEXT, EvidenceKind.ABOUT_PAGE, EvidenceKind.TEAM_PAGE)

# §7.5: signals that show the page is actually *used*, not merely linked
FB_ACTIVE_KINDS = (EvidenceKind.FB_WIDGET, EvidenceKind.FB_EMBED, EvidenceKind.FB_SEARCH_ACTIVE)


def classify_fb_signal(fb_evidence: list[Evidence]) -> FbSignal:
    """§7.5, defaulting down: strong needs two or more signals of which at
    least one is an active-usage cue; any lesser observation is weak; nothing
    observed is none. Never up-ranks on uncertainty (Constitution V)."""
    if len(fb_evidence) >= 2 and any(e.kind in FB_ACTIVE_KINDS for e in fb_evidence):
        return FbSignal.STRONG
    if fb_evidence:
        return FbSignal.WEAK
    return FbSignal.NONE


def select_variant(channel: Channel, fb_signal: FbSignal) -> Variant:
    """Mechanical template selection (FR-014) — never a judgment call."""
    if channel is Channel.MESSENGER:
        return Variant.MESSENGER_DM
    if fb_signal is FbSignal.STRONG:
        return Variant.EMAIL_FB
    return Variant.EMAIL_AGNOSTIC


def first_name_of(full_name: str) -> str:
    return full_name.strip().split()[0].capitalize()


def apply_name_scoring(
    prospect: Prospect,
    email_inference: NameInference,
    hunter_inference: NameInference | None = None,
) -> None:
    company = prospect.company
    research = prospect.research

    high_name = _high_tier_name(company, research, email_inference)
    if high_name:
        prospect.name_confidence = Confidence.HIGH
        prospect.name_used = high_name
        prospect.name_candidate = None
        return

    candidate = _medium_tier_candidate(research, email_inference, hunter_inference)
    if candidate:
        prospect.name_confidence = Confidence.MEDIUM
        prospect.name_used = "team"
        prospect.name_candidate = candidate
        prospect.needs_review = True
        return

    prospect.name_confidence = Confidence.NONE
    prospect.name_used = "team"
    prospect.name_candidate = None


def _high_tier_name(
    company: Company, research: ResearchResult, email_inference: NameInference
) -> str | None:
    if company.owner_name:
        return first_name_of(company.owner_name)
    for evidence in research.name_evidence:
        if evidence.kind in HIGH_SITE_KINDS:
            return first_name_of(evidence.value)
        if evidence.kind is EvidenceKind.INPUT:
            return first_name_of(evidence.value)
    if email_inference.first_name:
        return email_inference.first_name
    return None


def _medium_tier_candidate(
    research: ResearchResult,
    email_inference: NameInference,
    hunter_inference: NameInference | None,
) -> str | None:
    for evidence in research.name_evidence:
        if evidence.kind is EvidenceKind.FOOTER:
            return evidence.value
    if email_inference.candidate:
        return email_inference.candidate
    if hunter_inference and hunter_inference.candidate:
        return hunter_inference.candidate
    return None
