# Contract: Send ledger (JSONL)

One JSON object per line, append-only. Default path `send_ledger.jsonl` (gitignored).

## Record schema

```json
{
  "ts": "2026-07-15T16:40:12",
  "slug": "boston-air-duct-cleaning",
  "recipient": "info@bostonairduct.com",
  "company": "Boston Air Duct Cleaning",
  "message_id": "1990af...c1",
  "result": "sent",
  "error": null,
  "from_account": "nestaroassistant@gmail.com"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| ts | string (ISO-8601 local) | yes | date portion = the send day |
| slug | string | yes | note identity |
| recipient | string | yes | lowercased email |
| company | string | yes | audit/convenience |
| message_id | string \| null | yes | provider id on success; null on failure |
| result | `"sent"` \| `"failed"` | yes | |
| error | string \| null | yes | reason when failed; else null |
| from_account | string | yes | verified sending address |

## Module interface (`prospector/ledger.py`)

| Function | Signature | Contract |
|----------|-----------|----------|
| `append(path, record)` | `(Path, LedgerRecord) -> None` | Serialize one line + `\n`, open in append mode, flush. Never rewrites the file. |
| `read_all(path)` | `(Path) -> list[LedgerRecord]` | Parse each line; silently skip a trailing malformed/partial line (crash-safety). Missing file ⇒ `[]`. |
| `daily_count(path, day)` | `(Path, date) -> int` | Count `result=="sent"` rows whose `ts` date == `day`. |
| `already_sent(path)` | `(Path) -> tuple[set[str], set[str]]` | Return `(recipients, slugs)` from `result=="sent"` rows for O(1) skip lookups. |
| `first_send_date(path)` | `(Path) -> date \| None` | min `ts` date across `result=="sent"` rows; None if none. |

## Invariants (tested)

- Append never mutates prior lines (byte-length before == prefix of after).
- `daily_count` ignores `failed` rows and other days.
- `already_sent` matches by recipient OR slug.
- Partial last line does not crash `read_all`.
- Empty/missing ledger ⇒ `first_send_date` None ⇒ caller treats today as week 0.
