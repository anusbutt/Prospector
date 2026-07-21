# Phase 0 Research: Agentic Drafting

**Feature**: 006-agentic-drafting | **Date**: 2026-07-20
**Input**: [spec.md](./spec.md), Constitution v5.0.0

Nine decisions. R2 and R3 are the load-bearing ones: together they remove the
need for any "is this sentence a claim?" classifier, which was the feature's
largest open risk at spec time.

---

## R1. Stable evidence identifiers

**Decision**: `<evidence_kind>_<ordinal>`, ordinal starting at 1, assigned in the
order evidence appears in `ResearchResult.name_evidence + fb_evidence +
[hook_evidence]`. Examples: `about_page_1`, `email_pattern_1`, `fb_link_1`,
`hook_source_1`, `city_source_1`. Plus one reserved, tool-owned id: `offer`.

**Rationale**: Citations must survive into the note and be readable by the
operator at review time — `about_page_1` tells them where to look; a hash does
not. Evidence order is already deterministic given identical research, so the
same research produces the same ids, satisfying byte-idempotency (FR-329).
Prefixing with the kind means a citation is partly self-validating to a human
skimming the note.

**Alternatives considered**:
- *Bare index (`ev_1`, `ev_2`)*: shorter, but opaque in the note and shifts
  meaning if evidence ordering changes between runs.
- *Content hash*: stable across reordering, but unreadable, and reordering is
  not a real failure mode here since extraction order is fixed by page order.
- *Source URL as the id*: too long for a citation list, and several records can
  share one URL.

---

## R2. The claim-bearing block problem — dissolved, not solved

**Decision**: **Every block MUST carry at least one citation.** There is no
classifier. Offer, product, and sender facts cite the reserved id `offer`; facts
about the prospect cite real evidence ids. A block with an empty citation list
is rejected outright.

**Rationale**: The spec left open "how does code decide which blocks are
claim-bearing and therefore need a citation?" Any such classifier is either a
model call (forbidden by FR-311) or a heuristic that will be wrong in both
directions. Requiring a citation on *every* block removes the question: there is
no category of block that is allowed to be uncited, so nothing needs
classifying. The model cannot opt out by declaring a claim to be non-claim,
because "no citation" is never a legal state.

**The loophole this leaves, and its closure**: a model could write a sentence
about the prospect and cite `offer` to escape needing real evidence. Closed
deterministically — a block whose citations are *only* `offer` MUST NOT contain
prospect-specific tokens: the company name (or any distinctive token from it),
the resolved city, the owner name or candidate, or the hook value. All of those
values are already in hand at validation time, so the check is a substring
scan, not a judgment. A block that talks about the prospect while citing only
the offer is rejected.

**Alternatives considered**:
- *Model self-declares `is_claim` per block*: trusts the model with the very
  decision the validator exists to make. Rejected.
- *Keyword/POS heuristic over block text*: unbounded false-negative surface;
  every miss is a fabricated claim reaching a note.
- *Second model call as judge*: forbidden by FR-311 and Principle IV, and it
  replaces a hard guarantee with a probabilistic one.

---

## R3. The model does not write the greeting

**Decision**: The model returns `subject` and `blocks[]` only. The greeting line
(`Hi Scott,` / `Hi Acme Ducts team,`) and the signature are assembled in code
from the existing `name_used` value, exactly as today.

**Rationale**: Name honesty is already fully solved upstream — `score.py`
decides `high`/`medium`/`none` and `expected_greeting()` derives the greeting
deterministically. Letting the model restate the name reintroduces a solved
problem and creates a second place a fabricated name could enter. Withholding
the greeting from the model means the entire name-fabrication class of failure
is structurally impossible on the agent path, not merely validated against.
The existing greeting check (FR-312) is retained as a backstop for a block that
tries to greet again inside its own text.

**Alternatives considered**:
- *Model writes the greeting, validator checks it traces to evidence*: this is
  what FR-312 already does, but it turns a structural guarantee into a checked
  one for no gain — the model has no information about the name that the code
  lacks.

---

## R4. Drafting seam and module layout

**Decision**: A new module `prospector/agent_draft.py` holds the agent path and
the fallback coordinator. `prospector/draft.py` is untouched except for one
additive field on `Draft`. The pipeline calls one function:

```
agent_draft.draft_email(prospect, settings, instructions) -> Draft
    tries the agent path; on ANY failure or rejection returns
    draft.build_email_draft(...) with draft_source="template"
```

**Rationale**: Mirrors how 004 introduced `transport.py` — a seam module that
owns provider selection while the concrete providers stay independent and
independently tested. Keeping `draft.py` byte-stable is what makes FR-316
("template path unchanged, independently tested") verifiable rather than
asserted: its existing test suite must pass without modification.

A full `Drafter` Protocol with two implementations was considered and rejected
as heavier than the problem — there are exactly two paths, the fallback
direction is fixed, and no third drafter is foreseen. Principle VI prefers the
smaller diff.

**Alternatives considered**:
- *Protocol + registry like `create_sender()`*: justified in 004 because the
  provider is user-selectable at runtime; here it is not — the agent always
  runs first and the template always catches.
- *Coordination inline in `pipeline._process_company`*: hides the fallback
  decision inside orchestration where it is awkward to unit-test.

---

## R5. Instruction file loading and bounding

**Decision**: Instruction files ship as package data under
`prospector/agent/`, loaded via `importlib.resources` (the pattern already used
for `data/us_metros.txt`). Four required files, concatenated in fixed order with
`##` section separators:

| Order | File | Purpose |
|-------|------|---------|
| 1 | `IDENTITY.md` | who the sender is, company, voice |
| 2 | `OFFER.md` | the pilot, the product, the single permitted link |
| 3 | `CONSTRAINTS.md` | hard rules restated for the model in its own language |
| 4 | `skills/write-cold-email.md` | structure, length, opening lines, what good looks like |

Loaded once per run, not per company. A missing or unreadable file raises
`ConfigError` at pre-flight (exit 1, nothing written). Assembled instruction
text is capped at **20,000 characters**; exceeding it is a pre-flight
`ConfigError` naming the total and the cap.

**Rationale**: Pre-flight failure matches how every other missing-configuration
case in this codebase behaves (`require_llm`, `require_places`, `require_send`)
— fail before touching the network or writing anything. Loading once per run
keeps 130 companies from re-reading four files 130 times. The cap exists so a
pasted-in essay degrades into a clear startup error rather than silently
crowding out the per-company research context.

The 20k figure is a working bound: roughly 5k tokens, leaving ample room for
per-company evidence and the response inside a standard context window. It is a
constant, tunable without a schema change.

**Alternatives considered**:
- *Files outside the package (project root or `~/.prospector`)*: breaks
  `pip install -e .` portability and makes the "version-controlled content"
  guarantee (FR-321) depend on where the user put them.
- *Silent truncation at the cap*: forbidden by FR-325 — a truncated constraints
  file would drop hard rules invisibly, which is the worst possible failure.

---

## R6. Request and response contract

**Decision**: One `POST` to the existing OpenRouter endpoint, reusing
`OPENROUTER_MODEL`, with `response_format: {"type": "json_object"}`,
**temperature 0.7**, and a 60s timeout. Request carries the assembled
instructions as the system message and a JSON user message containing company
name, channel, greeting (already resolved), and the evidence catalogue as
`[{id, kind, value, source, excerpt}]`. Response schema is fixed in
`contracts/agent-draft.md`.

**Rationale**: Temperature rises from the current 0.3 because variation across
the batch is now a goal rather than a risk — SC-301 requires that drafts differ.
The honesty floor no longer depends on determinism, so the sampling temperature
is free to serve copy quality. Everything else reuses 001's existing call shape,
including the code-fence stripping already needed for providers that ignore
`response_format`.

Raw HTML is never included (FR-302) — only the already-extracted `Evidence`
fields, which is also what keeps the request small enough to stay cheap.

**Alternatives considered**:
- *Tool/function calling for structured output*: better schema adherence on
  some providers, but OpenRouter's tool support varies by underlying model and
  Principle VI forbids drifting toward a tool-calling session.
- *Temperature 0.3 retained*: would suppress exactly the variation SC-301 asks
  for.

---

## R7. Frozen-note guard placement

**Decision**: Read the existing note's `status` **before** drafting, in
`pipeline._process_company`, via a new read-only helper
`vault.read_status(vault_dir, slug) -> str | None`. When the status is
`approved` or `sent`, skip drafting entirely (no model call — FR-326), and pass
`freeze_draft=True` into the merge so the existing `## Draft` section is
preserved verbatim.

`merge_notes(existing, fresh, *, freeze_draft: bool = False)` gains one keyword
argument: when set, `Draft` is taken from `existing` rather than `fresh`.

**Rationale**: The guard must sit before the model call, not after, or the
feature burns a request per frozen company and violates FR-326's "MUST NOT
issue a model request." Reading status is a cheap file read the pipeline already
performs implicitly during upsert; hoisting it is a small, local change.

This also repairs a latent defect: today `merge_notes` always takes `Draft` from
fresh output, so re-running an already-sent company silently rewrites the record
of what was mailed. That is a live risk for the 27 sent notes the moment the
chosen "re-draft everything" rollout runs.

**Alternatives considered**:
- *Freeze inside `upsert_note` by re-reading status there*: the model call has
  already happened by then — wasted cost and an FR-326 violation.
- *Skip frozen companies entirely (no note write at all)*: would stop refreshing
  the `## Research` section on sent notes, losing harmless useful updates, and
  would break the "every input row yields a note" accounting.

---

## R8. New frontmatter fields and their ownership

**Decision**: Two additive keys, appended to `FRONTMATTER_KEYS` after
`needs_review`:

| Key | Owner | Values | Merge behavior |
|-----|-------|--------|----------------|
| `draft_source` | machine | `agent` \| `template` | from fresh |
| `outcome` | human | empty \| `replied` \| `bounced` \| `interested` \| `no` | from existing, like `status` |

**Rationale**: `outcome` joins `status` as the second human-owned frontmatter
key, so `merge_notes` preserves it by the same rule already proven for status
(FR-332). `draft_source` is machine-owned and follows fresh output, except on
frozen notes where the whole draft region is preserved and the recorded source
must stay consistent with the preserved text.

Appending rather than inserting keeps existing notes' key order stable, so the
first re-run does not produce a 130-note diff of pure reordering.

**Alternatives considered**:
- *Store `outcome` in a separate sidecar file*: violates Principle III (the
  vault is the datastore) and makes the dashboard query impossible.
- *Infer outcome automatically by reading the mailbox*: explicitly out of scope,
  and would require read access the tool deliberately does not have.

---

## R9. Testing strategy

**Decision**: Reuse the repo's existing conventions — `respx` to mock the
OpenRouter call, fixture instruction files under `tests/fixtures/agent/`, and
hand-built `Prospect` objects for validator unit tests. Three layers:

1. **Validator unit tests** — pure functions, no network: citation resolution,
   empty-citation rejection, offer-only-block leakage, block count bounds, and
   each retained check from FR-312.
2. **Fallback tests** — force transport error, malformed JSON, and validation
   rejection; assert the template draft appears and `draft_source: template`.
3. **Freeze tests** — a vault seeded with one note per status; assert the model
   is never called for approved/sent and their draft bytes are unchanged.

`draft.py`'s existing test suite must pass **unmodified** — that is the
mechanical proof of FR-316.

**Rationale**: No new test infrastructure is warranted. The `respx` +
injected-dependency pattern already covers HTTP (001–004) and SMTP (004); the
drafting call is just another HTTP call.

**Alternatives considered**:
- *Live model calls in CI*: non-deterministic, costs money, and cannot exercise
  the failure modes that matter most here.
- *Golden-file assertions on generated copy*: meaningless against temperature
  0.7 output; assertions target the validator's verdicts, not the prose.

---

## Resolved unknowns summary

| Spec-time unknown | Resolution |
|---|---|
| How are claim-bearing blocks identified? | R2 — they aren't; every block cites something |
| Can the model launder a claim through `offer`? | R2 — offer-only blocks may not contain prospect tokens |
| Who writes the greeting? | R3 — code, from existing name scoring |
| How do citations stay stable across runs? | R1 — `kind_ordinal`, deterministic evidence order |
| Where does the fallback decision live? | R4 — `agent_draft.draft_email()` |
| How are instruction files bounded? | R5 — 20k char cap, pre-flight failure |
| How is a frozen note protected before cost is incurred? | R7 — status read before drafting |
| How is `outcome` preserved across re-runs? | R8 — human-owned merge key, same rule as `status` |

No NEEDS CLARIFICATION markers remain.
