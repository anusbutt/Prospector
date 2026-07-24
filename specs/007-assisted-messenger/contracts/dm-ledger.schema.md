# Contract: `dm_ledger.jsonl` record schema

Append-only JSON Lines. One object per confirmed, human-performed Messenger
delivery. Reuses `prospector.models.LedgerRecord` and `prospector.ledger.append`.

## Record fields

| Field | Type | Required | Value / meaning |
| --- | --- | --- | --- |
| `ts` | string (ISO 8601) | yes | Timestamp when the operator confirmed the send. |
| `slug` | string | yes | Note stem — the **dedupe key** for this ledger. |
| `recipient` | string | yes | The `facebook_url` target (empty string when none was on file). |
| `company` | string | yes | Company display name. |
| `message_id` | null | yes | Always `null` — no automated message id exists (FR-014). |
| `result` | string | yes | Always `"dm_sent_manual"`. |
| `error` | null | yes | Always `null` (declines/skips are never written). |
| `from_account` | null | no | Absent/null — no sending identity on this path. |

## Example line

```json
{"ts":"2026-07-24T14:03:11","slug":"air-duct-cleaners-llc","recipient":"https://www.facebook.com/AirDuctCleanersLLC/","company":"Air Duct Cleaners LLC","message_id":null,"result":"dm_sent_manual","error":null}
```

## Rules

- **Append-only, immutable.** Never rewritten; a stopped run resumes safely.
- **Dedupe on `slug`.** `ledger.already_sent(dm_ledger_path)` returns
  `(recipients, slugs)`; the DM path skips any candidate whose `slug ∈ slugs`
  (FR-012). Recipient/target matching is not used for dedupe (messenger targets
  may be blank or shared).
- **Separate file.** MUST be a different path from `send_ledger.jsonl`
  (`PROSPECTOR_DM_LEDGER`, default `dm_ledger.jsonl`) so email cap accounting
  (`ledger.daily_count`/`first_send_date` over the send ledger) is unaffected
  (FR-011).
- **Gitignored.** Local audit trail only; never committed.
- Only written on affirmative human confirmation; declines/skips write nothing.
