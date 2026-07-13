# Quickstart: Prospector

## Setup

```bash
# Python 3.11+
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # installs prospector + pytest tooling

cp .env.example .env             # then fill in:
# OPENROUTER_API_KEY=...         # required for drafting
# GOOGLE_PLACES_API_KEY=...     # optional — better resolution/city data
# HUNTER_API_KEY=...            # optional — email-name enrichment

# Optional, only for JS-rendered sites:
pip install playwright && playwright install chromium
```

## Run a batch

```bash
# companies.csv:
# company,email,website,city
# Boston Air Duct Cleaning,info@bostonairduct.com,,Boston

prospector run companies.csv                 # writes Vault/Outreach/
prospector run companies.csv --vault ~/Obsidian/Outreach
prospector run companies.csv --limit 3       # try a few first
prospector run companies.csv --no-llm        # research only, no drafts
prospector run companies.csv --only boston-air-duct-cleaning   # one company
```

Open the vault folder in Obsidian. Install the **Dataview** community plugin to make
`_Dashboard.md` queries live (notes work fine without it).

## Review loop

1. Open `_Dashboard.md` → **Needs review**: confirm/fix `name_candidate` rows, edit
   frontmatter if you know better, clear `needs_review`.
2. **To-send queue**: read each `## Draft`, paste into your inbox, send manually.
3. After sending, change `status: sent` in the note (the tool never touches `status`
   again, and never touches `## Log`).
4. Re-run anytime — safe: `prospector run companies.csv` updates research without
   clobbering your edits.

## Tests

```bash
pytest                    # unit + fixture integration (offline, no keys needed)
pytest tests/unit -q      # fast honesty-rule checks
```

## What it will never do

Send anything. Touch Facebook. Invent a name. Claim someone runs ads.
