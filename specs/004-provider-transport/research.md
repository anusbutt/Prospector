# Phase 0 Research: Provider-Neutral Send Transport

All Technical Context unknowns resolved below. No open NEEDS CLARIFICATION.

## R1. Abstraction shape: Protocol vs ABC vs callables

- **Decision**: A `typing.Protocol` named `EmailSender` in a new
  `prospector/transport.py`:
  - `verify_identity() -> str` — authenticate and return the account/identity
    the provider will actually send as (Gmail: OAuth account email; SMTP: the
    login username after a successful login). Raises `AuthError` on failure.
  - `send_message(from_address, to_address, subject, body) -> str` — deliver
    one message; return the provider message id (Gmail id / SMTP Message-ID).
    Raises `SendError` on failure.
- **Rationale**: The pipeline already isolates exactly these two provider
  touchpoints (identity check once per run; one send per note). A structural
  Protocol needs no inheritance, keeps both transports independent, and lets
  tests pass a plain fake object. Matches the repo's "plain Python, no
  framework" style (Principle VI).
- **Alternatives**: ABC base class (inheritance ceremony for two classes —
  rejected); function pair injection (loses the grouping and naming — rejected).

## R2. Where identity *policy* lives

- **Decision**: Unchanged from 003 (contracts/gmail-send.md): the transport
  reports the authenticated identity; the **pipeline** compares it to
  `Settings.send_from` case-insensitively and aborts on mismatch
  (`IdentityError` → exit 2). For SMTP there is additionally a **pre-network
  config check**: `send_from != smtp_username` (normalized) fails in
  pre-flight before any connection (FR-107) — spoof refusal must not depend on
  reaching the server.
- **Rationale**: Policy in one place (pipeline), providers stay mechanism-only;
  the extra SMTP static check satisfies "fail before sending" even offline.

## R3. SMTP client mechanics

- **Decision**: Standard library only — `smtplib.SMTP_SSL` (security `ssl`,
  default port 465) or `smtplib.SMTP` + `starttls()` (security `starttls`,
  default port 587), always with `ssl.create_default_context()` (certificate
  verification on) and a 30-second connection timeout. One connection per
  message: connect → login → `send_message()` → quit, inside a context manager.
- **Rationale**: No new dependency (Principle VI). Per-message connections are
  correct here because real sends are paced 30–90s apart — a held connection
  would idle out; reconnecting also isolates connection failures per note
  (FR-110). `SMTP.send_message(msg)` handles dot-stuffing and BDAT/DATA
  details; recipient refusal raises `SMTPRecipientsRefused`, which maps to a
  failed send.
- **Alternatives**: `aiosmtplib` (async — pointless for a paced sequential
  loop, new dep); holding one connection with NOOP keepalives (complexity for
  nothing). Rejected.

## R4. Message construction

- **Decision**: A shared builder in `transport.py`:
  `build_email(from_address, from_name, reply_to, to_address, subject, body,
  message_id=None) -> EmailMessage`. Headers: `From` via
  `email.utils.formataddr((from_name, from_address))` when a name is set, else
  the bare address; `To`; `Subject`; `Reply-To` when configured; `Date` via
  `email.utils.formatdate(localtime=True)`; `Message-ID` via
  `email.utils.make_msgid(domain=<from_address domain>)` for SMTP. Plain text
  body via `set_content` (UTF-8).
- **Gmail note**: the Gmail transport reuses the same builder (so display name
  and Reply-To work identically) but lets Gmail assign the message id recorded
  in the ledger — exactly the 003 behavior. `gmail.build_raw` becomes a thin
  wrapper over the shared builder to avoid two message-construction paths.
- **Rationale**: One tested construction path; the "Anas from Omniveer
  <anas@omniveer.com>" formatting requirement (FR-106) is satisfied by
  `formataddr`, which also handles quoting/encoding edge cases correctly.

## R5. Configuration and pre-flight validation

- **Decision**: New `Settings` fields (env → field): `send_provider`
  (`PROSPECTOR_SEND_PROVIDER`, default `gmail`), `smtp_host`, `smtp_port`
  (optional int), `smtp_security` (default `ssl`), `smtp_username`,
  `smtp_password` (dataclass `repr=False`), `send_name`, `reply_to`; and
  `send_from` loses its Nestaro default (now `None` until configured).
  Validation happens in a `require_send()` pre-flight method (mirroring
  `require_llm`/`require_places`), NOT at `load_settings()` time, so a broken
  SMTP variable can never break `run`/`source`/`dashboard`. `require_send()`
  checks: provider valid; `send_from` present; and for `smtp`: host/username/
  password present, security in {ssl, starttls}, port a positive int when
  given, and normalized `send_from == smtp_username`.
- **Rationale**: Matches the existing Settings pattern; keeps failure at the
  send pre-flight (exit 1) as specified; `repr=False` keeps the password out of
  any accidental `repr(settings)`/traceback locals dump.
- **Alternatives**: validating at load (breaks unrelated commands — rejected);
  a separate SmtpConfig file (config sprawl for six values — rejected).

## R6. Secret hygiene (FR-111)

- **Decision**: Defense in depth: (a) `smtp_password` is `repr=False`;
  (b) the SMTP transport catches `smtplib.SMTPException`/`OSError` and
  re-raises `SendError`/`AuthError` built only from the exception's own text
  (smtplib never embeds the password in its exceptions — the value passed to
  `login()` is not echoed back); (c) error messages reference the env var
  *name*, never the value; (d) a test greps captured logs/output/ledger from a
  failed-auth run for the sentinel password value.
- **Rationale**: The only place the password exists is the `login()` call;
  every failure surface is either sanitized or verified by test.

## R7. Backward compatibility for Gmail users

- **Decision**: `PROSPECTOR_SEND_PROVIDER` defaults to `gmail`; the Gmail
  OAuth flow, scopes, token storage, ledger contents, and exit codes are
  untouched. The single breaking config change: `PROSPECTOR_SEND_FROM` no
  longer defaults to `nestaroassistant@gmail.com` — it must be set explicitly
  (constitution v4.0.0 removed the hardcoded account; a silent default of
  someone's mailbox is an identity hazard). Pre-flight says exactly which
  variable to set.
- **Rationale**: One explicit line in `.env` versus the risk of a stale
  hardcoded identity; sanctioned by the amendment.

## R8. Testing strategy

- **Decision**: No real SMTP server. `SmtpSender` takes an injectable
  `smtp_factory` (defaults to the real `smtplib` classes); tests inject a fake
  recording connect/login/send/quit and raising on demand
  (`SMTPAuthenticationError`, `SMTPRecipientsRefused`). Pipeline tests pass a
  fake `EmailSender`. Dry-run tests use a sender/factory that raises on ANY
  use, proving zero network intent (SC-102). Existing gmail respx tests stay
  as-is; existing send-pipeline tests are re-pointed at the neutral interface
  with identical assertions.
- **Rationale**: Matches the repo's offline-stub convention (respx for httpx;
  factory injection is the smtplib equivalent).

## Summary of decisions

| # | Topic | Decision |
|---|-------|----------|
| R1 | Abstraction | `EmailSender` Protocol: `verify_identity`, `send_message` |
| R2 | Identity policy | Pipeline compares to `send_from`; SMTP adds pre-network From==username check |
| R3 | SMTP client | stdlib smtplib, SSL 465 / STARTTLS 587, default TLS context, 30s timeout, one connection per message |
| R4 | Message | shared `build_email`; formataddr From, Reply-To, Date, make_msgid Message-ID (SMTP) |
| R5 | Config | new Settings fields; lazy `require_send()` pre-flight; `repr=False` password |
| R6 | Secrets | sanitized exceptions + repr-safe field + grep test |
| R7 | Compat | provider defaults to `gmail`; `send_from` now required (no Nestaro default) |
| R8 | Tests | injectable smtp factory fake; fail-on-use sender for dry-run |
