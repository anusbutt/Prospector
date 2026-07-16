# Contract: `prospector send` CLI command

## Synopsis

```
prospector send [--send] [--limit N] [--vault PATH] [--yes]
```

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--send` | absent (dry-run) | Perform REAL sends. Absent ⇒ dry-run: no email, no status change, no ledger write (FR-002). |
| `--limit N` | none | Send at most N in this run (still also bounded by the daily cap). |
| `--vault PATH` | Settings.vault_dir | Vault folder to scan. |
| `--yes` | false | Skip the interactive "about to really send X" confirmation (for automation). |

## Behavior (real-send path)

1. Load settings; resolve ledger, token, caps, pacing, expected sender.
2. **Verify identity**: resolve the token account; if it != `send_from`, ABORT (send nothing) (FR-004).
   - If no token exists, run the one-time consent flow first, then verify.
3. Scan vault → collect notes with `status == approved` (FR-001). Non-approved skipped.
4. For each, build a SendCandidate; mark not-sendable (skipped+reported) if channel != email,
   invalid/missing email, or missing subject/body (FR-005, FR-013).
5. Collapse duplicate recipients within the run to one send (FR-014); drop candidates already
   in the ledger as `sent` (by recipient or slug) (FR-010).
6. Compute `remaining = cap_for(today) - daily_count(today)`; also apply `--limit`.
   Order sendable candidates oldest-approved-first; take the first `remaining`. The rest are
   `deferred_cap` (FR-006, FR-003 order).
7. For each selected candidate, in order:
   a. Send via Gmail (httpx). On success → append ledger `result:sent` **then** flip note
      `approved → sent` with timestamp + `## Log` line (FR-008).
   b. On failure → append ledger `result:failed` with error; leave note `approved`; continue
      (FR-011). A failure does not consume future-day cap (only `sent` rows count).
   c. If another send remains, sleep a random pacing delay (FR-019).
8. Print RunReport: sent / deferred_cap / skipped_* / failed with slugs (FR-016).

## Behavior (dry-run path, default)

- Steps 1–6 run (including identity check if a token exists; if no token, report that consent
  will be needed and still preview). Step 7 is **not** executed: no send, no ledger write, no
  status change (FR-002). Print the exact list and count that *would* be sent, and the deferred
  count.

## Exit codes

| Code | Condition |
|------|-----------|
| 0 | Completed (dry-run, or real run with ≥0 sends and no fatal error). |
| 2 | Identity mismatch / wrong account → aborted, nothing sent (FR-004). |
| 3 | No usable OAuth client secret / consent failed. |
| 1 | Unexpected fatal error before the send loop. |

Per-message send failures are NOT fatal (reported in the RunReport; exit 0).

## Acceptance (maps to spec)

- No `--send` ⇒ zero sends/writes (SC-002).
- Real run never exceeds today's cap across repeated runs (SC-003).
- No note/recipient sent twice (SC-004).
- Every `sent` note has a ledger row and vice versa (SC-005).
- One failure neither aborts the run nor marks the note sent (SC-006).
- Non-Nestaro token ⇒ refuse (SC-007).
