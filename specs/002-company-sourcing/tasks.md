# Tasks: Company Sourcing (`prospector source`)

**Input**: Design documents from `/specs/002-company-sourcing/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — Constitution VII requires a concrete acceptance check per task, and
feature 001's offline-suite standard (network stubbed at the httpx-transport level via
respx; tests live in the local-only, gitignored `tests/` tree) carries over.

**Organization**: Grouped by user story so each story is an independently testable
increment. Every task ends with an **Accept:** line — the command/observation that must
actually run before the box is checked.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (discovery), US2 (pixel filter), US3 (email capture)

## Phase 1: Setup

**Purpose**: ship the one new data asset everything else reads

- [X] T001 Add bundled metro list `prospector/data/us_metros.txt` — the 30 metros from research.md R5, `City, ST` one per line, `#` comments allowed; confirm the existing `data/*.txt` package-data glob in `pyproject.toml` picks it up.
  **Accept**: `python -c "from importlib.resources import files; ls=[l for l in files('prospector').joinpath('data/us_metros.txt').read_text().splitlines() if l.strip() and not l.lstrip().startswith('#')]; print(len(ls))"` prints `30` from an installed venv.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: config pre-flight, module skeleton, CLI surface — nothing story-specific works without these

- [X] T002 Add `require_places()` to `prospector/config.py` (mirrors `require_llm()`: raises `ConfigError` naming `GOOGLE_PLACES_API_KEY` when absent) with unit test in `tests/unit/test_config.py`.
  **Accept**: `pytest tests/unit/test_config.py -k places` green.
- [X] T003 Create `prospector/source.py` skeleton: `Candidate` and `SourcingSummary` dataclasses per data-model.md, `load_metros(path: Path | None) -> list[str]` (bundled default; blank/comment handling; empty/malformed → `ConfigError`) with unit tests in `tests/unit/test_source_metros.py` (bundled=30, custom file, comments, empty file errors, missing file errors).
  **Accept**: `pytest tests/unit/test_source_metros.py` green.
- [X] T004 Add `source` command to `prospector/cli.py` per contracts/cli.md (`--keyword`, `--metros`, `--out`, `--all`, `--max-queries`, `--limit`, `--verbose`) calling a `source.run_sourcing(...)` stub; pre-flight order: settings → `require_places()` → metro list → `--out` writability; exit 1 on any pre-flight failure with nothing written. CLI tests in `tests/unit/test_source_cli.py` (help text, missing key → exit 1 + message, bad metros file → exit 1, nothing written).
  **Accept**: `pytest tests/unit/test_source_cli.py` green and `prospector source --help` shows all options.

**Checkpoint**: `prospector source` exists, validates, and fails politely — but discovers nothing yet.

---

## Phase 3: User Story 1 — Nationwide candidate discovery (P1) 🎯 MVP

**Goal**: one command → deduplicated CSV of real companies (name/city/website) across metros.

**Independent Test**: stubbed-transport end-to-end run of `prospector source --all` produces a correct CSV and consistent summary; live smoke on 2 metros.

- [X] T005 [US1] Implement `PlacesSearcher` in `prospector/source.py`: POST `places:searchText` per metro (field mask `places.id,places.displayName,places.formattedAddress,places.websiteUri`, `maxResultCount: 20`, no pagination), query-budget guard (stop issuing at `--max-queries`, record metros covered), per-metro failure isolation. respx tests in `tests/integration/test_places_search.py` (parses results; budget stops cleanly mid-sweep; HTTP 403/429 on one metro doesn't kill the rest).
  **Accept**: `pytest tests/integration/test_places_search.py` green.
- [X] T006 [P] [US1] Candidate parsing in `prospector/source.py`: Places JSON → `Candidate` (city from `formattedAddress` with metro fallback; website normalized — fetch URL kept, dedupe/CSV domain lowercased + `www.` stripped; empty company dropped and counted). Unit tests in `tests/unit/test_source_candidates.py`.
  **Accept**: `pytest tests/unit/test_source_candidates.py` green.
- [X] T007 [P] [US1] Dedupe in `prospector/source.py`: pass 1 by `place_id`, pass 2 by domain; first-seen (metro-list order) wins; website-less candidates dedupe by id only; collapsed count recorded. Unit tests in `tests/unit/test_source_dedupe.py` (same id two metros; two listings sharing a domain; no-website rows; count correctness).
  **Accept**: `pytest tests/unit/test_source_dedupe.py` green.
- [X] T008 [US1] CSV writer + summary in `prospector/source.py`: header exactly `company,email,website,city,ad_signal` (contracts/csv-format.md), deterministic row order, header-only file on zero rows; `SourcingSummary` printed as a stdout table in 001's style. Contract tests in `tests/unit/test_source_csv.py`.
  **Accept**: `pytest tests/unit/test_source_csv.py` green.
- [X] T009 [US1] Wire `run_sourcing()` end-to-end (search → parse → dedupe → write, `ad_signal` hardcoded `none` until US2, so this phase is exercised with `--all`) and add the story's end-to-end fixture test in `tests/integration/test_source_e2e.py`: 3 stubbed metros with an overlapping listing → CSV rows + every summary count consistent; exit code 0 with an injected per-metro failure.
  **Accept**: `pytest tests/integration/test_source_e2e.py` green — US1 checkpoint reached.

**Checkpoint**: `prospector source --all` works end-to-end against stubbed transport — an unfiltered but real discovery MVP.

---

## Phase 4: User Story 2 — Meta-ads targeting filter (P2)

**Goal**: classify `ad_signal` from each candidate's own homepage and filter output to pixel-positive by default.

**Independent Test**: fixture pages with/without pixel markup classify correctly; transport-level assertion proves zero Facebook-host requests; default vs `--all` output differs correctly.

- [X] T010 [P] [US2] `detect_pixel(html: str) -> Literal["pixel","none"]` in `prospector/source.py` — case-insensitive substring checks for `connect.facebook.net`, `fbq(`, `facebook.com/tr` (research.md R3); pure function, no imports from fetch. Unit tests in `tests/unit/test_detect_pixel.py`: each marker alone, all together, casing variants, pixel-free page with ordinary Facebook profile links → `none`, prose mentioning "facebook" → `none`.
  **Accept**: `pytest tests/unit/test_detect_pixel.py` green.
- [X] T011 [US2] Homepage fetch integration in `run_sourcing()`: fetch each unique candidate's website via the existing `Fetcher` (timeouts, ≤2 retries, per-host spacing; robots per 001's subpage convention), classify `ad_signal`; unreachable/robots-blocked/website-less → `none` + failure recorded, batch continues. Fixture tests in `tests/integration/test_source_pixel_fetch.py`, including the transport-level guarantee test (a candidate page stuffed with Facebook URLs → respx records **zero** requests to any blocked host).
  **Accept**: `pytest tests/integration/test_source_pixel_fetch.py` green, including the FB-host zero-request assertion.
- [X] T012 [US2] Default pixel-only filter + `--all` behavior + zero-hit reporting ("0 rows written; --all would have kept N") in `prospector/source.py`/`cli.py`; extend `tests/integration/test_source_e2e.py` with mixed pixel/no-pixel fixtures asserting default vs `--all` row sets and the zero-hit header-only case.
  **Accept**: `pytest tests/integration/test_source_e2e.py` green — US2 checkpoint reached.

- [X] T018 [US2] *(added 2026-07-14 after live validation — see research.md R3 amendment)* GTM container inspection in `prospector/source.py`: extract up to 2 `GTM-…` container ids from pages referencing `googletagmanager.com`; fetch each container's public JS (`https://www.googletagmanager.com/gtm.js?id=<id>`) via the existing `Fetcher`; classify `ad_signal: pixel` when the same three markers appear in the container JS; container-fetch failure → `none` + candidate failure note. Unit tests for id extraction in `tests/unit/test_detect_pixel.py`; integration tests in `tests/integration/test_source_pixel_fetch.py` (GTM-mediated install → pixel; GTM without Meta tags → none; container fetch failure → none; FB-host zero-request assertion still holds).
  **Accept**: `pytest tests/unit/test_detect_pixel.py tests/integration/test_source_pixel_fetch.py` green.

**Checkpoint**: default output is the targeted list the feature exists for.

---

## Phase 5: User Story 3 — Contact email capture (P3)

**Goal**: publicly listed emails captured so downstream `run` routes to the email channel.

**Independent Test**: fixture pages with mailto / plaintext / no email extract correctly; homepage-miss + contact-page-hit works via one nav hop.

- [X] T013 [P] [US3] `extract_public_email(html: str) -> str | None` in `prospector/source.py`: first `mailto:` in document order (strip `?subject=` etc.) else first conservative plaintext regex match; lowercased; asset-suffix rejection (`.png`/`.jpg`/`.webp`/`.svg`); never constructed (research.md R4). Unit tests in `tests/unit/test_extract_email.py` (mailto wins over earlier plaintext? — no: document order among mailtos, mailto tier beats plaintext tier; multiple emails → deterministic pick; obfuscated/none → blank; asset false-positive rejected).
  **Accept**: `pytest tests/unit/test_extract_email.py` green.
- [X] T014 [US3] Contact-page hop in `run_sourcing()`: when the homepage yields no email, follow at most one same-host nav link whose path contains `contact` (via selectolax, robots-respected through `Fetcher`) and retry extraction; fixture tests in `tests/integration/test_source_email_hop.py` (homepage-no-email → contact-page email found; no contact link → blank; cross-host contact link ignored). Update `tests/integration/test_source_e2e.py` summary assertions (`emails_found`).
  **Accept**: `pytest tests/integration/test_source_email_hop.py` and `tests/integration/test_source_e2e.py` green — US3 checkpoint reached.

**Checkpoint**: full sourcing pipeline complete against stubbed transport.

---

## Phase 6: Polish & Cross-Cutting

- [X] T015 [P] Downstream-compatibility contract test in `tests/integration/test_source_feeds_run.py`: a sourced CSV (with `ad_signal` column and one blank-email row) ingested by 001's `ingest` → `ad_signal` produces only the standard unknown-column warning; blank-email row lands in the messenger bucket; no 001 code changes needed.
  **Accept**: `pytest tests/integration/test_source_feeds_run.py` green.
- [X] T016 [P] Docs: README gains a "Sourcing" section (command, options, honesty note that `ad_signal` never affects drafts) and moves `GOOGLE_PLACES_API_KEY` to "required for `source`" in the Configuration table; `.env.example` comment updated to match; quickstart.md commands verified verbatim.
  **Accept**: README + `.env.example` diffs reviewed; every command in `specs/002-company-sourcing/quickstart.md` matches the implemented CLI (`--help` cross-check).
- [X] T017 Full offline suite + live acceptance: run the entire test suite, then a real 2-metro sweep (`prospector source --limit 2 --all --out /tmp/claude-smoke.csv --verbose`) with the real key — verify summary counts, spot-check one pixel-positive candidate's site actually contains a pixel marker, confirm queries-used ≤ budget — then feed 3 rows into `prospector run --no-llm` and confirm notes render. Record results in PROGRESS.md only when the human asks.
  **Accept**: full `pytest` green; live sweep artifacts observed and consistent (SC-001..SC-006 spot-checked); `prospector run --no-llm` consumes the file unmodified.

---

## Dependencies

```text
T001 (Setup)
  └─► T002, T003, T004 (Foundational; T002/T003 parallel, T004 needs T003)
        └─► US1: T005 ─► T006[P], T007[P] ─► T008 ─► T009  🎯 MVP
              └─► US2: T010[P] (anytime after T003), T011 (needs T009), T012 (needs T010+T011)
                    └─► US3: T013[P] (anytime after T003), T014 (needs T011's fetch step)
                          └─► Polish: T015[P], T016[P], T017 (last)
```

- US1 is fully independent once Foundational is done (MVP = T001–T009).
- US2's pure detector (T010) and US3's pure extractor (T013) are parallelizable early;
  their integration tasks (T011, T014) hang off the US1 pipeline — T014 additionally
  reuses the homepage fetch introduced in T011, which is why US3 is sequenced after US2.
- Polish tasks T015/T016 are parallel; T017 is the final gate.

## Implementation Strategy

MVP first: stop and demo after T009 (`prospector source --all` on stubbed transport +
optional tiny live smoke) before building the filter. Then US2 delivers the actual
targeting value, US3 the channel routing, and T017 is the only task that touches the
real network end-to-end. One task at a time, top-down; check a box only after its
**Accept** line has actually run (Constitution VII).
