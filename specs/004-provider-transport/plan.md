# Implementation Plan: Provider-Neutral Send Transport

**Branch**: `004-provider-transport` | **Date**: 2026-07-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-provider-transport/spec.md`

## Summary

Refactor the approved-send stage behind a provider-neutral `EmailSender` Protocol
and add an authenticated-SMTP transport (Zoho Mail, `anas@omniveer.com`) beside
the existing Gmail API transport. The pipeline (`prospector/send.py`) becomes
provider-blind; configuration (`PROSPECTOR_SEND_PROVIDER=gmail|smtp` + SMTP/
identity variables) selects the transport at the CLI boundary. Every 003
guarantee — approved-only, dry-run default, ramped cap, pacing, append-only
ledger, double-send prevention, failure isolation, exit codes — is preserved
unchanged and re-verified by the existing suite.

**Technical approach**: new `prospector/transport.py` holds the `EmailSender`
Protocol, shared `build_email()` (formataddr From, Reply-To, Date, Message-ID),
the `SendError`/`AuthError` exceptions, and a `create_sender(settings)` factory.
New `prospector/smtp_send.py` implements `SmtpSender` on stdlib
`smtplib`/`ssl`/`EmailMessage` with an injectable factory for offline tests.
`prospector/gmail.py` keeps its OAuth + httpx mechanics; a thin `GmailSender`
adapter satisfies the Protocol. `send.py` drops its direct `gmail` import and
takes a `sender`. `config.py` gains the new fields plus a lazy `require_send()`
pre-flight; `PROSPECTOR_SEND_FROM` loses its hardcoded Nestaro default.

## Technical Context

**Language/Version**: Python 3.11+ (unchanged)
**Primary Dependencies**: NONE added — SMTP uses the standard library
(`smtplib`, `ssl`, `email.message`, `email.utils`); Gmail path keeps
`google-auth(-oauthlib)` + httpx as in 003.
**Storage**: unchanged — vault notes + append-only JSONL ledger (`message_id`
now carries a Gmail id or an SMTP Message-ID).
**Testing**: pytest; SMTP mocked via an injectable smtp factory (the smtplib
analogue of the repo's respx convention); pipeline tests use fake senders;
dry-run proven network-free with fail-on-use fakes.
**Target Platform**: local CLI (Linux/WSL/macOS/Windows), unchanged
**Project Type**: single CLI package `prospector/`
**Performance Goals**: unchanged — paced sends, not throughput-bound. One SMTP
connection per message (30s timeout) is deliberate: paced batches would idle
out a held connection, and per-message connects isolate failures.
**Constraints**: dry-run makes zero network requests; SMTP password never
logged/printed/persisted/committed; From must equal the authenticated SMTP
username; exit codes preserved (0/1/2/3).
**Scale/Scope**: unchanged (~15–100 sends/day, single operator).

## Constitution Check

*GATE: against Constitution v4.0.0 (amended 2026-07-17 for this feature).*

- **I. Human-Approved Sending Only (v4.0.0)** — ✅ This feature implements the
  amended rule: exactly two providers (Gmail API | authenticated SMTP over
  SSL/STARTTLS); configured dedicated mailbox (`PROSPECTOR_SEND_FROM`,
  required, no hardcoded account); authenticated identity verified against the
  configured sender before any send, mismatch → abort exit 2; SMTP requires
  auth and refuses From != username (no spoofing); approved-only, dry-run
  default (no network in dry-run), ramped cap, pacing, append-only ledger,
  never auto-approve — all unchanged and re-tested. Credentials never
  logged/persisted/committed.
- **II. Open Web Only — Facebook Never Accessed** — ✅ N/A; mail providers only.
- **III. Obsidian Is the Interface** — ✅ unchanged; the only vault write
  remains the scoped `approved → sent` flip + `## Log` line.
- **IV. Name Honesty** — ✅ N/A; no drafting changes. (`PROSPECTOR_SEND_NAME`
  is the *operator's own* display name, not a prospect name.)
- **V. Channel Honesty** — ✅ N/A; message content sent verbatim from `## Draft`.
- **VI. Smallest Viable Build** — ✅ Zero new dependencies (stdlib smtplib);
  two small new modules; no refactor of unrelated code; Protocol over
  framework.
- **VII. Verified Claims Only** — ✅ every task carries an acceptance check;
  the full suite must pass; a live 1-recipient Zoho smoke send is the final
  acceptance.

**Result**: PASS (no violations; no new dependencies to justify).

## Project Structure

### Documentation (this feature)

```text
specs/004-provider-transport/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output (Zoho SMTP setup + everyday flow)
├── contracts/
│   ├── email-sender.md      # EmailSender Protocol + factory + build_email
│   └── smtp-sender.md       # SmtpSender behavior, config, error taxonomy
├── checklists/requirements.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
prospector/
├── transport.py      # NEW: EmailSender Protocol, SendError/AuthError, build_email, create_sender
├── smtp_send.py      # NEW: SmtpSender (stdlib smtplib/ssl, injectable factory)
├── gmail.py          # MODIFY: GmailSender adapter; build_raw delegates to shared build_email
├── send.py           # MODIFY: drop direct gmail import; take `sender: EmailSender`
├── cli.py            # MODIFY: pre-flight require_send(); build sender via factory; exit codes preserved
└── config.py         # MODIFY: provider/SMTP/identity fields, repr-safe password, require_send()

tests/unit/
├── test_transport.py      # NEW: build_email headers, formataddr From, factory selection
├── test_smtp_send.py      # NEW: SSL/STARTTLS paths, auth required, Message-ID returned, refusal → SendError, password hygiene
├── test_config_send.py    # NEW: provider/SMTP env parsing, require_send() pre-flight failures
├── test_send.py           # MODIFY: pipeline tests re-pointed at fake EmailSender (assertions unchanged)
├── test_send_failures.py  # MODIFY: same re-point
├── test_cli_send.py       # MODIFY: same re-point + SMTP identity-mismatch exit 2, dry-run no-network
├── test_gmail.py          # KEEP: respx transport tests unchanged
└── test_gmail_auth.py     # KEEP: OAuth tests unchanged
```

**Structure Decision**: same single-project layout; transport concern gets its
own module pair (`transport` = neutral seam, `smtp_send` = one provider),
mirroring how `gmail.py` already isolates the other provider.

## Interface & error taxonomy (summary — full text in contracts/)

- `EmailSender.verify_identity() -> str` (raises `AuthError`)
- `EmailSender.send_message(from_address, to_address, subject, body) -> str`
  (raises `SendError`)
- `create_sender(settings) -> EmailSender` (assumes `require_send()` passed)
- Exit codes: 1 = `ConfigError` pre-flight (incl. missing/invalid SMTP config,
  From != username); 2 = `IdentityError` (verified identity != `send_from`);
  3 = `AuthError` (OAuth failure | SMTP login failure); per-message `SendError`
  → `failed` ledger row, run continues, exit 0.

## Decisions needing ADR

Provider-abstraction + stdlib-SMTP + identity-policy placement is one grouped,
architecturally significant decision (long-term transport seam, alternatives
considered, cross-cutting). Suggested at the end of the build; never
auto-created.
