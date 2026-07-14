# Quickstart: Company Sourcing (`prospector source`)

**Prerequisite**: `GOOGLE_PLACES_API_KEY` in `.env` (required — `source` exits 1
without it; see README Configuration).

```bash
# 1. Smoke test: 2 metros, keep everything, see what comes back
prospector source --limit 2 --all --out /tmp/smoke.csv --verbose

# 2. Real sweep: 30 bundled metros, pixel-positive candidates only
prospector source --out candidates.csv

# 3. Inspect the summary (printed on stdout):
#    metros covered, queries used vs budget, discovered, duplicates collapsed,
#    pixel-positive, emails found, rows written, failures

# 4. Feed straight into the existing pipeline (research only, no drafting):
prospector run candidates.csv --no-llm --limit 3

# 5. Custom targeting later:
prospector source --keyword "air duct cleaning" --metros my_metros.txt --all
```

**What to expect**: ~600 raw results from a full sweep, collapsing to fewer after
dedupe; pixel-positive share is list-dependent (this *is* the targeting filter — a
small number is the filter working, not failing). Rows with a blank `email` will land
in 001's messenger bucket downstream.

**What it will never do**: contact a Facebook host, paginate past page 1, exceed
`--max-queries`, invent an email, or influence draft copy (`ad_signal` is
filter-only; 001 ignores the column with its standard warning).
