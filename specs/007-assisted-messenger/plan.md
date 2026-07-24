# Implementation Plan: Assisted-Manual Messenger Send

**Branch**: `007-assisted-messenger` | **Date**: 2026-07-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-assisted-messenger/spec.md`

## Summary

Add a `prospector dm` command that walks `approved` messenger-channel vault notes
one at a time: in real mode it copies the deterministic draft body to the OS
clipboard and opens the note's `facebook_url` in the operator's own browser, then
— after a per-note human confirmation — records a human-performed delivery in a
dedicated Messenger ledger (`dm_ledger.jsonl`, slug-deduped) and flips the note
`approved → sent`. Preview (dry-run) is the default and touches nothing. The tool
never sends a Messenger message, never automates a browser, and never issues an
HTTP request to Facebook — it only hands a URL to the operator's browser
(sanctioned by Constitution v6.0.0 Principle I "Assisted-manual Messenger
delivery" + Principle II clarification). A new `facebook_url` frontmatter field is
appended to note headers to give the command a machine-readable target.

The technical approach deliberately mirrors the existing email `send` path
(`send.py`) and reuses `ledger.py` and `vault.set_status`, so the new surface is
a small, well-understood remix rather than novel machinery.

## Technical Context

**Language/Version**: Python 3.11+ (unchanged)
**Primary Dependencies**: Typer (CLI), stdlib `webbrowser` (OS browser handoff),
stdlib `subprocess`/platform clipboard command (no new third-party dep — see
research.md R1). Existing: httpx, selectolax, trafilatura, pyyaml.
**Storage**: Filesystem only — the Obsidian vault (Markdown notes) plus a new
append-only JSONL ledger `dm_ledger.jsonl` (gitignored), sibling to
`send_ledger.jsonl`.
**Testing**: pytest (48 existing test files); new unit + integration tests with
injected clipboard/browser/confirm callables (no real browser, no network).
**Target Platform**: Local CLI (Linux/WSL/macOS/Windows); interactive terminal.
**Project Type**: single (existing `prospector/` package + `tests/`).
**Performance Goals**: N/A — human-paced, one note at a time.
**Constraints**: Zero outbound Facebook HTTP; preview mutates nothing; graceful
degradation when clipboard or browser is unavailable; existing `send`/`run`
behavior byte-unchanged.
**Scale/Scope**: One new module (`prospector/dm.py`), one CLI command, ~2 config
settings, small edits to `models.py`/`vault.py`/`pipeline.py`, docs reconcile.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against Constitution **v6.0.0** (amended 2026-07-24 to enable this
feature — see `history/prompts/constitution/0004-*`).

- **I. Human-Approved Sending Only — Assisted-manual Messenger delivery**: PASS.
  The command reads only `status: approved` messenger notes; preview is the
  default; real mode requires an explicit flag AND a per-note human confirmation;
  it prepares (clipboard + `webbrowser.open`) but never transmits and never
  automates a browser; it delivers the deterministic template verbatim (no LLM);
  it appends to a dedicated immutable Messenger ledger (slug-deduped, no
  automated message id); the only status write is `approved → sent`; never
  auto-approves. Directly satisfies the new sub-section's MUSTs.
- **II. Open Web Only — Facebook Is Never Accessed**: PASS. The tool issues no
  HTTP request to any Facebook host; `fetch.py`'s outbound host guard is
  untouched. `webbrowser.open(facebook_url)` hands the URL to the operator's own
  browser — explicitly clarified in v6.0.0 as *not* a tool fetch. `facebook_url`
  is stored as an input/target field only.
- **III. Obsidian Is the Interface (No Web UI)**: PASS. No UI/server; output is
  terminal + existing Markdown notes.
- **IV. Evidence-Bound Copy / V. Channel Honesty**: PASS (not exercised). No copy
  is generated or altered; the existing validated deterministic Messenger draft
  is delivered verbatim. No new claims are produced.
- **VI. Smallest Viable Build**: PASS. No agent framework, no autonomous loop, no
  new network client. Reuses `ledger.py`, `vault.set_status`, and the `send.py`
  structure. Clipboard/browser via stdlib; no new dependency.
- **VII. Verified Claims Only**: PASS (enforced by process). Every task carries a
  concrete acceptance check (pytest or observed CLI run); nothing marked done
  unless run.

**Result: PASS — no violations, Complexity Tracking not required.**

## Project Structure

### Documentation (this feature)

```text
specs/007-assisted-messenger/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── dm-command.md    # `prospector dm` CLI + walk-loop contract
│   └── dm-ledger.schema.md  # dm_ledger.jsonl record schema
├── checklists/
│   └── requirements.md  # (from /sp.specify)
└── tasks.md             # Phase 2 output (/sp.tasks — NOT created here)
```

### Source Code (repository root)

```text
prospector/
├── dm.py                # NEW: collect_dm_candidates(), run_dm() walk-loop, report
├── cli.py               # EDIT: add `dm` command (mirrors `send`)
├── config.py            # EDIT: dm_ledger_path setting (+ PROSPECTOR_DM_LEDGER)
├── models.py            # EDIT: DmCandidate dataclass; DmOutcome enum; DmRunReport;
│                        #       DM LedgerRecord result value ("dm_sent_manual")
├── vault.py             # EDIT: append "facebook_url" to FRONTMATTER_KEYS + values;
│                        #       add parse_messenger_body()/facebook_url read helper
├── pipeline.py          # EDIT: resolve facebook_url (input + fb_evidence) into note
└── clipboard.py         # NEW (small): copy_to_clipboard() with graceful fallback

tests/
├── test_dm_candidates.py      # NEW: collection/filter/sendable/link-resolution
├── test_dm_run.py             # NEW: walk-loop, confirm/decline, ledger, status flip
├── test_dm_ledger.py          # NEW: dedupe + record shape
├── test_dm_no_facebook_http.py# NEW: assert zero Facebook network calls
├── test_vault_facebook_url.py # NEW: frontmatter field append + diff-stability
└── test_cli_dm.py             # NEW: preview default, --send, --limit, --vault, --yes

.gitignore               # EDIT: add dm_ledger.jsonl
.env.example             # EDIT: document PROSPECTOR_DM_LEDGER
README.md / PRODUCT.md   # EDIT: reconcile Messenger delivery + facebook_url field
```

**Structure Decision**: Single-project layout (existing). The new `dm.py` sits
beside `send.py` as a sibling delivery module; `clipboard.py` isolates the only
platform-specific concern so it is trivially injectable/testable. No new package
boundaries.

## Phase 0 — Research

See [research.md](./research.md). Key resolved decisions:

- **R1 Clipboard mechanism** → stdlib-only, no `pyperclip` dependency: shell out
  to the platform copier (`clip.exe` on WSL/Windows, `pbcopy` on macOS,
  `xclip`/`xsel`/`wl-copy` on Linux), injected as a callable; on failure, print
  the body for manual copy and continue (never abort).
- **R2 Browser open** → stdlib `webbrowser.open(url, new=2)`, injected; on
  failure, print the URL to open manually. This is the sanctioned OS handoff, not
  a tool fetch.
- **R3 Facebook-target resolution** → prefer `company.facebook_url` (input), else
  the first `fb_evidence` record whose value is a `facebook.com` page URL
  (`FB_SEARCH_ACTIVE`, `FB_LINK`); empty when none. Store on the note frontmatter.
- **R4 Ledger separation** → dedicated `dm_ledger.jsonl` reusing `ledger.py`
  primitives (`append`, `already_sent`) with `result="dm_sent_manual"`,
  `message_id=None`; keeps email cap accounting isolated.
- **R5 Confirmation & idempotency** → ledger row written only after human
  confirmation, then status flip; interrupt-safe and resumable.

## Phase 1 — Design & Contracts

- **[data-model.md](./data-model.md)**: `DmCandidate`, `DmOutcome`, `DmRunReport`,
  DM `LedgerRecord` usage, and the `facebook_url` note field.
- **[contracts/dm-command.md](./contracts/dm-command.md)**: CLI signature, flags,
  exit codes, preview vs real semantics, per-note interaction, report format.
- **[contracts/dm-ledger.schema.md](./contracts/dm-ledger.schema.md)**: JSONL
  record schema and dedupe key.
- **[quickstart.md](./quickstart.md)**: end-to-end operator walkthrough +
  verification steps.

### Reused existing code (do not reinvent)

- `prospector/ledger.py`: `append()`, `already_sent()`, `read_all()` — used
  as-is against the DM ledger path.
- `prospector/vault.py`: `parse_note()`, `set_status()` (the sole sanctioned
  `approved → sent` writer, preserves all other content).
- `prospector/send.py`: structural template for `collect_dm_candidates` /
  `run_dm` (candidate collection → dedupe → preview/real → report).
- `prospector/models.py`: `Channel`, `LedgerRecord`, `SendOutcome` patterns.

## Complexity Tracking

*No Constitution violations — section intentionally empty.*

## ADR candidate

Adding `facebook_url` to the note frontmatter schema, plus establishing a second
delivery ledger, is a cross-cutting, long-lived data decision. **📋 Architectural
decision detected: assisted-manual Messenger delivery channel + `facebook_url`
note-schema field + separate DM ledger.** Recommend documenting reasoning and
tradeoffs — run `/sp.adr assisted-manual-messenger-delivery` (human consent
required; not auto-created).
