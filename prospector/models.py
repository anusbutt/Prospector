"""In-memory data model (data-model.md). The vault note is the only persisted form."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Channel(str, Enum):
    EMAIL = "email"
    MESSENGER = "messenger"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    NONE = "none"


class FbSignal(str, Enum):
    STRONG = "strong"
    WEAK = "weak"
    NONE = "none"


class Variant(str, Enum):
    EMAIL_FB = "email_fb"
    EMAIL_AGNOSTIC = "email_agnostic"
    MESSENGER_DM = "messenger_dm"


class EvidenceKind(str, Enum):
    OWNER_TEXT = "owner_text"
    ABOUT_PAGE = "about_page"
    TEAM_PAGE = "team_page"
    FOOTER = "footer"
    EMAIL_PATTERN = "email_pattern"
    INPUT = "input"
    HUNTER = "hunter"
    FB_LINK = "fb_link"
    FB_EMBED = "fb_embed"
    FB_WIDGET = "fb_widget"
    FB_SEARCH_ACTIVE = "fb_search_active"
    FB_URL_INPUT = "fb_url_input"
    CITY_SOURCE = "city_source"
    HOOK_SOURCE = "hook_source"


@dataclass
class Company:
    company: str
    email: str | None
    raw_email_field: str = ""
    website: str | None = None
    facebook_url: str | None = None  # input only; NEVER fetched (Constitution II)
    city: str | None = None
    owner_name: str | None = None
    notes: str | None = None
    row_num: int = 0
    channel: Channel = Channel.EMAIL
    bucket_reason: str | None = None
    duplicate_of: str | None = None
    slug: str = ""
    needs_review: bool = False


@dataclass
class Evidence:
    kind: EvidenceKind
    value: str
    source: str
    excerpt: str = ""


@dataclass
class ResearchResult:
    website: str | None = None
    gbp_city: str | None = None
    name_evidence: list[Evidence] = field(default_factory=list)
    fb_evidence: list[Evidence] = field(default_factory=list)
    hook: str | None = None
    hook_evidence: Evidence | None = None
    city: str | None = None
    sources_consulted: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


@dataclass
class Prospect:
    company: Company
    research: ResearchResult
    name_confidence: Confidence = Confidence.NONE
    name_used: str = "team"
    name_candidate: str | None = None
    fb_signal: FbSignal = FbSignal.NONE
    variant: Variant = Variant.EMAIL_AGNOSTIC
    angle: str = "offer-led"
    needs_review: bool = False


@dataclass
class Draft:
    subject: str | None
    body: str
    model: str
    validated: bool = True
    validation_errors: list[str] = field(default_factory=list)
    # 006: which path produced this copy — "agent" (model-written, cited and
    # validated) or "template" (locked deterministic fallback). Defaults to
    # template so every pre-006 construction site keeps its existing meaning.
    source: str = "template"
    # 006: citations per body paragraph, in order. Retained after validation so
    # the operator can audit WHICH record each claim rests on — the validator
    # can only prove a cited record exists, never that it supports the
    # sentence, and that second check is the human's (SC-302). Empty on the
    # template path, which makes no per-paragraph claims.
    citations: list[list[str]] = field(default_factory=list)


# --- Agentic drafting (006) -------------------------------------------------
# The model writes prose but never facts: each block declares the evidence it
# rests on, and a deterministic validator resolves every citation before the
# copy reaches a note (Constitution v5.0.0 Principle IV).

OFFER_CITE = "offer"  # reserved id: offer/product/sender facts, not a prospect claim


@dataclass
class EvidenceRef:
    """A stable, citable handle on one Evidence record (data-model.md).

    Derived fresh each run, never persisted. `id` is `<kind>_<ordinal>` so a
    citation is readable by the operator at review time and identical across
    runs with identical research (byte-idempotency, FR-329)."""

    id: str
    kind: str
    value: str
    source: str
    excerpt: str = ""


@dataclass
class DraftBlock:
    """One paragraph of model-written prose plus its supporting citations.

    The unit of validation: accepted or rejected whole, never edited by code."""

    text: str
    cites: list[str] = field(default_factory=list)


@dataclass
class AgentResponse:
    """The parsed model reply, before assembly and validation."""

    subject: str
    blocks: list[DraftBlock] = field(default_factory=list)


class SendOutcome(str, Enum):
    SENT = "sent"
    DEFERRED_CAP = "deferred_cap"
    SKIPPED_NOT_APPROVED = "skipped_not_approved"
    SKIPPED_NOT_SENDABLE = "skipped_not_sendable"
    SKIPPED_ALREADY_SENT = "skipped_already_sent"
    FAILED = "failed"


@dataclass
class SendCandidate:
    """A parsed, sendable view of one approved vault note (data-model.md)."""

    slug: str
    company: str
    recipient: str | None
    channel: str
    subject: str | None
    body: str | None
    note_path: "Path"
    approved_at: float = 0.0  # sort key for oldest-approved-first (note mtime)

    def sendable_error(self) -> str | None:
        """Return a reason string if this candidate is NOT sendable, else None."""
        if self.channel != Channel.EMAIL.value:
            return "not an email-channel note"
        if not self.recipient or "@" not in self.recipient or "." not in self.recipient.split("@")[-1]:
            return "missing or invalid email address"
        if not self.subject or not self.subject.strip():
            return "draft has no subject"
        if not self.body or not self.body.strip():
            return "draft has no body"
        return None


@dataclass
class LedgerRecord:
    """One append-only send-ledger row (contracts/ledger.schema.md)."""

    ts: str
    slug: str
    recipient: str
    company: str
    message_id: str | None
    result: str  # "sent" | "failed"
    error: str | None
    from_account: str


@dataclass
class SendResult:
    slug: str
    recipient: str | None
    outcome: SendOutcome
    detail: str = ""


@dataclass
class RunReport:
    dry_run: bool = True
    cap_today: int = 0
    already_today: int = 0
    results: list[SendResult] = field(default_factory=list)

    def count(self, outcome: SendOutcome) -> int:
        return sum(1 for r in self.results if r.outcome == outcome)

    @property
    def sent(self) -> int:
        return self.count(SendOutcome.SENT)

    @property
    def deferred(self) -> int:
        return self.count(SendOutcome.DEFERRED_CAP)

    @property
    def failed(self) -> int:
        return self.count(SendOutcome.FAILED)

    @property
    def skipped(self) -> int:
        return (
            self.count(SendOutcome.SKIPPED_NOT_APPROVED)
            + self.count(SendOutcome.SKIPPED_NOT_SENDABLE)
            + self.count(SendOutcome.SKIPPED_ALREADY_SENT)
        )


@dataclass
class RunSummary:
    total: int = 0
    processed: int = 0
    failed: int = 0
    named_high: int = 0
    named_medium: int = 0
    named_none: int = 0
    messenger: int = 0
    duplicates: int = 0
    needs_review: int = 0
    per_company: list[tuple[str, str, str]] = field(default_factory=list)  # (slug, outcome, detail)
    # 006 drafting-path visibility (FR-320). These need NOT sum to `processed`:
    # messenger notes, --no-llm runs, and frozen notes are drafted by neither path.
    drafted_agent: int = 0
    drafted_template: int = 0
    fallback_reasons: list[tuple[str, str]] = field(default_factory=list)  # (slug, reason)

    def reconciles(self) -> bool:
        return self.total == self.processed + self.failed
