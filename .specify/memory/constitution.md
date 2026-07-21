<!--
Sync Impact Report
- Version change: 4.0.1 → 5.0.0 (2026-07-20)
- Reason: drafting moves from locked-template slot-filling to agent-written
  personalized prose, constrained by versioned markdown instruction/skill files,
  with the locked template retained as an automatic fallback. Principles IV and
  V were previously enforced STRUCTURALLY — the model could not write prose, so
  it could not lie. That mechanism is REDEFINED as evidence-citation validation
  (MAJOR bump: enforcement redefinition). Approved by the human 2026-07-20;
  enables feature 006-agentic-drafting.
- Modified principles:
  - I (Human-Approved Sending Only) — CLARIFIED, nothing relaxed: adds the
    explicit rule that outreach copy is generated at `run` time only and is
    immutable after approval; the send path MUST NOT generate or alter copy.
  - IV (Name Honesty → Evidence-Bound Copy — Never Fabricate) — REDEFINED:
    scope widens from names to every claim about the prospect; each such claim
    MUST cite a recorded Evidence id, deterministically validated; an
    uncitable or unvalidated draft falls back to the locked template. The
    name-confidence tiers themselves are unchanged.
  - V (Channel Honesty) — REDEFINED enforcement: mechanical template-variant
    selection is replaced by per-claim evidence citation. The rule itself
    (prospect-usage claims need observed signals; product facts permitted;
    ad-running never claimed) is unchanged.
  - VI (Smallest Viable Build) — REDEFINED: "single-shot prompt-per-company"
    widens to rich-instruction single-call drafting from versioned markdown
    files. Agent/orchestration frameworks and autonomous tool-using loops
    remain excluded; the drafting model MUST have no tools and no network.
- Added sections: none. Removed sections: none.
- Modified constraints: "Templates are locked" is now scoped to the fallback
  path; a new constraint governs the instruction/skill files.
- Templates requiring updates: ✅ .specify/templates/plan-template.md
  (Constitution Check gates verified compatible) ✅ spec-template.md (no change
  required) ✅ tasks-template.md (no change required)
  ✅ PRODUCT.md §8 rewritten as "Message generation" (2026-07-20): citation-based
  honesty, instruction files, locked template retained as documented fallback
  ✅ README guarantees reworked (2026-07-20): #3 name honesty restated as
  structural (code owns the greeting), #4 added for evidence citation, #5/#6
  renumbered; the drafting step in "How it works" rewritten
- Follow-up TODOs: none.
-->

<!--
Prior version 4.0.1 Sync Impact Report (2026-07-17)
- Version change: 4.0.0 → 4.0.1 (2026-07-17)
- Reason: the offered product is rebranded — "Nestaro" becomes Omniveer's
  "Duct Lead Qualifier" (https://www.omniveer.com/duct-lead-qualifier).
  PATCH: Principle V's product-name reference is updated; the rule itself
  (prospect-usage claims gated by observed signals; product facts allowed;
  ad-running never claimed) is unchanged.
- Modified principles: V (name/example wording only — no rule change).
- Added sections: none. Removed sections: none.
- Templates requiring updates: ✅ PRODUCT.md §7.5/§8/§10 (updated first, same
  date: rebranded templates, single-promotional-link strategy, founder-led
  signature) ✅ draft.py locked constants + validator ✅ draft/integration tests.
- Follow-up TODOs: none.
-->

<!--
Prior version 4.0.0 Sync Impact Report (2026-07-17)
- Version change: 3.0.0 → 4.0.0 (2026-07-17)
- Reason: outreach moves to a custom-domain mailbox (anas@omniveer.com on Zoho
  Mail) for deliverability (SPF/DKIM/DMARC). Principle I's "Gmail API only ...
  no SMTP" channel rule and the hardcoded Nestaro Gmail identity are REDEFINED
  (MAJOR bump: principle redefinition). Approved by the human 2026-07-17;
  enables feature 004-provider-transport.
- Modified principles: I (Human-Approved Sending Only). New rule: sends go
  through a provider-neutral transport limited to exactly two providers — the
  Gmail API (unchanged, backward compatible) or authenticated SMTP over
  SSL/STARTTLS — selected by configuration; the sending identity is the
  configured dedicated outreach mailbox (`PROSPECTOR_SEND_FROM`, no hardcoded
  account), verified against the authenticated identity before any send
  (SMTP: From MUST equal the authenticated username — no From spoofing).
  Every other guardrail is unchanged: approved-only, dry-run default, ramped
  cap, immutable ledger, never auto-approve, never off-channel (no Messenger,
  no browser automation), never past the cap, never the personal account.
- Modified principles: VI (Smallest Viable Build) — "guarded, approval-gated
  Gmail sender" wording generalized to "guarded, approval-gated email sender
  (Gmail API or authenticated SMTP)".
- Added sections: none. Removed sections: none.
- Templates requiring updates: ✅ PRODUCT.md §2/§3/§11 (updated first, same
  date) ✅ README guarantee #1 + config/sending docs ✅ .env.example.
- Follow-up TODOs: none.
-->

<!--
Prior version 3.0.0 Sync Impact Report (2026-07-15)
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

- send **only email**, through exactly one of two configured providers — the
  **Gmail API** or **authenticated SMTP** (SSL or STARTTLS, e.g. a Zoho
  custom-domain mailbox) — and never any other channel (no browser automation,
  no Messenger send);
- send **only from the configured dedicated outreach mailbox**
  (`PROSPECTOR_SEND_FROM`, required — no hardcoded default) — **never** the
  operator's personal account. Before any send the authenticated identity
  (Gmail: the OAuth account; SMTP: the login username) MUST be verified to
  match the configured sender, case-insensitively; on mismatch the run aborts
  with nothing sent. SMTP MUST require authentication, and the From address
  MUST equal the authenticated username — arbitrary From spoofing is refused;
- **send exactly the words the human approved**: outreach copy is generated at
  `run` time and written into the note. The send path MUST NOT generate,
  rewrite, re-request, complete, or otherwise alter subject or body text — it
  reads what is in the note and delivers it verbatim. No LLM call may occur on
  the send path *(added 2026-07-20, v5.0.0)*;
- **never exceed the configured daily cap** (a ramped schedule, not a flat
  number), enforced against the send ledger;
- **default to dry-run**: a real send requires an explicit flag; absent it, the
  tool only reports what it *would* send — and dry-run MUST NOT authenticate,
  open a network connection, or make any external request;
- **append every send to an immutable ledger** (recipient, note, timestamp,
  message id, result) — the ledger is the source of truth for the daily count
  and the audit trail;
- **never auto-approve, never bulk-send past the cap**, and never send a note
  whose `status` is anything other than `approved`;
- **never log, print, persist, or commit** the SMTP password, OAuth tokens, or
  any other sending credential.

*Rationale: automating human-approved sends at controlled volume is a product
requirement, and deliverability at that volume requires a custom-domain mailbox
with SPF/DKIM/DMARC (amended 2026-07-17, v4.0.0: authenticated SMTP joins the
Gmail API as a sanctioned transport for the Omniveer mailbox). The guardrails
keep the human as the sole approver, bind the tool to one verified dedicated
identity, protect the sending account's reputation via a ramped cap, and make
double-sends impossible via the ledger. The draft-time-only rule (v5.0.0) is
what keeps "human-approved" meaningful once copy is model-written: approval
attaches to specific words, so generating copy after approval would deliver
something no human ever read.*

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

### IV. Evidence-Bound Copy — Never Fabricate

The tool MUST NOT fabricate a name, an email address, a personalization hook,
or **any statement about the prospect**. This holds identically whether the
copy is assembled from a locked template or written by the model.

**Names.** A real first name is used in a draft only at `high` confidence as
defined in PRODUCT.md §7 (name from `/about`/`/team`, explicit owner text, or
unambiguous email pattern). At `medium` confidence the greeting stays
"[Company] team", the candidate goes to `name_candidate`, and
`needs_review: true` is set. At `none`, "[Company] team" with no candidate.
When in doubt, score down.

**Claims.** Every sentence asserting anything about the prospect — their city,
tenure, services, size, reputation, channels, or history — MUST cite the
identifier of an `Evidence` record captured during research, and the cited
evidence MUST actually support the claim. Statements about the offered product,
the offer itself, and the sender are product facts and cite the offer source
instead. Copy MUST be emitted in a structured, per-claim-citable form; free
text with no citation structure is not acceptable output.

**Enforcement.** Citations MUST be validated deterministically in plain Python
— every cited id resolves to a real recorded Evidence record; every
claim-bearing unit carries a citation. Validation MUST NOT be delegated to a
model. A draft that fails validation is REJECTED and MUST fall back to the
locked deterministic template; it is never sent, never silently emptied, and
never repaired by another model call. Fallbacks MUST be recorded on the note
and counted in the run summary, so a broken drafting path is visible rather
than merely quiet *(amended 2026-07-20, v5.0.0)*.

*Rationale: one fabricated detail destroys trust in every draft in the batch,
and empty-and-flagged always beats wrong. Until v5.0.0 this was guaranteed
structurally — the model could not write prose, so it could not invent. Once
the model writes prose, only per-claim citation restores that guarantee: the
model gains freedom of phrasing, never freedom of fact.*

### V. Channel Honesty — Claims About the Prospect Require Observed Signals

Every claim in outreach copy **about the prospect's own channels** MUST be
backed by an open-web signal observed and recorded during research
(`fb_signal` per PRODUCT.md §7.5), and MUST cite that signal's evidence record
per Principle IV. Ad-running is NEVER claimed or implied — it is not observable
from outside Facebook and the tool never looks inside; ad-claim vocabulary is
rejected by the validator at every signal level. Describing the **product's own
capability** (Omniveer's Duct Lead Qualifier answers a Facebook page inbox) is
a fact about the product, not the prospect, and is permitted at every signal
level *(amended 2026-07-14, v2.0.0; product renamed from "Nestaro" 2026-07-17,
v4.0.1)*.

What `fb_signal` gates is what may be *asserted about them*: at `strong`, their
page activity may be referenced with a citation; at `weak` or `none`, Facebook
may appear only as product capability, with no assertion about their usage.
Enforcement moved from mechanical template-variant selection to per-claim
evidence citation *(amended 2026-07-20, v5.0.0)*; the rule being enforced is
unchanged. When the signal is uncertain, default DOWN, never up.

*Rationale: honesty means not asserting things about the prospect we haven't
observed; it does not forbid saying what the product we're offering does.
Variant selection was only ever the mechanism — citation enforces the same
rule with finer resolution, per sentence rather than per template.*

### VI. Smallest Viable Build — No Gold-Plating

Scope is bounded by PRODUCT.md; features not specified there MUST NOT be built.
Explicitly **excluded**: CRM features, web UI, agent/orchestration frameworks
(LangChain, LlamaIndex, and equivalents), and autonomous tool-using or
multi-step agent loops. Explicitly **in scope**: a guarded, approval-gated
email sender (Gmail API or authenticated SMTP) per Principle I, and
rich-instruction drafting per the next paragraph.

**LLM usage** is one OpenRouter call per company via direct HTTP. The call MAY
carry substantial instruction context assembled from versioned markdown files
(role/identity, offer, constraints, and writing skills) plus that company's
recorded research, and MAY request structured output. It MUST NOT become a
conversation, a retry-until-valid loop, a planner/critic chain, or a
tool-calling session: the drafting model has **no tools, no network access, and
no filesystem access**, and receives only already-extracted `Evidence` records
— never raw fetched HTML. Exactly one drafting call per company per run; on
failure or validation rejection the deterministic template answers instead
*(amended 2026-07-20, v5.0.0)*.

External services are called via direct HTTP/SDK calls. Prefer the smallest
viable diff; do not refactor unrelated code; add persistence (SQLite) only if a
demonstrated need arises.

*Rationale: the product's value is the research pipeline and honest drafts;
everything else is drag. Better instructions are cheap and reviewable in git;
agent machinery is neither, and a tool-using drafting loop would additionally
open a path around the Principle II fetch choke point.*

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
  for single-call LLM drafting; SQLite only if needed.
- **Secrets**: API keys live in `.env` (gitignored), never hardcoded, never
  committed, never logged.
- **Input**: CSV or markdown table with minimum `company`, `email`; blank /
  `messenger` / a Facebook URL in the email field routes to the messenger bucket.
- **Fallback templates are locked** (PRODUCT.md §8): on the deterministic
  fallback path the LLM fills bracketed slots only, and template prose is not
  paraphrased or restyled by the model. This path MUST remain functional and
  independently tested — it is the honesty floor the agent path falls back to.
- **Drafting instruction files**: the identity, offer, constraint, and skill
  markdown files that steer the drafting call are **content, not code**. They
  live in the repository under version control, are reviewed like prose, and
  MUST NOT contain secrets, credentials, live URLs to be fetched, or
  instructions that would weaken Principles I–V. They cannot grant the model
  capabilities the code does not give it.
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

**Version**: 5.0.0 | **Ratified**: 2026-07-13 | **Last Amended**: 2026-07-20
