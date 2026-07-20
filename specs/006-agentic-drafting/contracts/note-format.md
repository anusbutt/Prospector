# Contract: Note Format Delta and Merge Ownership

**Feature**: 006-agentic-drafting | **Date**: 2026-07-20
**Module**: `prospector/vault.py`
**Supersedes**: nothing — this is a delta on 001's `contracts/note-format.md`

---

## 1. Frontmatter delta

Two keys appended to `FRONTMATTER_KEYS`, positioned after `needs_review` and
before `tags`:

```yaml
---
company: Acme Duct Cleaning
email: scott@acmeduct.com
channel: email
status: to-send
name_used: Scott
name_confidence: high
name_candidate:
hook: 22 years in business
website: acmeduct.com
angle: offer-led
fb_signal: weak
duplicate_of:
needs_review: false
draft_source: agent          # NEW — machine-owned
outcome:                     # NEW — human-owned, empty by default
tags: [outreach, duct-cleaning, prospector]
---
```

**Why appended rather than inserted**: existing notes keep their key order, so
the first re-run after this feature produces content diffs only — not a
130-note diff of pure reordering.

### `draft_source`

| Value | Meaning |
|-------|---------|
| `agent` | Copy written by the model and validated |
| `template` | Copy from the locked template (fallback, `--no-llm`, or messenger) |
| *(empty)* | Not drafted this run |

### `outcome`

Human-owned. The tool writes it **empty on creation and never again**.

| Value | Meaning |
|-------|---------|
| *(empty)* | Nothing recorded yet |
| `replied` | Prospect responded |
| `interested` | Prospect responded positively |
| `bounced` | Delivery failed |
| `no` | Explicit decline |

Values are a convention, not an enforced enum — an operator writing something
else is preserved, not corrected. The dashboard groups on whatever is present.

---

## 2. Merge ownership (complete table, post-006)

| Region | Owner | Re-run behavior |
|--------|-------|-----------------|
| `company`, `email`, `channel`, `name_*`, `hook`, `website`, `angle`, `fb_signal`, `duplicate_of`, `needs_review`, `tags` | machine | from fresh |
| `draft_source` | machine | from fresh; preserved with the draft on a frozen note |
| `status` | human | preserved |
| `outcome` | **human** | **preserved** *(new)* |
| `## Draft` | machine | from fresh, **unless frozen** *(new)* |
| `## Citations` | machine | from fresh, **unless frozen** *(new)* |
| `## Research` | machine | from fresh, always — including frozen notes |
| `## Log` | human | preserved verbatim |
| Unrecognized sections | human | preserved, after known sections, original order |

Section order is `Draft, Citations, Research, Log`. Citations sit directly under
the draft so a reviewer reads a paragraph and glances one line down. Notes
written before this feature have no Citations section and are skipped, so
nothing is reordered.

---

## 2a. The `## Citations` section

Present only on agent drafts. Template drafts make no per-paragraph claims, so
they get no section — and a re-run that falls back to the template **removes**
an existing Citations section rather than leaving a stale one.

```markdown
## Citations
*What each body paragraph rests on. The tool proves a cited record exists;
only you can confirm it actually says what the sentence claims.*

1. `hook_source_1` — "over 20 years of experience. All Pro Duct Cleaning is
   locally owned, operated and licensed in Washington" (https://…/about-us/)
   `fb_search_active_1` — "All Pro Duct Cleaning LLC | Portland OR - Facebook"
   (ddg-search: "All Pro Duct Cleaning LLC" facebook)
2. `offer` — the offer, product, or sender (not a claim about them)
```

**Numbering** matches the body paragraphs *below the greeting*. The greeting and
sign-off are written by code, never the model, so they carry no citation.

**Why it exists.** Validation proves a cited record exists and belongs to this
company; it cannot prove the record *supports* the sentence. That second check
is the operator's, and it is impossible to perform unless the note shows which
record each paragraph claimed. Without this section, SC-302 ("every
personalized statement traces to a research record an operator can inspect from
the same note") is only half delivered.

**Frozen notes keep their citations.** Preserving a draft while refreshing its
citations would produce a note whose trace describes copy that was never sent —
worse than no trace at all. `DRAFT_OWNED_SECTIONS` moves both together.

---

## 3. The freeze rule

```python
def read_status(vault_dir: Path, slug: str) -> str | None:
    """Existing note's frontmatter status, or None if the note does not exist.
    Read-only; performs no write and no merge."""

FROZEN_STATUSES = frozenset({"approved", "sent"})

def is_frozen(status: str | None) -> bool:
    """True when the note's copy must not be regenerated.

    None (new note) and "to-send" are drafted. EVERY other value is frozen,
    including unrecognized ones — defaulting down, consistent with how this
    codebase treats every uncertain signal."""
    return status is not None and status != "to-send"
```

`merge_notes` gains one keyword argument:

```python
def merge_notes(existing: str, fresh: str, *, freeze_draft: bool = False) -> str:
    """When freeze_draft is True, `## Draft` and `draft_source` come from
    `existing` instead of `fresh`. Every other rule is unchanged."""
```

`upsert_note` passes it through.

**Call ordering — load-bearing.** The pipeline MUST read status *before*
drafting:

```
read_status(vault_dir, slug)
      │
      ├─ frozen ──► skip drafting entirely (NO model call — FR-326)
      │             refresh ## Research only
      │
      └─ not frozen ──► draft ──► validate ──► write
```

Checking after the model call would satisfy the "don't rewrite" half of FR-326
while violating the "no model request" half, and would bill for every frozen
company on every run.

---

## 4. Dashboard delta

Two Dataview queries appended to the static `DASHBOARD_CONTENT`. It stays
entirely machine-owned with plain write-if-differ, so re-runs remain
byte-idempotent.

```markdown
## Draft source

```dataview
TABLE rows.company AS Companies
FROM #prospector
GROUP BY draft_source
```

## Outcomes by draft source

```dataview
TABLE rows.company AS Companies
FROM #prospector
WHERE outcome
GROUP BY draft_source + " / " + outcome
```
```

The second query is what SC-308 requires: reply outcomes grouped by which path
wrote the copy.

---

## 5. Test obligations

| Rule | Test |
|---|---|
| `outcome` preserved across re-run | Seed note with `outcome: replied`, re-run, assert unchanged |
| `status` still preserved | Existing test must pass unmodified |
| Frozen note keeps `## Draft` bytes | Seed `approved` + `sent` notes, re-run, assert draft byte-identical |
| Frozen note refreshes `## Research` | Same fixture, assert Research updated |
| Unknown status is frozen | Seed `status: hold`, assert draft unchanged |
| No model call for frozen notes | respx call count == 0 for an approved-only vault |
| Key order stable | Existing note gains the two keys without reordering the rest |
| Byte-idempotency retained | Run twice with identical stub response, assert `unchanged` |
