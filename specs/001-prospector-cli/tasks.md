# Tasks: Prospector — Outreach Research & Draft Vault

**Input**: Design documents from `/specs/001-prospector-cli/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, contracts/note-format.md

**Tests**: Included — the constitution (VII) requires every task to carry a concrete
run/test acceptance check, and the honesty rules (IV, V) are explicitly test-gated.

**Organization**: Phases 1–2 build shared infrastructure; Phases 3–8 map to spec.md
user stories US1–US6 in priority order. Execution is strictly top-down, one task at a
time; a task is checked off only after its acceptance check has actually been run.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: could run in parallel (different files, no dependency) — informational; we
  still execute top-down per the approved workflow
- **[Story]**: US1–US6 from spec.md
- **AC:** = acceptance check that must be run and observed before checking off

## Path Conventions

Single project at repo root: `prospector/` (package), `tests/` (pytest). Per plan.md.

---

## Phase 1: Setup

**Purpose**: Installable package skeleton + test harness

- [x] T001 Create project skeleton: `pyproject.toml` (name `prospector`, Python ≥3.11, deps: typer, httpx, selectolax, trafilatura, python-dotenv, pyyaml; dev extras: pytest, respx), package dir `prospector/` with `__init__.py` and empty stage modules per plan.md, `tests/{unit,integration,fixtures}/` dirs, `.env.example`, `.gitignore` (.env, .venv, `__pycache__`, Vault/)
      **AC:** `pip install -e ".[dev]"` succeeds and `python -c "import prospector"` exits 0
- [x] T002 Configure pytest in `pyproject.toml` ([tool.pytest.ini_options], testpaths) and add smoke test `tests/unit/test_smoke.py` asserting package imports and version
      **AC:** `pytest -q` runs and passes (1 test)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, data models, and the constitutionally-gated fetch layer every story uses

**⚠️ CRITICAL**: No user story work until this phase is complete

- [x] T003 [P] Implement `prospector/config.py`: load `.env` via python-dotenv; expose `Settings` (openrouter_key, openrouter_model default `anthropic/claude-sonnet-4.5`, places_key, hunter_key, vault_dir default `Vault/Outreach`); `require_llm()` raises a clear error when key missing (contracts/cli.md env table)
      **AC:** `pytest tests/unit/test_config.py -q` passes: env precedence, defaults, missing-key error message
- [x] T004 [P] Implement `prospector/models.py`: dataclasses/enums per data-model.md (Company, Evidence + EvidenceKind, ResearchResult, Prospect, Draft, RunSummary; Confidence, FbSignal, Channel, Variant enums)
      **AC:** `pytest tests/unit/test_models.py -q` passes: construction, enum values match §6/§7 vocab, RunSummary count reconciliation helper
- [x] T005 Implement `prospector/fetch.py`: single `fetch(url)` choke point using httpx — hard block raising `BlockedHostError` for facebook.com/fb.com/fb.me/fbcdn.net/messenger.com (+subdomains) **before any request**; timeouts (10s/15s), custom UA, ≤2 retries on 5xx/timeout, 1s per-host spacing, robots.txt check for non-homepage paths (research.md R2/R10)
      **AC:** `pytest tests/unit/test_fetch.py -q` passes with respx: FB-host block raises with zero transport calls recorded; retry/timeout behavior; politeness spacing unit-tested with a fake clock

**Checkpoint**: Foundation ready — Principle II enforcement now provable in one test

---

## Phase 3: User Story 1 — Batch list to paste-ready vault (P1) 🎯 MVP

**Goal**: `prospector run list.csv` produces one well-formed note per company + drafts.
MVP scope-limits: greeting is always "[Company] team" (names arrive in US2), email
drafts always use the channel-agnostic/none variant (fb variants arrive in US3),
messenger rows get notes with `needs_review: true` and no draft (DM template in US3),
notes are plain writes (merge semantics arrive in US5).

**Independent Test**: Run against a fixture CSV with stubbed network/LLM; every row
yields a schema-valid note with a complete draft; then a live smoke run on 2 real rows.

- [x] T006 [US1] Implement `prospector/ingest.py`: CSV + markdown-table parsing (case-insensitive headers, min `company,email`, optionals per contracts/cli.md), row normalization, malformed-row reporting by number, channel bucketing (valid email → email; blank/"messenger"/FB-URL → messenger; other → messenger + needs_review)
      **AC:** `pytest tests/unit/test_ingest.py -q` passes: both formats, header aliasing, bucketing matrix incl. odd-value flagging, malformed rows skipped-not-fatal
- [x] T007 [US1] Implement `prospector/vault.py` (write path): `slugify` + collision disambiguation (research.md R7), canonical note renderer (frontmatter key order, bare empty values, §6 body sections per contracts/note-format.md), write-if-bytes-differ, vault dir creation
      **AC:** `pytest tests/unit/test_vault.py -q` passes: canonical bytes stable across two renders of same data, slug collision/city suffix, unsafe-char sanitization, golden-file comparison to contracts/note-format.md example
- [x] T008 [US1] Implement `prospector/resolve.py`: website resolution when missing — Google Places text search when key set, DDG HTML fallback with domain-plausibility + homepage-name validation (research.md R1); records sources_consulted/failures
      **AC:** `pytest tests/unit/test_resolve.py -q` passes with respx fixtures: Places path, DDG path, no-match → failure recorded, never raises on network error
- [x] T009 [US1] Implement `prospector/extract.py` (research core): from fetched homepage + nav-discovered `/about|/team|/contact` (≤3 extra pages), extract via selectolax/trafilatura: city/service-area, one hook with Evidence, owner-name candidates with Evidence (regex owner-title patterns, about/team headings, footer names; reject company-name/city/service-word matches) (research.md R2/R3)
      **AC:** `pytest tests/unit/test_extract.py -q` passes against ≥4 recorded HTML fixtures in tests/fixtures/sites/: hook found, city found, name candidate with correct EvidenceKind, generic-word rejection
- [x] T010 [US1] Implement `prospector/draft.py` (agnostic variant only): §8 templates as string constants; OpenRouter single-shot httpx call (json_object response, temp 0.3, slot-JSON contract per research.md R5); deterministic assembly; base validator (no unfilled `[slot]`, template invariant lines intact, ad-claim vocabulary guard, signature intact); API failure → no draft + needs_review
      **AC:** `pytest tests/unit/test_draft.py -q` passes: assembly from canned slot JSON matches golden draft, validator catches unfilled slot / mutated template / "running ads" injection; respx-stubbed API failure path flags not raises
- [x] T011 [US1] Implement `prospector/pipeline.py` + `prospector/cli.py`: Typer app `run` command with `--vault/--limit/--only/--no-llm/--verbose`, pre-flight checks (exit 1) per contracts/cli.md, per-company orchestration ingest→resolve→fetch→extract→draft→vault with per-company failure isolation (exit 0 + summary), RunSummary table on stdout
      **AC:** `pytest tests/unit/test_cli.py -q` passes (Typer runner: help text, exit codes, --no-llm skips draft); `prospector --help` and `prospector run --help` render
- [x] T012 [US1] Integration test `tests/integration/test_batch_run.py`: full `run` over `tests/fixtures/companies_small.csv` (5 rows: with-website, without-website, messenger, malformed, no-findable-hook) with respx-stubbed network + canned LLM responses — assert one note per valid row, schema-valid frontmatter, complete draft bodies, messenger row flagged, **zero requests to blocked hosts recorded by the mock transport**
      **AC:** `pytest tests/integration/test_batch_run.py -q` passes
- [x] T013 [US1] Live smoke run (Constitution VII gate): create `samples/live_smoke.csv` with 2 real duct-cleaning companies, run `prospector run samples/live_smoke.csv --limit 2 --vault /tmp/prospector-smoke` with real keys from `.env`, inspect generated notes by hand
      **AC:** command exits 0; both notes exist with real research content and drafts; paste run summary + one note (redact nothing — it's open-web data) into the task-completion report

**Checkpoint**: MVP — raw list in, reviewable vault out. STOP and validate before US2.

---

## Phase 4: User Story 2 — Honest name confidence gating (P1)

**Goal**: Real first names at high confidence only; medium → candidate + review flag;
never fabricated (§7, Principle IV).

**Independent Test**: Fixture emails/pages covering every §7 tier land exactly right;
validator proves no unsourced name can reach a draft.

- [x] T014 [P] [US2] Implement `prospector/enrich.py`: email local-part inference (`first.last@`, `firstlast@`, `firstb@`, `f.last@` against bundled top-1000 US first-names list in `prospector/data/first_names.txt`), ambiguity detection (`derickson@` → surname-likely = partial), optional Hunter.io lookup when key set (research.md R3)
      **AC:** `pytest tests/unit/test_enrich.py -q` passes: `scottb@` → Scott (unambiguous), `derickson@` → partial candidate, `info@` → nothing, Hunter stubbed via respx and skipped when key absent
- [x] T015 [US2] Implement name scoring in `prospector/score.py`: §7 rules mapping Evidence kinds → Confidence (owner_text/about_page/team_page/input/unambiguous email_pattern → high; partial/footer-only → medium; none → none); outputs name_used ("team" unless high), name_candidate (medium only), needs_review; input `owner_name` column honored as high
      **AC:** `pytest tests/unit/test_score.py -q` passes: full tier matrix from spec US2 acceptance scenarios incl. scottb@→high greet Scott, derickson@→medium team+candidate+review, nothing→none
- [x] T016 [US2] Wire names into drafting: pipeline passes gated `name_or_team` to draft slots; extend draft validator to reject any capitalized token in greeting position not present in the evidence set (unsourced-name guard); frontmatter fields name_used/name_confidence/name_candidate populated per data-model.md
      **AC:** `pytest tests/unit/test_draft.py tests/integration/test_batch_run.py -q` passes with new cases: high-confidence fixture greets by name, medium fixture stays "team" with candidate in frontmatter, injected LLM response containing a fabricated name is rejected → needs_review

**Checkpoint**: Names now provably honest — greeting can only come from recorded evidence

---

## Phase 5: User Story 3 — Channel-honest template selection (P1)

**Goal**: fb_signal from open-web evidence only; variant selection mechanical; FB never
mentioned without signal; ad-running never claimed; Facebook never contacted (§7.5,
Principles II & V).

**Independent Test**: Strong/weak/none fixtures produce correct variants; transport
mock proves zero FB requests; validator blocks FB mentions at signal none.

- [x] T017 [US3] Implement fb-evidence detection in `prospector/extract.py`: FB link in nav/footer/social block, FB embed iframe src, Messenger/customerchat widget script (all string-detected from already-fetched HTML — never fetched/executed); DDG `"<company>" facebook` search-snippet activity cue in `prospector/resolve.py`; `facebook_url` input recorded as fb_url_input Evidence (research.md R4)
      **AC:** `pytest tests/unit/test_extract.py -q` passes new fixtures: widget site, embed site, bare-footer-link site, no-FB site; respx transport log shows zero facebook host requests in all cases
- [x] T018 [US3] Implement fb_signal classification + variant selection in `prospector/score.py`: §7.5 rules (strong = ≥2 signals incl. one active-usage cue; weak = exactly one soft; none = zero; uncertain → down), Variant mapping (messenger bucket → messenger_dm; strong → email_fb; else email_agnostic)
      **AC:** `pytest tests/unit/test_score.py -q` passes: signal matrix from spec US3 scenarios, default-down tie cases, variant table
- [x] T019 [US3] Complete `prospector/draft.py` variants: Facebook email variant, weak-clause insertion/removal in agnostic variant (`fb_signal none` → no "Facebook" substring), Messenger DM template for messenger bucket (incl. optional city clause, info@ forward line for generic inboxes); extend validator: `none` → assert no "facebook" (case-insensitive) in body; all variants keep ad-claim guard
      **AC:** `pytest tests/unit/test_draft.py tests/integration/test_batch_run.py -q` passes: golden drafts for all three variants, none-variant FB-mention injection rejected, messenger fixture row now gets a DM draft (US1's placeholder behavior replaced)

**Checkpoint**: All three P1 stories done — honest, channel-aware drafts end to end

---

## Phase 6: User Story 4 — Dedupe and channel bucketing (P2)

**Goal**: One send per unique inbox; shared-domain detection; duplicates flagged, not
dropped.

**Independent Test**: Fixture list with same-email pair, same-custom-domain pair, and
same-gmail pair → first two grouped, gmail pair untouched.

- [x] T020 [US4] Implement dedupe in `prospector/ingest.py`: groups by exact email then by non-free-provider domain (bundled free-provider list in `prospector/data/free_providers.txt`); first-in-input is primary; duplicates get `duplicate_of: <primary-slug>`, needs_review, research note "shares inbox with <primary>" (research.md R8); `duplicate_of` added to frontmatter rendering (contracts/note-format.md)
      **AC:** `pytest tests/unit/test_ingest.py -q` passes: same-email group, same-custom-domain group, gmail NOT grouped, primary selection by row order
- [x] T021 [US4] Integration coverage `tests/integration/test_batch_run.py`: extend fixture CSV with a shared-inbox pair — assert exactly one note without `duplicate_of` per inbox and duplicate note carries flag + reference
      **AC:** `pytest tests/integration -q` passes; run summary shows duplicates count

**Checkpoint**: SC-003 satisfied on fixtures

---

## Phase 7: User Story 5 — Safe re-runs that respect human edits (P2)

**Goal**: Byte-idempotent re-runs; human `status` and `## Log` (and unknown sections)
survive; machine fields refresh.

**Independent Test**: Run → hand-edit → re-run → edits intact; run twice unchanged →
zero byte diff.

- [x] T022 [US5] Implement note parsing + section-ownership merge in `prospector/vault.py`: parse existing note into frontmatter + `## `-sections; merge per contracts/note-format.md ownership table (status written once then never touched; `## Log` and unrecognized sections verbatim; machine fields recomputed); write only when canonical bytes differ (research.md R6)
      **AC:** `pytest tests/unit/test_vault.py -q` passes: status=sent preserved, `## Log` verbatim (incl. weird whitespace), custom `## My notes` section preserved in position, newly-found name updates frontmatter+draft, unchanged data → identical bytes
- [x] T023 [US5] Integration test `tests/integration/test_rerun.py`: full batch → capture vault bytes → re-run same input → assert zero file changes; then simulate human edits (status change + Log entry) → re-run → assert edits intact while a newly-available name (changed fixture) updates its note
      **AC:** `pytest tests/integration/test_rerun.py -q` passes

**Checkpoint**: SC-006 satisfied — vault is safe to live in

---

## Phase 8: User Story 6 — Review queue via dashboard (P3)

**Goal**: `_Dashboard.md` with live Dataview queues + plain-markdown fallback.

**Independent Test**: Generated dashboard contains the four query blocks filtering the
documented frontmatter fields; renders as plain markdown without Dataview.

- [x] T024 [US6] Implement dashboard generation in `prospector/vault.py` + `prospector dashboard` CLI command: four Dataview blocks (to-send excl. duplicates, needs-review incl. medium-confidence with name_candidate column, messenger bucket, pipeline by status) per contracts/note-format.md; regenerate at end of every `run`; static content → byte-idempotent
      **AC:** `pytest tests/unit/test_dashboard.py -q` passes (query blocks reference correct fields/values, idempotent bytes); `prospector dashboard --vault /tmp/prospector-smoke` exits 0 and the file previews correctly as plain markdown

**Checkpoint**: All six user stories complete

---

## Phase 9: Polish & Final Verification

**Purpose**: Docs, success-criteria audit, real-world acceptance

- [x] T025 [P] Write `README.md` (what it is, constitution guarantees, setup from quickstart.md, Dataview note) and finalize `.env.example` with all four vars commented
      **AC:** follow README setup steps verbatim in a fresh venv: `pip install -e ".[dev]" && pytest -q` green
- [x] T026 Success-criteria audit against spec.md SC-001…SC-007 on the fixture batch: run full suite + a scripted check (`tests/integration/test_success_criteria.py`) asserting SC-002/003/004/005/006 mechanically; record SC-001/007 from the live run
      **AC:** `pytest -q` fully green; audit table (SC → evidence) pasted into completion report
- [x] T027 Final live acceptance run (Constitution VII): `prospector run` on a real ~10-company list into a real Obsidian vault; open in Obsidian, verify dashboard queues, review drafts for honesty (names sourced, FB mentions signal-backed, no ad claims)
      **AC:** run summary + observed queue counts reported; any honesty violation found = blocking bug, not a note

---

## Dependencies & Execution Order

- **Phase 1 → 2 → 3** strictly sequential; Phase 3 (US1) is the MVP gate.
- **Phases 4–8** each depend only on Phase 3 + earlier phases; executed in priority
  order US2 → US3 → US4 → US5 → US6 per the approved top-down workflow.
- **Phase 9** last.
- Within phases, [P]-marked tasks are independent files but are still executed
  one-at-a-time per the workflow contract (run/test each, check off, then next).

### Story dependency notes

- US2 and US3 both extend score.py/draft.py — US3 builds on US2's wiring (sequenced,
  not parallel).
- US4 touches only ingest/vault frontmatter; US5 only vault; US6 only vault/cli —
  independent of each other.

## Implementation Strategy

MVP-first: T001–T013 delivers a usable tool (team-greeting, agnostic drafts). Each
later phase is an independently testable increment with a checkpoint pause for the
human per the approved workflow. Total: **27 tasks** (Setup 2, Foundational 3, US1 8,
US2 3, US3 3, US4 2, US5 2, US6 1, Polish 3).
