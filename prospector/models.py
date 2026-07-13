"""In-memory data model (data-model.md). The vault note is the only persisted form."""

from dataclasses import dataclass, field
from enum import Enum


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

    def reconciles(self) -> bool:
        return self.total == self.processed + self.failed
