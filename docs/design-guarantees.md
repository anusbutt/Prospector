# Design guarantees

Prospector is built around a small set of hard guarantees. They are enforced in
code and covered by the test suite, so a change that weakens one fails CI rather
than shipping quietly. They exist because the tool researches real businesses and
sends real email on someone's behalf: the interesting engineering here is not the
drafting, it is the set of things the drafting is not allowed to do.

These correspond to the numbered principles in the project constitution (v7.0.0).

1. **Human-approved sending only** *(Principle I)*. Email is the only
   communication channel. The tool never sends anything a human has not
   explicitly marked `status: approved`. Real sending requires an explicit flag
   (dry-run is the default), is bound to the configured dedicated mailbox, is
   capped, and every send is recorded in an append-only ledger that prevents
   duplicates. No copy is generated or altered on the send path.
   *(See `prospector/send.py` and its tests.)*

2. **Open web only — Facebook is never accessed** *(Principle II)*. The tool
   makes no request to any Facebook or Messenger host — no Graph API, no
   scraping, no fetching a Facebook URL. All outbound HTTP passes through a host
   guard that rejects those hosts before any network activity. Facebook-owned
   markup found on a company's *own* site (the Meta Pixel) may be read as a
   sourcing signal, but the URLs in it are never requested.
   *(See `BLOCKED_HOSTS` in `prospector/fetch.py` and its tests.)*

3. **Obsidian is the interface** *(Principle III)*. Output is plain Markdown
   notes plus a dashboard note. No web UI, server, or GUI.

4. **Evidence-bound copy — never fabricate** *(Principle IV)*. Names,
   personalization hooks, and any claim about a prospect must be backed by
   captured evidence and validated deterministically in plain Python. Copy that
   cannot be validated is discarded and replaced with the selected profile's
   locked fallback template. Validation is never delegated to a model.
   *(See `prospector/draft.py` / `prospector/agent_draft.py` and their tests.)*

5. **Verified claims only** *(Principle VII)*. Nothing is asserted about a
   prospect that the tool has not observed. In particular, Meta Pixel presence is
   a targeting filter and is never presented as evidence that a company runs
   advertising.

Principle V (Channel Honesty) was **retired in v7.0.0** along with the Messenger
channel: the copy makes no claim about a prospect's channels, so the gate it
guarded is satisfied trivially. A channel-fit signal should not come back without
amending the constitution first.

## Profiles are content, not capability

Everything vertical-specific — the offer, the sender identity, the writing
guidance, the locked fallback copy, the note tags, the promotional link, and the
default sourcing keywords — lives in a profile directory rather than in Python.
Adding a vertical must never require a code change. Operator profiles live in
`./profiles/<name>/`; one reference profile ships inside the package at
`prospector/profiles/duct-cleaning/`.

Profiles are reviewed like prose, and held to two rules:

- **A profile cannot widen what the tool may do.** It grants the drafting model no
  tools, no network, and no filesystem access, and it cannot disable citation
  validation, the locked-fallback rule, approval-gated sending, or the Facebook
  host guard. A profile changes what is said, never what is permitted.
- **A profile never contains secrets**, credentials, or a URL intended to be
  fetched. Credentials come from `.env`.

A profile is validated in full *before* any company is processed, so a malformed
one costs nothing and writes nothing. A new key ships with its validation in
`prospector/profiles.py`, because a key that silently defaults is a key that
silently ships the wrong copy.

## Conventions that protect the above

- **The trust boundary is deterministic Python.** The LLM controls phrasing, never
  factual acceptance. Validation, classification, and citation checks stay in
  code, not in prompts. An instruction file that appears to grant an exception the
  validator does not honour is a bug in the instruction file.
- **Never commit prospect data.** Real company names, addresses, websites and
  scraped emails belong to third parties and stay local. The vault,
  `candidates.csv` (the default `--out` of `prospector source`), the send ledger
  and `samples/` are gitignored for this reason. Tests and fixtures use fictional
  data.
- **Never hardcode secrets.** Credentials come from the gitignored `.env` and are
  never logged, printed, or committed.
- **External services are called directly** over HTTP or a thin SDK. No heavy
  frameworks, no agent/orchestration machinery.
