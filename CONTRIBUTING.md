# Contributing to Prospector

Thanks for your interest in improving Prospector. This document explains how to
set up the project, the conventions we follow, and — most importantly — the
safety guarantees that every change must preserve.

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).

## Non-negotiable guarantees

Prospector is built around a small set of hard guarantees. They are enforced in
code and covered by the test suite. **A change that weakens any of them will not
be merged**, even if it is otherwise useful. If you believe one genuinely needs
to change, open an issue to discuss it first — don't work around it in a PR.

These correspond to the numbered principles in
`.specify/memory/constitution.md` (v7.0.0).

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
   notes plus a dashboard note. No web UI, server, or GUI is added.

4. **Evidence-bound copy — never fabricate** *(Principle IV)*. Names,
   personalization hooks, and any claim about a prospect must be backed by
   captured evidence and validated deterministically in plain Python. Copy that
   cannot be validated is discarded and replaced with the selected profile's
   locked fallback template. Validation is never delegated to a model.
   *(See `prospector/draft.py` / `prospector/agent_draft.py` and their tests.)*

5. **Verified claims only** *(Principle VII)*. Nothing is asserted about a
   prospect that the tool has not observed. In particular, Meta Pixel presence
   is a targeting filter and is never presented as evidence that a company runs
   advertising.

Principle V (Channel Honesty) was **retired in v7.0.0** along with the Messenger
channel: the copy makes no claim about a prospect's channels, so the gate it
guarded is satisfied trivially. Do not reintroduce a channel-fit signal without
amending the constitution first.

If your change touches any of these areas, please call out in your PR how the
guarantee is preserved, and add or update the test that proves it.

## Profiles are content, and they are reviewed

Everything vertical-specific — the offer, the sender identity, the writing
guidance, the locked fallback copy, the note tags, the promotional link, and the
default sourcing keywords — lives in a profile directory rather than in Python.
Adding a vertical must never require a code change. Operators keep their profiles
in `./profiles/<name>/`; the repo ships one reference profile inside the package
at `prospector/profiles/duct-cleaning/`.

Profiles are **content, not configuration-as-escape-hatch**. Review them the way
you review prose, and hold them to two rules:

- A profile cannot widen what the tool may do. It grants the drafting model no
  tools, no network, and no filesystem access, and it cannot disable citation
  validation, the locked-fallback rule, approval-gated sending, or the Facebook
  host guard. If a proposed profile key would weaken a guarantee above, the
  answer is no.
- A profile must never contain secrets, credentials, or a URL intended to be
  fetched. Credentials come from `.env`.

A profile is validated in full *before* any company is processed, so a malformed
one costs nothing and writes nothing. When you add a key, extend
`prospector/profiles.py` validation in the same PR — a key that silently defaults
is a key that silently ships the wrong copy. `prospector/profiles/duct-cleaning/` is
the bundled reference profile; keep it working, since the test suite asserts
against the copy it actually ships.

## Getting set up

Prospector requires **Python 3.11 or later**.

```bash
git clone https://github.com/anusbutt/Prospector.git
cd Prospector
python -m venv .venv
source .venv/bin/activate          # Windows: use WSL, then the same command
pip install -e ".[dev]"            # installs the package + test tools
```

Windows users should work inside **WSL** — the package lives in the Linux virtual
environment. See the "Running the CLI" section of the [README](README.md).

## Running the tests

```bash
pytest              # full suite
pytest -q           # quieter
pytest tests/unit/test_profiles.py      # a single file
pytest -k facebook                      # tests matching a keyword
```

Every change should keep the suite green. New behavior needs new tests; bug
fixes should include a test that fails before the fix and passes after.

## Development workflow

1. **Open an issue first** for anything non-trivial, so we can agree on the
   approach before you invest time.
2. **Branch** off `main` (e.g. `fix/duplicate-inbox-detection`).
3. **Keep changes small and focused.** Prefer the smallest diff that solves the
   problem; avoid unrelated refactors in the same PR.
4. **Add tests** and run `pytest` locally.
5. **Open a pull request** against `main`. CI runs the suite on your PR; it must
   pass before review.

## Coding conventions

- Match the style of the surrounding code: clear names, focused functions, and
  comments that explain *why* rather than *what*.
- The trust boundary is deterministic Python. The LLM controls phrasing, never
  factual acceptance — keep validation, classification, and citation checks in
  code, not in prompts.
- External services are called via direct HTTP/SDK calls. Don't add heavy
  frameworks or agent/orchestration machinery.
- Never hardcode secrets. Credentials come from the gitignored `.env`; never log
  or commit them.

## Commit and PR conventions

- Write imperative, descriptive commit subjects (e.g. `fix: guard against blank
  city tokens`). A short body explaining the reasoning is welcome.
- Reference the issue your PR closes.
- Keep the PR description focused on what changed, why, and how it was verified.

## Reporting bugs and requesting features

Use the GitHub issue templates. For bugs, include the command you ran, what you
expected, what happened, and the relevant output (with secrets redacted). For
security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public
issue.

## Code of conduct

Participation in this project is governed by our
[Code of Conduct](CODE_OF_CONDUCT.md). Please read it.
