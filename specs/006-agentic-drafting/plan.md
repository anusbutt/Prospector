# Implementation Plan: Agentic Drafting (Evidence-Cited Personalized Copy)

**Branch**: `006-agentic-drafting` | **Date**: 2026-07-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-agentic-drafting/spec.md`

## Summary

Replace two-slot template filling with model-written prose that must cite its
sources. The model receives the operator's versioned instruction files plus that
company's extracted evidence catalogue and returns a subject and 3–6 prose
blocks, each declaring which evidence records support it. Code assembles the
greeting, body, and signature; a deterministic validator resolves every citation
against that company's real records and applies the existing honesty checks. Any
failure — transport, parse, or validation — falls back to today's locked
template, which is left byte-unchanged as the honesty floor.

Two safety additions ride along: notes at `approved` or `sent` are frozen
against re-drafting (repairing a latent defect where re-runs rewrite the record
of what was mailed), and a human-owned `outcome` field makes the two drafting
paths comparable later.

## Technical Context

**Language/Version**: Python 3.11+ (unchanged)
**Primary Dependencies**: existing only — httpx (OpenRouter call), Typer (CLI
summary output), `importlib.resources` (bundled instruction files). No new
third-party dependency.
**Storage**: Filesystem only — the Obsidian vault remains the datastore; two
additive frontmatter keys. No database.
**Testing**: pytest + respx (existing convention); fixture instruction files
under `tests/fixtures/agent/`
**Target Platform**: Local CLI (Linux/WSL, macOS)
**Project Type**: Single project — a flat `prospector/` package
**Performance Goals**: One model request per email-channel company per run, as
today. Instruction files loaded once per run, not per company.
**Constraints**: Assembled instruction context ≤ 20,000 characters; per-company
drafting cost ≤ 3× current (SC-309); no model call on the send path; no model
call for frozen notes, messenger notes, or evidence-less companies.
**Scale/Scope**: ~130 vault notes today, batches of 30–150; ~4 new source files,
~5 modified.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Gates derived from Constitution v5.0.0.

| Principle | Gate | Initial | Post-Design |
|---|---|---|---|
| **I.** Human-Approved Sending | No LLM call on the send path; copy generated at `run` time only; approved copy immutable | ✅ `send.py` untouched (FR-330); drafting is `run`-only; FR-326 freezes approved notes | ✅ Design adds `read_status` guard *before* the model call (R7); `send.py` has no new import |
| **II.** Open Web Only | No Facebook host contacted; drafting adds no fetch capability | ✅ Model gets no tools/network (FR-303); no new outbound host except the existing OpenRouter endpoint | ✅ Model receives only extracted `Evidence` strings — cannot cause a fetch (R6) |
| **III.** Obsidian Is the Interface | No UI; vault writes idempotent and non-destructive | ✅ Output stays notes + dashboard; two additive frontmatter keys | ✅ `outcome` is human-owned in merge (R8); frozen notes preserve `## Draft` verbatim (R7); keys appended, not reordered |
| **IV.** Evidence-Bound Copy | Every prospect claim cites a real Evidence record; validation deterministic; rejection falls back; fallbacks recorded and counted | ✅ FR-309/310/311/314/315/319/320 | ✅ R2 removes the classifier — every block must cite; offer-only blocks may not carry prospect tokens. R3 removes name fabrication structurally |
| **V.** Channel Honesty | Prospect-channel claims need observed signals; ad-running never claimed | ✅ FR-312 retains the banned-vocabulary check | ✅ `fb_*` evidence is citable like any other record; a Facebook claim without an `fb_*` citation cannot pass R2's rule |
| **VI.** Smallest Viable Build | One call per company; no framework; no autonomous loop; model has no tools | ✅ FR-301/303/307 | ✅ R4 rejects a Protocol+registry as heavier than needed; no retry, no repair call, no judge model |
| **VII.** Verified Claims Only | Every task has a concrete acceptance check | ✅ Enforced in tasks.md | ✅ `draft.py`'s existing suite must pass **unmodified** as mechanical proof of FR-316 (R9) |

**Result**: PASS, no violations. Complexity Tracking section omitted — nothing
to justify.

Two notes carried forward rather than gated:

- Constitution v5.0.0 flags PRODUCT.md §8 and the README guarantee table as
  ⚠ pending. Both are tasks in this feature, not blockers to design.
- R2's offer-only-block rule is the single place where a determined model could
  still launder a claim (by paraphrasing a prospect fact using none of the
  prospect's own tokens). This residual is accepted and documented: the
  operator's review gate remains the last line, which is where the approval
  decision already lives.

## Project Structure

### Documentation (this feature)

```text
specs/006-agentic-drafting/
├── plan.md              # This file
├── research.md          # Phase 0 — nine decisions (R1..R9)
├── data-model.md        # Phase 1 — entities, ids, frontmatter
├── quickstart.md        # Phase 1 — operator walkthrough
├── contracts/
│   ├── agent-draft.md   # request/response contract + validation rules
│   └── note-format.md   # frontmatter delta + merge ownership
├── checklists/
│   └── requirements.md  # spec quality checklist (passing)
└── tasks.md             # Phase 2 output (/sp.tasks — NOT created here)
```

### Source Code (repository root)

```text
prospector/
├── agent/                      # NEW — instruction content, not code
│   ├── IDENTITY.md             #   who the sender is, voice
│   ├── OFFER.md                #   the pilot, product, the one permitted link
│   ├── CONSTRAINTS.md          #   hard rules in the model's own language
│   └── skills/
│       └── write-cold-email.md #   structure, openings, what good looks like
├── agent_draft.py              # NEW — agent path + fallback coordinator
├── instructions.py             # NEW — load/validate/bound instruction files
├── draft.py                    # UNCHANGED behavior; +draft_source on Draft
├── models.py                   # +DraftBlock, +evidence_id, +draft_source, +outcome
├── vault.py                    # +read_status, +freeze_draft merge, +2 keys, +dashboard
├── pipeline.py                 # freeze guard, drafter call, fallback counting
├── config.py                   # +require_instructions() pre-flight
├── cli.py                      # summary line: drafted by path, fallbacks
└── send.py                     # UNTOUCHED

tests/
├── unit/
│   ├── test_agent_draft.py     # NEW — validator rules, citation resolution
│   ├── test_instructions.py    # NEW — loading, missing file, size bound
│   ├── test_vault_freeze.py    # NEW — frozen-note merge behavior
│   └── test_draft.py           # MUST PASS UNMODIFIED (proof of FR-316)
├── integration/
│   └── test_agent_fallback.py  # NEW — end-to-end fallback across failure modes
└── fixtures/
    └── agent/                  # NEW — fixture instruction files
```

**Structure Decision**: The existing flat `prospector/` package is kept — this
feature adds three modules and one content directory, which does not justify
introducing subpackages. `prospector/agent/` holds *content*, not code, matching
the constitution's "instruction files are content, not code" constraint; it is
declared as package data alongside the existing `data/*.txt` entry so
`pip install -e .` continues to work unchanged.

## Phase 1 Design Highlights

Full detail in [data-model.md](./data-model.md) and
[contracts/agent-draft.md](./contracts/agent-draft.md). The four decisions that
shape the code:

1. **Every block cites something** (R2). No classifier decides which sentences
   are claims — a block with an empty citation list is illegal, so the question
   never arises. Offer/product/sender facts cite the reserved id `offer`, and a
   block citing only `offer` may not contain the company name, city, owner name,
   or hook value.
2. **The model never writes the greeting** (R3). It returns `subject` and
   `blocks[]`; code prepends the greeting derived from existing name scoring and
   appends the signature. Name fabrication is structurally impossible on the
   agent path rather than merely checked.
3. **The fallback is a function, not a framework** (R4).
   `agent_draft.draft_email()` tries the agent and returns the template draft on
   any failure. `draft.py` is untouched so its existing tests prove FR-316
   mechanically.
4. **Status is read before the model is called** (R7). Frozen notes cost nothing
   and cannot be rewritten; `merge_notes` gains a `freeze_draft` flag that takes
   `## Draft` from the existing note.

## Phase 2 Notes (for `/sp.tasks`)

Suggested task ordering follows the spec's story priorities, with the safety
work first because it protects live data:

1. **US3 (freeze)** before anything else — the 27 sent notes are exposed the
   moment a re-run happens, and this is a small, self-contained change.
2. **Instruction loading + content files** — no model call yet; testable alone.
3. **US1 (agent path + validator)** — the feature core.
4. **US2 (fallback + counting)** — completes the safety story.
5. **US5 (measurement fields + dashboard)** — additive, independent.
6. **Docs reconciliation** — PRODUCT.md §8, README guarantees, `.env.example`.

Each task needs a runnable acceptance check per Principle VII: a pytest node, a
CLI invocation, or an observed file.

## Risks

| Risk | Blast radius | Mitigation |
|---|---|---|
| Fallback rate high enough to make the feature pointless | Wasted cost, no benefit | FR-320 surfaces the rate every run; R2's rules tuned against real fixtures before rollout |
| A model paraphrases a prospect fact using none of the prospect's own tokens, citing only `offer` | One dishonest sentence reaches review | Accepted residual; operator review is the backstop, cited excerpts stay visible in the note |
| Re-drafting 130 notes at once produces unreviewable churn | Operator burden | Freeze rules bound it to awaiting-review notes; `--only` and `--limit` allow a staged rollout |
