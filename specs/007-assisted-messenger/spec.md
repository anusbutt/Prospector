# Feature Specification: Assisted-Manual Messenger Send

**Feature Branch**: `007-assisted-messenger`
**Created**: 2026-07-24
**Status**: Draft
**Input**: User description: "Assisted-manual Messenger send. Add a `prospector dm` command that walks approved messenger-channel notes one at a time, copies the draft body to the clipboard, opens the company's Facebook URL in the user's own browser, and — after the human confirms they sent it manually — records the send to a dedicated DM ledger and flips the note to sent. The tool never contacts Facebook. Also add a `facebook_url` frontmatter field to messenger notes."

## Overview

Prospector already writes a finished, deterministic outreach draft into every
Messenger-channel note, but the delivery of those drafts is entirely unassisted.
The operator must hunt through the vault for approved Messenger notes, locate the
company on Facebook, copy the draft text, paste it into Messenger, and send —
then remember which ones are done. This is slow, error-prone, and easy to lose
your place in across a large batch.

This feature adds a guided delivery loop for Messenger prospects. The operator
approves a Messenger note exactly as they approve an email note, then runs a
single command that walks the approved notes one at a time: it puts the draft on
the clipboard and opens the company's Facebook page in the operator's own
browser. The operator pastes, sends by hand, and confirms. The tool then records
the send in a dedicated ledger and marks the note as sent, so the same company
is never queued again.

The defining constraint is unchanged from the rest of the product: **Prospector
never contacts Facebook.** The tool opens a page in the operator's own browser
and manages a to-do list; the only party that ever communicates with Facebook is
the human, logged into their own account. This preserves the constitutional
guarantee that outbound automated traffic never reaches a Facebook host, while
removing almost all of the manual toil.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Guided delivery of one approved Messenger note (Priority: P1)

The operator has approved a Messenger-channel note. They run the delivery
command. For that note, the tool copies the draft body to the clipboard, shows
the company name and message, opens the company's Facebook page in the
operator's browser, and pauses. The operator pastes the message, sends it by
hand, returns to the terminal, and confirms it was sent. The tool records the
send and flips the note to `sent`.

**Why this priority**: This is the entire value of the feature — turning a
multi-step manual chore into a paste-and-confirm. Without it there is no feature.

**Independent Test**: With one approved Messenger note carrying a Facebook URL,
run the command in real mode, confirm the send, and verify (a) the browser open
and clipboard copy were requested, (b) a ledger record exists, (c) the note's
status is now `sent` with a log entry, and (d) no outbound HTTP request was made
to any Facebook host.

**Acceptance Scenarios**:

1. **Given** an approved Messenger note with a Facebook URL and a valid draft
   body, **When** the operator runs the command in real mode and confirms the
   send, **Then** the draft body is copied to the clipboard, the Facebook URL is
   opened in the operator's browser, a ledger record is written, and the note
   becomes `sent`.
2. **Given** the same note, **When** the operator declines to confirm the send,
   **Then** nothing is recorded, the note stays `approved`, and the loop moves
   on without altering that note.

---

### User Story 2 - Safe preview before touching anything (Priority: P1)

The operator wants to see which Messenger notes would be walked, and in what
order, without opening any browser tabs or changing any note. They run the
command with no send flag. The tool lists the eligible approved Messenger notes
and a per-note reason for anything skipped, opens nothing, copies nothing, and
writes nothing.

**Why this priority**: Mirrors the dry-run-by-default safety contract of the
existing send command. A destructive-feeling action (opening browser tabs,
changing note state) must never be the default.

**Independent Test**: Run the command with no send flag against a vault
containing approved, unapproved, and already-delivered Messenger notes; verify
the summary counts are correct and that no browser, clipboard, ledger, or note
mutation occurred.

**Acceptance Scenarios**:

1. **Given** a vault with approved Messenger notes, **When** the operator runs
   the command without the send flag, **Then** a preview summary is printed and
   no browser opens, no clipboard write occurs, no ledger record is written, and
   no note status changes.
2. **Given** the preview, **When** it is displayed, **Then** each already-
   delivered or non-sendable note is shown with a reason rather than silently
   omitted.

---

### User Story 3 - Never deliver the same prospect twice (Priority: P1)

The operator delivered a Messenger note yesterday. Today they re-approve notes
and run the command again. The previously delivered company is not offered for
delivery again, even if its note status was changed back to `approved`.

**Why this priority**: This is the same duplicate-protection guarantee the email
send path provides, and it is what the operator directly relied on in practice.
Re-contacting a prospect is a real-world harm, not just a bug.

**Independent Test**: Deliver a note (recording it in the DM ledger), reset its
status to `approved`, run again, and verify it is reported as already-delivered
and never re-queued.

**Acceptance Scenarios**:

1. **Given** a company already recorded in the DM ledger, **When** the command
   runs, **Then** that company is skipped as already-delivered and no browser
   opens for it.
2. **Given** two approved Messenger notes sharing the same Facebook target in
   one run, **When** the command walks them, **Then** the second is treated as a
   duplicate within the run and not delivered twice.

---

### User Story 4 - A machine-readable Facebook target on every Messenger note (Priority: P2)

Messenger notes today store the Facebook link only inside free-text research
prose (when it exists at all). The operator wants the delivery command to open
the right page reliably, and wants to see the target link in the note's
structured header.

**Why this priority**: Without a dependable target the delivery loop degrades to
"go find them yourself," which erodes the feature's value. It is P2 because the
loop still functions (with a graceful fallback) when a link is absent.

**Independent Test**: Re-run research on a Messenger company that has a Facebook
signal or input Facebook URL; verify the note's structured header now carries a
`facebook_url` value, and that existing notes without one keep their previous
field order unchanged.

**Acceptance Scenarios**:

1. **Given** a Messenger company with an input Facebook URL or a discovered
   active-Facebook signal, **When** its note is written, **Then** the note's
   structured header includes a `facebook_url` value.
2. **Given** an existing note produced before this feature, **When** it is
   refreshed, **Then** the new field is appended without reordering or losing any
   existing header field or human-owned content.

---

### User Story 5 - Graceful handling when there is no Facebook link (Priority: P3)

The operator reaches an approved Messenger note that has no Facebook link on
file. The tool still copies the draft and shows the company name, but instead of
opening a page it tells the operator no link is on file and to locate the company
manually. The operator can still confirm or skip.

**Why this priority**: Many Messenger notes arise from a blank email field and
carry no Facebook link at all; the loop must not crash or silently drop them.

**Independent Test**: Run against an approved Messenger note with no Facebook
link and verify the loop presents it, opens no browser, and lets the operator
confirm or skip.

**Acceptance Scenarios**:

1. **Given** an approved Messenger note with no Facebook link, **When** the
   command reaches it in real mode, **Then** the draft is still copied, a "no
   link on file" notice is shown, no browser opens, and the operator may confirm
   or skip.

---

### Edge Cases

- **Approved note that is not sendable** (empty draft body): reported as skipped
  with a reason, never delivered.
- **Operator interrupts mid-batch**: every already-confirmed note is safely
  recorded; the run can be resumed and confirmed notes are not re-offered.
- **Clipboard unavailable** on the operator's platform: the draft body is shown
  in the terminal for manual copying and the loop continues rather than aborting.
- **Browser cannot be opened**: the operator is shown the Facebook URL to open
  manually and the loop continues.
- **Limit reached**: an optional per-run limit stops the walk early; unwalked
  notes remain `approved`.
- **Note whose channel is email**: never enters this loop; it belongs to the
  existing email send path.

## Requirements *(mandatory)*

### Functional Requirements

#### Delivery command

- **FR-001**: The system MUST provide a command that walks vault notes whose
  status is `approved` and whose channel is Messenger, one at a time.
- **FR-002**: The command MUST default to a non-destructive preview that opens no
  browser, writes to no clipboard, records no ledger entry, and changes no note.
- **FR-003**: The command MUST require an explicit opt-in flag to perform real
  delivery (browser open, clipboard copy, ledger write, status change).
- **FR-004**: In real mode, for each eligible note the system MUST copy the draft
  body to the clipboard and open the note's Facebook URL in the operator's own
  browser before pausing for confirmation.
- **FR-005**: The system MUST require a per-note human confirmation before
  recording a send or changing a note's status; declining leaves the note
  `approved` and unrecorded.
- **FR-006**: The command MUST accept an optional limit that caps how many notes
  are walked in a run, and MUST support selecting an alternate vault folder,
  consistent with existing commands.

#### Facebook contact boundary

- **FR-007**: The system MUST NOT make any outbound network request to a Facebook
  or Messenger host as part of this feature; the existing outbound host guard
  MUST remain in force and unmodified in intent.
- **FR-008**: The only Facebook interaction the feature performs MUST be handing a
  URL to the operator's own browser for the operator to act on.

#### Content and honesty

- **FR-009**: The delivered message body MUST be the existing deterministic,
  validated Messenger draft; this feature MUST NOT introduce a model call or
  alter draft content.
- **FR-010**: An approved Messenger note with no valid draft body MUST be
  reported as skipped and MUST NOT be delivered.

#### Duplicate protection and ledger

- **FR-011**: The system MUST record each confirmed delivery in a dedicated
  Messenger delivery ledger, separate from the email send ledger so that email
  cap accounting is unaffected.
- **FR-012**: The system MUST skip any company already recorded in the Messenger
  ledger, even if its note status was reset to `approved`.
- **FR-013**: Within a single run, the system MUST treat repeat Facebook targets
  as duplicates and deliver each at most once.
- **FR-014**: Each ledger record MUST identify the note, the company, the
  Facebook target (if any), and mark the delivery as human-performed (no
  automated message identifier is produced).

#### Note state

- **FR-015**: On confirmed delivery, the system MUST change the note's status
  from `approved` to `sent` and append a single log entry, leaving every other
  header field and human-owned section byte-identical.
- **FR-016**: The status change MUST be the only automatic status transition this
  feature performs.

#### Facebook URL field

- **FR-017**: Messenger notes MUST carry a structured `facebook_url` field in
  their header, populated from the company's input Facebook URL when present, or
  otherwise from a discovered active-Facebook signal.
- **FR-018**: The new field MUST be appended to the existing header field order
  so that notes created before this feature keep their field order and do not
  produce spurious reordering diffs on the first refresh.
- **FR-019**: When no Facebook link is available, the field MUST be present but
  empty, and the delivery command MUST still present the note with a "no link on
  file" notice.

#### Reporting

- **FR-020**: The command MUST print a summary distinguishing delivered,
  skipped-already-delivered, skipped-not-sendable, and (in preview) would-deliver
  counts, and MUST show a per-note reason for skipped notes.

### Key Entities

- **Messenger delivery candidate**: A parsed view of one approved
  Messenger-channel note — its slug, company, Facebook target (possibly absent),
  draft body, and note path — used to drive one step of the delivery loop.
- **Messenger delivery ledger record**: An append-only record of one confirmed,
  human-performed Messenger delivery, used for duplicate protection and audit;
  distinct from the email send ledger.
- **Facebook URL field**: A structured header value on Messenger notes naming the
  operator's delivery target, sourced from input or discovered signals.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can deliver an approved Messenger note end to end with
  a single command and one confirmation per note, without manually searching the
  vault or copying text by hand.
- **SC-002**: 100% of confirmed Messenger deliveries are recorded such that
  re-running the command never re-offers an already-delivered company.
- **SC-003**: Running the command in preview mode changes nothing: zero browser
  tabs opened, zero clipboard writes, zero ledger records, zero note mutations.
- **SC-004**: Across any run, zero outbound network requests reach a Facebook or
  Messenger host.
- **SC-005**: Every Messenger note produced or refreshed after this feature
  carries a `facebook_url` header field, and refreshing a pre-existing note
  introduces no reordering of previously present header fields.
- **SC-006**: An approved Messenger note with no Facebook link is still presented
  for delivery and never causes the command to fail.

## Assumptions

- The operator runs the command interactively at a terminal, on a machine with a
  browser and (usually) a clipboard; the loop degrades gracefully when either is
  unavailable.
- Confirmation is trust-based: the operator asserting "sent" is treated as
  ground truth, since the tool cannot and must not observe Facebook to verify.
- The existing deterministic Messenger draft template already produces the final
  message; no personalization beyond current behavior is in scope.
- A weekly cap/pacing ramp like the email path is not required for manual
  delivery; if desired it can be layered later without changing this contract.
- The Messenger ledger's default location is a local, gitignored file alongside
  the existing send ledger.

## Dependencies

- The existing vault note format, status model, and scoped status-write behavior.
- The existing deterministic Messenger draft generation and validation.
- The existing append-only ledger mechanics (reused with a separate ledger file).
- The existing outbound host guard, which must remain the sole authority that
  blocks Facebook network traffic.

## Out of Scope

- Any automated sending of Facebook or Messenger messages.
- Any request to, scraping of, or authentication against Facebook by the tool.
- Personalizing or re-generating Messenger draft copy (owned by prior features).
- A weekly cap ramp or randomized pacing for manual delivery.
- Tracking prospect replies or outcomes beyond the human-owned `outcome` field.
