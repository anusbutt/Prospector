# Tasks: Assisted-Manual Messenger Send

**Feature**: 007-assisted-messenger | **Branch**: `007-assisted-messenger`
**Input**: plan.md, spec.md, data-model.md, contracts/, research.md, quickstart.md
**Constitution**: v6.0.0 (assisted-manual Messenger path sanctioned)

Tests are included: this repo enforces Principle VII (Verified Claims Only) and
the two hardest guarantees (zero Facebook HTTP; preview-inert) must be verified,
not asserted. Each user story is an independently testable increment.

Legend: `[P]` = parallelizable (different files, no incomplete deps).
Story labels map to spec.md user stories US1–US5.

---

## Phase 1: Setup

- [x] T001 Confirm baseline is green: run `pytest -q` from repo root and record the pass count (Principle VII sanity check before edits).
- [x] T002 Add `dm_ledger.jsonl` to `.gitignore` and document `PROSPECTOR_DM_LEDGER` in `.env.example`.

---

## Phase 2: Foundational (blocking prerequisites for all stories)

- [x] T003 [P] Add `DmOutcome` enum (`DELIVERED`, `SKIPPED_NOT_SENDABLE`, `SKIPPED_ALREADY_SENT`, `DECLINED`, `WOULD_DELIVER`) to `prospector/models.py` per data-model.md.
- [x] T004 [P] Add `DmCandidate` dataclass (`slug`, `company`, `facebook_url`, `body`, `note_path`, `approved_at`) with `sendable_error()` (body-missing → reason; missing facebook_url is NOT an error) to `prospector/models.py`.
- [x] T005 [P] Add `DmResult` and `DmRunReport` (with `delivered`/`would_deliver`/`skipped`/`declined` count properties, mirroring `RunReport`) to `prospector/models.py`.
- [x] T006 [P] Add `dm_ledger_path: Path` to `Settings` (default `dm_ledger.jsonl`) and load `PROSPECTOR_DM_LEDGER` in `load_settings()` in `prospector/config.py`.
- [x] T007 [P] Create `prospector/clipboard.py`: `copy_to_clipboard(text) -> bool` shelling to `clip.exe`/`pbcopy`/`xclip`/`xsel`/`wl-copy` (first available), returning False (never raising) when none work (research.md R1).
- [x] T008 Add `parse_messenger_body(text) -> str | None` to `prospector/vault.py` (returns the `## Draft` section body for subject-less messenger drafts; None if empty) — used by candidate collection.

**Checkpoint**: models/config/clipboard/body-parser exist; nothing wired yet.

---

## Phase 3: User Story 1 — Guided delivery of one approved note (P1) 🎯 MVP

**Goal**: `prospector dm --send` walks one approved messenger note: copy → open →
confirm → ledger → status flip.
**Independent test**: one approved messenger note with a `facebook_url` and body;
run real mode, confirm `y`; assert clipboard+browser called, ledger row written,
status now `sent`, no Facebook HTTP.

- [x] T009 [P] [US1] Write `tests/test_dm_run.py`: approved messenger note + injected clipboard/browser/confirm stubs → confirm `y` appends one DM ledger row and flips status `approved → sent` with a `## Log` bullet; decline `n` records DECLINED and leaves status `approved`. (Expected RED.)
- [x] T010 [P] [US1] Write `tests/test_dm_no_facebook_http.py`: run `run_dm` real mode with a respx/httpx mock asserting ZERO requests to any facebook host; assert `webbrowser.open` received the note's facebook_url. (Expected RED.)
- [x] T011 [US1] Implement `collect_dm_candidates(vault_dir)` in `prospector/dm.py`: select `status==approved` AND `channel==messenger`, read body via `vault.parse_messenger_body`, read `facebook_url` from frontmatter, return `(candidates, skipped_not_sendable)` (mirrors `send.collect_candidates`).
- [x] T012 [US1] Implement `run_dm(settings, *, vault_dir, dry_run=True, limit=None, confirm=..., opener=webbrowser.open, copier=clipboard.copy_to_clipboard, today=...)` in `prospector/dm.py`: for each candidate in real mode copy→open→confirm; on `y` append `LedgerRecord(result="dm_sent_manual", message_id=None, ...)` via `ledger.append(settings.dm_ledger_path, ...)` THEN `vault.set_status(path, "sent", log)`; build `DmRunReport`. Injectable `confirm`/`opener`/`copier` for tests.
- [x] T013 [US1] Add the `dm` command to `prospector/cli.py` (mirrors `send`): `--send/--limit/--vault/--yes`; preflight vault-exists (exit 1); real mode wires real `confirm` (typer `[y/N/q]`), `webbrowser.open`, `clipboard.copy_to_clipboard`; calls `run_dm`; prints report via a `_print_dm_report` helper.
- [x] T014 [US1] Run `pytest tests/test_dm_run.py tests/test_dm_no_facebook_http.py -q` → GREEN. Then live-verify on a scratch vault copy (one approved messenger note) that `prospector dm --send` opens the browser and flips status.

**Checkpoint**: MVP works end to end — a single approved note can be delivered.

---

## Phase 4: User Story 2 — Safe preview before touching anything (P1)

**Goal**: `prospector dm` (no flag) lists eligible notes and changes nothing.
**Independent test**: mixed vault; run preview; assert zero browser/clipboard/
ledger/status effects and correct counts with per-note skip reasons.

- [x] T015 [P] [US2] Write `tests/test_cli_dm.py`: preview run opens no browser (opener stub asserts not called), writes no clipboard, appends nothing to the DM ledger, mutates no note; report shows `would_deliver` + skip reasons. Also assert `--limit`, `--vault`, `--yes` are accepted. (Expected RED for preview-inert specifics.)
- [x] T016 [US2] Ensure `run_dm` `dry_run=True` path (default) records `WOULD_DELIVER`/skip results only and performs NO copy/open/ledger/status; wire `_print_dm_report` preview header per contracts/dm-command.md.
- [x] T017 [US2] Run `pytest tests/test_cli_dm.py -q` → GREEN; live-verify `prospector dm` on the scratch vault opens nothing and leaves `dm_ledger.jsonl` and note statuses unchanged.

---

## Phase 5: User Story 3 — Never deliver the same prospect twice (P1)

**Goal**: DM-ledgered slugs and in-run duplicate targets are skipped.
**Independent test**: ledger a slug, reset note to approved, run again → reported
already-delivered, no browser opens.

- [x] T018 [P] [US3] Write `tests/test_dm_ledger.py`: a slug present in `dm_ledger.jsonl` is skipped as `SKIPPED_ALREADY_SENT`; two approved notes with the same facebook_url in one run → second is an in-run duplicate; DM ledger record shape matches contracts/dm-ledger.schema.md. (Expected RED.)
- [x] T019 [US3] Implement dedupe in `run_dm`: use `ledger.already_sent(settings.dm_ledger_path)` slug set to drop ledgered candidates; track a `seen_targets` set within the run for duplicate facebook_url; record `SKIPPED_ALREADY_SENT` with detail.
- [x] T020 [US3] Run `pytest tests/test_dm_ledger.py -q` → GREEN; live-verify re-running `prospector dm --send` after a confirmed delivery skips that note.

---

## Phase 6: User Story 4 — Machine-readable facebook_url on notes (P2)

**Goal**: every messenger note carries a `facebook_url` header field, populated
from input or discovered signal, appended diff-stably.
**Independent test**: re-run research on a messenger company with an fb signal →
note header has `facebook_url`; a pre-existing note shows no field reordering.

- [x] T021 [P] [US4] Write `tests/test_vault_facebook_url.py`: `build_note` for a messenger company emits `facebook_url` (from `company.facebook_url`, else first facebook.com URL in `fb_evidence`, else empty); the key is appended after `outcome`; an existing-note refresh reorders no prior keys. (Expected RED.)
- [x] T022 [US4] Append `"facebook_url"` to `FRONTMATTER_KEYS` (after `outcome`, before `tags`) and add it to the `values` dict in `vault.build_note` in `prospector/vault.py`.
- [x] T023 [US4] Resolve the target in `prospector/pipeline.py` (helper `_resolve_facebook_url(company, research)` per research.md R3: input → first `FB_SEARCH_ACTIVE`/`FB_LINK` facebook.com value → empty) and pass it into `build_note`.
- [x] T024 [US4] Run `pytest tests/test_vault_facebook_url.py -q` → GREEN; live-verify `prospector run` on a small fixture writes `facebook_url` and that re-running produces no key-reordering diff on an existing note.

---

## Phase 7: User Story 5 — Graceful handling with no Facebook link (P3)

**Goal**: approved messenger note with empty `facebook_url` is still presented;
no browser opens; operator can confirm or skip.
**Independent test**: approved note, empty facebook_url, real mode → draft copied,
"no link on file" notice, opener NOT called, confirm still offered.

- [x] T025 [P] [US5] Write a `tests/test_dm_run.py` case (or `test_dm_no_link.py`): candidate with `facebook_url=None` in real mode → copier called, opener NOT called, a "no link" detail present, confirm still prompted; `y` still ledgers + flips status. (Expected RED.)
- [x] T026 [US5] In `run_dm`, guard the open: only call `opener` when `facebook_url` is truthy; otherwise emit the "no Facebook link on file — locate the company manually" notice and continue to the confirm prompt.
- [x] T027 [US5] Run the no-link test → GREEN; live-verify with an approved messenger note whose `facebook_url` is empty.

---

## Phase 8: Polish & Cross-Cutting

- [x] T028 [P] Update `README.md`: revise the "Facebook is never contacted" guarantee wording to reflect the assisted-manual handoff (tool still never contacts Facebook; the operator's browser does), add a `prospector dm` usage subsection and Messenger review-workflow step.
- [x] T029 [P] Reconcile `PRODUCT.md` (Messenger delivery section) with the assisted-manual path and the `facebook_url` field, per the constitution v6.0.0 sync-report ⚠ flags.
- [x] T030 Run the full suite `pytest -q` → all green (new + existing); confirm `run`/`send` behavior is unchanged (no regressions in `send_ledger.jsonl` accounting).
- [ ] T031 Suggest `/sp.adr assisted-manual-messenger-delivery` (facebook_url note-schema field + second ledger + new delivery channel) — human consent required; do not auto-create.

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)** → user stories.
- **US1 (Phase 3)** is the MVP and depends only on Foundational. It reads
  `facebook_url` from frontmatter, so it can be tested with a manually-set field
  before US4 populates it automatically.
- **US2, US3** extend `run_dm`/CLI from US1 (same files → mostly sequential after
  US1; their *test* files T015/T018 are `[P]`).
- **US4 (Phase 6)** is independent of US1–US3 (touches `vault.py`/`pipeline.py`)
  and can proceed in parallel with the DM loop work.
- **US5 (Phase 7)** depends on US1's `run_dm`.
- **Polish (Phase 8)** last.

## Parallel opportunities

- Foundational: T003, T004, T005, T006, T007 are all `[P]` (distinct concerns;
  T004/T005 both in models.py → coordinate or do sequentially).
- Test-authoring tasks T009, T010, T015, T018, T021, T025 are `[P]` (distinct
  files) and can be written up front (TDD RED) before their implementations.
- US4 (T021–T024) can run in parallel with US1–US3 by a second track.

## MVP scope

**User Story 1 (Phase 3)** alone delivers a working `prospector dm --send` for a
single approved messenger note with a link — the core value. US2 (preview) and
US3 (dedupe) harden it to the safety bar of the email `send` path; ship all three
P1 stories together for parity.

## Format validation

All tasks use `- [ ] Txxx [P?] [USx?] description + file path`. Setup/Foundational/
Polish carry no story label; US phases carry US1–US5. Total: 31 tasks.
