# Phase 1 Data Model: Provider-Neutral Send Transport

No new on-disk artifacts. The vault note lifecycle, ledger file, and cap/pacing
entities from 003 are unchanged. This feature adds in-memory configuration and
transport entities only.

## Entity: EmailSender (Protocol, in-memory)

The seam the pipeline depends on. Structural (`typing.Protocol`) — no base class.

| Member | Signature | Contract |
|--------|-----------|----------|
| `verify_identity` | `() -> str` | Authenticate with the provider and return the identity it will send as (Gmail: OAuth account email; SMTP: login username after successful `login()`). Raises `AuthError` on any authentication failure. Network use allowed (real runs only — never called in dry-run). |
| `send_message` | `(from_address: str, to_address: str, subject: str, body: str) -> str` | Deliver one plain-text message. Returns the provider message id (Gmail API id / SMTP `Message-ID`). Raises `SendError` on refusal or transport error. |

## Entity: SmtpConfig (fields on Settings)

| Field | Type | Env | Default | Rule |
|-------|------|-----|---------|------|
| smtp_host | str \| None | `PROSPECTOR_SMTP_HOST` | None | required for provider `smtp` |
| smtp_port | int \| None | `PROSPECTOR_SMTP_PORT` | None → 465 (`ssl`) / 587 (`starttls`) | positive int when set |
| smtp_security | str | `PROSPECTOR_SMTP_SECURITY` | `ssl` | must be `ssl` or `starttls` (lowercased) |
| smtp_username | str \| None | `PROSPECTOR_SMTP_USERNAME` | None | required for provider `smtp` |
| smtp_password | str \| None | `PROSPECTOR_SMTP_PASSWORD` | None | required for provider `smtp`; dataclass `repr=False`; never logged/echoed |

## Entity: SenderIdentity (fields on Settings)

| Field | Type | Env | Default | Rule |
|-------|------|-----|---------|------|
| send_provider | str | `PROSPECTOR_SEND_PROVIDER` | `gmail` | `gmail` \| `smtp` (lowercased) |
| send_from | str \| None | `PROSPECTOR_SEND_FROM` | None (BREAKING: was `nestaroassistant@gmail.com`) | required for `send`; for `smtp`, normalized value must equal normalized `smtp_username` |
| send_name | str \| None | `PROSPECTOR_SEND_NAME` | None | when set, From = `formataddr((send_name, send_from))` → e.g. `Anas from Omniveer <anas@omniveer.com>` |
| reply_to | str \| None | `PROSPECTOR_REPLY_TO` | None | when set, `Reply-To` header added |

**Normalization**: `addr.strip().lower()` for every address comparison
(identity check, From==username rule). Nothing else is altered — the *sent*
headers preserve the configured casing.

## Validation: `Settings.require_send()` (pre-flight, no network)

Order of checks (first failure raises `ConfigError` → exit 1):

1. `send_provider` ∈ {`gmail`, `smtp`} — else name the variable and valid values.
2. `send_from` present — else name `PROSPECTOR_SEND_FROM`.
3. Provider `smtp` only:
   a. `smtp_host` present; b. `smtp_username` present; c. `smtp_password`
   present (message names the variable, never echoes any value);
   d. `smtp_security` ∈ {`ssl`, `starttls`}; e. `smtp_port` positive when set.
4. Provider `smtp` only: normalized `send_from == smtp_username` — else raise
   the spoof-refusal error. (Also re-verified against the *authenticated*
   identity at run time via `verify_identity` → `IdentityError` → exit 2.)

## Message headers (SMTP transport)

| Header | Source | Required |
|--------|--------|----------|
| From | `formataddr((send_name, send_from))` or bare `send_from` | yes |
| To | candidate recipient | yes |
| Subject | note `## Draft` subject | yes |
| Date | `email.utils.formatdate(localtime=True)` | yes |
| Message-ID | `email.utils.make_msgid(domain=send_from.split("@")[1])` | yes — returned & ledgered |
| Reply-To | `reply_to` | only when configured |
| Content-Type | `text/plain; charset="utf-8"` (via `set_content`) | yes |

Gmail transport builds the identical message (same builder, so From display
name + Reply-To behave the same) but the ledger stores the **Gmail-assigned
id**, exactly as in 003.

## Ledger (unchanged schema)

`message_id` semantics widen: Gmail API id (provider `gmail`) or generated
RFC 5322 Message-ID (provider `smtp`). `from_account` continues to record the
verified sending address. No migration needed — the field was already a string.

## Error taxonomy → exit codes (unchanged mapping)

| Error | Raised by | Exit |
|-------|-----------|------|
| `ConfigError` | `require_send()` pre-flight | 1 |
| `IdentityError` | pipeline identity comparison | 2 |
| `AuthError` | transport auth (`verify_identity`, OAuth consent, SMTP login) | 3 |
| `SendError` | per-message delivery | not fatal → `failed` row, exit 0 |
