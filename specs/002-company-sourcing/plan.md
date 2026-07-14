# Implementation Plan: Company Sourcing (`prospector source`)

**Branch**: `002-company-sourcing` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-company-sourcing/spec.md`

## Summary

Add a `prospector source` subcommand that builds the input list feature 001 assumes:
Google Places Text Search (New) for a service keyword (default `duct cleaning`) across
a bundled ~30-US-metro list → dedupe by place id + website domain → polite homepage
fetch (existing `Fetcher`, FB-host block in force) → Meta Pixel detection by string
inspection (`ad_signal: pixel|none`) → public contact-email capture → CSV in the
feature-001 input format plus an `ad_signal` column, filtered to pixel rows by default.
Everything is deterministic Python — no LLM anywhere in sourcing. Purpose: find first
users for the Lead Qualifier agent among businesses already paying for Meta ads.

## Technical Context

**Language/Version**: Python 3.11+ (unchanged from 001)
**Primary Dependencies**: existing only — Typer (new `source` command on the existing
app), httpx (Places calls + homepage fetches through the existing `Fetcher`),
selectolax (mailto/contact-link extraction), python-dotenv (config). **No new
dependencies.** No trafilatura needed (raw HTML string inspection, not text extraction).
**External services**: Google Places API (New) Text Search — **required** for `source`
(pre-flight error if absent; no fallback, per FR-003). No OpenRouter, no Hunter, no
DuckDuckGo involvement in sourcing.
**Storage**: Filesystem only — output is a plain CSV (not a merged store; the vault
downstream remains the idempotent datastore). Bundled metro list as package data
(`prospector/data/us_metros.txt`, same mechanism as `first_names.txt`).
**Testing**: pytest + respx (existing dev deps); unit tests on pure logic (pixel
detection, email extraction, dedupe, budget math); transport-stubbed Places + homepage
fixtures; transport-level proof that no Facebook host is contacted (same standard as
001). Live acceptance: small real sweep (2–3 metros).
**Target Platform**: Local CLI, Linux/WSL2 and macOS (unchanged)
**Project Type**: Single project — extends the existing `prospector` package
**Performance Goals**: default 30-metro sweep completes unattended well under 30 min
(SC-001); serial polite fetches per host as in 001
**Constraints**: Constitution v1.1.0 I–VII + Sourcing constraint (Places-only
discovery; pixel read from candidate's own page source; `ad_signal` never in copy);
query budget default keeps a full sweep inside the Places free tier (FR-011)
**Scale/Scope**: ~30 metros × ~20 results/metro → ≤ ~600 candidates/run pre-dedupe;
single user; US/English market

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Design compliance | Status |
|---|-----------|-------------------|--------|
| I | No email sender | `source` writes a CSV; no send path added anywhere | ✅ |
| II | Open web only, FB never accessed | All fetches go through the existing `Fetcher` choke point with its FB-host hard block; Places is called via httpx to `places.googleapis.com` only; pixel detection is substring inspection of already-fetched HTML — URLs found in pages (incl. `facebook.com/tr`) are never fetched | ✅ |
| III | Obsidian is the interface | No UI added; sourcing output is an input artifact (CSV) for the existing pipeline, and the vault remains the only interface | ✅ |
| IV | Name honesty | Sourcing extracts no names and never invents emails — only publicly listed ones are captured (FR-008); name work stays in 001's pipeline | ✅ |
| V | Channel honesty | `ad_signal` is written to the CSV only; `run` ignores it as an unknown column, so it cannot reach template selection or copy (FR-013); `fb_signal` rules untouched | ✅ |
| VI | Smallest viable build | One new module + one CLI command + one data file; zero new dependencies; reuses `Fetcher`, `Settings`, and the Places endpoint already used in `resolve.py` | ✅ |
| VII | Verified claims only | Every task will carry a run/test acceptance check; final acceptance is a live 2–3-metro sweep fed into `prospector run --no-llm` | ✅ |
| — | Sourcing constraint (v1.1.0) | Places-only discovery (no directory scraping, no lead DBs); pixel via string inspection; `ad_signal` filter-only | ✅ |

**Post-Phase-1 re-check**: design artifacts introduce no violations — the CSV contract
carries `ad_signal` as data-only; the Places client uses a field mask limited to
id/name/address/website; the pixel detector takes a string and returns an enum, with
no network capability at all. ✅ PASS

## Project Structure

### Documentation (this feature)

```text
specs/002-company-sourcing/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli.md           # `prospector source` command contract
│   └── csv-format.md    # output CSV + metro-list file contracts
└── tasks.md             # Phase 2 output (/sp.tasks — NOT created by /sp.plan)
```

### Source Code (repository root)

```text
prospector/
├── cli.py               # MODIFIED: add `source` command (arguments/options per contracts/cli.md)
├── config.py            # MODIFIED: add `require_places()` pre-flight helper
├── source.py            # NEW: sourcing pipeline —
│                        #   PlacesSearcher (Text Search New, field-masked, budget-guarded)
│                        #   dedupe (place_id, then website domain)
│                        #   detect_pixel(html) -> "pixel" | "none"   (pure string inspection)
│                        #   extract_public_email(html) -> str | None (mailto > plaintext, deterministic)
│                        #   write_candidates_csv(...), SourcingSummary
├── data/
│   └── us_metros.txt    # NEW: bundled default ~30 US metros ("City, ST", one per line)
├── fetch.py             # REUSED unchanged (Fetcher: FB block, robots, spacing, retries)
└── (all other 001 modules untouched)

tests/  (local-only, gitignored — as in 001)
├── unit/       # pixel detector, email extractor, dedupe, budget, metro-list parsing
├── fixture/    # respx-stubbed Places responses + homepage HTML fixtures (with/without pixel)
└── contract/   # CLI exit codes, CSV column contract, FB-host never contacted (transport assert)
```

**Structure Decision**: extend the existing single-package layout with one new module
(`source.py`) and one data file. `resolve.py` is not reused directly (its Places call
resolves one known company; sourcing does keyword discovery) but the endpoint,
header, and field-mask pattern are copied from it. The Places client lives in
`source.py`, not a shared module, until a second consumer exists (Constitution VI).

## Complexity Tracking

No violations to justify — no new dependencies, no new storage, one new module.
