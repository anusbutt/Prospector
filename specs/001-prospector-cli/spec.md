# Feature Specification: Prospector — Outreach Research & Draft Vault

**Feature Branch**: `001-prospector-cli`
**Created**: 2026-07-13
**Status**: Draft
**Input**: User description: "Prospector — a CLI batch tool that researches home-service companies on the open web, finds owner first names with honest confidence scoring, detects channel and duplicate inboxes, reads open-web Facebook-usage signals, drafts paste-ready outreach from locked templates, and writes an Obsidian vault (one note per company + Dataview dashboard). No sender, no Facebook access, no web UI. Source of truth: PRODUCT.md."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Batch list to paste-ready vault (Priority: P1)

The founder has a raw list of duct cleaning companies (CSV or markdown table with at
minimum company name and email, some rows blank or Facebook-only). They run one command.
For every company the tool researches the open web, finds the owner's first name when it
can, picks one personalization hook, drafts a message in the founder's locked voice, and
writes one Obsidian note per company plus a dashboard note. The founder opens the vault,
reviews the queue, and pastes drafts into their inbox to send manually.

**Why this priority**: This is the entire product. Everything else refines it.

**Independent Test**: Feed a small sample list (mix of rows with/without websites and
emails), run the command, verify the vault contains one well-formed note per company with
a complete draft, correct frontmatter, and a dashboard note.

**Acceptance Scenarios**:

1. **Given** a CSV with `company,email` rows, **When** the batch command runs, **Then**
   `Vault/Outreach/` contains one note per unique company with frontmatter matching the
   PRODUCT.md §6 schema and a full draft body with no unfilled bracket slots.
2. **Given** a company whose website has an `/about` page naming the owner, **When**
   processed, **Then** the draft greets the owner by first name, `name_confidence: high`,
   and the source is recorded under `## Research`.
3. **Given** a company where no name is found anywhere, **When** processed, **Then** the
   greeting is "[Company] team", `name_confidence: none`, and no name appears anywhere in
   the draft.
4. **Given** a row with no usable website and no resolvable listing, **When** processed,
   **Then** a note is still written with the best available data and `needs_review: true`.

---

### User Story 2 - Honest name confidence gating (Priority: P1)

The founder trusts the tool never to guess. A name is used in a greeting only when the
evidence is strong (explicit owner text on the site, `/about`/`/team` naming, or an
unambiguous email pattern like `johnsmith@`). Ambiguous evidence (e.g. `derickson@`) is
surfaced as a candidate for human review, never used. Nothing is ever invented.

**Why this priority**: One fabricated name poisons trust in the whole batch. This is a
constitutional guarantee (Principle IV), not a nice-to-have.

**Independent Test**: Run fixtures covering each confidence tier and verify the greeting,
`name_confidence`, `name_candidate`, and `needs_review` fields land exactly per §7.

**Acceptance Scenarios**:

1. **Given** an email `scottb@company.com`, **When** scored, **Then** confidence is
   `high` and the draft greets "Scott".
2. **Given** an email `derickson@company.com` and no other evidence, **When** scored,
   **Then** confidence is `medium`, greeting is "[Company] team", `name_candidate` holds
   the guess, and `needs_review: true`.
3. **Given** no name evidence at all, **When** scored, **Then** confidence is `none` and
   the note carries "[Company] team" with an empty `name_candidate`.
4. **Given** any input, **When** drafting, **Then** no name appears in a draft that was
   not observed in a recorded source (verifiable from `## Research` sources list).

---

### User Story 3 - Channel-honest template selection (Priority: P1)

Outreach copy only mentions Facebook when open-web signals show the business actually
uses it (site links/embeds their FB page, Messenger widget, active page visible in
search results). Strong signal → Facebook variant; weak → channel-agnostic variant with
a conditional mention; none → channel-agnostic with no Facebook mention. Ad-running is
never claimed. Facebook itself is never accessed.

**Why this priority**: Pitching a Facebook assistant to a non-Facebook business burns
leads; claiming unobservable facts is a constitutional violation (Principles II & V).

**Independent Test**: Fixtures with strong/weak/no FB signals produce the correct
template variant; the words used never claim ad-running; no request is ever made to a
facebook.com URL (verifiable from fetch logs).

**Acceptance Scenarios**:

1. **Given** a site that embeds its Facebook page and shows recent FB activity in search
   results, **When** processed, **Then** `fb_signal: strong` and the Facebook email
   variant is drafted.
2. **Given** one soft signal only (e.g. a bare FB link in the footer), **When**
   processed, **Then** `fb_signal: weak` and the channel-agnostic variant is used with
   the conditional "or Facebook if you use it" clause.
3. **Given** no findable FB usage, **When** processed, **Then** `fb_signal: none`, the
   channel-agnostic variant is used, and the draft contains no mention of Facebook.
4. **Given** a `facebook_url` in the input, **When** the batch runs, **Then** no HTTP
   request is made to any facebook.com/fb.com host at any point.

---

### User Story 4 - Dedupe and channel bucketing (Priority: P2)

Two businesses sharing one inbox (same email or domain) are detected so the founder
sends once, not twice. Rows with a blank email, "messenger", or a Facebook URL in the
email field go to the messenger bucket and get a Messenger DM draft instead of an email.

**Why this priority**: Prevents embarrassing double-sends and makes the messenger-only
slice actionable, but the tool is useful without it on clean lists.

**Independent Test**: A fixture list containing a shared inbox pair and messenger-only
rows produces one primary note per inbox with duplicates flagged, and DM drafts in the
messenger bucket.

**Acceptance Scenarios**:

1. **Given** two companies with the same email, **When** ingested, **Then** one is the
   primary send and the other is flagged as a duplicate referencing the primary (no two
   `to-send` notes share an inbox).
2. **Given** a row whose email field is blank, "messenger", or a Facebook URL, **When**
   ingested, **Then** `channel: messenger` and the note's draft is the Messenger DM
   template.

---

### User Story 5 - Safe re-runs that respect human edits (Priority: P2)

The founder re-runs the batch after fixing inputs or as new info appears. Existing notes
are updated in place (e.g. a newly found name fills in), but human edits to `## Log` and
manual `status` changes are never overwritten.

**Why this priority**: The vault is a working pipeline document; clobbering human state
makes the tool unusable for real outreach cycles.

**Independent Test**: Run the batch, hand-edit a note's `status` and `## Log`, re-run,
and verify the edits survive while machine-owned fields refresh.

**Acceptance Scenarios**:

1. **Given** an existing note with `status: sent` and a filled `## Log`, **When** the
   batch re-runs over the same list, **Then** `status` remains `sent` and the `## Log`
   content is unchanged.
2. **Given** a note whose owner name was previously not found, **When** a re-run finds a
   high-confidence name, **Then** the frontmatter and draft update to use it without
   touching human-owned sections.
3. **Given** the same input list run twice with no changes, **When** the second run
   completes, **Then** the vault content is identical to the first run's output
   (idempotent).

---

### User Story 6 - Review queue via dashboard (Priority: P3)

The founder opens `_Dashboard.md` in Obsidian and sees live queues: to-send, needs
review (medium-confidence names and flagged rows), messenger bucket, and pipeline by
status — without the tool providing any UI of its own.

**Why this priority**: Pure convenience over the per-note output; plain notes already
work without it.

**Independent Test**: Open the generated dashboard in Obsidian with Dataview enabled and
confirm each query returns the expected notes from a known fixture batch.

**Acceptance Scenarios**:

1. **Given** a completed batch, **When** the dashboard is opened with Dataview
   installed, **Then** it lists to-send, needs-review, and messenger queues matching the
   notes' frontmatter.
2. **Given** Dataview is not installed, **When** the dashboard is opened, **Then** the
   note still renders as readable markdown (queries degrade gracefully).

### Edge Cases

- Input row with a company name only (no email, no website): resolve what's possible,
  write the note flagged `needs_review: true`.
- Website unreachable, times out, or blocks fetches: proceed with remaining sources;
  record the failure under `## Research`; never retry aggressively.
- Two different companies with the same name in one list: slugs must not collide
  (disambiguate deterministically, e.g. by city or domain).
- Company name with characters unsafe for filenames: slug is sanitized and stable across
  runs.
- Email field contains something that is neither an email, "messenger", nor a Facebook
  URL: treat as messenger-bucket and flag for review.
- LLM draft output violates the locked template (missing slots, extra prose, banned
  style): detected and the note is flagged rather than silently accepted.
- LLM or enrichment API unavailable mid-batch: already-written notes stay valid; failed
  companies are reported and can be re-run (idempotency covers resume).
- A found "owner name" matches the company name or a generic word (e.g. "Duct Master"):
  rejected as a name candidate, not greeted.
- Malformed CSV / markdown table rows: reported with row numbers; valid rows still
  process.

## Requirements *(mandatory)*

### Functional Requirements

**Ingest & bucketing**

- **FR-001**: System MUST accept an input list as CSV or markdown table with minimum
  columns `company` and `email`, and optional `website`, `facebook_url`, `city`,
  `owner_name`, `notes`.
- **FR-002**: System MUST normalize rows (trim, case-fold emails/domains) and report
  malformed rows by number without aborting the batch.
- **FR-003**: System MUST detect duplicate inboxes (identical email, or identical email
  domain where the domain is not a shared/free provider) and mark all but one note as
  duplicates referencing the primary.
- **FR-004**: System MUST bucket each company as `email` or `messenger`; blank email,
  the literal "messenger", or a Facebook URL in the email field routes to `messenger`.

**Research (open web only)**

- **FR-005**: System MUST resolve a company's website and Google Business listing when
  no website is provided, using open-web lookups only.
- **FR-006**: System MUST fetch and extract from the company website homepage and, when
  present, `/about`, `/team`, and `/contact` pages: owner-name candidates, city/service
  area, and one personalization hook.
- **FR-007**: System MUST NOT make any request to Facebook hosts or use any Facebook
  API/MCP; `facebook_url` input is stored and considered as a signal only.
- **FR-008**: System MUST support name enrichment from email patterns (e.g. `scottb@` →
  Scott) and MAY support optional third-party enrichment when configured; absence of the
  optional service MUST NOT block the pipeline.
- **FR-009**: System MUST record, per company, which sources were consulted and what
  each contributed (the `## Research` section).

**Scoring & honesty**

- **FR-010**: System MUST score name confidence exactly per PRODUCT.md §7: `high`
  (explicit owner text, /about- or /team-sourced name, unambiguous email pattern),
  `medium` (partial/ambiguous), `none`.
- **FR-011**: System MUST use a real first name in a draft only at `high` confidence; at
  `medium` it MUST keep "[Company] team", populate `name_candidate`, and set
  `needs_review: true`; at `none` it MUST use "[Company] team".
- **FR-012**: System MUST never emit in a draft any name, email, or hook that does not
  trace to a recorded source (no fabrication).
- **FR-013**: System MUST classify `fb_signal` as `strong`/`weak`/`none` per PRODUCT.md
  §7.5 from open-web observations only, defaulting downward when uncertain.

**Drafting**

- **FR-014**: System MUST select the template variant mechanically: `fb_signal: strong`
  → Facebook email variant; `weak`/`none` → channel-agnostic email variant (with the
  conditional Facebook clause only at `weak`); messenger bucket → Messenger DM template.
- **FR-015**: System MUST fill only the bracketed slots of the locked PRODUCT.md §8
  templates; template prose MUST pass through unaltered, and drafts MUST NOT claim or
  imply ad-running.
- **FR-016**: System MUST produce each draft via a single LLM call per company (no
  multi-agent orchestration), and validate the output against the template (all slots
  filled, no extra sections); failures set `needs_review: true` with the reason logged.

**Vault output**

- **FR-017**: System MUST write one note per company to the vault folder (default
  `Vault/Outreach/`, overridable), with YAML frontmatter exactly matching the PRODUCT.md
  §6 schema, plus `## Draft`, `## Research`, and `## Log` sections.
- **FR-018**: System MUST write/refresh a `_Dashboard.md` containing Dataview queries
  for: to-send queue, needs-review (flagged or medium-confidence), messenger bucket, and
  pipeline grouped by status.
- **FR-019**: Notes MUST be keyed by a deterministic company slug; re-runs MUST update
  machine-owned frontmatter and `## Draft`/`## Research` without modifying human-owned
  `status` values or `## Log` content, and MUST be byte-idempotent when inputs are
  unchanged.
- **FR-020**: System MUST NOT send email or messages by any mechanism, and MUST NOT
  provide any web/GUI interface; the CLI and the vault are the entire surface.

**Operations**

- **FR-021**: System MUST finish a batch even when individual companies fail (network
  errors, missing data), reporting per-company outcomes in a run summary (counts:
  named-high, review-needed, messenger, duplicates, failures).
- **FR-022**: System MUST read all credentials from environment configuration; a missing
  optional credential degrades that step, a missing required one fails fast with a clear
  message before any processing.
- **FR-023**: System MUST fetch third-party websites politely: bounded timeouts, no
  parallel hammering of a single host, and no crawling beyond the defined page set.

### Key Entities

- **Company (input row)**: company name, email (may be blank/"messenger"/FB URL),
  optional website, facebook_url, city, owner_name, notes.
- **Research result**: resolved website/listing, owner-name candidates with sources,
  city/service area, hook, fb_signal evidence list, consulted-source log.
- **Scored prospect**: channel bucket, duplicate linkage, name_used, name_confidence,
  name_candidate, fb_signal, angle, needs_review.
- **Company note**: one markdown file; frontmatter (§6 schema) + Draft + Research + Log;
  keyed by slug; mixed ownership (machine fields vs human `status`/`## Log`).
- **Dashboard note**: `_Dashboard.md` of Dataview queries over the note collection.
- **Run summary**: per-batch counts and per-company outcomes/failures shown by the CLI.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a representative 20-company list, at least 8 drafts (~40%+) greet a
  real first name at high confidence — up from ~2/20 by hand — with zero fabricated
  names (every used name traceable to a recorded source).
- **SC-002**: 100% of companies in an input list produce a vault note (with a draft or
  a flagged reason), even when research fails for some rows.
- **SC-003**: 100% of duplicate-inbox pairs in the input are detected, leaving exactly
  one to-send note per unique inbox.
- **SC-004**: 100% of messenger-only rows receive a Messenger DM draft and appear in
  the messenger queue.
- **SC-005**: Facebook is mentioned only in notes whose recorded fb_signal evidence
  supports it; zero drafts claim or imply ad-running; zero requests reach Facebook
  hosts during a batch.
- **SC-006**: Re-running an unchanged list changes zero bytes in the vault; re-running
  after human edits preserves 100% of `status` changes and `## Log` content.
- **SC-007**: A 20-company batch completes unattended in one command and produces a
  review-ready dashboard; the human's remaining work is review-and-paste only.

## Assumptions

- The §6 note schema, §7/§7.5 scoring rules, and §8 templates in PRODUCT.md are the
  authoritative definitions; this spec references rather than restates them.
- "Open web" means: the company's own website, Google Places / search results, public
  registries, email-pattern inference, and optional configured enrichment — never any
  authenticated or Facebook-owned surface.
- Default angle is offer-led (settled in PROGRESS.md decisions log).
- The vault path defaults to `Vault/Outreach/` relative to the working directory and is
  overridable via CLI option.
- Dataview is a recommended-but-optional Obsidian plugin; notes must be fully usable
  without it.
- Name hit rate of ~40–60% is acceptable by design; the goal is lift, not perfection.
- English-language sites and US-style naming conventions are the initial target market
  (duct cleaning, US); no localization in scope.
