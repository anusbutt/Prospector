# Prospector

**A CLI batch tool that turns a raw list of local service companies into an
Obsidian vault of honest, personalized, paste-ready outreach drafts.**

Cold outreach converts far better when each message carries the owner's first
name and one specific, true hook. Producing that by hand across a list is slow,
repetitive research: find the site, dig for a name, note the city, catch
duplicate inboxes, sort out who has no email. Prospector automates the research
and personalization — the expensive part — and leaves sending to you.

Built for duct-cleaning outreach first; the pipeline itself is
vertical-agnostic.

---

## Guarantees

These are hard constraints enforced in code and tests, not aspirations
(see [`.specify/memory/constitution.md`](.specify/memory/constitution.md)):

| # | Guarantee | How it's enforced |
|---|-----------|-------------------|
| 1 | **Never sends anything** | There is no send code path, no SMTP/API dependency, and no `send` command. Output is drafts in markdown. |
| 2 | **Never touches Facebook** | Every outbound request passes through one HTTP choke point that raises on `facebook.com`, `fb.com`, `fb.me`, `fbcdn.net`, and `messenger.com` before any network activity. A `facebook_url` input is stored as a signal and never fetched. |
| 3 | **Never fabricates a name** | A real first name appears in a draft only at high confidence, and only when it traces to a recorded source (a page URL and excerpt). A validator rejects any unsourced name, even if the LLM produces one. |
| 4 | **Never claims what it can't observe** | Ad-running is never claimed or implied. Statements about the *prospect's own* Facebook activity appear only when observed open-web signals support them (uncertain signals always rank *down*); describing the offered product's Facebook capability is a product fact, not a claim about the prospect. |
| 5 | **No web UI** | The Obsidian vault *is* the interface. |

## How it works

```
CSV / markdown list
      │
      ▼
ingest ──► dedupe & bucket ──► resolve ──► fetch ──► extract ──► score ──► draft ──► vault
                                (Places /   (polite,   (names,     (§ conf-  (locked    (one note per
                                 DuckDuckGo)  FB-host    city, hook, idence +  templates, company +
                                              blocked)   FB signals) fb_signal) 1 LLM call) dashboard)
```

1. **Ingest & dedupe** — parses CSV or markdown tables, normalizes rows, and
   detects shared inboxes (identical emails always group; shared custom domains
   group; two unrelated businesses on gmail.com don't). One send per inbox.
2. **Bucket** — a valid email routes to the email channel; a blank field, the
   word `messenger`, or a Facebook URL in the email field routes to the
   Messenger bucket (which gets a DM draft instead).
3. **Resolve** — when no website is given: Google Places (if a key is
   configured) with a DuckDuckGo HTML fallback, validated against the homepage.
4. **Fetch** — homepage plus nav-discovered `/about`, `/team`, `/contact`
   pages. Polite by design: bounded timeouts, ≤2 retries, per-host spacing,
   robots.txt respected for subpages.
5. **Extract** — deterministic (non-LLM) extraction of owner-name candidates,
   city/service area, one personalization hook, and Facebook-usage signals —
   each carrying its source URL and a text excerpt as evidence.
6. **Score** — name confidence and channel fit (see tables below). All scoring
   is plain, unit-tested Python. The LLM never makes a trust decision.
7. **Draft** — one LLM call per company (OpenRouter, direct HTTP, no agent
   framework). The model returns *slot values only* as strict JSON; the locked
   template prose is assembled in code and cannot be paraphrased. A validator
   then rejects unfilled slots, altered template text, unsourced names,
   Facebook mentions without signal, and ad-running vocabulary. Messenger DMs
   are fully deterministic — no LLM call at all.
8. **Write vault** — one note per company plus a `_Dashboard.md` of Dataview
   queries. Re-runs are byte-idempotent and merge by section ownership: your
   `status` edits, `## Log` entries, and any sections you add are never
   touched.

### Name confidence

| Level | Meaning | Effect on the draft |
|-------|---------|---------------------|
| `high` | Explicit owner text, an `/about`–`/team` page name, or an unambiguous email pattern (`scottb@`, `john.smith@`) | Greeted by first name |
| `medium` | Partial/ambiguous evidence (`derickson@` — surname-likely; footer-only names; third-party enrichment) | Greeting stays "[Company] team"; candidate stored in `name_candidate`; flagged `needs_review` |
| `none` | Nothing found | "[Company] team" |

Site-extracted candidates must additionally start with a known US first name
(bundled 660-name list) — losing a rare real name beats greeting a fake one.

### Channel fit (`fb_signal`)

All read from the open web — the Facebook page itself is never contacted:

| Signal | Rule | Template variant |
|--------|------|------------------|
| `strong` | Two or more observed signals, at least one showing active usage (chat widget, page embed, active page in search snippets) | Facebook variant |
| `weak` | Exactly one signal, or presence without activity cues | Channel-agnostic, with one conditional Facebook mention |
| `none` | Nothing observed | Channel-agnostic, no Facebook mention at all |

Uncertainty always ranks down, never up.

## Installation

Requires Python 3.11+.

```bash
git clone https://github.com/anusbutt/Prospector.git
cd Prospector
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

cp .env.example .env   # then add your keys
```

### Configuration

| Variable | Required | Behavior when absent |
|----------|----------|----------------------|
| `OPENROUTER_API_KEY` | For drafting | Pre-flight error (or run with `--no-llm`) |
| `OPENROUTER_MODEL` | No | Defaults to `anthropic/claude-sonnet-4.5` |
| `GOOGLE_PLACES_API_KEY` | For `source` | `source` exits pre-flight (no fallback discovery); `run`'s website/city resolution falls back to DuckDuckGo only |
| `HUNTER_API_KEY` | No | Email-name enrichment skipped (capped at medium confidence when present) |

Secrets live in `.env` (gitignored). Nothing is ever logged or committed.

## Sourcing (optional): build the list itself

`prospector source` discovers companies before any of the above runs — for when
you don't have a list yet:

```bash
prospector source                                  # 30 major US metros -> candidates.csv
prospector source --limit 2 --all --verbose        # small smoke test, keep everything
prospector source --keyword "air duct cleaning" --metros my_metros.txt
prospector run candidates.csv                      # output feeds run unchanged
```

Per metro it queries Google Places Text Search once (budgeted — `--max-queries`,
default 60, usage reported), dedupes across metros by place id and website
domain, then fetches each candidate's **own homepage** (same polite fetcher,
same Facebook-host block) and inspects the HTML source for **Meta Pixel**
tracking markup — including inside any referenced Google Tag Manager
container's public configuration, where most modern installs live. Companies whose sites carry the pixel — businesses already
investing in Meta ads — are written to the CSV (`ad_signal: pixel`); pass
`--all` to keep every discovered company. A publicly listed contact email is
captured when one exists (never inferred); rows without one route to the
Messenger bucket downstream.

Two honesty notes, enforced in code: pixel detection is string inspection of
already-fetched pages — **no Facebook host is ever contacted** — and
`ad_signal` is a targeting filter only. It is ignored by `run` and can never
appear as an ad-running claim in a draft (a pixel can be dormant; guarantee #4
stands).

## Input format

CSV or markdown table. Minimum columns: `company`, `email`. Optional:
`website`, `facebook_url`, `city`, `owner_name`, `notes`. Headers are
case-insensitive; unknown columns are ignored with a warning; malformed rows
are reported by number without aborting the batch.

See [`samples/companies.example.csv`](samples/companies.example.csv) for a
fictional list exercising every feature: email and messenger buckets, a
Facebook-URL email field, a human-supplied owner name, and a shared-inbox
duplicate pair.

## Usage

```bash
prospector run companies.csv                       # writes Vault/Outreach/
prospector run companies.csv --vault ~/Obsidian/Outreach
prospector run companies.csv --limit 3             # try a few rows first
prospector run companies.csv --no-llm              # research & score only
prospector run companies.csv --only summit-duct-care
prospector dashboard --vault ~/Obsidian/Outreach   # refresh _Dashboard.md only
```

Exit codes: `0` batch completed (individual company failures are isolated and
reported in the summary), `1` pre-flight failure (nothing written), `2`
unexpected mid-run crash (already-written notes remain valid; re-running
resumes safely).

## Output

One note per company, keyed by a stable slug:

```markdown
---
company: Summit Duct Care
email: info@summitduct.example.com
channel: email
status: to-send
name_used: team
name_confidence: none
name_candidate:
hook: Denver service area
website: summitduct.example.com
angle: offer-led
fb_signal: none
duplicate_of:
needs_review: false
tags: [outreach, duct-cleaning, prospector]
---

## Draft
**Subject:** ...paste-ready subject...

...paste-ready body...

## Research
- Owner name: not found (no /about page)
- Sources: every URL consulted, including failures
- Hook: Denver service area (input row: "city: Denver")
- fb_signal: none — no FB link/widget/search presence found
- Failures: (none)

## Log
-
```

`_Dashboard.md` provides live queues via the
[Dataview](https://blacksmithgu.github.io/obsidian-dataview/) community plugin
(to-send, needs-review, messenger bucket, pipeline by status). Without
Dataview, everything still works as plain markdown.

### Review workflow

1. Open the vault folder in Obsidian.
2. **Needs review** queue: confirm or reject `name_candidate` suggestions,
   clear `needs_review`.
3. **To-send** queue: read the draft, paste it into your own inbox, send, and
   set `status: sent`.
4. Re-run whenever the list changes. The tool updates its own fields and never
   overwrites yours — `status` is written once and never machine-changed
   again, and `## Log` plus any custom sections are preserved verbatim.

## Design notes

- **Deterministic honesty core, LLM at the edge.** Everything that affects
  trust — confidence scoring, signal classification, template selection,
  validation — is plain Python with unit tests. The LLM's only job is phrasing
  slot values, and even those are validated after the fact.
- **Spec-driven.** The project was built constitution → spec → plan → tasks →
  implementation; all artifacts are in [`specs/001-prospector-cli/`](specs/001-prospector-cli/)
  and the product intent in [`PRODUCT.md`](PRODUCT.md).
- **Verification.** A 200-test offline suite (network and LLM stubbed at the
  httpx-transport level) covers the pipeline, including transport-level proof
  that no request ever reaches a Facebook host and golden tests that locked
  template prose survives byte-for-byte. Validated live against real companies
  before release. The suite is kept out of this repository.

## Honest limitations

- Name hit rate on real lists runs roughly 30–60% depending on how much the
  target sites disclose — the goal is lift over manual research, not
  perfection. Everything below high confidence is flagged, never guessed.
- Heuristics are tuned for US/English local-service businesses with simple
  websites. Enterprises, e-commerce, and non-English markets would need work.
- The message templates encode one specific offer and voice. Adapting the tool
  to another vertical means supplying your own templates (a planned
  campaign-profile feature would make that configuration, not code).

## License

[MIT](LICENSE)
