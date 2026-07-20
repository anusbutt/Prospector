# Data Model: Agentic Drafting

**Feature**: 006-agentic-drafting | **Date**: 2026-07-20

In-memory dataclasses in `prospector/models.py`, plus the vault note's
frontmatter delta. The note remains the only persisted form (Principle III).

---

## New entities

### `DraftBlock`

One paragraph-sized unit of model-written prose and the citations supporting it.
The unit of validation.

| Field | Type | Notes |
|-------|------|-------|
| `text` | `str` | Prose as written by the model. Never edited by code — only accepted or rejected. |
| `cites` | `list[str]` | Evidence ids, or the reserved `"offer"`. MUST be non-empty (FR-309). |

**Validation rules**

1. `text` is non-empty after stripping.
2. `cites` has ≥ 1 entry.
3. Every entry resolves to an `EvidenceRef.id` for this company, or equals
   `"offer"`.
4. If `cites == ["offer"]` (offer-only), `text` MUST NOT contain any
   prospect-specific token: the company name or a distinctive token from it, the
   resolved city, `name_used`, `name_candidate`, or the hook value. Case-
   insensitive substring match. This is the anti-laundering rule from research R2.

### `EvidenceRef`

A stable, citable handle on an existing `Evidence` record. Derived, not stored —
built fresh each run from the research result.

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | `<evidence_kind>_<ordinal>`, ordinal from 1 (R1) |
| `kind` | `str` | The existing `EvidenceKind` value |
| `value` | `str` | The extracted fact |
| `source` | `str` | URL or source description |
| `excerpt` | `str` | Supporting text, ≤ 200 chars (existing convention) |

**Id assignment.** Deterministic, from the concatenation
`name_evidence + fb_evidence + [hook_evidence]` in list order, with a per-kind
counter. Identical research ⇒ identical ids ⇒ byte-idempotent notes (FR-329).

The reserved id `"offer"` is not an `EvidenceRef`. It is a tool-owned constant
denoting the offer, the product, and the sender — facts that are not
observations about the prospect.

### `AgentResponse`

The parsed model reply, before assembly and validation.

| Field | Type | Notes |
|-------|------|-------|
| `subject` | `str` | Validated against company-name tokens (FR-313) |
| `blocks` | `list[DraftBlock]` | 3–6 inclusive (FR-305) |

### `InstructionSet`

The loaded, bounded instruction content. Built once per run.

| Field | Type | Notes |
|-------|------|-------|
| `text` | `str` | All four files concatenated in fixed order (R5) |
| `sources` | `list[str]` | File names in load order, for the failure message |
| `char_count` | `int` | Enforced ≤ `MAX_INSTRUCTION_CHARS` (20,000) |

---

## Modified entities

### `Draft` (existing)

| Field | Change |
|-------|--------|
| `source` | **NEW** — `"agent"` or `"template"`, defaults to `"template"` |

Existing fields (`subject`, `body`, `model`, `validated`, `validation_errors`)
are unchanged. `validation_errors` now also carries citation-rejection reasons
(FR-314).

### `RunSummary` (existing)

| Field | Change |
|-------|--------|
| `drafted_agent` | **NEW** — `int`, companies drafted by the model path |
| `drafted_template` | **NEW** — `int`, companies drafted by the fallback |
| `fallback_reasons` | **NEW** — `list[tuple[str, str]]` of `(slug, reason)` (FR-320) |

`reconciles()` is unchanged. `drafted_agent + drafted_template` need not equal
`processed`: messenger-channel and `--no-llm` companies fall in neither bucket,
and frozen notes are not drafted at all.

---

## Frontmatter delta

Two keys appended to `FRONTMATTER_KEYS` after `needs_review`, before `tags`.
Appending rather than inserting keeps existing notes' key order stable, so the
first re-run does not produce a 130-note diff of pure reordering (R8).

| Key | Owner | Values | Merge source |
|-----|-------|--------|--------------|
| `draft_source` | machine | `agent` \| `template` \| *(empty when not drafted)* | fresh — except on a frozen note, where it is preserved with the draft |
| `outcome` | **human** | *(empty)* \| `replied` \| `bounced` \| `interested` \| `no` | **existing** — same rule as `status` |

`outcome` becomes the second human-owned frontmatter key. The tool writes it
empty on note creation and never writes it again.

### Merge ownership after this feature

| Region | Owner | Behavior on re-run |
|--------|-------|--------------------|
| All frontmatter except `status`, `outcome` | machine | from fresh |
| `status` | human | preserved |
| `outcome` | human | preserved *(new)* |
| `## Draft` | machine | from fresh, **unless the note is frozen** *(new)* |
| `## Research` | machine | from fresh, always — including on frozen notes |
| `## Log` | human | preserved verbatim |
| Unrecognized sections | human | preserved, after known sections |

---

## Note status and the freeze rule

| `status` | Re-drafted? | Model called? | `## Draft` on re-run |
|----------|-------------|---------------|----------------------|
| *(absent / new note)* | yes | yes | written fresh |
| `to-send` | yes | yes | from fresh |
| `approved` | **no** | **no** | **preserved verbatim** |
| `sent` | **no** | **no** | **preserved verbatim** |
| any other value | **no** | **no** | **preserved verbatim** |

Unknown status values are treated as frozen — defaulting down, consistent with
how the codebase handles uncertain signals everywhere else. An operator who
invents `status: hold` gets protection, not a surprise rewrite.

`## Research` refreshes even on frozen notes: it is machine-owned observation,
not approved copy, and keeping it current is useful and harmless.

---

## State transitions

```
   (new note)
       │  run
       ▼
   to-send ──────── run ────────► to-send        (draft regenerated)
       │
       │ human edits frontmatter
       ▼
   approved ─────── run ────────► approved       (draft FROZEN, no model call)
       │
       │ prospector send
       ▼
     sent ───────── run ────────► sent           (draft FROZEN, no model call)
       │
       │ human records what came back
       ▼
  outcome: replied | bounced | interested | no   (preserved across every run)
```

The only machine-written status transition remains `approved → sent`, made by
`vault.set_status()` on the send path (Constitution Principle I). This feature
adds no new machine-written transition.

---

## Dashboard additions

Two Dataview queries appended to `_Dashboard.md` (machine-owned, static content,
so re-runs stay byte-idempotent):

```dataview
TABLE rows.company AS Companies
FROM #prospector
WHERE draft_source
GROUP BY draft_source
```

```dataview
TABLE rows.company AS Companies
FROM #prospector
WHERE outcome
GROUP BY draft_source + " / " + outcome
```

The second is the comparison SC-308 requires: reply outcomes grouped by which
path wrote the copy.
