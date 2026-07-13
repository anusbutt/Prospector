# PROGRESS.md — Prospector

**What this file is for:** narrative progress across sessions, so a fresh session with zero prior context can resume. This is **not** a task list — tasks live in spec-kit's `tasks.md`. This file holds *where we are* and *what happened*, nothing else.

## How to use this file

- **Read at session start** to resume (start from `CURRENT STATE` below).
- **Write only when the human asks** (usually at session close). When asked, append one entry to the Session Log using the format below, then update `CURRENT STATE`.
- Keep it honest: describe only what actually got done and runs.

## Entry format (per session)

```
### <date> — session N
- Done: <what shipped/works this session>
- State: <where things stand; which tasks.md items are complete>
- Next: <exact entry point for the next session>
- Notes: <blockers, decisions, gotchas — optional>
```

---

## CURRENT STATE

- **Build complete.** All 27 tasks in `specs/001-prospector-cli/tasks.md` checked off; 201 tests green; live-validated on 10 real companies (branch `001-prospector-cli`, nothing committed yet).
- SDD artifacts done: constitution v1.0.0, spec, plan, research, data-model, contracts, tasks. PHRs 0001–0007 under `history/prompts/`.
- Working CLI: `prospector run <list>` and `prospector dashboard`. Secrets in `.env` (gitignored; OpenRouter key present — user may want to rotate it, it transited chat).
- Resume point: human verifies `Vault/Outreach/` in Obsidian with Dataview (expected queues: 5 to-send / 0 needs-review / 5 messenger), then decide: commit + PR, and/or first real outreach batch. Pending ADR suggestion: honesty-core architecture (`/sp.adr honesty-core-architecture`).

## Decisions log (append-only)

- FB access: open web only — no Graph API, no MCP, no FB scraping. (settled)
- Output: Obsidian `.md` + YAML frontmatter + Dataview dashboard. Not a spreadsheet, not a web UI. (settled)
- Not building an email sender; sending is manual. (settled)
- Stack: Python + Typer, httpx/selectolax/trafilatura, Playwright fallback, OpenRouter single-shot, SQLite only if needed. (settled)
- Default angle: offer-led. (settled)
- Deterministic honesty core: scoring, fb_signal, and template selection are pure Python; the LLM only fills slots via strict JSON and a validator rejects unsourced names / FB mentions without signal / ad claims. (settled during plan, proven in build)
- Site-extracted name candidates must start with a known US first name (bundled 660-name list) — rare real names dropped beats fake names greeted. (settled after live acceptance caught "Whether"/"Quick" greeted as owners)
- Messenger DM drafts are fully deterministic (city is the only slot) — no LLM call for that bucket. (settled)
- Third-party enrichment (Hunter.io) never exceeds medium confidence. (settled)

## Session Log

### 2026-07-13 — session 1

- Done: Full SDD cycle end to end. Constitution v1.0.0 (7 hard principles), spec (6 user stories, 23 FRs, 7 SCs), plan + research + data-model + contracts, tasks.md (27 tasks) — then implemented all 27, one at a time, each checked off only after its acceptance command actually ran. Working package: `prospector run` (ingest → dedupe → resolve → polite fetch w/ hard Facebook-host block → extract → §7/§7.5 scoring → locked-template drafting via single-shot OpenRouter slot-JSON → idempotent vault merge → Dataview dashboard) and `prospector dashboard`. 201 tests (offline; network/LLM stubbed at transport level), plus fresh-venv install verified.
- State: tasks.md 27/27 complete. Live-validated twice: 2-company smoke, then 10-company real acceptance batch into `Vault/Outreach/` — 10/10 drafted, 3 names at high confidence all traceable to recorded sources (Michael Vinick, Brian Long, Karl Hafner), 5 messenger DMs, zero Facebook requests, zero fabrications after fix. SC-002..006 pass mechanically; SC-001 observed at 3/10 on this list (list-dependent; mechanism verified). Not committed to git yet.
- Next: (1) open `Vault/Outreach/` in Obsidian + Dataview and confirm dashboard queues render (5 / 0 / 5); (2) commit + PR if wanted (`/sp.git.commit_pr`); (3) optionally document the architecture ADR (`/sp.adr honesty-core-architecture`); (4) first real outreach batch.
- Notes: Live acceptance caught two things fixtures couldn't: (a) OpenRouter-via-Bedrock ignores response_format and fences JSON — parser now strips fences; (b) real sites produced page furniture ("Whether", "Quick", "Main") as high-confidence owner names — fixed with the first-names-list gate + regression tests. API key was pasted into .env.example at one point (a tracked file) — moved to gitignored .env, scrubbed; rotating the key is recommended.
