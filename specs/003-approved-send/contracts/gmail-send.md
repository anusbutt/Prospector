# Contract: Gmail auth + send (`prospector/gmail.py`)

Internal interface. Auth via `google-auth(-oauthlib)`; transport via `httpx` (respx-mockable).

## Scopes (least privilege)

- `https://www.googleapis.com/auth/gmail.send` — send only (no mailbox read).
- `https://www.googleapis.com/auth/userinfo.email` + `openid` — resolve the account address
  for the identity check (FR-004).

## Functions

| Function | Signature | Contract |
|----------|-----------|----------|
| `load_or_authorize(client_secret_path, token_path, scopes)` | `(...) -> Credentials` | If a valid/refreshable token exists at `token_path`, load + refresh it. Else run `InstalledAppFlow.run_local_server` for one-time consent and persist the token JSON to `token_path` (gitignored). Never logs token material (FR-018). |
| `account_email(creds)` | `(Credentials) -> str` | GET the userinfo endpoint with the bearer token; return the account email. Used for the identity check. |
| `send_message(creds, from_addr, to_addr, subject, body)` | `(...) -> str` | Build an RFC 2822 plain-text message, base64url-encode, `POST users/me/messages/send {"raw": ...}` via httpx with the bearer token. Return the Gmail `message id`. Raise `SendError` on non-2xx (caught by the pipeline → ledger `failed`). |

## Identity enforcement (FR-004)

The **pipeline** (not this module) calls `account_email(creds)` once per run and aborts if it
does not case-insensitively equal `Settings.send_from`. `gmail.py` provides the value; it does
not itself decide policy.

## Message format (FR-013, R9)

```
From: <from_addr>
To: <to_addr>
Subject: <subject>
Content-Type: text/plain; charset="utf-8"

<body>
```

Base64url of the above → `{"raw": "<b64url>"}`. No HTML, no tracking headers.

## Endpoints

- Send: `POST https://gmail.googleapis.com/gmail/v1/users/me/messages/send`
- Identity: `GET https://www.googleapis.com/oauth2/v3/userinfo` (or `gmail/v1/users/me/profile`)

## Testability

- All HTTP (`send` + `userinfo`) goes through `httpx` → mocked with `respx` offline.
- `load_or_authorize` accepts an injected credentials object in tests so no browser/consent
  is triggered; the real `InstalledAppFlow` path is exercised only in the live smoke test.
- `send_message` is pure w.r.t. the message bytes given inputs → assert the base64url decodes
  to the expected RFC822 (subject/body/recipient present).
