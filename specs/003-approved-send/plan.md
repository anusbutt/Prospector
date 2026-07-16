# Implementation Plan: Approved Send

**Branch**: `003-approved-send` | **Date**: 2026-07-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-approved-send/spec.md`

## Summary

Add a guarded `prospector send` command that delivers only human-approved vault notes
(`status: approved`) as plain emails from the dedicated Nestaro account, via the Gmail API.
It defaults to dry-run, enforces a ramped daily cap against an append-only ledger, paces
real sends with a randomized delay, flips each delivered note to `sent`, and never sends
from the personal account, off-channel, unapproved, or past the cap.

**Technical approach**: a new `prospector/send.py` module holds the send pipeline; a new
`prospector/gmail.py` handles one-time OAuth (via `google-auth-oauthlib`) and message send
(via `httpx` POST to the Gmail REST endpoint, so the path is mockable with the existing
`respx` test infra). A new `prospector/ledger.py` reads/writes an append-only JSONL ledger
(the source of truth for the daily count and double-send prevention). Cap schedule and
pacing are env-configured via the existing `Settings` pattern. A scoped `set_status` writer
in `vault.py` performs the single machine-owned `approved → sent` transition without
clobbering human-owned `## Log` / other sections.

## Technical Context

**Language/Version**: Python 3.11+ (unchanged)
**Primary Dependencies**: Typer (CLI), httpx (Gmail REST send — reuses existing dep),
`google-auth` + `google-auth-oauthlib` (NEW — one-time OAuth consent + token refresh),
PyYAML (existing), python-dotenv (existing)
**Storage**: Filesystem only — Obsidian vault notes (existing) + one append-only JSONL send
ledger (new) + a gitignored OAuth token file (new). No database.
**Testing**: pytest + respx (existing) — Gmail send + profile calls mocked at the httpx
transport level, exactly like the existing network/LLM stubs; OAuth flow injected via a fake
credentials object so no real browser/consent is needed in tests.
**Target Platform**: Local CLI on the operator's machine (Linux/WSL/macOS/Windows)
**Project Type**: single project (CLI package `prospector/`)
**Performance Goals**: Not throughput-bound — real sends are deliberately paced ~30–90s
apart; a full-cap (100) run is expected to take up to ~2.5h and runs in the foreground,
resumable via the ledger.
**Constraints**: Dry-run default; never send from a non-Nestaro account; never exceed the
daily cap; append-only ledger; no secrets logged or committed.
**Scale/Scope**: ~15–100 sends/day; vault of ~120+ notes; single operator, single account.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Human-Approved Sending Only (v3.0.0)** — ✅ Core of this feature. Design enforces
  every sub-rule: sends only `status: approved`; Gmail API only, from
  `nestaroassistant@gmail.com` (identity verified via the profile endpoint, refuses any
  other account incl. personal); ramped daily cap enforced against the ledger; dry-run
  default with an explicit `--send` flag for real sends; append-only ledger; never
  auto-approves; never off-channel; never past the cap.
- **II. Open Web Only — Facebook Never Accessed** — ✅ N/A; no Facebook access. Gmail only.
- **III. Obsidian Is the Interface (No Web UI)** — ✅ No UI. The operator approves by editing
  frontmatter in Obsidian. The send command's only vault write is the scoped, idempotent
  `approved → sent` status flip + a `## Log` line; human sections are preserved.
- **IV. Name Honesty** — ✅ N/A; this feature does not touch names or copy.
- **V. Channel Honesty** — ✅ N/A; message content is sent verbatim from the existing
  `## Draft`; no claims are generated or altered.
- **VI. Smallest Viable Build** — ✅ Two new deps (`google-auth`, `google-auth-oauthlib`) for
  OAuth only; the send itself reuses `httpx`. No agent framework, no web UI, no CRM, no ESP.
  Ledger is a flat JSONL file (SQLite not needed). Justified in Complexity Tracking.
- **VII. Verified Claims Only** — ✅ Each task carries an acceptance check; send/ledger/cap
  logic is unit- and integration-tested offline (respx); a live 1-recipient smoke send is
  the final acceptance.

**Result**: PASS (no unjustified violations). New dependencies noted in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/003-approved-send/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── send-command.md      # CLI contract for `prospector send`
│   ├── ledger.schema.md     # Ledger record schema + invariants
│   └── gmail-send.md        # Internal Gmail auth/send interface contract
└── tasks.md             # Phase 2 output (/sp.tasks — not created here)
```

### Source Code (repository root)

```text
prospector/
├── cli.py            # MODIFY: add `send` command (dry-run default, --send/--limit flags)
├── config.py         # MODIFY: Settings gains send_from, send_caps, send_delay, ledger/token paths
├── gmail.py          # NEW: one-time OAuth (google-auth-oauthlib) + token refresh + httpx send + profile identity check
├── ledger.py         # NEW: append-only JSONL read/write; daily count; already-sent lookup
├── send.py           # NEW: send pipeline — select approved, dedupe inbox, cap/pace, send, flip status, ledger
├── vault.py          # MODIFY: add scoped set_status(approved→sent) + parse of ## Draft subject/body
└── models.py         # MODIFY (if needed): lightweight SendCandidate / SendResult / RunReport dataclasses

secrets/
├── gmail_client_secret.json   # EXISTING (gitignored) — OAuth client
└── gmail_token.json           # NEW (gitignored) — stored refresh token after first consent

send_ledger.jsonl              # NEW (gitignored) — append-only ledger (default path; configurable)

tests/
├── test_ledger.py    # NEW: append/read, daily count, already-sent, day-boundary
├── test_send.py      # NEW: selection, dry-run, cap, pacing, failure isolation, status flip
├── test_gmail.py     # NEW: send via respx, profile identity check, non-Nestaro refusal
└── test_cli_send.py  # NEW: command wiring, dry-run default, --send gating
```

**Structure Decision**: Single-project CLI (Option 1). New feature = 3 new modules
(`gmail`, `ledger`, `send`) + targeted edits to `cli`, `config`, `vault`, mirroring the
existing per-concern module layout (fetch/extract/score/draft/vault). Tests follow the
existing offline-with-respx convention.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New deps: `google-auth`, `google-auth-oauthlib` | Gmail uses OAuth2; the one-time consent + secure token refresh must not be hand-rolled (security-critical, easy to get wrong). | Raw manual OAuth over httpx rejected: reimplements token refresh/signing and risks credential mistakes for zero benefit. Send itself still uses httpx (no google-api-python-client) to stay minimal and respx-testable. |
| New JSONL ledger file | FR-007/010: durable, append-only source of truth for daily count + double-send prevention that survives crashes and vault edits. | Deriving "already sent" from vault `status` alone rejected: statuses are human-editable and a reset would re-send; the spec explicitly makes the ledger authoritative. SQLite rejected as heavier than needed for append-only rows (Principle VI). |
