# Feature Specification: Agentic Drafting (Evidence-Cited Personalized Copy)

**Feature Branch**: `006-agentic-drafting`
**Created**: 2026-07-20
**Status**: Draft
**Input**: User description: "Agent-written personalized outreach copy constrained by evidence citation, with the locked template retained as an automatic fallback"

## Overview

Today every prospect receives byte-identical prose. The model fills two slots
(`greeting_name`, `subject_company`) and the sentences are fixed constants, so
the only thing that varies across a 130-company batch is the greeting and the
subject. This was a deliberate honesty mechanism — a model that cannot write
prose cannot invent facts — but it costs the two things cold outreach runs on:
relevance to the individual reader, and variation across a sending domain whose
reputation is still ramping.

This feature lets the model write the copy, steered by versioned markdown
instruction files, while keeping the honesty guarantee intact by a different
mechanism: **every sentence about the prospect must cite the research record it
came from**, checked deterministically. Copy that cannot be validated is
discarded and the existing locked template answers instead.

The model gains freedom of phrasing. It never gains freedom of fact.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Personalized copy that cannot invent facts (Priority: P1)

The operator runs the batch. For each email-channel company, the drafting model
receives that company's recorded research (owner name evidence, city, hook,
channel signals — each with a source and an excerpt) plus the instruction files
describing who the sender is, what the offer is, and how to write a good cold
email. It returns a small set of prose blocks, each block declaring which
research records support it. The tool assembles the body from those blocks,
checks every citation resolves to a record actually captured for that company,
and writes the note. The operator opens Obsidian and reads an email that sounds
written for that business — and can see, in the same note, exactly what each
personalized claim rests on.

**Why this priority**: This is the feature. Without it nothing else here has a
reason to exist, and it is independently valuable the moment one company drafts
correctly.

**Independent Test**: Run the batch against a fixture company with known
research records and a stubbed model response; confirm the note contains the
model's prose, that each personalized statement carries a citation, and that
the citations resolve to that company's real records.

**Acceptance Scenarios**:

1. **Given** a company with a recorded owner name, city, and hook, **When** the
   batch runs, **Then** the note's draft is model-written prose whose
   personalized statements each cite a recorded research record.
2. **Given** a model response citing a record identifier that was never
   captured for that company, **When** the draft is validated, **Then** the
   draft is rejected and the note receives the locked-template draft instead.
3. **Given** a model response containing a statement about the prospect with no
   citation at all, **When** the draft is validated, **Then** the draft is
   rejected and the locked template answers instead.
4. **Given** a company for which research captured no records at all, **When**
   the batch runs, **Then** the tool uses the locked template without calling
   the model, because there is nothing to personalize from.
5. **Given** a model response that names a person not present in any recorded
   evidence, **When** the draft is validated, **Then** the draft is rejected.

---

### User Story 2 - The locked template always answers (Priority: P1)

Whatever the model does — times out, returns malformed output, returns prose
that fails validation, or is disabled entirely — the operator still gets a
usable, honest draft for every company. The existing template path continues to
work exactly as it does today, and the note records which path produced its
copy so a degraded run is visible rather than merely quiet.

**Why this priority**: Equal to P1 because the batch's guarantee is "every input
row yields a note." A drafting path that can fail without a floor underneath it
would regress an existing, working guarantee.

**Independent Test**: Force each failure mode in turn (transport error,
malformed output, validation rejection) and confirm the note is still written,
still honest, still marked as template-sourced, and counted as a fallback in
the run summary.

**Acceptance Scenarios**:

1. **Given** the model call fails with a transport error, **When** the company
   is processed, **Then** the note receives the locked-template draft, is
   marked as template-sourced, and the batch continues to the next company.
2. **Given** the model returns output that cannot be parsed, **When** the
   company is processed, **Then** the locked template answers and no second
   model call is made.
3. **Given** any draft falls back, **When** the batch finishes, **Then** the
   run summary reports how many companies fell back and why.
4. **Given** a run where every company falls back, **When** the batch finishes,
   **Then** the output is byte-comparable to today's template-only output.

---

### User Story 3 - Approved and sent copy is frozen (Priority: P1)

The operator has already approved some notes and already sent others. A re-run
regenerates drafts for companies still awaiting review, but must never rewrite
copy the operator has approved (they would then send words they never read) and
must never rewrite copy that was already mailed (that is the record of what
went out).

**Why this priority**: This is a safety property, not an enhancement. Re-drafting
everything is the chosen rollout, which makes this the difference between a
useful refresh and a silent violation of the approval guarantee.

**Independent Test**: Seed a vault with one note at each status, run the batch,
and confirm only the awaiting-review note's draft changed.

**Acceptance Scenarios**:

1. **Given** a note the operator marked approved, **When** the batch re-runs
   that company, **Then** its draft text is unchanged and no model call is made
   for it.
2. **Given** a note already marked sent, **When** the batch re-runs that
   company, **Then** its draft text is unchanged and no model call is made.
3. **Given** a note still awaiting review, **When** the batch re-runs, **Then**
   its draft is regenerated.
4. **Given** any re-run, **When** notes are written, **Then** operator-owned
   regions (status, log history, operator-added sections) are preserved exactly
   as they are today.

---

### User Story 4 - Tuning the voice without touching code (Priority: P2)

The operator wants a different angle, a softer close, or a new offer. They edit
a markdown file describing the offer or the writing guidance, re-run, and read
the result. No code changes, no test rewrites, no reinstall.

**Why this priority**: This is the durable payoff — the current rebrand required
editing code constants plus their invariant copies plus the tests. Valuable but
not required for the first correct draft.

**Independent Test**: Change a sentence in the offer file, re-run one company,
observe the change in the produced draft with no code modified.

**Acceptance Scenarios**:

1. **Given** an edited instruction file, **When** the batch runs, **Then** the
   produced copy reflects the edit with no code change.
2. **Given** a missing or unreadable instruction file, **When** the batch
   starts, **Then** the run stops before processing any company with a message
   naming the missing file.
3. **Given** an instruction file that tries to grant the model a capability the
   tool does not implement, **When** the batch runs, **Then** the capability
   does not materialize and drafting proceeds under the normal constraints.

---

### User Story 5 - Knowing whether it worked (Priority: P3)

Months from now the operator needs to answer "did personalized copy beat the
template?" Each note records which path wrote it, and the operator can record
what came back from the prospect. The dashboard groups replies by draft source.

**Why this priority**: No immediate effect on a single draft, but the comparison
is impossible to reconstruct later if the data was never captured — and the
template-era baseline disappears the moment the rollout completes.

**Independent Test**: Set outcomes by hand on a few notes of each source and
confirm the dashboard groups and counts them correctly.

**Acceptance Scenarios**:

1. **Given** notes from both drafting paths, **When** the operator opens the
   dashboard, **Then** outcomes are grouped by draft source.
2. **Given** an operator-recorded outcome on a note, **When** the batch
   re-runs, **Then** the recorded outcome is preserved.

---

### Edge Cases

- **Model returns too few or too many blocks** — output outside the accepted
  block count is rejected; the template answers.
- **Model returns a well-formed block whose cited record does not actually
  support the claim** — citation resolution can only prove the record exists
  and was captured for this company; semantic support is not machine-checkable.
  Mitigated by keeping the cited excerpt visible in the note so the operator
  verifies at review time, which is where the approval gate already sits.
- **Model smuggles a second link, a tracking URL, or a booking link into a
  block** — the existing single-promotional-link rule is applied to the
  assembled body; violation rejects the draft.
- **Model writes ad-running or advertising language** — the existing banned
  vocabulary check is applied to the assembled body; violation rejects.
- **Model greets a name that appears in no recorded evidence** — rejected by the
  existing name-traceability check, which now runs against model-written prose.
- **Company has evidence but only weak signals** — the model may cite only the
  offer, producing copy close to the template. This is acceptable output, not a
  failure.
- **Company is messenger-channel** — untouched by this feature; the deterministic
  DM template continues to run with no model call.
- **Company is a duplicate inbox** — drafting behavior is unchanged; duplicates
  are still marked and excluded downstream by the existing send logic.
- **Operator edits the draft text by hand** — the draft region remains
  tool-owned, as today; the operator's lever is approve, reject, or edit-then-
  approve, and an edited note that is then approved is frozen by User Story 3.
- **Instruction files grow large enough to crowd the request** — the assembled
  instruction context is bounded; exceeding the bound is a startup failure, not
  a silent truncation.

## Requirements *(mandatory)*

### Functional Requirements

#### Drafting

- **FR-301**: The system MUST generate email-channel outreach copy by a single
  model request per company per run, supplying that company's recorded research
  records and the operator's instruction files as context.
- **FR-302**: The model MUST receive only already-extracted research records
  (value, kind, source, excerpt) and MUST NOT receive raw fetched page content.
- **FR-303**: The model MUST have no tool access, no network access, and no
  filesystem access during drafting.
- **FR-304**: The system MUST require the model's response to be a structured
  set of prose blocks, each carrying its own list of citations, plus a subject
  line. Unstructured free text MUST be rejected.
- **FR-305**: The system MUST accept between 3 and 6 blocks inclusive; any other
  count MUST be rejected.
- **FR-306**: The system MUST assemble the final body from the returned blocks
  in order, adding the fixed signature; the assembled body is what is written to
  the note and later sent.
- **FR-307**: The system MUST make exactly one drafting request per company per
  run. It MUST NOT retry with a modified prompt, request a repair, or issue a
  second request to fix a rejected draft.
- **FR-308**: Messenger-channel companies MUST continue to use the existing
  deterministic template with no model request.

#### Citation and validation

- **FR-309**: Every block asserting anything about the prospect MUST carry at
  least one citation. A block carrying zero citations MUST cause rejection
  unless it is drawn only from the offer/product/sender vocabulary, which cites
  the reserved offer source.
- **FR-310**: Every citation MUST resolve to a research record captured for that
  same company in that same run. A citation to an unknown, empty, or
  other-company identifier MUST cause rejection.
- **FR-311**: Validation MUST be performed by deterministic program logic. The
  system MUST NOT use a model to judge, score, or approve any draft.
- **FR-312**: The system MUST apply to the assembled body every check that
  guards the current template path: banned advertising vocabulary, exactly one
  promotional link which MUST be the product URL, no professional-network link
  in the pitch, an intact signature, no unfilled placeholder markers, and a
  greeting name that traces to recorded evidence or the operator-supplied owner
  name column.
- **FR-313**: The subject line MUST be validated against the company name as it
  is today: it may only contain words drawn from the company's own name.
- **FR-314**: When validation rejects a draft, the system MUST record every
  reason for the rejection so the operator can see why the model's output was
  discarded.

#### Fallback

- **FR-315**: On model failure, unparseable output, or validation rejection, the
  system MUST fall back to the existing locked-template draft for that company.
- **FR-316**: The locked-template path MUST remain functional, unchanged in
  behavior, and covered by its own tests independent of the model path.
- **FR-317**: When a company has no research records to cite, the system MUST
  use the locked template directly without issuing a model request.
- **FR-318**: A fallback MUST NOT abort the batch; processing continues with the
  next company.
- **FR-319**: Each note MUST record which path produced its copy.
- **FR-320**: The run summary MUST report the number of companies drafted by
  each path and the reasons for fallbacks.

#### Instruction files

- **FR-321**: The operator's instruction content — sender identity, the offer,
  the hard constraints, and writing guidance — MUST live in version-controlled
  markdown files, separate from program code.
- **FR-322**: Editing an instruction file MUST change the produced copy with no
  code change required.
- **FR-323**: A missing or unreadable required instruction file MUST stop the
  run before any company is processed, naming the file.
- **FR-324**: Instruction files MUST NOT contain secrets or credentials, and
  MUST NOT be able to grant the model capabilities the program does not
  implement.
- **FR-325**: The assembled instruction context MUST be bounded in size;
  exceeding the bound MUST fail at startup rather than silently truncate.

#### Re-draft scope and note safety

- **FR-326**: The system MUST NOT regenerate, alter, or replace the draft of a
  note whose status is approved or sent, and MUST NOT issue a model request for
  such a company.
- **FR-327**: Notes awaiting review MUST have their drafts regenerated on a
  re-run.
- **FR-328**: Existing preservation of operator-owned regions — status, log
  history, and operator-added sections — MUST be unchanged.
- **FR-329**: Re-runs MUST remain byte-idempotent when nothing has changed:
  identical research plus an identical model response MUST produce an identical
  note.

#### Send path

- **FR-330**: The send path MUST NOT issue any model request, and MUST NOT
  generate, rewrite, complete, or alter subject or body text. It delivers what
  the note contains, verbatim.

#### Measurement

- **FR-331**: Each note MUST carry an operator-editable outcome field, empty by
  default, for recording what came back from the prospect.
- **FR-332**: The operator-recorded outcome MUST be preserved across re-runs.
- **FR-333**: The dashboard MUST let the operator compare outcomes grouped by
  which path produced the copy.

### Key Entities

- **Draft Block**: One paragraph-sized unit of model-written prose plus the list
  of citations supporting it. The unit of validation.
- **Citation**: A reference from a block to either a research record captured
  for that company, or the reserved offer source used for product, offer, and
  sender facts.
- **Research Record**: An existing captured fact — its kind, value, source URL,
  and text excerpt. This feature gives each one a stable identifier so blocks
  can refer to it.
- **Instruction Set**: The collection of markdown files supplying sender
  identity, offer description, hard constraints, and writing guidance.
- **Draft Source**: Which path produced a note's copy — the model or the locked
  template.
- **Outcome**: The operator's record of what the prospect did, used only for
  comparing the two drafting paths.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-301**: Across a 30-company batch, no two produced emails are byte-
  identical in their personalized portion, where the underlying research
  differs.
- **SC-302**: Every personalized statement in every produced draft traces to a
  research record an operator can inspect from the same note, in 100% of cases.
- **SC-303**: Zero drafts containing an uncited claim about the prospect reach a
  note; every such attempt falls back to the template instead.
- **SC-304**: Every input row still yields a note, matching today's guarantee,
  including when the model path fails for every company in the batch.
- **SC-305**: A batch run with the model path entirely unavailable produces
  output equivalent to today's template-only output.
- **SC-306**: Zero notes at approved or sent status have their draft text
  altered by any re-run.
- **SC-307**: An operator can change the sender's offer wording and observe the
  change in produced copy without editing code, in under five minutes.
- **SC-308**: The operator can determine, from the dashboard alone, the reply
  rate of each drafting path once outcomes have been recorded.
- **SC-309**: Drafting cost per company stays within three times the current
  per-company cost.
- **SC-310**: The rejection rate of model drafts is observable after every run,
  so a degraded drafting path is detected within one batch rather than
  discovered later.

## Assumptions

- The existing research stage already captures enough per-company signal to make
  personalization worthwhile; this feature adds no new research capability.
- The operator reviews every draft in Obsidian before approving, so semantic
  mis-citation (a real record that does not actually support the sentence) is
  caught by the human gate that already exists.
- Copy remains plain text, single promotional link, no tracking, no attachments.
- The reserved offer source is a fixed, tool-owned identifier rather than a
  research record, since offer and product facts are not observations about the
  prospect.
- Re-drafting the existing awaiting-review notes in one pass is acceptable
  review burden for the operator.
- Model cost per company rises relative to the current two-slot call; the
  bound in SC-309 is the accepted ceiling.

## Dependencies

- Constitution v5.0.0, Principles I, IV, V, VI.
- The existing research and scoring stages, unchanged.
- The existing locked-template drafting path, retained as the fallback floor.
- The existing note merge semantics for operator-owned regions.

## Out of Scope

- Any change to the send pipeline's selection, cap, pacing, ledger, or transport
  behavior.
- Agent-written Messenger DMs.
- Automated reply detection, inbox polling, or any read access to the mailbox.
- Multi-step, tool-using, or self-critiquing drafting loops.
- A/B assignment logic; the comparison is observational, from recorded outcomes.
- Follow-up sequences or multi-touch campaigns.
