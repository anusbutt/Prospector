# Tasks: Provider-Neutral Send Transport

**Input**: Design documents from `/specs/004-provider-transport/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Tests**: INCLUDED — Constitution Principle VII; safety-critical paths
(identity, secret hygiene, dry-run isolation) are written tests-first.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup & Governance

- [ ] T101 Amend the constitution to v4.0.0 (Principle I: Gmail API | authenticated SMTP; configured mailbox, no hardcoded account; SMTP From==username; dry-run = zero network) with a dated Sync Impact Report; update PRODUCT.md §2/§3/§11 first per governance. Acceptance: both files updated, version footer reads 4.0.0.
- [ ] T102 [P] Add the new variables to `.env.example` (`PROSPECTOR_SEND_PROVIDER`, `PROSPECTOR_SMTP_HOST/PORT/SECURITY/USERNAME/PASSWORD`, `PROSPECTOR_SEND_FROM` (now required), `PROSPECTOR_SEND_NAME`, `PROSPECTOR_REPLY_TO`) with Zoho-oriented comments and no real secrets. Acceptance: all nine keys listed; file contains no password value.

## Phase 2: Foundational — configuration

- [ ] T103 Write `tests/unit/test_config_send.py` (tests-first): provider default `gmail`; provider/security lowercased; SSL and STARTTLS parsing incl. port defaults 465/587 and explicit override; `require_send()` failures — invalid provider, missing `send_from`, missing host/username/password (message names the variable, never echoes values), invalid security mode, non-positive port, From≠username spoof refusal; `repr(settings)` contains no password. Acceptance: fails pre-impl.
- [ ] T104 Extend `prospector/config.py`: new fields (`send_provider`, `smtp_host`, `smtp_port`, `smtp_security`, `smtp_username`, `smtp_password` repr=False, `send_name`, `reply_to`); `send_from` default removed (None); `require_send()` pre-flight per data-model.md §Validation. Acceptance: `pytest tests/unit/test_config_send.py` green.

## Phase 3: US1 — transport abstraction + SMTP sender (P1)

- [ ] T105 [P] Write `tests/unit/test_transport.py` (tests-first): `build_email` sets From `Anas from Omniveer <anas@omniveer.com>` via formataddr (bare address when no name), To, Subject, Reply-To only when configured, Date present, Message-ID set when passed; body plain text; `create_sender` returns GmailSender for `gmail`, SmtpSender for `smtp`. Acceptance: fails pre-impl.
- [ ] T106 Implement `prospector/transport.py`: `EmailSender` Protocol, `SendError`/`AuthError`, `build_email`, lazy `create_sender(settings)` per contracts/email-sender.md. Acceptance: transport tests green.
- [ ] T107 [P] Write `tests/unit/test_smtp_send.py` (tests-first): SSL→SMTP_SSL:465, STARTTLS→SMTP+starttls:587, explicit port override; login always precedes send; `verify_identity` returns username on success, raises AuthError on SMTPAuthenticationError; `send_message` returns the message's Message-ID; recipient refusal / SMTPException / OSError → SendError; connection context is `ssl.create_default_context()`; timeout=30; **password sentinel absent from every raised message and captured output**. Acceptance: fails pre-impl.
- [ ] T108 Implement `prospector/smtp_send.py` `SmtpSender` per contracts/smtp-sender.md with injectable `smtp_factory`. Acceptance: smtp tests green.
- [ ] T109 Add `GmailSender` adapter to `prospector/gmail.py` (wraps `load_or_authorize`/`account_email`/`send_message`; message built via shared `build_email` so display name + Reply-To work; ledger keeps the Gmail-assigned id); re-point `gmail.SendError`/`AuthError` to the shared transport exceptions without breaking existing imports. Acceptance: `tests/unit/test_gmail.py` + `test_gmail_auth.py` still green.

## Phase 4: US2 — provider-blind pipeline (P1)

- [ ] T110 Refactor `prospector/send.py`: remove the direct `gmail` import; `run_send(..., sender: EmailSender | None)`; `authorize_and_verify` → `verified_sender(settings)` using `create_sender` + `verify_identity` + the existing case-insensitive comparison (IdentityError unchanged). Acceptance: no `import gmail` in send.py; pipeline tests green with fake senders.
- [ ] T111 Update `prospector/cli.py` send command: call `settings.require_send()` pre-flight (ConfigError → exit 1); build/verify the sender only when `--send` (dry-run constructs nothing); map IdentityError → 2, AuthError → 3 (both providers). Acceptance: `tests/unit/test_cli_send.py` green including new SMTP cases.
- [ ] T112 Re-point existing pipeline/CLI tests (`test_send.py`, `test_send_failures.py`, `test_cli_send.py`) at the neutral interface — same assertions, no weakened checks; add: dry-run with a fail-on-use sender (proves zero network intent), SMTP identity mismatch → exit 2, successful SMTP send updates ledger+status, failed SMTP send leaves note approved. Acceptance: full suite green.

## Phase 5: Polish & docs

- [ ] T113 [P] Update README (guarantee #1 wording, configuration table, Sending section: provider selection, Zoho SMTP setup, Gmail backward-compat; remove Nestaro sending-account references) and cross-check quickstart.md. Acceptance: `grep -ri nestaro README.md` empty for sending-account context.
- [ ] T114 Run the complete test suite + a compile/format pass; fix every failure caused by the change. Acceptance: `pytest` exits 0.
- [ ] T115 Live smoke (operator): configure real Zoho values in `.env`, `prospector send` (dry-run) then `prospector send --send` with ONE approved test note to a personal inbox; confirm arrival with the formatted From header, ledger row with Message-ID, note flipped to `sent`. Acceptance: observed delivery (Principle VII).

## Dependencies

- T101–T102 → everything.
- T103→T104 → T105/T107 (settings shape) → T106/T108/T109 → T110→T111→T112 → T113/T114 → T115.

## Task Summary

- **Total**: 15 tasks (T101–T115); tests-first on config, transport, SMTP.
- **MVP**: T101–T112 (Zoho send working, guarantees intact); T113–T115 polish + live acceptance.
