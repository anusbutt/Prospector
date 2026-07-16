# Tasks: Approved Send

**Input**: Design documents from `/specs/003-approved-send/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Tests**: INCLUDED — required by Constitution Principle VII and the repo's offline (respx) test
convention; safety-critical modules (ledger, cap math) are written tests-first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5 (user-story phases only)
- All paths are repo-relative; single-project layout (`prospector/`, `tests/`).

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Add `google-auth>=2.0` and `google-auth-oauthlib>=1.0` to `dependencies` in `pyproject.toml`; run `pip install -e .` and confirm both import. Acceptance: `python -c "import google_auth_oauthlib, google.oauth2.credentials"` exits 0.
- [X] T002 Add `send_ledger.jsonl` and `secrets/gmail_token.json` to `.gitignore` (secrets/ already covered; add the root ledger explicitly). Acceptance: `git check-ignore send_ledger.jsonl` prints the path.
- [X] T003 [P] Add new send variables to `.env.example` with comments: `PROSPECTOR_SEND_FROM`, `PROSPECTOR_SEND_CAPS=15,30,60,100`, `PROSPECTOR_SEND_DELAY=30,90`, `PROSPECTOR_LEDGER`, `PROSPECTOR_GMAIL_CLIENT`, `PROSPECTOR_GMAIL_TOKEN`. Acceptance: file lists all six keys.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: shared building blocks every story depends on. MUST complete before Phase 3+.

- [X] T004 Extend `Settings` in `prospector/config.py` with `send_from`, `send_caps` (parsed `list[int]`), `send_delay` (parsed `(min,max)`), `ledger_path`, `gmail_client_secret_path`, `gmail_token_path`, reading the envs from T003 with the data-model defaults. Acceptance: `load_settings()` returns them; bad `PROSPECTOR_SEND_CAPS` raises `ConfigError`.
- [X] T005 [P] Add dataclasses to `prospector/models.py`: `SendCandidate`, `LedgerRecord`, `SendResult` (with an `outcome` enum/str), `RunReport`. Acceptance: importable; `RunReport` aggregates counts per outcome.
- [X] T006 [P] Write `tests/test_ledger.py` (tests-first): append is append-only, `read_all` skips a partial last line, `daily_count` counts only today's `sent` rows, `already_sent` matches by recipient OR slug, `first_send_date` returns min sent date (None when empty). Acceptance: tests exist and FAIL (no module yet).
- [X] T007 Implement `prospector/ledger.py` (`append`, `read_all`, `daily_count`, `already_sent`, `first_send_date`) per `contracts/ledger.schema.md`. Acceptance: `pytest tests/test_ledger.py` green.
- [X] T008 Add `## Draft` parsing helper to `prospector/vault.py`: given a note's text, return `(subject, body)` from the `## Draft` section (subject from the first `**Subject:**` line), or `None` if either missing. Acceptance: unit-covered in T009.
- [X] T009 Add scoped `set_status(path, new_status, log_line)` to `prospector/vault.py`: rewrite ONLY the frontmatter `status:` and append a `## Log` bullet, preserving all other frontmatter and human sections verbatim. Acceptance: `tests/test_vault_send.py` proves status flips and `## Log`/other sections are byte-identical except the intended changes.

---

## Phase 3: User Story 1 — Send the approved queue with one command (Priority: P1) 🎯 MVP

**Goal**: `prospector send --send` delivers approved email-channel notes, flips them to `sent`, and records the ledger.
**Independent test**: 2 approved notes → both sent (mocked), both `status: sent` + ledger rows; a `to-send` note and a messenger note are untouched/skipped.

- [X] T010 [P] [US1] Write `tests/test_gmail.py`: `send_message` builds RFC822 (subject/body/recipient present, base64url decodes correctly) and POSTs via respx-mocked httpx returning a message id; `account_email` reads the userinfo endpoint. Acceptance: tests fail pre-impl.
- [X] T011 [US1] Implement `prospector/gmail.py` `send_message(creds, from, to, subject, body) -> message_id` (httpx POST to Gmail send endpoint) and `account_email(creds) -> str` per `contracts/gmail-send.md`. Acceptance: `pytest tests/test_gmail.py` green.
- [X] T012 [P] [US1] Write `tests/test_send.py` selection cases: collect only `status==approved`; skip messenger and invalid/missing-email as `skipped_not_sendable`; skip non-approved. Acceptance: fails pre-impl.
- [X] T013 [US1] Implement candidate collection in `prospector/send.py`: scan vault, parse frontmatter + `## Draft`, build `SendCandidate`s, classify sendable vs skipped (email-only, valid email, subject+body). Acceptance: selection tests from T012 green.
- [X] T014 [US1] Implement the real-send loop in `prospector/send.py`: for each selected candidate send via `gmail.send_message`, on success append ledger `result:sent` THEN `vault.set_status(approved→sent)` with a dated `## Log` line. Acceptance: `tests/test_send.py` shows 2 approved → 2 ledger sent rows + 2 status flips.
- [X] T015 [US1] Add the `send` command to `prospector/cli.py` wiring settings → pipeline, with `--send`, `--limit`, `--vault`, `--yes`; print a `RunReport` summary. Acceptance: `tests/test_cli_send.py` invokes `--send` against a temp vault (gmail mocked) and sees notes sent.

**Checkpoint**: MVP — approved notes can be sent end-to-end (still needs the dry-run default guard from US2 to be safe by default).

---

## Phase 4: User Story 2 — Safe by default: preview before anything leaves (Priority: P1)

**Goal**: with no `--send`, nothing is sent/written; a preview lists intended sends + count.
**Independent test**: run with no flag over approved notes → zero emails, zero status changes, zero ledger writes, preview shown; `--send` performs them.

- [X] T016 [P] [US2] Write `tests/test_cli_send.py` dry-run cases: default run performs no gmail call, no ledger write, no status change, and prints the would-send list/count; `--send` flips to real. Acceptance: fails pre-impl.
- [X] T017 [US2] Add `dry_run` handling in `prospector/send.py`: when dry-run, run selection + cap computation but SKIP the send/ledger/status steps; produce a preview `RunReport` (would-send + deferred). Wire `cli.py` so absence of `--send` ⇒ dry-run (default). Acceptance: T016 green; SC-002 holds (zero side effects without `--send`).

**Checkpoint**: safe by default — the tool previews unless explicitly told to send.

---

## Phase 5: User Story 3 — Never exceed the ramped daily cap (Priority: P1)

**Goal**: enforce today's cap (from the ramp, anchored on first ledger send) against the ledger; defer the excess; pace real sends.
**Independent test**: cap=2 with 5 approved → exactly 2 sent, 3 remain approved, report "2 sent, 3 deferred"; cap reached → nothing sent.

- [X] T018 [P] [US3] Write `tests/test_cap.py`: `CapSchedule.cap_for` picks the right weekly step from `first_send_date`; `remaining = cap - daily_count`; empty ledger ⇒ week 0 cap; date-boundary correctness. Acceptance: fails pre-impl.
- [X] T019 [US3] Implement `CapSchedule` (+ `remaining`) in `prospector/send.py` using `ledger.first_send_date` and `ledger.daily_count`. Acceptance: `pytest tests/test_cap.py` green.
- [X] T020 [US3] Enforce the cap in the pipeline: order sendable candidates oldest-approved-first, take `min(remaining, --limit)`, mark the rest `deferred_cap`; never send when remaining is 0. Acceptance: `test_send.py` cap case (2 of 5) passes; repeated same-day runs never exceed the cap (SC-003).
- [X] T021 [P] [US3] Implement pacing in `prospector/send.py`: between real sends sleep a random delay in `send_delay` via an injectable `sleep` (no delay in dry-run or after the last send). Acceptance: `test_send.py` asserts `sleep` called n-1 times for n real sends and never in dry-run.

**Checkpoint**: volume is safely bounded and paced.

---

## Phase 6: User Story 4 — Connect the Nestaro account once (Priority: P2)

**Goal**: one-time OAuth consent stored + reused; refuse any account other than `send_from`.
**Independent test**: no token → consent (injected in tests) then send; stored token reused without re-consent; a non-Nestaro token → refuse (exit 2), nothing sent.

- [X] T022 [P] [US4] Write `tests/test_gmail_auth.py`: `load_or_authorize` loads+refreshes an existing token file (injected fake creds), and persists after (simulated) consent; identity check rejects a non-`send_from` account. Acceptance: fails pre-impl.
- [X] T023 [US4] Implement `load_or_authorize(client_secret_path, token_path, scopes)` in `prospector/gmail.py` (InstalledAppFlow one-time consent + token persist/refresh), never logging token material. Acceptance: `pytest tests/test_gmail_auth.py` green.
- [X] T024 [US4] Add the identity guard to the pipeline in `prospector/send.py`: resolve `account_email(creds)` once per real run; if it != `settings.send_from` (case-insensitive), abort with exit code 2 and send nothing. Acceptance: non-Nestaro token test refuses; `send.py` calls consent on first real run only. (SC-007)

**Checkpoint**: sending is bound to the Nestaro account, set up once.

---

## Phase 7: User Story 5 — Failures never lose a note or double-send (Priority: P2)

**Goal**: a send failure leaves the note `approved` + logs the error + continues; already-sent notes are never re-sent.
**Independent test**: 2nd of 3 fails → 1 & 3 sent, 2 stays approved with a logged error, run reports "2 sent, 1 failed"; a note/recipient already `sent` in the ledger is skipped.

- [X] T025 [P] [US5] Write `tests/test_send_failures.py`: a mid-batch send raises → that note stays `approved`, a ledger `result:failed` row is written, the loop continues; a candidate whose recipient OR slug is already `sent` in the ledger is `skipped_already_sent`; duplicate recipients within one run collapse to one send. Acceptance: fails pre-impl.
- [X] T026 [US5] Implement failure isolation in `prospector/send.py`: wrap each send in try/except → on error append ledger `failed`, leave status `approved`, continue; never mark a failed note `sent`. Acceptance: failure test green (SC-006).
- [X] T027 [US5] Implement double-send prevention in `prospector/send.py`: before sending, drop candidates present in `ledger.already_sent()` (recipient or slug) and collapse duplicate recipients within the run. Acceptance: already-sent + duplicate-inbox tests green (SC-004).

**Checkpoint**: safe to run repeatedly; resumable after interruption.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T028 [P] Reconcile docs: add `PRODUCT.md` §11 (the send stage) resolving the forward reference from the constitution amendment, and update the README guarantee wording from "sending is manual" to the guarded-send model. Acceptance: no doc claims "no email sender"; §11 exists.
- [X] T029 [P] Run the full suite (`pytest`) and confirm all prior 260 tests plus the new send tests are green. Acceptance: `pytest` exits 0 with the new files included.
- [X] T030 Live smoke: with the real Nestaro token, mark ONE test note (to a personal test inbox) `approved`, run `prospector send` (dry-run) to preview, then `prospector send --send`; confirm the email arrives, the note flips to `sent`, and one ledger row is written. Acceptance: observed delivery + ledger row (Principle VII live check).
- [X] T031 [P] Update `PROGRESS.md` CURRENT STATE + Session Log with the 003 build outcome (only when the human asks per the file's rule).

---

## Dependencies & Execution Order

- **Setup (T001–T003)** → **Foundational (T004–T009)** block everything.
- **US1 (T010–T015)** is the MVP; depends on Foundational.
- **US2 (T016–T017)** depends on US1's pipeline (adds the dry-run default guard).
- **US3 (T018–T021)** depends on Foundational (ledger) + US1 pipeline.
- **US4 (T022–T024)** depends on `gmail.py` (T011) + pipeline (T014).
- **US5 (T025–T027)** depends on the send loop (T014) + ledger (T007).
- **Polish (T028–T031)** last; T030 requires US1–US5 complete.

## Parallel Opportunities

- Setup: T003 ∥ (T001, T002).
- Foundational: T005 ∥ T006 (different files); T007 after T006.
- Test-authoring tasks marked [P] (T010, T012, T016, T018, T022, T025) can be written in parallel with each other before their implementations.
- Polish: T028 ∥ T029 ∥ T031.

## Implementation Strategy

- **MVP = Phase 1 + 2 + US1**, immediately followed by **US2** so the default is safe before any real use.
- Then US3 (cap/pacing), US4 (auth/identity), US5 (resilience) as independent hardening slices.
- Safety-critical modules (ledger T006→T007, cap T018→T019) are written tests-first.
- Live smoke (T030) is the final acceptance, per Principle VII.

## Task Summary

- **Total**: 31 tasks (T001–T031)
- **Setup**: 3 · **Foundational**: 6 · **US1**: 6 · **US2**: 2 · **US3**: 4 · **US4**: 3 · **US5**: 3 · **Polish**: 4
- **Tests**: 7 test files (ledger, gmail, send, cli_send, cap, gmail_auth, send_failures) + vault-send
- **MVP scope**: T001–T017 (Setup + Foundational + US1 + US2 = can safely send the approved queue)
