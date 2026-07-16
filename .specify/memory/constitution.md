<!--
Sync Impact Report
- Version change: 2.0.0 → 3.0.0 (2026-07-15)
- Reason: Nestaro outreach now requires automated sending of human-approved
  drafts at controlled volume (100/day goal, ramped). Principle I's absolute
  "MUST NOT send ... no sending code path may be added" is REDEFINED into a
  narrow, guarded-send exception (MAJOR bump: principle redefinition). Enables
  feature 003-approved-send.
- Modified principles: I (No Email Sender → Human-Approved Sending Only).
  New rule: drafts by default; sends ONLY notes a human marked `status: approved`
  in the vault; Gmail API only, from the designated Nestaro outreach account
  (nestaroassistant@gmail.com), never the operator's personal account; hard
  ramped daily cap; dry-run default (real sends require an explicit flag); every
  send appended to an immutable ledger; never auto-approve, never another
  channel, never past the cap.
- Modified principles: VI (Smallest Viable Build) — exclusion list updated: a
  guarded, approval-gated Gmail sender is now IN scope; CRM features, web UI, and
  agent frameworks remain excluded.
- Added sections: none. Removed sections: none.
- Templates requiring updates: ✅ plan-template.md Constitution Check (no "no
  sender" gate present) ⚠ PRODUCT.md §2/§7.5 sending language (pending 003 spec)
  ⚠ README guarantee wording, public repo (pending 003 spec).
- Follow-up TODOs: reconcile PRODUCT.md + README "sending is manual" language
  during 003-approved-send spec.
-->

<!--
Prior version 2.0.0 Sync Impact Report (2026-07-14)
- Version change: 1.1.0 → 2.0.0 (2026-07-14)
- Reason: the outreach offer is now the named product Nestaro — an AI agent
  that answers a business's Facebook Messenger inbox (lead_qualifier_feature.md).
  The product cannot be described without mentioning Facebook, so Principle V's
  blanket "no Facebook mention at fb_signal none" rule was REDEFINED with the
  human's explicit approval (MAJOR bump: principle redefinition).
- Modified principles: V (Channel Honesty). New rule: claims about the
  PROSPECT's Facebook usage or advertising remain banned at every signal level
  and ad-running is still never claimed or implied; describing the PRODUCT's
  own Facebook capability ("an assistant that answers your Facebook page
  messages") is permitted in all template variants. Variant selection stays
  mechanical on fb_signal; what the signal now gates is their-usage claims,
  not product-fact mentions.
- Added sections: none. Removed sections: none.
- Templates requiring updates: PRODUCT.md §7.5/§8 (same amendment), README
  guarantee #4 wording (public repo), draft.py validator rule.
- Follow-up TODOs: none
-->

<!--
Prior version 1.1.0 Sync Impact Report (2026-07-14)
- Version change: 1.0.0 → 1.1.0 (2026-07-14)
- Reason: PRODUCT.md §10 adds an optional company-sourcing stage
  (`prospector source`: Google Places discovery + on-site Meta Pixel ad-signal)
  to acquire first users for the Lead Qualifier agent.
- Modified principles: NONE. Principle II (Facebook never accessed) was
  explicitly reconsidered at the human's request and REAFFIRMED unchanged:
  the pixel signal is read from the candidate's own website source only.
- Added sections: one "Sourcing" bullet under Additional Constraints.
- Removed sections: none.
- Templates requiring updates: none (gates unchanged).
- Follow-up TODOs: none
-->

<!--
Prior version 1.0.0 Sync Impact Report (2026-07-13)
- Version change: (template, unversioned) → 1.0.0
- Modified principles: all placeholders replaced (initial ratification)
- Added sections:
  - Core Principles I–VII (No Sender; Open Web Only; Obsidian Is the Interface;
    Name Honesty; Channel Honesty; Smallest Viable Build; Verified Claims Only)
  - Additional Constraints (stack, data handling, idempotency)
  - Development Workflow (SDD cycle, task discipline, phase checkpoints)
  - Governance
- Removed sections: none (template slots filled)
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md (Constitution Check gates verified compatible)
  - ✅ .specify/templates/spec-template.md (no changes required)
  - ✅ .specify/templates/tasks-template.md (no changes required)
- Follow-up TODOs: none
-->

# Prospector Constitution

Prospector is a CLI batch tool that researches home-service companies on the open
web and writes personalized, paste-ready outreach drafts into an Obsidian vault.
Source of truth for intent: `PRODUCT.md`. These principles are hard constraints:
a change that violates one MUST be rejected or the constitution amended first.

## Core Principles

### I. Human-Approved Sending Only (Draft-First, Guarded Send)

The tool drafts by default and MUST NOT send anything a human has not explicitly
marked `status: approved` in the vault. When it sends, it MUST:

- send **only via the Gmail API**, from the designated Nestaro outreach account
  (`nestaroassistant@gmail.com`) — **never** the operator's personal account and
  never any other channel (no SMTP, no browser automation, no Messenger send);
- **never exceed the configured daily cap** (a ramped schedule, not a flat
  number), enforced against the send ledger;
- **default to dry-run**: a real send requires an explicit flag; absent it, the
  tool only reports what it *would* send;
- **append every send to an immutable ledger** (recipient, note, timestamp,
  message id, result) — the ledger is the source of truth for the daily count
  and the audit trail;
- **never auto-approve, never bulk-send past the cap**, and never send a note
  whose `status` is anything other than `approved`.

*Rationale: automating human-approved sends at controlled volume is now a
product requirement (Nestaro outreach at scale). The guardrails keep the human
as the sole approver, protect the sending account's reputation via a ramped cap,
and make double-sends impossible via the ledger — while still forbidding the
personal account and any unapproved or off-channel send.*

### II. Open Web Only — Facebook Is Never Accessed

The tool MUST NOT use the Facebook Graph API, any Facebook MCP server, or any
form of Facebook scraping, crawling, or authenticated access. A `facebook_url`
is a valid *input* field (it confirms the business; a vanity URL may hint a
name), but the URL is never fetched, the page is never scraped, and no login to
Facebook ever occurs. Owner data and channel-fit signals come exclusively from
the open web: the company website, Google (Places API / search results),
email-pattern inference, optional enrichment (Hunter.io), and optional public
business registries.

*Rationale: the Graph API cannot grant the needed access, scraping FB is
login-walled, brittle, and ToS-violating — decided and settled in PRODUCT.md §5.*

### III. Obsidian Is the Interface (No Web UI)

The tool's output interface is an Obsidian vault: one `.md` note per company
with YAML frontmatter, plus a `_Dashboard.md` of Dataview queries. No web UI,
dashboard app, server, or GUI of any kind may be built. Vault writes MUST be
idempotent and non-destructive: notes are keyed by company slug; re-running
merges frontmatter updates without clobbering human edits to `## Log` or
`status` (PRODUCT.md §6).

*Rationale: Obsidian already provides review, search, and pipeline views for
free; any UI is duplicated effort outside the product's job.*

### IV. Name Honesty — Never Fabricate

The tool MUST NOT fabricate a name, email address, or personalization hook.
A real first name is used in a draft only at `high` confidence as defined in
PRODUCT.md §7 (name from `/about`/`/team`, explicit owner text, or unambiguous
email pattern). At `medium` confidence the greeting stays "[Company] team",
the candidate goes to `name_candidate`, and `needs_review: true` is set. At
`none`, "[Company] team" with no candidate. When in doubt, score down.

*Rationale: one fabricated name destroys trust in every draft in the batch;
empty-and-flagged always beats wrong.*

### V. Channel Honesty — Claims About the Prospect Require Observed Signals

Every claim in outreach copy **about the prospect's own channels** MUST be
backed by an open-web signal observed and recorded during research
(`fb_signal` per PRODUCT.md §7.5). Ad-running is NEVER claimed or implied —
it is not observable from outside Facebook and the tool never looks inside.
Describing the **product's own capability** (Nestaro answers a Facebook page
inbox) is a fact about the product, not the prospect, and is permitted in all
variants *(amended 2026-07-14, v2.0.0)*. Template selection remains
mechanical: `fb_signal: strong` → variant that references their page activity;
`weak`/`none` → variant that frames Facebook as product capability only, with
no assertion about their usage. When the signal is uncertain, default DOWN,
never up.

*Rationale: honesty means not asserting things about the prospect we haven't
observed; it does not forbid saying what the product we're offering does.*

### VI. Smallest Viable Build — No Gold-Plating

Scope is bounded by PRODUCT.md; features not specified there MUST NOT be
built (explicitly excluded: CRM features, web UI, agent frameworks; a guarded,
approval-gated Gmail sender is IN scope per Principle I). LLM usage is
single-shot prompt-per-company via OpenRouter with
direct API calls — no LangChain or other agent/orchestration framework.
External services are called via direct HTTP/SDK calls. Prefer the smallest
viable diff; do not refactor unrelated code; add persistence (SQLite) only if
a demonstrated need arises.

*Rationale: the product's value is the research pipeline and honest drafts;
everything else is drag.*

### VII. Verified Claims Only

No task is marked complete, and no capability is described as working, unless
it has actually been run and its output observed. Test/demo runs MUST use real
invocations (CLI runs, unit tests, live fixture runs) — not assumed behavior.
Progress reporting (including `PROGRESS.md` session entries) records only what
verifiably works.

*Rationale: unverified "done" compounds into a codebase nobody can trust.*

## Additional Constraints

- **Stack (settled)**: Python + Typer CLI; httpx + selectolax + trafilatura for
  fetch/extract; Playwright only as fallback for JS-rendered sites; OpenRouter
  for single-shot LLM drafting; SQLite only if needed.
- **Secrets**: API keys live in `.env` (gitignored), never hardcoded, never
  committed, never logged.
- **Input**: CSV or markdown table with minimum `company`, `email`; blank /
  `messenger` / a Facebook URL in the email field routes to the messenger bucket.
- **Templates are locked** (PRODUCT.md §8): the LLM fills bracketed slots only;
  template prose is not paraphrased or restyled by the model.
- **Rate courtesy**: scraping targets are small businesses' websites — fetch
  politely (timeouts, no hammering, respect robots.txt for crawl paths).
- **Sourcing (PRODUCT.md §10)**: candidate discovery uses the Google Places
  API only — no directory scraping, no paid lead databases. The Meta Pixel
  ad signal (`ad_signal`) is detected by string inspection of the candidate's
  own website source; no Facebook host is ever contacted for it (Principle II
  applies in full). `ad_signal` filters the candidate list only and MUST NOT
  surface as an ad-running claim in outreach copy (Principle V applies in full).

## Development Workflow

- Full SDD cycle: constitution → spec → plan → tasks → implementation.
  `specs/<feature>/tasks.md` is the single source of tasks; the list is not
  duplicated elsewhere (PROGRESS.md holds narrative state only, written when
  the human asks).
- Implementation proceeds from the first task, top-down, one task at a time:
  run/test the task's output, then check it off. Pause and summarize at each
  phase boundary.
- Every user prompt gets a PHR under `history/prompts/`; significant
  architectural decisions get an ADR suggestion (never auto-created).
- Each task MUST have a concrete acceptance check (a command run, a test, an
  observed file/output) consistent with Principle VII.

## Governance

- This constitution supersedes all other practices for this repository. Where
  CLAUDE.md, templates, or habit conflict with it, the constitution wins.
- **Amendment**: propose the change, state which principle(s) it touches and
  why reality forces it, update PRODUCT.md first if intent changed, then bump
  the version here with a dated entry. The human approves all amendments.
- **Versioning**: semantic — MAJOR for principle removals/redefinitions, MINOR
  for new principles or materially expanded guidance, PATCH for clarifications.
- **Compliance review**: every plan and PR is checked against Principles I–VII
  before merge; violations block until resolved or the constitution is amended.

**Version**: 3.0.0 | **Ratified**: 2026-07-13 | **Last Amended**: 2026-07-15
