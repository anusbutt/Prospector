# Contract: `prospector dm` command

## Signature

```text
prospector dm [--send] [--limit N] [--vault PATH] [--yes]
```

| Flag | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--send` | bool | `False` | Perform real assist (clipboard + browser + confirm + ledger + status). Absent = preview only. |
| `--limit` | int | none | Walk at most N eligible notes this run. |
| `--vault` | Path | `settings.vault_dir` | Vault folder (default `Vault/Outreach`). |
| `--yes` | bool | `False` | Skip the ONE upfront "about to walk N notes" confirmation. Per-note confirmations are NEVER skipped in real mode. |

Mirrors `prospector send` ergonomics intentionally (FR-006).

## Behavior

### Preview (default, no `--send`) — FR-002, US2

1. Collect approved messenger candidates (`dm.collect_dm_candidates`).
2. Drop DM-ledgered slugs and in-run duplicate targets.
3. Print a summary: `would deliver`, `skipped (already delivered)`,
   `skipped (not sendable)` with per-note reasons.
4. Open **no** browser, write **no** clipboard, append **no** ledger row, change
   **no** note. MUST make no external request.

### Real (`--send`) — FR-003/004/005, US1

Upfront (unless `--yes`): print `About to walk N approved messenger note(s); you
will confirm each send yourself. Proceed?` → abort on no.

Then for each eligible candidate, oldest-approved-first:

1. Copy `body` to clipboard (`clipboard.copy_to_clipboard`); on failure print the
   body for manual copy.
2. If `facebook_url` present: `webbrowser.open(facebook_url, new=2)`; on failure
   print the URL. If absent: print `no Facebook link on file — locate the company
   manually`.
3. Show company name + the message body.
4. Prompt: `Did you send this message? [y/N/q]`
   - `y` → append DM ledger row, then `vault.set_status(..., "sent", log)`,
     record `DELIVERED`.
   - `n`/Enter → record `DECLINED`, note stays `approved`, continue.
   - `q` → stop the walk; already-confirmed notes remain recorded.
5. Respect `--limit` (count of notes walked) and stop early if reached.

### Exit codes (mirrors `send` family)

| Code | Meaning |
| --- | --- |
| `0` | Completed (preview or real); per-note declines/skips are normal. |
| `1` | Pre-flight failure (vault folder not found). |

No identity/auth codes apply — this path has no authenticated sender.

## Preconditions

- Vault folder exists (else exit 1, nothing done).
- No provider/identity config required (unlike `send`); `require_send()` is NOT
  called.

## Invariants (constitution v6.0.0)

- Only `status: approved` + `channel: messenger` notes are ever walked.
- The tool issues **zero** HTTP requests to Facebook; only `webbrowser.open`
  hands off the URL.
- No browser automation; `webbrowser` cannot read the page back.
- Body delivered is the deterministic template verbatim; no LLM call.
- Only automatic status transition is `approved → sent`, after human confirm.
- Ledger row precedes the status flip (source-of-truth ordering).

## Report format (FR-020)

```text
Prospector dm [WOULD WALK (preview) | ASSISTED SEND]
  vault: Vault/Outreach
  to walk: 4   delivered: 0   skipped (already): 2   skipped (not sendable): 1   declined: 0

  air-duct-cleaners-llc   would_deliver   https://www.facebook.com/AirDuctCleanersLLC/
  peak-vent-cleaning      skipped_not_sendable   draft has no body
  ...
```
