# Phase 0 Research: Approved Send

All Technical Context unknowns resolved below. No open NEEDS CLARIFICATION.

## R1. Gmail send mechanism (auth vs. transport)

- **Decision**: Use `google-auth-oauthlib` `InstalledAppFlow` for the one-time desktop
  consent and `google.oauth2.credentials.Credentials` (from `google-auth`) for storage +
  automatic refresh. Perform the actual message send with a direct **`httpx` POST** to
  `https://gmail.googleapis.com/gmail/v1/users/me/messages/send`, passing the bearer token.
- **Rationale**:
  - OAuth token lifecycle is security-critical and standardized — do not hand-roll it.
  - The send call is a single authenticated POST; using `httpx` (already a dependency) keeps
    the new footprint minimal and, crucially, makes the send path **mockable with `respx`**,
    matching the repo's existing offline test convention (network stubbed at transport level).
  - Avoids `google-api-python-client` (a large transitive dependency) for one endpoint.
- **Alternatives considered**:
  - `google-api-python-client` (`build('gmail','v1')...send`): simplest call site but heavy
    dep tree and awkward to mock offline. Rejected (Principle VI + testability).
  - Fully manual OAuth over httpx (no google libs): reimplements refresh/consent; error-prone
    and offers nothing. Rejected.
  - SMTP via app password: Gmail is deprecating app passwords / less-secure-app access and it
    sidesteps the OAuth account-scoping we want. Rejected — spec mandates the Gmail API.

## R2. OAuth scope (least privilege)

- **Decision**: Request exactly `https://www.googleapis.com/auth/gmail.send`.
- **Rationale**: The tool only needs to send. `gmail.send` cannot read mailbox contents,
  minimizing blast radius if the token leaks. It is sufficient for `messages/send`.
- **Note on identity check (FR-004)**: `gmail.send` does **not** grant access to the profile
  endpoint's email address in all cases. To verify the sending identity we additionally
  request `https://www.googleapis.com/auth/userinfo.email` (read-only, email address only) and
  call the OpenID `userinfo` endpoint OR `gmail/v1/users/me/profile`. Chosen: add
  `userinfo.email` + `openid` and read the address from the userinfo endpoint. This keeps us
  off any broad Gmail read scope while still confirming the account is the Nestaro address.
- **Alternatives considered**: `gmail.compose` / full `https://mail.google.com/` — broader than
  needed. Rejected.

## R3. Token storage

- **Decision**: After first consent, persist the refreshable credentials as JSON at
  `secrets/gmail_token.json` (gitignored via the existing `secrets/` rule). Load + auto-refresh
  on subsequent runs; if missing/expired-unrefreshable, re-run the consent flow.
- **Rationale**: `secrets/` is already gitignored and already holds the client secret; the
  token belongs beside it. JSON is the native serialization for `Credentials`.
- **Alternatives**: OS keyring — extra dep + cross-platform friction for a single-user local
  CLI. Rejected (Principle VI).

## R4. Ledger format and location

- **Decision**: Append-only **JSONL** (one JSON object per line) at a configurable path,
  default `send_ledger.jsonl` in the repo root, **gitignored**. Each successful send appends
  one line; the file is never rewritten.
- **Rationale**: Append-only JSONL is crash-safe (a partial last line is detectable/skippable),
  trivially parseable, and human-inspectable. It is the authoritative record for the daily
  count (FR-007) and double-send prevention (FR-010). Contains prospect emails (PII) → must be
  gitignored.
- **Alternatives**: CSV (quoting fragility with subjects), SQLite (heavier than needed for
  append-only rows). Rejected (Principle VI).
- **Double-send key**: a send is "already done" if the ledger holds a `result: sent` row whose
  `recipient` (normalized, lowercased) OR `slug` matches. Recipient match covers duplicate
  inboxes across notes; slug match covers a note whose status was manually reset.

## R5. Daily cap ramp + configuration

- **Decision**: Cap schedule is a list of weekly steps, default `[15, 30, 60, 100]` where the
  last value applies to week 4 and beyond. "Week N" is computed from the **first send date in
  the ledger** (Clarifications 2026-07-15): `week_index = (today - first_send_date).days // 7`,
  clamped to the schedule. Today's remaining allowance =
  `cap(week_index) - count(ledger rows with result==sent dated today)`.
  Configurable via env `PROSPECTOR_SEND_CAPS` (e.g. `"15,30,60,100"`), following the existing
  `Settings`/`.env` pattern — satisfies FR-017 (no code change).
- **Rationale**: Env-based config matches the codebase; a simple comma list is enough for a
  linear ramp. Anchoring on first ledger send matches the resolved clarification and means an
  empty ledger ⇒ day 1 ⇒ week 0 cap (15).
- **Day boundary**: local machine date (`date.today()`), per Assumptions.
- **Alternatives**: YAML schedule file — more ceremony than a 4-number ramp needs. Deferred
  (can be added later without breaking the env form).

## R6. Inter-send pacing (Clarifications 2026-07-15)

- **Decision**: Between real sends, sleep a uniform random delay in a configurable range,
  default `[30, 90]` seconds, via env `PROSPECTOR_SEND_DELAY` (e.g. `"30,90"`). No delay in
  dry-run; no delay after the final send of a run. The delay is injected as a `sleep`
  callable so tests pass a no-op.
- **Rationale**: Randomized spacing mimics human sending and protects deliverability (the
  point of the ramp). Injecting `sleep` keeps tests instant and deterministic.

## R7. Run model: foreground, resumable

- **Decision**: `prospector send` runs in the **foreground** and prints per-send progress. It
  is **resumable**: because each success is committed to the ledger immediately (and the note
  flipped to `sent`), a Ctrl-C or crash loses at most the in-flight send; re-running skips
  everything already in the ledger and continues until the daily cap is reached.
- **Rationale**: Simplicity (Principle VI); the ledger already provides safe resumption, so no
  background/daemon machinery is warranted. A `--limit N` flag lets the operator run a smaller
  slice than the full daily cap.

## R8. Account identity enforcement (FR-004)

- **Decision**: Before any send in a run, resolve the token's account email (userinfo endpoint)
  and compare, case-insensitively, to the configured expected sender (env
  `PROSPECTOR_SEND_FROM`, default `nestaroassistant@gmail.com`). On mismatch, **abort the run**
  with a clear message and send nothing.
- **Rationale**: Hard guarantee against sending from the personal (or any wrong) account — a
  core Principle I rule. Done once per run, not per message.

## R9. Message construction

- **Decision**: Build an RFC 2822 message with `To`, `From` (the Nestaro address), `Subject`
  (from the `## Draft` `**Subject:**` line), and a plain-text body (the remainder of `## Draft`).
  Base64url-encode and POST as `{"raw": "..."}`. No HTML, no tracking pixels, no custom headers
  beyond the standard ones — consistent with "looks like a human sent it."
- **Rationale**: Matches the existing note format (`draft_markdown_for` already renders
  `**Subject:** ...\n\n body`) and the plain-personal-email assumption.
- **Parsing**: reuse `vault.parse_note` to get frontmatter + the `## Draft` section; split the
  first `**Subject:**` line from the body. A note missing either is skipped and reported (FR-013).

## Summary of decisions

| # | Topic | Decision |
|---|-------|----------|
| R1 | Send mechanism | google-auth(-oauthlib) for token; httpx POST for send |
| R2 | Scope | `gmail.send` + `userinfo.email`/`openid` (least privilege) |
| R3 | Token storage | `secrets/gmail_token.json` (gitignored, auto-refresh) |
| R4 | Ledger | append-only JSONL, `send_ledger.jsonl` (gitignored) |
| R5 | Cap ramp | `[15,30,60,100]` weekly, anchored on first ledger send; env-configurable |
| R6 | Pacing | random 30–90s between real sends; injectable sleep; env-configurable |
| R7 | Run model | foreground, resumable via ledger; `--limit` slice |
| R8 | Identity | verify token account == `PROSPECTOR_SEND_FROM` or abort |
| R9 | Message | plain RFC822 from `## Draft`; base64url raw send |
