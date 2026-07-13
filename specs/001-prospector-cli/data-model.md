# Data Model: Prospector

**Date**: 2026-07-13 | **Plan**: [plan.md](./plan.md)

All models are Python dataclasses (`prospector/models.py`). The vault note is the only
persisted form; everything else is in-memory per run.

## Company (input row, post-normalization)

| Field | Type | Rules |
|-------|------|-------|
| company | str | required, non-empty after trim |
| email | str \| None | lowercased; None if blank/"messenger"/FB-URL |
| raw_email_field | str | original value, kept for research log |
| website | str \| None | normalized to https origin |
| facebook_url | str \| None | stored only; NEVER fetched |
| city | str \| None | |
| owner_name | str \| None | human-provided → treated as high-confidence evidence (kind `input`) |
| notes | str \| None | |
| row_num | int | 1-based input position (error reporting, dedupe priority) |

**Derived on ingest**: `channel` (`email` if valid email else `messenger`),
`bucket_reason` (why messenger: blank / literal / fb-url / invalid),
`duplicate_of` (primary's slug or None), `slug`.

## Evidence

| Field | Type | Rules |
|-------|------|-------|
| kind | enum | `owner_text` \| `about_page` \| `team_page` \| `footer` \| `email_pattern` \| `input` \| `hunter` \| `fb_link` \| `fb_embed` \| `fb_widget` \| `fb_search_active` \| `fb_url_input` \| `city_source` \| `hook_source` |
| value | str | the extracted datum (name, url, phrase) |
| source | str | URL or "input row N" |
| excerpt | str | ≤200 chars of surrounding text (for `## Research` + validation) |

**Invariant**: every name/hook/signal used downstream traces to ≥1 Evidence (FR-012).

## ResearchResult (per company)

| Field | Type | Rules |
|-------|------|-------|
| website | str \| None | resolved or input |
| gbp_city | str \| None | from Places when available |
| name_evidence | list[Evidence] | may be empty |
| fb_evidence | list[Evidence] | only open-web kinds; never from FB itself |
| hook | str \| None | one phrase, sourced |
| hook_evidence | Evidence \| None | |
| city | str \| None | input > GBP > site |
| sources_consulted | list[str] | every URL fetched / API called, incl. failures |
| failures | list[str] | human-readable fetch/step failures |

## Prospect (scored, ready to draft)

| Field | Type | Rules |
|-------|------|-------|
| company | Company | |
| research | ResearchResult | |
| name_confidence | enum | `high` \| `medium` \| `none` — deterministic per §7 |
| name_used | str | first name (high only) or `"team"` |
| name_candidate | str \| None | populated iff medium |
| fb_signal | enum | `strong` \| `weak` \| `none` — deterministic per §7.5 |
| variant | enum | `email_fb` \| `email_agnostic` \| `messenger_dm` — mechanical (FR-014) |
| angle | str | default `offer-led` |
| needs_review | bool | medium name, messenger-odd input, draft-validation failure, research failure, duplicate |

**State rule**: `variant` = `messenger_dm` if channel messenger; else `email_fb` iff
`fb_signal == strong`; else `email_agnostic`.

## Draft

| Field | Type | Rules |
|-------|------|-------|
| subject | str \| None | None for messenger DM |
| body | str | assembled from template constant + validated slot fills |
| model | str | OpenRouter model id used |
| validated | bool | passed draft validator |
| validation_errors | list[str] | non-empty → needs_review |

**Validator asserts**: no unfilled `[slot]` remains; body ⊇ template invariant lines;
no name outside evidence set; `fb_signal none` → no "facebook" substring;
never any of {"your ads", "ad campaign", "running ads", "advertising"} (ad-claim guard);
no em-dash runs; signature intact.

## Note (persisted vault file)

Filename: `<slug>.md` in vault dir. Structure = YAML frontmatter (§6 key order) +
`## Draft` + `## Research` + `## Log` (+ any human-added sections, preserved).

**Frontmatter keys** (fixed order): company, email, channel, status, name_used,
name_confidence, name_candidate, hook, website, angle, fb_signal, duplicate_of,
needs_review, tags.

**Ownership**:
- Machine-owned: all frontmatter except `status`; `## Draft`; `## Research`.
- Human-owned: `status` (machine sets `to-send` on first write, never changes it
  after), `## Log` body, any unrecognized sections.
- Merge: write only if canonical rendering differs from existing bytes (SC-006).

**Status lifecycle** (human-driven after first write):
`to-send → sent → replied → pilot | dead`

## RunSummary

| Field | Type |
|-------|------|
| total, processed, failed | int |
| named_high, named_medium, named_none | int |
| messenger, duplicates, needs_review | int |
| per_company | list[(slug, outcome, detail)] |

Printed as the CLI's final table; counts must reconcile (`total == processed + failed`).

## Dashboard (`_Dashboard.md`)

Machine-owned entirely, regenerated each run (stable content → byte-idempotent).
Dataview blocks: to-send queue (`status = to-send AND !duplicate_of`), needs-review
(`needs_review = true OR name_confidence = medium`), messenger bucket
(`channel = messenger`), pipeline table grouped by `status`. Plain-markdown fallback
note at top for non-Dataview users.
