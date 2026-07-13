<!--
Sync Impact Report
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

### I. No Email Sender (Research and Draft Only)

The tool MUST NOT send email or messages of any kind, on any channel, through
any mechanism (SMTP, API, browser automation, or otherwise). Its output is
drafts; sending is performed manually by the human from their own inbox.
No task, dependency, or code path related to sending may be added.

*Rationale: sending is trivial and already solved; a DIY sender saves nothing
and risks the human's domain reputation.*

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

### V. Channel Honesty — Claims Require Observed Signals

Every channel claim in outreach copy MUST be backed by an open-web signal
observed and recorded during research (`fb_signal` per PRODUCT.md §7.5).
Ad-running is NEVER claimed or implied — it is not observable from outside
Facebook and the tool never looks inside. Template selection is mechanical:
`fb_signal: strong` → Facebook variant; `weak` → channel-agnostic variant with
at most a conditional Facebook mention; `none` → channel-agnostic variant with
no Facebook mention. When the signal is uncertain, default DOWN, never up.

*Rationale: pitching a Facebook assistant to someone who doesn't use Facebook
burns the lead and the sender's credibility.*

### VI. Smallest Viable Build — No Gold-Plating

Scope is bounded by PRODUCT.md; features not specified there MUST NOT be
built (explicitly excluded: email sender, CRM features, web UI, agent
frameworks). LLM usage is single-shot prompt-per-company via OpenRouter with
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

**Version**: 1.0.0 | **Ratified**: 2026-07-13 | **Last Amended**: 2026-07-13
