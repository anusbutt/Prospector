# Implementation Plan: Prospector — Outreach Research & Draft Vault

**Branch**: `001-prospector-cli` | **Date**: 2026-07-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-prospector-cli/spec.md`

## Summary

Prospector is a Python CLI (`prospector run <list>`) that turns a raw company list into
an Obsidian vault of honest, personalized outreach drafts. Pipeline: ingest/dedupe →
resolve website → polite fetch of a fixed page set → extract name/hook/fb-signal →
deterministic confidence scoring → single-shot OpenRouter draft into locked templates →
idempotent vault write. All scoring and template selection is deterministic Python; the
LLM only fills bracketed slots. No sender, no Facebook access, no web UI (Constitution
I–III).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Typer (CLI), httpx (HTTP), selectolax (HTML parsing),
trafilatura (text extraction), python-dotenv (config), PyYAML (frontmatter);
Playwright as optional fallback for JS-rendered sites; OpenRouter chat-completions via
direct httpx calls (no SDK, no agent framework)
**External services**: OpenRouter (required), Google Places API (optional — degrades to
skip resolution), Hunter.io (optional), DuckDuckGo HTML search for site resolution
fallback and FB-activity signal (no API key needed)
**Storage**: Filesystem only — the Obsidian vault is the datastore (notes keyed by
slug). No SQLite unless a demonstrated need arises (Constitution VI).
**Testing**: pytest; unit tests on pure logic (scoring, dedupe, slugs, merge), fixture
tests with recorded HTML pages; live smoke run on a tiny real list as final acceptance
**Target Platform**: Local CLI, Linux/WSL2 and macOS
**Project Type**: Single project (CLI package + tests)
**Performance Goals**: 20-company batch completes unattended; per-company research
bounded (~≤30s worst case); polite serial fetches per host
**Constraints**: Constitution I–VII (no sender, no FB access, vault-only interface,
name/channel honesty, smallest viable build, verified claims); locked templates filled
slot-wise only; byte-idempotent re-runs; human-owned `status`/`## Log` never clobbered
**Scale/Scope**: Batches of tens (≤100) companies; single user; English/US market

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Design compliance | Status |
|---|-----------|-------------------|--------|
| I | No email sender | No SMTP/send dependency anywhere; CLI has no `send` command; drafts are text in notes | ✅ |
| II | Open web only, FB never accessed | Fetcher hard-blocks `facebook.com`/`fb.com`/`fb.me`/`messenger.com` hosts at the HTTP-client level (allowlist gate + test); `facebook_url` only feeds the fb_signal classifier as static input | ✅ |
| III | Obsidian is the interface | Output = vault dir of .md + `_Dashboard.md`; no server, no GUI deps; merge-not-overwrite writer with section ownership rules | ✅ |
| IV | Name honesty | Confidence scoring is deterministic Python (not LLM); LLM prompt receives the already-gated `name_or_team` value, so it cannot introduce a name; post-draft validator rejects drafts containing names absent from sources | ✅ |
| V | Channel honesty | `fb_signal` classified by deterministic rules over observed evidence list; template variant selected mechanically in code; validator asserts no FB mention when signal is `none` and no ad-running vocabulary ever | ✅ |
| VI | Smallest viable build | Direct httpx calls to OpenRouter; no LangChain/agents; no DB; Playwright optional and lazy; scope = PRODUCT.md pipeline only | ✅ |
| VII | Verified claims only | Every task in tasks.md carries a run/test acceptance check; final acceptance is a live smoke run | ✅ |

**Post-Phase-1 re-check**: design artifacts (data-model.md, contracts/) introduce no
violations — templates live as code constants filled slot-wise, vault writer merges by
section ownership, fetch layer has a single choke point for the FB host block. ✅ PASS

## Project Structure

### Documentation (this feature)

```text
specs/001-prospector-cli/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli.md           # CLI surface contract
│   └── note-format.md   # Vault note + dashboard contract
└── tasks.md             # Phase 2 output (/sp.tasks — NOT created by /sp.plan)
```

### Source Code (repository root)

```text
prospector/
├── __init__.py
├── cli.py               # Typer app: `run`, `dashboard` commands
├── config.py            # .env loading, key presence checks, defaults
├── models.py            # dataclasses: Company, Evidence, ResearchResult, Prospect, RunSummary
├── ingest.py            # CSV/markdown-table parsing, normalization, dedupe, bucketing
├── resolve.py           # website + Google Places resolution (optional key), DDG fallback
├── fetch.py             # polite httpx fetcher; FB-host hard block; Playwright fallback
├── extract.py           # selectolax/trafilatura: name candidates, city, hook, fb evidence
├── enrich.py            # email-pattern name inference; optional Hunter.io
├── score.py             # name confidence (§7) + fb_signal (§7.5) deterministic rules
├── draft.py             # locked templates (§8) as constants; slot fill; OpenRouter call; validator
├── vault.py             # slugging, frontmatter merge, section-ownership writer, dashboard
└── pipeline.py          # orchestration: per-company flow + run summary

tests/
├── unit/                # ingest, score, enrich, vault-merge, draft-validator, slug tests
├── fixtures/            # recorded HTML pages, sample CSVs, canned LLM outputs
└── integration/         # end-to-end batch on fixtures (network + LLM stubbed)
```

**Structure Decision**: Single flat package, one module per pipeline stage (mirrors
PRODUCT.md §4 flow). No src/ nesting, no services/models split — smallest structure
that keeps stages independently unit-testable (Constitution VI).

## Key Decisions

1. **Deterministic honesty core, LLM at the edge.** Confidence scoring, fb_signal
   classification, and template-variant selection are pure Python rules. The LLM gets
   only pre-gated slot values (`name_or_team`, `hook`, `city`, variant id) and returns
   slot fills; a validator then checks the assembled draft (all slots filled, no extra
   prose, no FB mention when disallowed, no unsourced names). This makes Principles IV/V
   testable in unit tests instead of hoping the model behaves. *(Alternative rejected:
   letting the LLM pick names/variants — unverifiable, violates honesty-by-construction.)*
2. **FB block at the HTTP choke point.** All outbound requests go through one
   `fetch.py` function that raises on blocked hosts (facebook.com, fb.com, fb.me,
   fbcdn, messenger.com). One place to enforce, one test to prove SC-005.
3. **Vault as the only store.** Idempotency = parse existing note → merge machine-owned
   fields → write only if content changed. Human-owned: `status` (once changed from
   `to-send`) and `## Log` body. Machine-owned: everything else. No SQLite: state that
   matters lives in frontmatter and is re-derivable.
4. **Search fallback without keys.** DuckDuckGo HTML endpoint (scrape-friendly, no key)
   resolves websites when missing and provides the "active FB page visible in search"
   signal *without touching Facebook* — only the search-result snippets are read.
   Google Places used when a key is configured (better city/service-area data).
5. **Templates as code constants.** §8 templates are string constants with named
   placeholders; template text is never sent through the LLM for rewriting. The LLM
   fills only `[hook]` phrasing and greeting-adjacent slot content; deterministic code
   assembles the final message.

## Complexity Tracking

> No constitutional violations — table intentionally empty.
