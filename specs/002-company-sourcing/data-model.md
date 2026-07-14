# Data Model: Company Sourcing (`prospector source`)

**Date**: 2026-07-14 | **Plan**: [plan.md](./plan.md)

All entities are in-memory dataclasses in `prospector/source.py`; the only durable
artifact is the output CSV (see [contracts/csv-format.md](./contracts/csv-format.md)).

## Candidate

One discovered business, from Places result through classification to CSV row.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `place_id` | str | Places `places.id` | stable provider id; primary dedupe key |
| `company` | str | Places `displayName.text` | required; row dropped (and counted) if absent |
| `city` | str | Places `formattedAddress` | parsed "City, ST" via the same address-parsing approach as `resolve.py`; falls back to the metro queried |
| `website` | str \| None | Places `websiteUri` | normalized: scheme kept for fetching; domain (host, lowercase, `www.` stripped) derived for dedupe and CSV |
| `ad_signal` | `"pixel"` \| `"none"` | pixel detector over fetched homepage HTML | `none` when website missing, unreachable, or robots-blocked (never guessed up — spec US2/AS4) |
| `email` | str \| None | mailto/plaintext extraction (R4) | never inferred or constructed |
| `metro` | str | the metro whose query returned it | reporting only |
| `failures` | list[str] | fetch/extract errors | reporting only; failures never abort the batch |

**Validation rules**
- `company` non-empty after strip (else dropped + counted in summary).
- `email` must match the conservative email regex; else treated as not found.
- `ad_signal` defaults to `"none"`; only the detector may set `"pixel"`.

**State transitions**
`discovered` → (dedupe) `unique | duplicate-dropped` → (fetch+detect) `classified`
→ (filter) `written | filtered-out (kept with --all)`.

## MetroList

| Field | Type | Notes |
|-------|------|-------|
| `metros` | list[str] | ordered, `City, ST` per line; blank lines / `#` comments ignored |
| `source` | `"bundled"` \| path | bundled `prospector/data/us_metros.txt` (30 entries) or `--metros FILE` |

**Validation rules**: file must exist, parse, and contain ≥1 metro — else pre-flight
error (exit 1, nothing written).

## SourcingSummary

Printed at end of run (stdout table, same style as 001's `RunSummary`).

| Field | Type | Meaning |
|-------|------|---------|
| `metros_covered` | int / total | metros actually queried (may be < total on budget stop) |
| `queries_used` | int | Places requests issued vs. `--max-queries` budget |
| `discovered` | int | raw results across all queries |
| `duplicates_collapsed` | int | rows removed by place_id/domain dedupe |
| `pixel_positive` | int | candidates with `ad_signal: pixel` |
| `emails_found` | int | candidates with a captured email |
| `written` | int | rows in the output CSV |
| `failures` | list[(candidate, reason)] | per-candidate isolated failures |

## Relationships

```text
MetroList ──1:N──► Places query ──1:N──► Candidate ──filter──► CSV row
                                              │
                                    SourcingSummary (aggregates)
```

Downstream: a CSV row maps 1:1 onto feature 001's input row (`company,email,website,
city`); `ad_signal` rides along as an ignored extra column and exists purely as an
audit trail of why the row made the list.
