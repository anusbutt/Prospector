# Research: Company Sourcing (`prospector source`)

**Date**: 2026-07-14 | **Plan**: [plan.md](./plan.md)

No NEEDS CLARIFICATION markers existed in the Technical Context; this document records
the concrete decisions behind each moving part.

## R1. Places API (New) Text Search request shape

- **Decision**: `POST https://places.googleapis.com/v1/places:searchText` with JSON body
  `{"textQuery": "<keyword> in <City>, <ST>", "maxResultCount": 20}` and headers
  `X-Goog-Api-Key` + `X-Goog-FieldMask: places.id,places.displayName,places.formattedAddress,places.websiteUri`.
  One request per metro; **no pagination** (page 1 only).
- **Rationale**: identical endpoint/header/field-mask pattern already proven in
  `resolve.py` (58:72:prospector/resolve.py) — only the field mask gains `places.id`
  (needed for dedupe) and the query becomes keyword+metro instead of a company name.
  20 results/metro × 30 metros ≈ 600 candidates — breadth beats depth for a
  first-users list (spec Assumptions). The field mask is kept minimal on purpose:
  every extra field risks a higher billing SKU and buys nothing.
- **Alternatives considered**: Nearby Search (needs lat/lng per metro — extra geocoding
  queries for no gain); legacy Text Search (older SKU, project already uses New);
  pagination via `pageToken` (triples query cost for tail-quality results).

## R2. Query budget

- **Decision**: budget counts **Places requests only** (homepage fetches are free and
  polite by construction). Default cap: **60 per run** (`--max-queries`), double the
  default sweep's 30, leaving headroom for a custom metro file. When the cap is hit,
  no further Places queries are issued; metros covered so far are reported and the run
  completes normally on partial data (spec Edge Cases).
- **Rationale**: exact Text Search SKU pricing changes; what matters is the order of
  magnitude — tens of requests per sweep against a monthly free credit that covers
  thousands. The implementation task verifies current pricing and documents it in the
  summary output ("N queries used, budget M").
- **Alternatives considered**: per-month persistent budget ledger (needs state storage —
  Constitution VI says no persistence without demonstrated need); no cap (one malformed
  metro file could burn quota).

## R3. Meta Pixel detection markers

- **Decision**: `detect_pixel(html: str)` returns `"pixel"` iff the raw HTML contains
  (case-insensitive) any of:
  1. `connect.facebook.net` (the pixel loader host — covers `fbevents.js` includes),
  2. `fbq(` (the pixel's global init/track function),
  3. `facebook.com/tr` (the `<noscript>` image beacon URL, inspected as text).
  Else `"none"`. Pure function, no network capability; input is the homepage body
  already fetched through `Fetcher`.
- **Rationale**: these are the three components of Meta's publicly documented standard
  pixel snippet; any real install contains at least one. String inspection keeps
  Principle II airtight — nothing is fetched, and even a hostile page full of Facebook
  URLs can only ever be *read*. False negatives (tag-manager-only installs) are
  accepted per spec Assumptions; false positives are near-impossible (these strings
  don't occur in prose).
- **Alternatives considered**: executing JS via Playwright to observe the pixel firing
  (heavyweight, slower, and would make requests to Facebook hosts — Principle II
  violation); parsing `<script>` tags with selectolax first (adds nothing over
  substring checks and misses the noscript beacon).
- **AMENDED 2026-07-14 (live validation)**: a real 2-metro sweep (29 fetched sites)
  plus manual checks of known heavy Meta advertisers found **zero** inline installs —
  modern pixels are overwhelmingly loaded via Google Tag Manager, whose config never
  appears in page HTML. Decision extended with user approval: when the page references
  a GTM container (`GTM-XXXXXXX` id near a `googletagmanager.com` reference), fetch
  that container's public JS once — `https://www.googletagmanager.com/gtm.js?id=<id>`,
  a Google host, never a Facebook host, Principle II intact — and apply the same
  three markers to it. At most 2 container ids checked per site; any container-fetch
  failure classifies down to `none`. Server-side tagging remains an accepted miss.

## R4. Public email extraction

- **Decision**: deterministic preference order over the fetched page(s):
  1. first `mailto:` href in document order (query params like `?subject=` stripped),
  2. else first plaintext match of a conservative email regex in the page text.
  Lowercased; obvious asset false-positives rejected (ends in `.png`/`.jpg`/`.webp`
  etc.); if the homepage yields nothing, fetch at most **one** same-host contact page
  discovered from nav links (path containing `contact`), robots-respected via the
  existing `Fetcher`, and repeat the same order there. Nothing found → blank.
- **Rationale**: mailto links are author-intended contact addresses — strictly better
  evidence than scraped text. One contact-page hop mirrors 001's nav-discovery pattern
  without importing its full page-set logic. Never constructing emails keeps FR-008's
  "never inferred" guarantee trivially true.
- **Alternatives considered**: preferring `info@`-style role addresses (arbitrary —
  document order is simpler and deterministic); Hunter.io enrichment (belongs to 001's
  enrich step, out of sourcing scope); crawling all subpages (impolite, slow, low yield).

## R5. Bundled metro list

- **Decision**: `prospector/data/us_metros.txt` — 30 lines, `City, ST` format, chosen
  as the largest US metros by population (NYC, LA, Chicago, Dallas, Houston, DC,
  Philadelphia, Atlanta, Miami, Phoenix, Boston, San Francisco, Riverside, Detroit,
  Seattle, Minneapolis, San Diego, Tampa, Denver, Baltimore, St. Louis, Orlando,
  Charlotte, San Antonio, Portland, Sacramento, Pittsburgh, Austin, Las Vegas,
  Cincinnati). Blank lines and `#` comments ignored. `--metros FILE` overrides with the
  same format; empty/malformed file → pre-flight error (spec Edge Cases).
- **Rationale**: population is a fair proxy for duct-cleaning + Meta-ads density; the
  list is data, not code (PRODUCT.md §10), loaded via the same package-data mechanism
  as `first_names.txt` (32:33:pyproject.toml).
- **Alternatives considered**: MSA census data file (overkill for 30 rows); geocoded
  lat/lng list (only needed for Nearby Search, rejected in R1).

## R6. Dedupe keys

- **Decision**: two-pass dedupe, first by Places `id` (exact), then by website domain —
  host lowercased with a single leading `www.` stripped; no eTLD+1 library. Candidates
  without a website only dedupe by place id. First-seen row wins (metro order is the
  bundled list order, so bigger metros win ties).
- **Rationale**: place id catches the same listing returned by overlapping metro
  queries; domain catches multi-listing businesses (spec US1/AS2). A public-suffix
  library would add a dependency to handle cases (`co.uk`) that don't occur in a
  US-metro sweep (Constitution VI).
- **Alternatives considered**: fuzzy name matching (false-merge risk between
  identically named companies in different cities — worse than an occasional dup).

## R7. Output CSV & downstream compatibility

- **Decision**: UTF-8 CSV, header `company,email,website,city,ad_signal`, written via
  stdlib `csv`. Default rows: `ad_signal == "pixel"` only; `--all` keeps everything
  (including no-website candidates, whose `ad_signal` is `none`). Default output path
  `candidates.csv` in CWD, `--out` to override.
- **Rationale**: first four columns are exactly 001's documented input format
  (README "Input format"; ingest treats unknown columns as a warning), verified by a
  contract test that pipes sourced output into `prospector run --no-llm --limit 1`
  fixtures. Keeping `ad_signal` in the file preserves the audit trail of *why* a row
  made the list without touching 001's ingest.
- **Alternatives considered**: writing directly into the vault (sourcing is discovery,
  not research — the human should be able to inspect/trim the list before spending
  fetch/LLM effort); a second file for excluded rows (`--all` covers the need).

## R8. Where the code lives

- **Decision**: one new module `prospector/source.py` holding the Places searcher,
  dedupe, pixel detector, email extractor, CSV writer, and `SourcingSummary`; one new
  CLI command in `cli.py`; one helper `require_places()` in `config.py`. `resolve.py`
  is left untouched.
- **Rationale**: smallest viable diff (Constitution VI). The Places call in
  `resolve.py` answers "what is this known company's website?" while sourcing asks
  "what companies exist for this keyword+metro?" — different queries, different result
  handling; sharing a client now would couple them for ~15 saved lines. Extract a
  shared `places.py` only when a third consumer appears.
- **Alternatives considered**: extending `resolve.py` (muddies 001's tested module);
  a `sourcing/` subpackage (structure without need).
