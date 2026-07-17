# Quickstart: Sending via Zoho SMTP (anas@omniveer.com)

## Prerequisites (one-time, outside the tool)

1. Zoho Mail hosts `omniveer.com`; the mailbox `anas@omniveer.com` exists.
2. SPF/DKIM/DMARC published for `omniveer.com` in your DNS (Zoho Admin →
   Domains — this is the deliverability upgrade that motivates SMTP).
3. Generate a Zoho **app-specific password** for SMTP (Zoho Accounts →
   Security → App Passwords). Do NOT use your account password if 2FA is on.

## Configure

In `.env` (gitignored — never commit this file):

```bash
PROSPECTOR_SEND_PROVIDER=smtp
PROSPECTOR_SMTP_HOST=smtp.zoho.com
PROSPECTOR_SMTP_PORT=465            # optional; 465 is the ssl default (587 for starttls)
PROSPECTOR_SMTP_SECURITY=ssl        # or: starttls (then port defaults to 587)
PROSPECTOR_SMTP_USERNAME=anas@omniveer.com
PROSPECTOR_SMTP_PASSWORD=<your Zoho app password — env only, never committed>
PROSPECTOR_SEND_FROM=anas@omniveer.com   # must equal PROSPECTOR_SMTP_USERNAME
PROSPECTOR_SEND_NAME=Anas from Omniveer  # From: Anas from Omniveer <anas@omniveer.com>
#PROSPECTOR_REPLY_TO=anas@omniveer.com   # optional
# Cap/pacing/ledger settings are unchanged from feature 003:
#PROSPECTOR_SEND_CAPS=15,30,60,100
#PROSPECTOR_SEND_DELAY=30,90
#PROSPECTOR_LEDGER=send_ledger.jsonl
```

Guard rails you will hit if something is off (all before anything sends):

- missing password / host / username → pre-flight error naming the variable (exit 1)
- `PROSPECTOR_SMTP_SECURITY` not `ssl`/`starttls` → pre-flight error (exit 1)
- `PROSPECTOR_SEND_FROM` ≠ `PROSPECTOR_SMTP_USERNAME` → refused, no spoofing (exit 1/2)
- wrong password → SMTP auth failure (exit 3), password never echoed

## Everyday flow (identical to before)

```bash
prospector send                 # DRY-RUN preview — no connection, no auth, nothing sent
prospector send --send          # real send: verify identity, cap, pace, ledger, flip to sent
prospector send --send --limit 5
```

## Verify it worked

- `send_ledger.jsonl` gains one `result:sent` row per delivery, `message_id`
  holding the generated Message-ID and `from_account: anas@omniveer.com`.
- Delivered notes show `status: sent` + a dated `## Log` line.
- Zoho Mail "Sent" folder shows the messages from
  `Anas from Omniveer <anas@omniveer.com>`.

## Switching back to Gmail (backward compatible)

```bash
PROSPECTOR_SEND_PROVIDER=gmail
PROSPECTOR_SEND_FROM=<the dedicated Gmail address>
# secrets/gmail_client_secret.json + one-time OAuth consent as in feature 003
```

Note: `PROSPECTOR_SEND_FROM` no longer has a built-in default — set it
explicitly for either provider.

## Safety recap (unchanged from 003)

- Only `status: approved` notes; dry-run default; `--send` required for real sends.
- Ramped daily cap + randomized 30–90 s pacing.
- Append-only ledger; recipient/slug double-send prevention.
- A failed send leaves the note `approved`; one failure never stops the batch.
- The SMTP password lives only in `.env`/environment — never logged, never committed.
