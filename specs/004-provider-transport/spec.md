# Feature Specification: Provider-Neutral Send Transport (Zoho SMTP)

**Feature Branch**: `004-provider-transport`
**Created**: 2026-07-17
**Status**: Draft
**Input**: User description: "Replace the Gmail-only sending architecture with a
provider-agnostic email transport while preserving Gmail support and adding
authenticated SMTP support for Zoho Mail (anas@omniveer.com), keeping every
approved-send guarantee unchanged."

## Overview

Feature 003 delivers approved outreach notes exclusively via the Gmail API from a
free Gmail account. A free Gmail account cannot publish SPF/DKIM/DMARC, which caps
deliverability well below the target volume. The operator now owns a custom-domain
mailbox — `anas@omniveer.com` on Zoho Mail — that can publish those records.

This feature makes the send stage **provider-neutral**: the pipeline talks to an
abstract email sender, and configuration selects one of exactly two transports —
the existing Gmail API path (unchanged, backward compatible) or authenticated
SMTP (Zoho). Every approved-send guarantee from 003 is preserved verbatim; the
only thing that changes is *how* a verified, approved, capped send leaves the
machine.

Constitution v4.0.0 (amended 2026-07-17, human-approved) sanctions the SMTP
channel and replaces the hardcoded Nestaro Gmail identity with a required,
configured dedicated outreach mailbox.

## Invariants carried over from 003 (unchanged, non-negotiable)

- Only notes with `status: approved` are ever sent (FR-001/012 of 003).
- Dry-run is the default; a real send requires the explicit `--send` flag.
- The tool never auto-approves anything.
- The ramped daily cap and randomized inter-send delays are enforced unchanged.
- The append-only ledger remains the source of truth; recipient- and slug-based
  double-send prevention is unchanged.
- A note flips `approved → sent` only after the transport confirms acceptance;
  a failed send leaves the note `approved` and never aborts the batch.
- Exit codes are preserved: 0 completed, 1 pre-flight failure, 2 identity
  mismatch, 3 authentication failure.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Send approved notes through the Omniveer mailbox (Priority: P1)

The operator configures the SMTP provider with their Zoho mailbox
(`anas@omniveer.com`), approves notes in Obsidian, and runs the send command with
`--send`. Each approved note is delivered from
`Anas from Omniveer <anas@omniveer.com>`, flips to `sent`, and is recorded in the
ledger with the generated Message-ID.

**Independent Test**: with SMTP config pointing at a stub server, 2 approved
notes → 2 deliveries with the formatted From header, 2 `sent` statuses, 2 ledger
rows carrying Message-IDs.

**Acceptance Scenarios**:

1. **Given** provider `smtp` fully configured and 2 approved notes, **When** the
   operator runs a real send, **Then** both are delivered with
   `From: Anas from Omniveer <anas@omniveer.com>`, a `Reply-To` when configured,
   a `Date` header, and a generated `Message-ID`; both notes become `sent`; both
   ledger rows record the Message-ID.
2. **Given** the same setup run **without** `--send`, **Then** no SMTP
   connection is opened, nothing authenticates, no status changes, no ledger
   writes — only the preview is printed.
3. **Given** a recipient the SMTP server refuses, **When** send runs, **Then**
   that note stays `approved`, a `failed` ledger row is written, and the batch
   continues.

---

### User Story 2 - Gmail keeps working exactly as before (Priority: P1)

An operator who has not changed their configuration (or who sets
`PROSPECTOR_SEND_PROVIDER=gmail`) gets the 003 behavior unchanged: OAuth
identity check, Gmail REST send, Gmail message id in the ledger.

**Independent Test**: the entire existing 003 test suite passes with the
provider defaulted to `gmail`, with no weakened assertions.

**Acceptance Scenarios**:

1. **Given** provider `gmail` (the default), **When** send runs, **Then**
   behavior, exit codes, and ledger contents match feature 003.
2. **Given** a Gmail OAuth identity that differs from `PROSPECTOR_SEND_FROM`,
   **Then** the run aborts with exit code 2 and nothing is sent.

---

### User Story 3 - Misconfiguration fails safely, before anything sends (Priority: P1)

Missing or invalid SMTP settings are caught in pre-flight: missing password,
invalid security mode, or a From address that does not match the authenticated
SMTP username all abort the run before any message is attempted.

**Independent Test**: each broken config variant exits non-zero with a clear
message, zero deliveries, zero ledger rows, zero status changes.

**Acceptance Scenarios**:

1. **Given** provider `smtp` with no `PROSPECTOR_SMTP_PASSWORD`, **When** a real
   send runs, **Then** it fails pre-flight (exit 1) with a message naming the
   missing variable — the password value itself is never echoed.
2. **Given** `PROSPECTOR_SMTP_SECURITY=tlsv9` (invalid), **Then** pre-flight
   fails (exit 1) listing the valid modes (`ssl`, `starttls`).
3. **Given** `PROSPECTOR_SEND_FROM=someoneelse@omniveer.com` while
   `PROSPECTOR_SMTP_USERNAME=anas@omniveer.com`, **Then** the run refuses with
   exit code 2 before any connection is used for sending (no From spoofing).
4. **Given** valid config but a wrong password, **When** a real send runs,
   **Then** authentication fails with exit code 3, nothing sent, and the error
   output contains no password material.

---

### Edge Cases

- **Address-case differences** (`Anas@Omniveer.com` vs `anas@omniveer.com`) —
  comparison is case-insensitive after normalization; no false mismatch.
- **Port/security combinations** — `ssl` implies implicit TLS (default port
  465); `starttls` implies plaintext-then-upgrade (default port 587); an
  explicit `PROSPECTOR_SMTP_PORT` overrides the default for either mode.
- **No display name configured** — the From header degrades to the bare
  address; sending is not blocked.
- **No Reply-To configured** — the header is simply omitted.
- **Transient network failure mid-batch** — that send is recorded `failed`, the
  note stays `approved`, and the loop continues (one connection per message, so
  one broken connection cannot poison the rest).
- **Secrets in output** — no code path may place the SMTP password in an
  exception message, log line, report, or ledger row.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-101**: The send pipeline MUST depend only on a provider-neutral sender
  interface (verify identity; send one message returning a provider message id)
  and MUST NOT reference any concrete provider directly.
- **FR-102**: Exactly two provider implementations MUST exist: `gmail`
  (existing Gmail API behavior, unchanged) and `smtp` (authenticated SMTP).
- **FR-103**: The provider MUST be selected by `PROSPECTOR_SEND_PROVIDER`
  (`gmail` | `smtp`), defaulting to `gmail` for backward compatibility; any
  other value MUST fail pre-flight.
- **FR-104**: SMTP configuration MUST come from `PROSPECTOR_SMTP_HOST`,
  `PROSPECTOR_SMTP_PORT`, `PROSPECTOR_SMTP_SECURITY` (`ssl` | `starttls`),
  `PROSPECTOR_SMTP_USERNAME`, `PROSPECTOR_SMTP_PASSWORD`. Host, username, and
  password are required for the `smtp` provider; port defaults to 465 (`ssl`)
  or 587 (`starttls`); security defaults to `ssl`.
- **FR-105**: Sender identity MUST come from `PROSPECTOR_SEND_FROM` (required —
  no hardcoded default account), with optional `PROSPECTOR_SEND_NAME` (From
  display name) and `PROSPECTOR_REPLY_TO`.
- **FR-106**: When `PROSPECTOR_SEND_NAME` is set, the From header MUST be the
  RFC-formatted pair (e.g. `Anas from Omniveer <anas@omniveer.com>`).
- **FR-107**: The `smtp` provider MUST require authentication and MUST refuse
  to run when the normalized `PROSPECTOR_SEND_FROM` differs from the normalized
  `PROSPECTOR_SMTP_USERNAME` (case-insensitive) — before any send. No alias
  allowlist in this feature.
- **FR-108**: The `smtp` provider MUST support implicit SSL and STARTTLS using
  a default-verified TLS context, with a bounded connection timeout.
- **FR-109**: Each SMTP message MUST be a valid plain-text email carrying
  `From`, `To`, `Subject`, `Date`, `Message-ID`, and (when configured)
  `Reply-To` headers; the generated Message-ID MUST be returned and stored in
  the ledger.
- **FR-110**: Recipient refusal and any SMTP/transport exception MUST be
  treated as a failed send: `failed` ledger row, note stays `approved`, batch
  continues (003 FR-011 semantics unchanged).
- **FR-111**: The SMTP password MUST never appear in logs, console output,
  exception messages, reports, the ledger, or any committed file.
- **FR-112**: Dry-run MUST NOT authenticate, open an SMTP connection, or make
  any external request under either provider.
- **FR-113**: Existing 003 guarantees (approved-only, cap, pacing, ledger,
  double-send prevention, failure isolation, exit codes) MUST hold unchanged
  under both providers.

### Key Entities

- **Email sender (abstract)**: the provider-neutral interface the pipeline
  uses — verify the authenticated identity; deliver one message; report a
  provider message id.
- **SMTP transport config**: host, port, security mode, username, password
  (secret), timeout.
- **Sender identity**: the From address (required), optional display name,
  optional Reply-To.

## Success Criteria *(mandatory)*

- **SC-101**: With Zoho SMTP configured, the operator sends the approved queue
  with the same single command as before; messages arrive from
  `Anas from Omniveer <anas@omniveer.com>`.
- **SC-102**: 100% of dry-runs open zero network connections under either
  provider (verifiable in tests by a transport stub that fails on any use).
- **SC-103**: The full pre-004 test suite passes unmodified in behavior
  (assertions may be re-pointed at the neutral interface but never weakened).
- **SC-104**: No test, log, or output artifact contains the SMTP password.
- **SC-105**: A From/username mismatch is refused in 100% of attempts, before
  any message is attempted.

## Assumptions

- Zoho Mail SMTP for a custom domain: `smtp.zoho.com`, implicit SSL on 465 (or
  STARTTLS on 587), authenticated with the mailbox address and an
  app-specific/account password supplied by the operator via `.env`.
- The operator has published SPF/DKIM/DMARC for `omniveer.com` in Zoho —
  outside this tool's scope but the reason SMTP is worth adding.
- One SMTP connection per message (sends are 30–90s apart; holding a connection
  across a paced batch would idle-timeout).
- "Confirmed delivery to the SMTP server" means the server accepted the message
  for the recipient (no rejection during the SMTP dialogue). Downstream bounce
  handling is out of scope (as it was for Gmail in 003).

## Out of Scope

- A From-alias allowlist (future feature; until then From == authenticated
  username, always).
- Any third provider, transactional ESP, or API-based bulk sender.
- Reply/bounce handling, open/click tracking.
- Changes to drafting, scoring, sourcing, cap math, pacing, or ledger format
  (the ledger's `message_id` field simply carries the SMTP Message-ID).
- Renaming the Prospector product or changing message copy/templates.

## Risks

- **Password hygiene**: an SMTP password is a bearer secret; it lives only in
  `.env` (gitignored) and process env. Mitigation: FR-111 plus a repr-safe
  settings field and sanitized exceptions, all tested.
- **Zoho rate/abuse limits**: Zoho enforces its own daily sending limits;
  the ramped cap should be tuned to stay under them. The cap mechanism is
  unchanged and operator-configurable.
- **Two providers, one pipeline**: behavior drift between transports.
  Mitigation: the pipeline is provider-blind (FR-101) and both transports run
  the same contract tests.
