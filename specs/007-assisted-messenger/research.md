# Phase 0 Research: Assisted-Manual Messenger Send

## R1 — Clipboard mechanism (no new dependency)

**Decision**: Copy the draft body to the OS clipboard by shelling out to the
platform's native copier, wrapped in a small `prospector/clipboard.py` helper
that is injected as a callable so tests never touch a real clipboard.

- WSL/Windows: `clip.exe` (present on this operator's WSL setup)
- macOS: `pbcopy`
- Linux (X11/Wayland): `xclip -selection clipboard` / `xsel --clipboard --input`
  / `wl-copy` (first available)

**Rationale**: The constitution (Additional Constraints / Principle VI) mandates
the smallest viable build and settled stack; adding a third-party clipboard
package (`pyperclip`) is avoidable drag. Shelling out is stdlib-only. Clipboard
availability varies, so the helper MUST degrade gracefully: if no copier is
found or the copy fails, print the draft body to the terminal for manual copy and
continue the walk — never abort (spec Edge Cases; FR-004 is best-effort on the
clipboard, the human always has the text visible).

**Alternatives considered**:
- `pyperclip` dependency — rejected: unnecessary dependency for one call.
- Tkinter clipboard — rejected: heavy, GUI-coupled, unavailable headless.

## R2 — Browser open (the sanctioned Facebook handoff)

**Decision**: Open the target with stdlib `webbrowser.open(url, new=2)`, injected
as a callable for tests. On failure (no browser, headless), print the URL for the
operator to open manually and continue.

**Rationale**: This is exactly the OS default-browser handoff that Constitution
v6.0.0 Principle II clarifies is **not** a tool fetch — the tool issues no HTTP
request; the operator's browser (and the operator's own Facebook session) does
everything. `webbrowser` is stdlib, cross-platform, and does no automation (it
cannot read the page back), which keeps Principle I's "no browser automation"
literally true.

**Alternatives considered**:
- Playwright/Selenium — rejected hard: that IS browser automation of Facebook,
  forbidden by Principle I and the whole premise of the feature.
- Printing the URL only (no auto-open) — rejected as the default: loses the core
  convenience; retained only as the graceful fallback.

## R3 — Facebook-target resolution

**Decision**: Resolve the note's `facebook_url` at `run` time with this
precedence, storing the result in the note frontmatter:

1. `company.facebook_url` (explicit input) — highest trust.
2. Else the first `research.fb_evidence` record whose `value` is a usable
   `facebook.com` page URL — in practice `EvidenceKind.FB_SEARCH_ACTIVE` (a
   discovered active page) or `EvidenceKind.FB_LINK` (a link found on the
   company's own site). `FB_URL_INPUT` mirrors case 1.
3. Else empty.

`FB_WIDGET`/`FB_EMBED` values are markers/script srcs, not page URLs, so they are
**not** used as a target.

**Rationale**: Many messenger notes arise from a blank email field and carry no
Facebook link at all (confirmed by inspecting the live vault: e.g.
`air-duct-cleaners-llc.md` has `email:` blank and only an `fb_search_active`
line in `## Research`). A dependable, precedence-ranked target maximizes
auto-open coverage while the empty case is handled gracefully (FR-019, US5). This
is an input/target field only — resolving it involves **no** Facebook network
access (Principle II).

**Alternatives considered**:
- Regex the `## Research` prose at DM time — rejected: brittle, and the data is
  already structured in `fb_evidence`; better to persist a clean field once.

## R4 — Ledger separation

**Decision**: A dedicated `dm_ledger.jsonl` (configurable via
`PROSPECTOR_DM_LEDGER`, default alongside `send_ledger.jsonl`, gitignored),
reusing `prospector/ledger.py` primitives unchanged. DM records use
`result="dm_sent_manual"` and `message_id=None`.

**Rationale**: The email `send` path derives its ramped daily cap from
`send_ledger.jsonl` (`send.py` → `ledger.daily_count`/`first_send_date`). Writing
DM deliveries into the same ledger would corrupt email cap accounting (FR-011).
`ledger.already_sent()` returns `(recipients, slugs)`; DM dedupe keys on **slug**
(messenger notes often lack an email), which the existing function already
provides.

**Alternatives considered**:
- One shared ledger with a `channel` discriminator — rejected: forces cap math to
  filter by channel and risks a bug re-crossing the isolation the spec requires.

## R5 — Confirmation order & idempotency

**Decision**: For each eligible note in real mode: copy → open → show → **prompt
for confirmation**. Only on an affirmative confirmation does the tool (a) append
the ledger row, then (b) flip status `approved → sent`. Decline/skip records
nothing and leaves the note `approved`.

**Rationale**: Because the human performs the actual send, the ledger must record
only what the human asserts was sent (spec Assumptions: trust-based). Ledger-first
then status-flip mirrors `send.py:199-211` (ledger is source of truth), making the
run interrupt-safe and resumable: an already-confirmed note is in the ledger and
is skipped next run (FR-012), and a note not yet confirmed is simply re-offered.

**Alternatives considered**:
- Batch-confirm at the end — rejected: loses per-note accuracy and the
  interrupt-safety property; a mid-batch Ctrl-C would lose all record.

## Cross-cutting: zero Facebook HTTP (verification approach)

A dedicated test (`test_dm_no_facebook_http.py`) runs `run_dm` in real mode with
injected clipboard/browser/confirm stubs and asserts (a) `webbrowser.open` was
called with the expected URL, (b) no `httpx`/network client was invoked toward any
Facebook host, and (c) `fetch.py`'s host guard remains unmodified. This makes
SC-004 ("zero outbound requests reach a Facebook host") a verified claim
(Principle VII), not an assumption.
