# Phase 1 Data Model: Assisted-Manual Messenger Send

## New note frontmatter field: `facebook_url`

Appended to `FRONTMATTER_KEYS` in `vault.py` **after** `outcome` and before
`tags` — appended (not inserted) so notes created before this feature keep their
existing key order and the first re-run produces a content diff, not a full
reordering (FR-018, same migration discipline used for the 006 `draft_source`
addition).

| Field | Type | Source | Notes |
| --- | --- | --- | --- |
| `facebook_url` | string (may be empty) | R3 precedence: `company.facebook_url` → first `facebook.com` page URL in `research.fb_evidence` → empty | Input/target only; never fetched by the tool (Principle II). Present on all notes; primarily meaningful for `channel: messenger`. |

Written by `vault.build_note` from a value resolved in `pipeline.py`. On re-run,
treated as tool-owned (refreshed), consistent with other research-derived header
fields; human-owned fields (`status`, `outcome`, `## Log`, custom sections) are
untouched.

## `DmCandidate` (models.py)

A parsed, deliverable view of one `approved` messenger-channel note.

| Field | Type | Meaning |
| --- | --- | --- |
| `slug` | str | Note stem; the ledger dedupe key. |
| `company` | str | Display name (frontmatter `company` or slug). |
| `facebook_url` | str \| None | Target for `webbrowser.open`; None → "no link on file". |
| `body` | str \| None | Deterministic messenger draft body (no subject). |
| `note_path` | Path | For `vault.set_status`. |
| `approved_at` | float | Note mtime; oldest-approved-first ordering. |

**`sendable_error()` → str | None** (distinct from `SendCandidate`'s, which
requires an email + subject): returns a reason when the note is not deliverable,
else None.

- channel is not `messenger` → not collected at all (silently ignored, like
  non-approved notes in `send.collect_candidates`).
- `body` empty/missing → `"draft has no body"` → SKIPPED_NOT_SENDABLE (FR-010).
- A missing `facebook_url` is **NOT** an error — it is delivered with a "no link
  on file" notice (FR-019, US5).

## `DmOutcome` (models.py enum)

Mirrors `SendOutcome`, messenger-specific:

| Value | When |
| --- | --- |
| `DELIVERED = "delivered"` | Human confirmed a manual send; ledgered; status flipped. |
| `SKIPPED_NOT_SENDABLE = "skipped_not_sendable"` | Approved messenger note with no body. |
| `SKIPPED_ALREADY_SENT = "skipped_already_sent"` | Slug already in DM ledger, or duplicate target within the run. |
| `DECLINED = "declined"` | Operator chose not to confirm this note (stays approved). |
| `WOULD_DELIVER = "would_deliver"` | Preview/dry-run: eligible, nothing done. |

## `DmResult` / `DmRunReport` (models.py)

- `DmResult(slug, facebook_url, outcome: DmOutcome, detail: str)` — one per note.
- `DmRunReport(dry_run: bool, results: list[DmResult])` with convenience counts:
  `delivered`, `would_deliver`, `skipped`, `declined` (property accessors, like
  `RunReport`). Drives the summary printer (FR-020).

## DM ledger record (reuses `models.LedgerRecord`)

`ledger.append(dm_ledger_path, LedgerRecord(...))` with:

| Field | Value |
| --- | --- |
| `ts` | ISO timestamp of confirmation. |
| `slug` | note slug (dedupe key). |
| `recipient` | the `facebook_url` (or `""` when none) — the human's target. |
| `company` | display name. |
| `message_id` | `None` — no automated id exists (FR-014). |
| `result` | `"dm_sent_manual"`. |
| `error` | `None`. |
| `from_account` | `None`/omitted — no sending identity on this path. |

Dedupe via `ledger.already_sent(dm_ledger_path)` → uses the returned **slug** set
(`sent_slugs`); the recipient set is incidental here.

## State transitions

```text
note status: approved --(human confirms manual send)--> sent   [only automatic transition]
note status: approved --(operator declines/skips)-----> approved (unchanged)
preview mode: no transition ever
```

`vault.set_status(note_path, "sent", log_line)` performs the write, appending one
`## Log` bullet, e.g. `- 2026-07-24 messenger delivered manually (assisted)`.

## Config additions (config.py)

| Setting | Env var | Default |
| --- | --- | --- |
| `dm_ledger_path: Path` | `PROSPECTOR_DM_LEDGER` | `dm_ledger.jsonl` (repo root, gitignored) |

No new **required** config; the feature is inert until `prospector dm` is run.
