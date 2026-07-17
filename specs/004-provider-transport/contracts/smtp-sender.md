# Contract: SMTP transport (`prospector/smtp_send.py`)

Implements the `EmailSender` Protocol over the Python standard library
(`smtplib`, `ssl`, `email.message.EmailMessage`, `email.utils`). Zero new
dependencies.

## Construction

```python
SmtpSender(settings, smtp_factory=None)
```

Reads from `settings`: `smtp_host`, `smtp_port` (None → derived), 
`smtp_security` (`ssl` | `starttls`), `smtp_username`, `smtp_password`,
`send_name`, `reply_to`. `smtp_factory` is an injectable pair/callable used by
tests to substitute fake `SMTP`/`SMTP_SSL` classes; production uses the real
ones.

## Connection rules

| security | class | default port | TLS |
|----------|-------|--------------|-----|
| `ssl` | `smtplib.SMTP_SSL` | 465 | implicit, `ssl.create_default_context()` |
| `starttls` | `smtplib.SMTP` then `.starttls(context=...)` | 587 | upgraded, `ssl.create_default_context()` |

- Connection timeout: 30 seconds.
- **Authentication is mandatory**: every connection calls
  `login(smtp_username, smtp_password)` before any send. There is no
  unauthenticated path.
- One connection per message: connect → login → send → quit (context-managed).
  Sends are paced 30–90 s apart, so a held connection would idle out; a broken
  connection therefore affects exactly one message.

## `verify_identity() -> str`

1. Open a connection per the table above and `login(...)`.
2. On success, `quit` and return `smtp_username` (the identity Zoho will
   enforce as the envelope sender).
3. On `SMTPAuthenticationError` (or connect/TLS failure) raise `AuthError`
   with the server's own response text — never the password → CLI exit 3.

## `send_message(from_address, to_address, subject, body) -> str`

1. Build the message via the shared `transport.build_email(...)`, passing
   `message_id=email.utils.make_msgid(domain=<from_address domain>)`.
   Headers: `From` (formataddr display-name form when `send_name` set), `To`,
   `Subject`, `Reply-To` (when configured), `Date`, `Message-ID`; plain-text
   UTF-8 body.
2. Connect + login as above; `smtp.send_message(msg)`.
3. Server accepted (no exception, empty refused-recipients dict) → return the
   generated `Message-ID` string (stored in the ledger's `message_id`).
4. `SMTPRecipientsRefused`, any other `SMTPException`, `OSError`/timeout →
   raise `SendError` with the provider's response text. The pipeline records a
   `failed` ledger row, leaves the note `approved`, and continues.

## Identity / anti-spoofing

- Pre-network (config pre-flight, `Settings.require_send()`): normalized
  `send_from` MUST equal normalized `smtp_username`, else `ConfigError`
  (exit 1) — refused before any connection exists.
- Run-time (pipeline): `verify_identity()`'s return is compared to
  `send_from` again (`IdentityError` → exit 2). Both layers must pass.
- No alias allowlist in this feature; a future feature may add one.

## Secret hygiene (FR-111, tested)

- `smtp_password` never appears in: exception messages raised by this module,
  anything printed/logged, the ledger, `repr(settings)` (field is
  `repr=False`), or any committed file.
- Error text may include the server's SMTP response and the env var *names*,
  never values.

## Zoho reference values (documentation, not code defaults)

| Setting | Value |
|---------|-------|
| `PROSPECTOR_SMTP_HOST` | `smtp.zoho.com` |
| `PROSPECTOR_SMTP_PORT` | `465` (ssl) or `587` (starttls) |
| `PROSPECTOR_SMTP_SECURITY` | `ssl` |
| `PROSPECTOR_SMTP_USERNAME` | `anas@omniveer.com` |
| `PROSPECTOR_SMTP_PASSWORD` | Zoho app-specific password (env only) |
| `PROSPECTOR_SEND_FROM` | `anas@omniveer.com` |
| `PROSPECTOR_SEND_NAME` | `Anas from Omniveer` |

## Testability

- `smtp_factory` injection: tests provide fake SMTP classes recording
  `(host, port, timeout, context)` construction, `starttls`, `login`,
  `send_message`, `quit`; and raising `SMTPAuthenticationError` /
  `SMTPRecipientsRefused` on demand.
- Assertions cover: SSL vs STARTTLS class/port selection; login always called
  before send; returned id == message's `Message-ID`; headers From/Reply-To/
  Date/Message-ID present and correctly formatted; failures map to
  `AuthError`/`SendError`; password absent from all captured output.
