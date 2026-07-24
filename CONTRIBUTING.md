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

1. **Facebook is never contacted.** The tool makes no request to any Facebook or
   Messenger host — no Graph API, no scraping, no fetching a `facebook_url`. All
   outbound HTTP passes through a host guard that rejects those hosts before any
   network activity. Facebook URLs are stored only as input/target signals.
   *(See the fetch host-guard and its tests.)*

2. **Sending is human-approved only.** The tool never sends anything a human has
   not explicitly marked `status: approved`. Real sending requires an explicit
   flag (dry-run is the default), is bound to the configured dedicated mailbox,
   is capped, and every send is recorded in an append-only ledger that prevents
   duplicates. No copy is generated or altered on the send path.
   *(See `prospector/send.py` and its tests.)*

3. **Nothing is fabricated.** Names, personalization hooks, and any claim about a
   prospect must be backed by captured evidence and validated deterministically
   in plain Python. Copy that cannot be validated is discarded and replaced with
   a locked fallback template. Validation is never delegated to a model.
   *(See `prospector/draft.py` / `prospector/agent_draft.py` and their tests.)*

4. **Assisted Messenger delivery is human-performed.** `prospector dm` may copy a
   draft to your clipboard and open a page in *your own* browser, but the tool
   never sends a Messenger message and never automates a browser. You send it.
   *(See `prospector/dm.py` and its tests.)*

5. **The Obsidian vault is the interface.** Output is plain Markdown notes plus a
   dashboard note. No web UI, server, or GUI is added.

If your change touches any of these areas, please call out in your PR how the
guarantee is preserved, and add or update the test that proves it.

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
pytest tests/unit/test_dm.py            # a single file
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
