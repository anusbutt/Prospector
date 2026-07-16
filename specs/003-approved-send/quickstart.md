# Quickstart: Approved Send

## Prerequisites (one-time)

1. Google Cloud project with **Gmail API enabled** and a **Desktop OAuth client**
   (done — `secrets/gmail_client_secret.json` is in place, gitignored).
2. The Nestaro account `nestaroassistant@gmail.com` added as a **Test user** on the OAuth
   consent screen (Testing mode is fine).
3. Install deps (adds `google-auth`, `google-auth-oauthlib`):
   ```bash
   pip install -e .
   ```

## Configure (optional — sensible defaults)

In `.env` (gitignored):
```
PROSPECTOR_SEND_FROM=nestaroassistant@gmail.com
PROSPECTOR_SEND_CAPS=15,30,60,100      # weekly ramp; last value = week 4+
PROSPECTOR_SEND_DELAY=30,90            # random seconds between real sends
# PROSPECTOR_LEDGER=send_ledger.jsonl  # default
```

## Everyday flow

1. **Approve** in Obsidian: open a draft note, change frontmatter `status:` to `approved`.
2. **Preview** (safe — sends nothing):
   ```bash
   prospector send
   ```
   Shows exactly which notes would send, to whom, and how many against today's remaining cap.
3. **First real run** triggers a one-time browser consent for the Nestaro account, then sends:
   ```bash
   prospector send --send
   ```
   - Verifies the token account is the Nestaro address (aborts if not).
   - Sends up to today's cap, oldest-approved first, paced 30–90s apart.
   - Flips each delivered note to `status: sent` (+ a `## Log` line) and appends to the ledger.
4. **Re-run any time** — already-sent notes are skipped (ledger), so it's safe to resume after
   a Ctrl-C. Use `--limit N` to send a smaller slice.

## Verify it worked

- `send_ledger.jsonl` has one `result:sent` line per delivered note.
- Delivered notes now show `status: sent` with a timestamp in `## Log`.
- Re-running `prospector send` (dry-run) shows those notes are no longer pending.
- Check the Nestaro Gmail "Sent" folder for the actual emails.

## Safety recap

- Dry-run is the default; real sends need `--send`.
- Never sends from any account except `PROSPECTOR_SEND_FROM`.
- Never exceeds the daily cap; never re-sends; never touches non-approved notes.
- Only email-channel notes with a subject + body are sent.

## Deliverability note

The free Gmail account can't publish SPF/DKIM/DMARC, so warm it up (a few normal emails first)
and expect the realistic daily cap to plateau below 100 regardless of the schedule.
