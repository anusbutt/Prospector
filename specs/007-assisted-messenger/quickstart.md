# Quickstart: Assisted-Manual Messenger Send

Deliver approved Messenger drafts with the tool doing the boring parts — while
**you** remain the only party that touches Facebook and clicks send.

## Prerequisites

- A vault produced by `prospector run` containing `channel: messenger` notes.
- Each note you want to deliver has `status: approved` (edit the frontmatter in
  Obsidian).
- Interactive terminal with a web browser available (and usually a clipboard).

## 1. Preview (safe, changes nothing)

```bash
prospector dm
```

Prints which approved Messenger notes would be walked, in order, plus per-note
reasons for anything skipped (already delivered / no draft body). Opens no
browser, writes no clipboard, records nothing.

## 2. Assisted delivery

```bash
prospector dm --send
```

For each approved Messenger note, the tool:

1. Copies the draft to your clipboard.
2. Opens the company's Facebook page in your browser.
3. Shows you the message and asks: `Did you send this message? [y/N/q]`

You paste into Messenger, send it yourself, then answer:

- `y` — records the delivery and marks the note `sent`.
- `N` (or Enter) — skips it; the note stays `approved`.
- `q` — stops the walk; everything you already confirmed is saved.

Useful variants:

```bash
prospector dm --send --limit 5          # walk at most 5 notes
prospector dm --send --vault ~/Vault    # alternate vault
prospector dm --send --yes              # skip only the upfront confirm (per-note stays)
```

## 3. Notes with no Facebook link

If a note has no `facebook_url` on file, the tool still copies the draft and
shows the message, tells you `no Facebook link on file — locate the company
manually`, and lets you confirm or skip. It never crashes and never guesses.

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `PROSPECTOR_DM_LEDGER` | No | `dm_ledger.jsonl` | Where confirmed Messenger deliveries are recorded (gitignored). |

## Verification (acceptance)

- **Preview is inert**: run `prospector dm`, confirm no browser tab opened, no
  clipboard change, `dm_ledger.jsonl` unchanged, no note status changed. (SC-003)
- **End-to-end**: approve one messenger note with a `facebook_url`, run
  `prospector dm --send`, confirm `y`; verify a line was appended to
  `dm_ledger.jsonl`, the note is now `status: sent` with a `## Log` bullet, and
  your browser opened the right page. (SC-001)
- **No double-send**: reset that note to `approved`, run again; verify it is
  reported `skipped (already delivered)` and no browser opens. (SC-002)
- **Never contacts Facebook**: `prospector dm --send` makes zero HTTP requests to
  any Facebook host — only your browser is handed the URL. (SC-004; enforced by
  `tests/test_dm_no_facebook_http.py`.)
- **Field present & diff-stable**: after re-running `prospector run`, messenger
  notes carry a `facebook_url` header field, and pre-existing notes show no
  header reordering. (SC-005)
