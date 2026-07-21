# Contract: Provider-neutral email sender (`prospector/transport.py`)

The single seam between the send pipeline and any concrete mail provider.
`prospector/send.py` MUST import only this module (never `gmail` / `smtp_send`
directly).

## Protocol

```python
class EmailSender(Protocol):
    def verify_identity(self) -> str: ...
    def send_message(self, from_address: str, to_address: str,
                     subject: str, body: str) -> str: ...
```

| Member | Contract |
|--------|----------|
| `verify_identity()` | Authenticate with the provider; return the identity it will actually send as (Gmail: OAuth account email via userinfo; SMTP: the login username after a successful `login()` round-trip). Raise `AuthError` on authentication failure. Called at most once per real run, never in dry-run. |
| `send_message(...)` | Deliver one plain-text message; return the provider message id recorded in the ledger (Gmail API `id` / SMTP generated `Message-ID`). Raise `SendError` on recipient refusal or transport error — the pipeline converts that to a `failed` ledger row, leaves the note `approved`, and continues (003 FR-011). MUST never include credential material in the exception text. |

## Exceptions (defined here, shared by both transports)

- `SendError` — one message failed; non-fatal to the run.
- `AuthError` — the provider cannot authenticate; fatal, exit 3.
- (`IdentityError` stays in `send.py` — it is pipeline policy, not transport.)

## Factory

```python
def create_sender(settings: Settings) -> EmailSender
```

- `settings.send_provider == "gmail"` → `gmail.GmailSender(settings)`
- `settings.send_provider == "smtp"` → `smtp_send.SmtpSender(settings)`
- Assumes `settings.require_send()` already passed (CLI pre-flight); raises
  `ConfigError` on an unknown provider as a defensive backstop.
- Imports providers lazily (keeps `--help` fast; avoids import cycles).
- MUST NOT be called on the dry-run path: dry-run constructs no sender, opens
  no connection, performs no authentication (FR-112).

## Shared message builder

```python
def build_email(from_address, from_name, reply_to, to_address, subject, body,
                message_id: str | None = None) -> EmailMessage
```

- `From`: `email.utils.formataddr((from_name, from_address))` when `from_name`
  is set — e.g. `Anas from Omniveer <anas@omniveer.com>` — else the bare address.
- `To`, `Subject`: as given, verbatim.
- `Reply-To`: only when `reply_to` is set.
- `Date`: `email.utils.formatdate(localtime=True)`.
- `Message-ID`: set when `message_id` is given (SMTP passes
  `make_msgid(domain=...)`; Gmail omits it and lets Google assign one).
- Body: plain text UTF-8 via `set_content`. No HTML, no tracking headers.

Both transports MUST build their message through this function so header
behavior cannot drift between providers.

## Identity policy (pipeline side, unchanged from 003)

`send.py` compares `verify_identity()`'s result to `settings.send_from`
case-insensitively (both `.strip().lower()`); mismatch raises `IdentityError`
→ CLI exit 2, nothing sent. This runs once per real run before any send.

## Testability

- Pipeline tests inject fake `EmailSender` objects (no monkeypatching of
  provider modules).
- Dry-run tests inject a sender whose every method raises — proving the
  pipeline never touches the transport without `--send` (SC-102).
- Gmail transport keeps its respx-mocked httpx tests; SMTP transport uses an
  injectable smtplib factory (see contracts/smtp-sender.md).
