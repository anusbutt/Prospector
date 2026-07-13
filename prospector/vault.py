"""Obsidian vault output: slugging + canonical note rendering + write-if-changed.

The renderer is the single serializer: identical data MUST produce identical
bytes (SC-006). Merge semantics (human-edit preservation) arrive in US5 (T022).
"""

import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from prospector.models import Company, Draft, Prospect

FRONTMATTER_KEYS = (
    "company",
    "email",
    "channel",
    "status",
    "name_used",
    "name_confidence",
    "name_candidate",
    "hook",
    "website",
    "angle",
    "fb_signal",
    "duplicate_of",
    "needs_review",
    "tags",
)

TAGS_LINE = "[outreach, duct-cleaning, prospector]"
MAX_SLUG_LENGTH = 80


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH].rstrip("-") or "company"


def assign_slugs(companies: list[Company]) -> None:
    """Set a unique, deterministic slug on every company (input order stable)."""
    taken: set[str] = set()
    for company in companies:
        base = slugify(company.company)
        candidates = [base]
        if company.city:
            candidates.append(f"{base}-{slugify(company.city)}")
        domain = _email_domain(company.email)
        if domain:
            candidates.append(f"{base}-{slugify(domain)}")
        slug = next((c for c in candidates if c not in taken), None)
        if slug is None:
            n = 2
            while f"{base}-{n}" in taken:
                n += 1
            slug = f"{base}-{n}"
        company.slug = slug
        taken.add(slug)


def _email_domain(email: str | None) -> str | None:
    if email and "@" in email:
        return email.rsplit("@", 1)[1]
    return None


def _yaml_value(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if re.search(r'[:#"\[\]{}]|^\s|\s$|^[&*>|%@`!?-]', text):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def display_website(website: str | None) -> str | None:
    if not website:
        return None
    parsed = urlparse(website)
    host = parsed.netloc or website
    path = parsed.path.rstrip("/")
    return host + path if path else host


def render_note(
    prospect: Prospect,
    draft_markdown: str,
    research_markdown: str,
    *,
    status: str = "to-send",
    log_markdown: str = "-",
) -> str:
    company = prospect.company
    values = {
        "company": company.company,
        "email": company.email,
        "channel": company.channel.value,
        "status": status,
        "name_used": prospect.name_used,
        "name_confidence": prospect.name_confidence.value,
        "name_candidate": prospect.name_candidate,
        "hook": prospect.research.hook,
        "website": display_website(prospect.research.website or company.website),
        "angle": prospect.angle,
        "fb_signal": prospect.fb_signal.value,
        "duplicate_of": company.duplicate_of,
        "needs_review": bool(prospect.needs_review or company.needs_review),
        "tags": None,  # rendered specially below
    }
    lines = ["---"]
    for key in FRONTMATTER_KEYS:
        if key == "tags":
            lines.append(f"tags: {TAGS_LINE}")
        else:
            rendered = _yaml_value(values[key])
            lines.append(f"{key}: {rendered}".rstrip())
    lines.append("---")
    lines.append("")
    lines.append("## Draft")
    lines.append(draft_markdown.strip("\n"))
    lines.append("")
    lines.append("## Research")
    lines.append(research_markdown.strip("\n"))
    lines.append("")
    lines.append("## Log")
    lines.append(log_markdown.strip("\n"))
    return "\n".join(lines) + "\n"


def write_note(vault_dir: str | Path, slug: str, content: str) -> str:
    """Write only when bytes differ. Returns 'created' | 'updated' | 'unchanged'."""
    vault_dir = Path(vault_dir)
    vault_dir.mkdir(parents=True, exist_ok=True)
    path = vault_dir / f"{slug}.md"
    if path.exists():
        if path.read_text(encoding="utf-8") == content:
            return "unchanged"
        path.write_text(content, encoding="utf-8")
        return "updated"
    path.write_text(content, encoding="utf-8")
    return "created"


KNOWN_SECTIONS = ("Draft", "Research", "Log")


def parse_note(text: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Split a note into (raw frontmatter dict, ordered [(heading, body)])."""
    lines = text.split("\n")
    frontmatter: dict[str, str] = {}
    body_start = 0
    if lines and lines[0] == "---":
        for i in range(1, len(lines)):
            if lines[i] == "---":
                body_start = i + 1
                break
            key, _, value = lines[i].partition(":")
            frontmatter[key.strip()] = value.strip()
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    buffer: list[str] = []
    for line in lines[body_start:]:
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(buffer)))
            heading = line[3:].strip()
            buffer = []
        elif heading is not None:
            buffer.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(buffer)))
    return frontmatter, sections


def merge_notes(existing: str, fresh: str) -> str:
    """Section-ownership merge (contracts/note-format.md):
    machine-owned (from fresh): all frontmatter except status, ## Draft,
    ## Research. Human-owned (from existing): status — written once, never
    machine-changed after — ## Log verbatim, and any unrecognized sections,
    preserved after the known ones in their original order."""
    existing_fm, existing_sections = parse_note(existing)
    fresh_fm, fresh_sections = parse_note(fresh)

    merged_fm = dict(fresh_fm)
    if existing_fm.get("status"):
        merged_fm["status"] = existing_fm["status"]

    merged_sections = dict(fresh_sections)
    existing_map = dict(existing_sections)
    if "Log" in existing_map:
        merged_sections["Log"] = existing_map["Log"]

    ordered = [(h, merged_sections[h]) for h in KNOWN_SECTIONS if h in merged_sections]
    ordered += [(h, b) for h, b in existing_sections if h not in KNOWN_SECTIONS]

    out = ["---"]
    for key in FRONTMATTER_KEYS:
        out.append(f"{key}: {merged_fm.get(key, '')}".rstrip())
    out.append("---")
    out.append("")
    blocks = [f"## {heading}\n{body.strip(chr(10))}" for heading, body in ordered]
    return "\n".join(out) + "\n" + "\n\n".join(blocks) + "\n"


def upsert_note(vault_dir: str | Path, slug: str, fresh_content: str) -> str:
    """Create the note, or merge machine-owned regions into the existing one.
    Returns 'created' | 'updated' | 'unchanged'; writes only when bytes differ."""
    vault_dir = Path(vault_dir)
    path = vault_dir / f"{slug}.md"
    if not path.exists():
        return write_note(vault_dir, slug, fresh_content)
    existing = path.read_text(encoding="utf-8")
    merged = merge_notes(existing, fresh_content)
    if merged == existing:
        return "unchanged"
    path.write_text(merged, encoding="utf-8")
    return "updated"


DASHBOARD_CONTENT = """# Outreach Dashboard

> The queues below are live **Dataview** queries (community plugin — install it
> in Obsidian for live tables). Without Dataview this note still renders as
> plain markdown; browse notes by their frontmatter instead. All queries match
> notes tagged `#prospector`, so this works from any folder in your vault.

## To-send queue

```dataview
TABLE company, hook, fb_signal
FROM #prospector
WHERE status = "to-send" AND channel = "email" AND !duplicate_of
```

## Needs review

```dataview
TABLE company, name_candidate, name_confidence, needs_review
FROM #prospector
WHERE needs_review = true OR name_confidence = "medium"
```

## Messenger bucket

```dataview
TABLE company, hook, fb_signal
FROM #prospector
WHERE channel = "messenger"
```

## Pipeline

```dataview
TABLE rows.company AS Companies
FROM #prospector
GROUP BY status
```
"""


def write_dashboard(vault_dir: str | Path) -> str:
    """_Dashboard.md is entirely machine-owned: plain write-if-differ, no merge.
    Content is static, so re-runs are byte-idempotent."""
    return write_note(vault_dir, "_Dashboard", DASHBOARD_CONTENT)


def build_research_markdown(prospect: Prospect) -> str:
    research = prospect.research
    if research.name_evidence:
        best = research.name_evidence[0]
        name_line = f"{best.value} ({best.kind.value}: {best.source})"
    else:
        name_line = "not found"
    sources = ", ".join(research.sources_consulted) if research.sources_consulted else "(none)"
    hook_line = research.hook or "not found"
    if research.hook_evidence and research.hook_evidence.excerpt:
        hook_line += f' ({research.hook_evidence.source}: "{research.hook_evidence.excerpt}")'
    fb_line = prospect.fb_signal.value
    if research.fb_evidence:
        fb_line += " — " + "; ".join(f"{e.kind.value}: {e.value}" for e in research.fb_evidence)
    else:
        fb_line += " — no FB link/widget/search presence found"
    failures = "; ".join(research.failures) if research.failures else "(none)"
    lines = [
        f"- Owner name: {name_line}",
        f"- Sources: {sources}",
        f"- Hook: {hook_line}",
        f"- fb_signal: {fb_line}",
        f"- Failures: {failures}",
    ]
    if prospect.company.duplicate_of:
        lines.insert(0, f"- Duplicate: shares inbox with [[{prospect.company.duplicate_of}]] — one send per inbox")
    return "\n".join(lines)


def draft_markdown_for(draft: Draft | None, prospect: Prospect, *, no_llm: bool = False) -> str:
    if no_llm:
        return "*(not drafted — run without LLM)*"
    if draft is None:
        return "*(not drafted)*"
    if not draft.validated:
        reasons = "; ".join(draft.validation_errors) or "unknown"
        return f"*(draft failed validation: {reasons})*"
    if draft.subject:
        return f"**Subject:** {draft.subject}\n\n{draft.body}"
    return draft.body
