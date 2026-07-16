# Phase 1 Data Model: Approved Send

Filesystem-only. No database. Entities are in-memory dataclasses plus two on-disk artifacts
(vault note frontmatter — existing; JSONL ledger — new).

## Note status lifecycle (extended)

Existing statuses: `to-send | sent | replied | pilot | dead`. This feature inserts **`approved`**.

```
draft/to-send ──(human edits frontmatter)──▶ approved ──(prospector send --send)──▶ sent
                                                │
                                                └─(send fails)──▶ stays approved (error logged)
```

- Only a **human** sets `approved` (FR-012). The tool never writes `approved`.
- Only `prospector send --send` performs `approved → sent`, and only after a ledger row is
  committed (FR-008). This is the single machine-owned status transition, sanctioned by
  Constitution v3.0.0 Principle I. All other statuses remain human-owned.
- `vault.merge_notes` continues to treat `status` as human-owned during `prospector run`
  (re-drafting never changes an existing status); the send command uses a **separate scoped
  writer** (`set_status`) so the two flows do not conflict.

## Entity: SendCandidate (in-memory)

A parsed, sendable view of one approved note.

| Field | Type | Source / Rule |
|-------|------|---------------|
| slug | str | note filename slug (note identity) |
| company | str | frontmatter `company` |
| recipient | str | frontmatter `email`; must be a syntactically valid email (else not sendable) |
| channel | str | frontmatter `channel`; must be `email` (messenger → skipped, FR-005) |
| subject | str | first `**Subject:**` line under `## Draft` (required, FR-013) |
| body | str | remainder of `## Draft` after the subject line (required, non-empty, FR-013) |
| note_path | Path | absolute path for the status write |
| approved_at | datetime \| None | note mtime or a frontmatter timestamp, used for oldest-first ordering |

**Validation → "not sendable" (skipped + reported, never guessed)**:
- missing/blank/invalid `email`, or `channel != email`, or missing subject/body.

## Entity: LedgerRecord (on-disk, JSONL — one per line, append-only)

| Field | Type | Notes |
|-------|------|-------|
| ts | str (ISO-8601, local) | send timestamp; date portion drives the daily count |
| slug | str | note identity (for slug-based already-sent match) |
| recipient | str | lowercased email (for inbox-based already-sent + duplicate collapse) |
| company | str | convenience/audit |
| message_id | str \| null | Gmail message id on success; null on failure |
| result | str | `sent` \| `failed` |
| error | str \| null | reason when `result == failed` |
| from_account | str | the verified sending address (audit) |

**Invariants**:
- Append-only; existing lines are never modified or deleted.
- Daily count = number of lines with `result == "sent"` whose `ts` date == today (local).
- "Already sent" = any line with `result == "sent"` where `recipient` (normalized) or `slug`
  matches the candidate (FR-010) → skip.
- First-send date (ramp anchor) = min `ts` date across lines with `result == "sent"`
  (empty ledger ⇒ today ⇒ week 0).

## Entity: CapSchedule (in-memory, from config)

| Field | Type | Default | Source |
|-------|------|---------|--------|
| weekly_caps | list[int] | `[15, 30, 60, 100]` | env `PROSPECTOR_SEND_CAPS` |

- `cap_for(today, first_send_date)`: `wk = (today - first_send_date).days // 7`; return
  `weekly_caps[min(wk, len-1)]`.
- `remaining(today, ledger)`: `max(0, cap_for(...) - daily_count(today))`.

## Entity: PacingConfig (in-memory, from config)

| Field | Type | Default | Source |
|-------|------|---------|--------|
| min_seconds | int | 30 | env `PROSPECTOR_SEND_DELAY` (first value) |
| max_seconds | int | 90 | env `PROSPECTOR_SEND_DELAY` (second value) |

- `next_delay()` → uniform random int in `[min, max]`. Applied only for real sends, only
  between sends (not after the last).

## Entity: SendResult / RunReport (in-memory)

- **SendResult**: `{slug, recipient, outcome}` where outcome ∈
  `sent | deferred_cap | skipped_not_approved | skipped_not_sendable | skipped_already_sent | failed`.
- **RunReport**: aggregated counts per outcome + the affected slugs, printed at run end (FR-016).

## Settings additions (config.py)

| Setting | Env | Default |
|---------|-----|---------|
| send_from | `PROSPECTOR_SEND_FROM` | `nestaroassistant@gmail.com` |
| send_caps | `PROSPECTOR_SEND_CAPS` | `15,30,60,100` |
| send_delay | `PROSPECTOR_SEND_DELAY` | `30,90` |
| ledger_path | `PROSPECTOR_LEDGER` | `send_ledger.jsonl` |
| gmail_client_secret_path | `PROSPECTOR_GMAIL_CLIENT` | `secrets/gmail_client_secret.json` |
| gmail_token_path | `PROSPECTOR_GMAIL_TOKEN` | `secrets/gmail_token.json` |

No credentials/tokens are ever logged (FR-018).
