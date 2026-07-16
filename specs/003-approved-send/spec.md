# Feature Specification: Approved Send

**Feature Branch**: `003-approved-send`  
**Created**: 2026-07-15  
**Status**: Draft  
**Input**: User description: "Automated sending of human-approved outreach notes via Gmail API, dry-run default, ramped daily cap, immutable send ledger"

## Overview

Today the operator drafts outreach into the Obsidian vault and sends every message by hand from their inbox. At the target volume (up to ~100/day) manual sending is impractical, and hand-tracking what was sent has already caused uncertainty about which notes went out (double-send risk). This feature adds a guarded, human-in-the-loop send stage: the operator reviews a draft and marks it **approved** in the vault; a single command then delivers only the approved notes from the dedicated Nestaro outreach account, respecting a ramped daily cap, defaulting to a safe preview, and recording every send in an immutable ledger so nothing is ever sent twice.

The human remains the sole approver. The tool never decides *what* to say or *whether* to send — it only carries out sends the human has explicitly blessed, within hard limits.

## Clarifications

### Session 2026-07-15

- Q: When does "week 1" of the ramped cap schedule begin? → A: On the date of the first send recorded in the ledger (auto-detected; prior manual sends from the personal inbox do not count).
- Q: How should sends within a run be paced? → A: Space them out with a short randomized delay between each send (default ~30–90s) to mimic human sending and protect deliverability.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Send the approved queue with one command (Priority: P1)

The operator has reviewed drafts in the vault and marked several notes `status: approved`. They run the send command. Every approved note is delivered from the Nestaro outreach account, each delivered note's status flips to `sent` with a timestamp, and each send is recorded in the ledger. Notes not marked `approved` are untouched.

**Why this priority**: This is the core value — turning approved drafts into delivered emails without manual copy-paste. Without it, the feature delivers nothing.

**Independent Test**: Mark 2 notes `approved` in a test vault, run the command in real-send mode against a test recipient, and confirm both arrive, both statuses become `sent` with timestamps, and both appear in the ledger — while a third `to-send` note is left unchanged.

**Acceptance Scenarios**:

1. **Given** 3 notes marked `approved` and today's cap is 15, **When** the operator runs the send command in real-send mode, **Then** all 3 are emailed from the Nestaro account, their statuses become `sent` with a timestamp, and 3 ledger entries are appended.
2. **Given** a note with `status: to-send` (not approved), **When** send runs, **Then** that note is skipped and left unchanged.
3. **Given** a note marked `approved` on the messenger channel (no email address), **When** send runs, **Then** it is skipped and reported as not sendable (email channel only).

---

### User Story 2 - Safe by default: preview before anything leaves (Priority: P1)

The operator runs the send command without the explicit real-send flag. Nothing is sent. Instead the tool reports exactly which notes it *would* send, to which addresses, and how many that is against today's remaining cap. Only when the operator re-runs with the explicit real-send flag does anything actually go out.

**Why this priority**: A single mistaken run must never blast the vault. Dry-run-by-default is the primary guardrail and is required by the constitution (Principle I).

**Independent Test**: Run the command with no flags against a vault of approved notes; confirm zero emails are sent, zero statuses change, zero ledger entries are written, and the preview lists the intended recipients and count.

**Acceptance Scenarios**:

1. **Given** 5 approved notes, **When** the operator runs send with no real-send flag, **Then** no email is sent, no status changes, no ledger entry is written, and a preview of the 5 intended sends is shown.
2. **Given** the same 5 notes, **When** the operator runs send with the explicit real-send flag, **Then** the sends are actually performed.

---

### User Story 3 - Never exceed the ramped daily cap (Priority: P1)

Sending volume must ramp up over time to protect the account's reputation. The tool reads today's cap from a ramped schedule, checks the ledger for how many have already been sent today, and sends at most the remaining allowance. If more notes are approved than today's cap permits, the excess stay `approved` for a later day, and the tool reports how many it deferred.

**Why this priority**: Exceeding the cap risks getting the sending account flagged or suspended, which destroys the whole channel. The cap is a hard safety limit, not a preference.

**Independent Test**: Set today's cap to 2, mark 5 notes approved, run in real-send mode; confirm exactly 2 are sent, 3 remain `approved`, and the tool reports "2 sent, 3 deferred (daily cap reached)."

**Acceptance Scenarios**:

1. **Given** today's cap is 2 and 5 notes are approved, **When** send runs in real-send mode, **Then** exactly 2 are sent and 3 remain `approved`.
2. **Given** today's cap is 15 and 10 were already sent today (per ledger), **When** send runs, **Then** at most 5 more are sent.
3. **Given** today's cap has already been reached, **When** send runs, **Then** nothing is sent and the tool reports the cap is exhausted for today.

---

### User Story 4 - Connect the Nestaro account once (Priority: P2)

The first time the operator sends, they authorize the tool to send as the Nestaro outreach account. This one-time approval is remembered so future runs send without re-authorizing. The tool refuses to send from anything other than the designated Nestaro account.

**Why this priority**: Sending can't happen without authorization, but it's a one-time setup, so it's below the everyday send flows in priority.

**Independent Test**: On a machine with no stored authorization, run send in real-send mode; confirm the tool guides the operator through a one-time authorization for the Nestaro account, then completes the send; on the next run, confirm no re-authorization is required.

**Acceptance Scenarios**:

1. **Given** no stored authorization, **When** the operator runs send in real-send mode, **Then** the tool initiates a one-time authorization for the Nestaro account and, once granted, proceeds.
2. **Given** a stored authorization for the Nestaro account, **When** send runs again, **Then** no re-authorization is needed.
3. **Given** an authorization that resolves to any account other than the designated Nestaro account, **When** send runs, **Then** the tool refuses to send and reports the mismatch.

---

### User Story 5 - Failures never lose a note or double-send (Priority: P2)

If a single send fails (network error, rejected recipient), that note is left `approved` (not marked sent), the error is recorded, and the run continues with the remaining notes. A note already recorded as sent in the ledger is never sent again, even if its status was manually reset.

**Why this priority**: Silent drops and accidental re-sends both erode trust and waste the daily cap; resilience makes the tool safe to run repeatedly.

**Independent Test**: Simulate a failure on the 2nd of 3 approved notes; confirm notes 1 and 3 send and become `sent`, note 2 stays `approved` with a logged error, and the run reports "2 sent, 1 failed."

**Acceptance Scenarios**:

1. **Given** 3 approved notes and the 2nd fails to send, **When** send runs, **Then** notes 1 and 3 are sent and note 2 remains `approved` with the failure recorded; the run does not abort.
2. **Given** a note whose recipient already appears as a successful send in the ledger, **When** send runs, **Then** it is not sent again and is reported as already-sent.

---

### Edge Cases

- **Duplicate inbox**: two approved notes share one email address → the second is treated as already-sent for that address within the run and deferred/flagged (consistent with the existing "one send per inbox" rule).
- **Malformed or missing email** on an approved note → skipped and reported as not sendable; never guessed.
- **Draft missing a subject or body** under `## Draft` → skipped and reported; the tool never sends an empty or partial message.
- **Approved count exceeds cap** → send up to the cap, defer the rest, report the deferred count.
- **Cap is zero for today** (e.g., schedule not yet started) → nothing sends; tool explains why.
- **Interrupted run** (killed mid-batch) → notes already sent are in the ledger and marked `sent`; re-running resumes without re-sending them.
- **Clock/day boundary**: the daily count is scoped to the calendar day in the operator's local timezone; a run spanning midnight uses the day at send time per entry.
- **Authorization expired/revoked** → send stops with a clear message to re-authorize; nothing is half-sent silently.
- **Ledger and vault disagree** (note says `sent` but no ledger entry, or vice versa) → the ledger is authoritative for "already sent"; the tool reports the discrepancy.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST send only notes whose vault status is exactly `approved`; notes in any other status (`to-send`, `sent`, `replied`, `pilot`, `dead`) MUST be skipped.
- **FR-002**: The system MUST default to a dry-run: with no explicit real-send flag, it performs no sends, changes no statuses, and writes no ledger entries, but reports the notes and count it would send.
- **FR-003**: The system MUST perform real sends only when the operator supplies an explicit real-send flag.
- **FR-004**: The system MUST send only from the designated Nestaro outreach account (`nestaroassistant@gmail.com`) and MUST refuse to send if the active authorization resolves to any other account, including the operator's personal account.
- **FR-005**: The system MUST send only over email (the approved-send channel); notes on the messenger channel MUST be skipped.
- **FR-006**: The system MUST enforce a configurable ramped daily cap and MUST NOT send more than (today's cap − sends already recorded today) in any run.
- **FR-007**: The system MUST determine "sends already recorded today" from the immutable ledger, not from vault statuses.
- **FR-008**: On a successful send, the system MUST (a) append a ledger entry and (b) update the note's status to `sent` with a send timestamp.
- **FR-009**: The ledger MUST be append-only and MUST record, per send: recipient address, note identifier (slug), timestamp, provider message identifier, and result.
- **FR-010**: The system MUST NOT send to a recipient/note that already has a successful send recorded in the ledger (idempotency / no double-send), regardless of the note's current status.
- **FR-011**: On a send failure, the system MUST leave the note `approved`, record the failure (with reason), continue processing remaining notes, and never mark a failed note as `sent`.
- **FR-012**: The system MUST NOT change any note's status to `approved` itself under any circumstance; only a human sets `approved`.
- **FR-013**: The system MUST read the message subject and body from the note's existing `## Draft` section and MUST skip (and report) any approved note missing a subject or body.
- **FR-014**: The system MUST send at most one message per unique recipient address per run (duplicate inboxes collapse to one send).
- **FR-015**: The one-time account authorization MUST be stored locally in a location excluded from version control and reused on subsequent runs without re-authorization until it expires or is revoked.
- **FR-016**: Every run MUST end with a summary reporting counts of: sent, deferred (cap), skipped (not approved / not sendable), and failed — with enough detail to identify affected notes.
- **FR-017**: The daily cap schedule (the ramp values and progression) MUST be operator-configurable without code changes.
- **FR-018**: The system MUST NOT expose, log, or commit account credentials or tokens.
- **FR-019**: When performing real sends, the system MUST space consecutive sends apart by a randomized delay (default range ~30–90 seconds) to mimic human sending; the delay range MUST be operator-configurable, and dry-run MUST NOT apply any delay.

### Key Entities

- **Approved note**: a vault note the human has marked `status: approved`; carries the recipient `email`, the `channel`, and a `## Draft` section containing a subject line and body. It is the unit of sending.
- **Send ledger**: an append-only record of every send; the source of truth for the daily count and for double-send prevention. Fields: recipient, note slug, timestamp, provider message id, result.
- **Daily cap schedule**: an operator-configurable, ramped mapping from elapsed time (e.g., week-since-start) to a maximum number of sends per day.
- **Account authorization**: the stored, one-time grant that lets the tool send as the Nestaro account; scoped to sending only; excluded from version control.
- **Send run report**: the per-run summary of sent / deferred / skipped / failed outcomes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can send the entire approved queue for the day with a single command, with no manual copy-paste into an email client.
- **SC-002**: In 100% of runs without the explicit real-send flag, zero emails are sent and zero notes change status.
- **SC-003**: Across any sequence of runs in a single day, the number of emails actually sent never exceeds that day's configured cap.
- **SC-004**: No recipient/note is ever sent the same outreach message twice, verifiable by cross-checking the ledger against delivered mail.
- **SC-005**: After a run, 100% of notes shown as `sent` have a corresponding ledger entry, and no `sent` note is missing from the ledger.
- **SC-006**: A single failed send never aborts the run and never causes a note to be marked `sent`; the affected note remains `approved` and is reported.
- **SC-007**: The tool never sends from any account other than the designated Nestaro account (verified: an authorization for a different account is refused).
- **SC-008**: After first-time authorization, the operator can run subsequent days' sends without re-authorizing (until the grant expires/revokes).

## Assumptions

- **Ramp anchor** (resolved, Clarifications 2026-07-15): "week 1" of the cap schedule begins on the date of the first send recorded in the ledger, auto-detected; prior manual sends (done outside this tool, from the personal inbox) do not count toward the ramp or the daily cap.
- **Day boundary**: the daily cap is scoped to the calendar day in the operator's local machine timezone.
- **Send order**: when approved notes exceed the remaining cap, oldest-approved-first is sent; the remainder defer to a later day.
- **Inter-send pacing** (resolved, Clarifications 2026-07-15): real sends are spaced by a randomized delay (default ~30–90s, operator-configurable); a full-cap run therefore takes time and is expected to run as a background task. Dry-run applies no delay.
- **Default ramp values** (operator-editable): week 1 = 15/day, week 2 = 30/day, week 3 = 60/day, week 4+ = 100/day.
- **Subject/body source**: the message is taken verbatim from the note's `## Draft` section (subject line + body); this feature does not re-draft or restyle copy (consistent with locked-template honesty rules).
- **One recipient per note**: each note targets a single email address from its frontmatter; no CC/BCC/multi-recipient sending.
- **Plain, personal-style email**: outreach is sent as a simple email (no tracking pixels, no HTML campaign markup), consistent with the "looks like a human sent it" intent.

## Constraints (from Constitution v3.0.0, Principle I)

- Email channel only, via the Gmail API, from the Nestaro account — never the personal account, never another channel.
- Dry-run by default; real sends require an explicit flag.
- Hard ramped daily cap enforced against the ledger.
- Immutable ledger; never auto-approve; never send anything not `approved`; never send past the cap.

## Out of Scope

- Drafting, scoring, sourcing, or any change to message content (owned by features 001/002).
- Reply handling, open/click tracking, or campaign analytics.
- Any sending channel other than email (no Messenger send).
- A general-purpose or transactional-ESP sender.
- Custom domain / SPF-DKIM-DMARC setup (a free Gmail account is used initially; see Risks).

## Risks

- **Deliverability ceiling**: a free Gmail account cannot publish SPF/DKIM/DMARC, so cold volume is more likely to land in spam; the realistic daily cap may plateau below 100 regardless of the schedule. The ramp mitigates account-suspension risk but not spam-folder placement.
- **Account suspension**: cold outreach at volume can still trigger provider action; the ramp and cap reduce but do not eliminate this. Losing the account loses the channel (not the operator's identity, since a dedicated account is used).
