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

- **Feature 002 (company sourcing) built, live-validated, and in production use.** `prospector source` discovers companies via Google Places across 30 US metros, filters to Meta-Pixel-confirmed advertisers (incl. GTM-container inspection), captures public emails, and outputs a `run`-compatible CSV. All 18 tasks in `specs/002-company-sourcing/tasks.md` checked; 260 tests green. Branch `002-company-sourcing`.
- **Outreach is live.** Full 30-metro sweep produced 465 unique companies → 111 pixel-confirmed → all drafted into `Vault/Outreach/` (109 ok, 2 isolated failures). Templates rewritten for the real product: **Nestaro** (lead_qualifier_feature.md) — free 10-day run for 5 duct-cleaning companies. Constitution at **v2.0.0** (Principle V redefined: product-fact FB mentions allowed; their-usage/ad claims still signal-gated). First 6 emails sent manually from personal Gmail and marked `status: sent` (5 named leads + ugly-ductling earlier); ⚠ user reported ~10 sent — 4–5 unlogged sends from the general queue still need identifying and marking, else double-send risk.
- Working CLI: `prospector source`, `prospector run <list>`, `prospector dashboard`. Vault workflow verified in Obsidian with Dataview; helper note `Named leads.md` added to the vault. Secrets in `.env`. ⚠ OpenRouter key rotation STILL pending (flagged since session 1).
- Next feature agreed in principle: `003-approved-send` — Gmail-API send of human-approved notes (`status: approved` → send → `sent`), daily cap ~15, dry-run default, send ledger; requires MAJOR amendment of Principle I; MUST use a Nestaro-domain account, never the personal Gmail. Not specced yet.
- Resume point: (1) identify + mark the unlogged sends; (2) rotate OpenRouter key; (3) continue manual sends ≤15/day from the to-send queue, work needs-review (12; most candidates are junk email-prefixes — reject to "team"); (4) watch replies → fill 5 Nestaro spots; (5) when volume justifies: `/sp.specify` 003-approved-send; (6) `002-campaign-profiles` still deferred until outside adoption/second vertical.

## Decisions log (append-only)

- FB access: open web only — no Graph API, no MCP, no FB scraping. (settled)
- Sourcing (002): Google Places only for discovery — no directory scraping, no lead DBs; Meta-ad targeting via on-site pixel detection (string inspection of the candidate's own HTML + its public GTM container JS from googletagmanager.com), never via FB Ad Library. `ad_signal` filters the list only, never appears in copy. (settled 2026-07-14; Principle II reconsidered at user request and kept)
- Principle V amended (constitution v2.0.0): claims about the PROSPECT's FB usage/ads remain signal-gated and ad-running is never claimed; describing the PRODUCT's own FB capability (Nestaro answers a page inbox) is allowed in every variant. (settled 2026-07-14)
- Offer/copy: product named "Nestaro" in outreach; free 10-day run for 5 duct-cleaning companies, set up by Anas; case-study framing dropped. (settled 2026-07-14)
- Sending: first batches manual from personal Gmail, ≤15/day; future 003-approved-send automates only human-approved notes via Gmail API on a Nestaro-domain account — never the personal account, never a transactional ESP. (agreed 2026-07-14, not yet specced)
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
- Next: (1) rotate the OpenRouter key; (2) open `Vault/Outreach/` in Obsidian + Dataview and confirm dashboard queues render (5 / 0 / 5); (3) first real outreach batch (real lists live locally in `samples/*.local.csv`); (4) optional `/sp.adr honesty-core-architecture`; (5) future idea, deliberately deferred: `002-campaign-profiles` to generalize templates/tags/stopwords per vertical.
- Notes: Live acceptance caught two things fixtures couldn't: (a) OpenRouter-via-Bedrock ignores response_format and fences JSON — parser now strips fences; (b) real sites produced page furniture ("Whether", "Quick", "Main") as high-confidence owner names — fixed with the first-names-list gate + regression tests. API key was pasted into .env.example at one point (a tracked file) — moved to gitignored .env, scrubbed; rotating the key is recommended.
- Session close (same day, publication leg): committed and pushed to https://github.com/anusbutt/Prospector — `main` made the default, feature branch pushed alongside. Then, per user direction, rewrote history twice to keep the public repo clean: first to strip PHRs (`history/`) and `tests/` (both now gitignored, local-only — note: no remote backup for them anymore), then to redact the real prospect CSVs (now `samples/*.local.csv`, replaced publicly by a fictional `companies.example.csv` that exercises every input feature). Rewrote README in professional detail (guarantees table, pipeline diagram, scoring tables, workflow, honest limitations), set repo description + 12 topics, added MIT license (copyright "Anas Yousuf (anusbutt)" — correct the name if wrong; GitHub detects MIT). Final public state verified via GitHub API: no tests/PHRs/real-lists anywhere in history; both branches at the license commit. Gotcha for the ledger: a failed `git rm --cached` was swallowed by `&&/||` chain precedence and the first rewrite pushed the OLD index — caught only by post-push remote-tree verification; do rewrites stepwise. Two advisory assessments recorded (PHR 0012/0013): generalization is feasible without quality loss for local-SMB verticals via campaign profiles (deferred, Constitution VI); repo kept public for credibility after redacting prospect data.

### 2026-07-14 — session 2

- Done: Feature 002 end to end via full SDD (PRODUCT.md §10 → constitution 1.1.0 → spec/plan/research/data-model/contracts → tasks 18/18, each acceptance-run). `prospector source`: Places Text Search across bundled 30-metro list, place_id+domain dedupe, Meta-Pixel detection, public-email capture, budgeted queries, pixel-filtered CSV. Live validation caught that inline pixels are ~extinct (GTM-mediated now) — spec amended with user approval, GTM-container inspection added (T018), hit rate 0→111. Templates rewritten for Nestaro (lead_qualifier_feature.md dropped this session): constitution v2.0.0 Principle V amendment, new locked copy (10-day free run, 5 spots), validator got a structural their-page-activity check; verified with a real 3-row LLM run. Full production runs: 30-metro sweep (465 unique, 111 pixel-positive, 182 emails, 30/60 query budget) and full drafting run (109/111 ok, 9 named high all source-traced, 12 needs-review). Vault opened in Obsidian + Dataview, `Named leads.md` helper note added, 5 named sends marked `sent` with dated Log lines. 260 tests green throughout.
- State: tasks.md (002) 18/18 complete. Vault holds ~119 companies: 6 sent, ~46 email to-send, 57 messenger DMs, 12 needs-review. Not yet committed at session start; committed+pushed at close (branch `002-company-sourcing`).
- Next: mark the user's ~4-5 unlogged sends; rotate OpenRouter key; keep manual sends ≤15/day; then `/sp.specify` 003-approved-send (Principle I MAJOR amendment, Gmail API on a Nestaro-domain account, approval queue = `status: approved`).
- Notes: Live-validation lesson repeated: offline fixtures can't catch ecosystem drift (GTM). Two run failures from malformed hrefs in prospect sites ("BookingLink" as hostname) — harden URL parsing someday. Needs-review candidates are mostly email-prefix junk ("Leads", "Retailmarketing") — the medium gate is doing its job. gitignore widened to `samples/*.local.*` so sweep/run logs with real prospect data stay local.
