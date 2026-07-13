# Research: Prospector — Outreach Research & Draft Vault

**Date**: 2026-07-13 | **Plan**: [plan.md](./plan.md)

All Technical Context unknowns resolved below. Format: Decision / Rationale /
Alternatives considered.

## R1. Website resolution without a provided URL

- **Decision**: Try Google Places API (Text Search → place details incl. website) when
  `GOOGLE_PLACES_API_KEY` is set; otherwise (or when Places has no website) fall back to
  DuckDuckGo HTML search (`html.duckduckgo.com/html/?q=<company> <city>`) and take the
  top organic result whose domain plausibly matches the company name; validate by
  fetching the homepage and checking the company name appears.
- **Rationale**: Places gives clean business data (name, city, website) with a settled
  key; DDG HTML needs no key, no JS, and tolerates polite scraping — keeps the tool
  usable with only an OpenRouter key (FR-022 degradation).
- **Alternatives**: Google Custom Search API (quota + billing setup for marginal gain);
  Bing API (retired); Serper/SerpAPI (extra paid dependency — gold-plating for ≤100-row
  batches).

## R2. Fetch + extract stack

- **Decision**: httpx with explicit timeouts (10s connect/15s read), custom UA, ≤3
  pages per site from a fixed path set (`/`, `/about*`, `/team*`, `/contact*` — matched
  from homepage nav links, not blind guesses), serial per host. selectolax for DOM
  queries (footer, nav, mailto:, FB links/widgets); trafilatura for main-text extraction
  feeding name/hook heuristics. Playwright (chromium, headless) only when httpx returns
  a JS-shell page (heuristic: <500 chars of extracted text AND markers like `__NEXT_DATA__`/
  `id="root"`), and only if Playwright is installed — otherwise record the limitation.
- **Rationale**: Small-business sites are mostly static or WordPress; httpx+selectolax
  covers the bulk cheaply. Trafilatura is the strongest pure-Python boilerplate
  remover. Lazy Playwright keeps install light (Constitution VI) while §4 explicitly
  allows the fallback.
- **Alternatives**: requests+BeautifulSoup (slower parsing, no async need though — kept
  simple sync anyway); Scrapy (framework overhead, violates smallest-viable);
  always-Playwright (10× slower, heavier install).

## R3. Name extraction heuristics (deterministic)

- **Decision**: Layered extractors producing `Evidence(kind, value, source_url, excerpt)`:
  (a) regex over extracted text for `owner|founder|president|proprietor` within ±60
  chars of a capitalized name bigram; (b) `/about`-`/team` page person-name patterns
  (heading + role); (c) copyright-footer names; (d) email local-part parsing:
  `first.last@`, `firstlast@` (against a bundled top-1000 US first-names list),
  `firstb@`/`f.last@` patterns. Candidates matching the company name, service words, or
  city are rejected. Names are *sourced* — every candidate carries its evidence.
- **Rationale**: FR-010/012 require every used name to trace to a recorded source, and
  §7's tiers map directly onto evidence kinds: (a)/(b)/unambiguous-email → high;
  partial/ambiguous email or footer-only → medium. Deterministic rules are unit-testable
  (Constitution IV/VII).
- **Alternatives**: LLM-based name extraction (unverifiable, fabrication risk —
  constitutionally barred from this role); spaCy NER (50MB model for marginal lift on
  this page set; can add later behind the same Evidence interface if hit rate
  disappoints).

## R4. fb_signal evidence (open web only)

- **Decision**: Observable signals collected without any FB request: (1) FB link in
  site nav/footer/social block; (2) FB page *embedded* (iframe/plugin src referencing
  facebook — detected from the HTML source string, never fetched); (3) Messenger/FB
  chat widget script tags (`connect.facebook.net`, `xfbml.customerchat`) — detected in
  source, never executed; (4) DDG search `"<company>" facebook` returning a facebook.com
  result whose *snippet* shows recency/review cues; (5) `facebook_url` provided as
  input. Classification per §7.5: strong = ≥2 signals with at least one active-usage cue
  (widget/embed/active-in-search); weak = exactly one soft signal; none = zero. Uncertain
  → down-rank.
- **Rationale**: All five are readable from HTML we already have or search snippets —
  zero Facebook requests (SC-005). Deterministic → unit-testable against fixtures.
- **Alternatives**: fetching the FB page "just to check it exists" (constitutional
  violation, rejected); third-party FB-analytics APIs (paid, unnecessary, and most
  scrape FB themselves — reputational risk by proxy).

## R5. OpenRouter single-shot drafting

- **Decision**: Direct `POST https://openrouter.ai/api/v1/chat/completions` via httpx.
  Default model `anthropic/claude-sonnet-4.5` (config-overridable via `OPENROUTER_MODEL`).
  One call per company. Request: system prompt = honesty rules + the *selected* locked
  template with slots marked; user content = JSON of gated slot values `{company,
  name_or_team, channel, hook, city, angle, fb_signal, variant, is_generic_inbox}`.
  Response contract: strict JSON (`response_format: json_object`) returning only slot
  fills (`greeting_name`, `hook_phrase`, `subject_company`). Code assembles the final
  draft from template constant + fills; validator checks the result. Temperature 0.3.
  On API failure: mark company failed in summary, `needs_review: true`, no draft.
- **Rationale**: Single-shot, direct call (Constitution VI). Making the model return
  slot JSON instead of the whole message means template prose *cannot* be paraphrased
  (FR-015) and validation is trivial.
- **Alternatives**: model returns full message text (paraphrase risk, weaker
  validation); OpenAI/Anthropic SDK direct (OpenRouter settled in PROGRESS.md for model
  flexibility); LangChain (constitutionally barred).

## R6. Frontmatter + idempotent merge

- **Decision**: PyYAML with a fixed key order (§6 schema order) and explicit str
  quoting rules; notes rendered via a single serializer so identical data → identical
  bytes (SC-006). Merge algorithm: parse existing note into (frontmatter, sections by
  `## ` heading); machine-owned = all frontmatter keys except `status`, plus `## Draft`
  and `## Research`; human-owned = `status` (kept unless still default `to-send`… rule:
  status is *never* machine-changed after first write) and `## Log` body verbatim.
  Unknown/extra human-added sections are preserved verbatim, appended after known ones
  in original order. Write only when rendered bytes differ.
- **Rationale**: FR-019 and US5 demand byte-idempotency and human-edit safety; a single
  canonical serializer is the simplest way to guarantee both. python-frontmatter lib
  adds a dependency for what is ~30 lines with PyYAML.
- **Alternatives**: python-frontmatter (uses PyYAML underneath, less control over key
  order/quoting → idempotency risk); ruamel.yaml round-trip (heavier; we own both ends
  so canonical form is easier).

## R7. Slugging & collision handling

- **Decision**: `slugify(company)` — lowercase, ASCII-fold, non-alnum → `-`, collapse,
  trim, max 80 chars. On collision with a *different* company (different email/domain):
  append `-<city-slug>` if available, else `-<email-domain-slug>`, else `-2`, `-3` …
  chosen deterministically by input order. Slug recorded in frontmatter (`slug:` is the
  filename, implicit) so re-runs match existing notes by filename first, then by
  `company+email` frontmatter scan as fallback.
- **Rationale**: Edge case in spec (same-name companies, unsafe filename chars);
  deterministic disambiguation keeps re-runs stable.
- **Alternatives**: UUID suffixes (unstable across runs — breaks idempotency); hashing
  email into every slug (ugly filenames for the common no-collision case).

## R8. Dedupe rules

- **Decision**: Duplicate groups keyed by (a) exact normalized email match, or (b) same
  email domain when the domain is not in a free-provider list (gmail.com, yahoo.com,
  hotmail.com, outlook.com, aol.com, icloud.com, comcast.net, etc. — bundled constant).
  First row in input order is primary; others get `duplicate_of: <primary-slug>` in
  frontmatter, `status: dead` is NOT set (human decision) — they get `needs_review: true`
  and a `## Research` note "shares inbox with <primary>". Only primaries land in the
  to-send queue (dashboard filters `duplicate_of` absent).
- **Rationale**: FR-003/SC-003; §1 explicitly calls out "two businesses sharing one
  inbox → one send". Free-provider domains legitimately shared by unrelated businesses
  must not group.
- **Alternatives**: fuzzy company-name dedupe (false-positive risk, not in PRODUCT.md —
  gold-plating).

## R9. Testing strategy

- **Decision**: Three tiers. (1) Unit: score.py, enrich.py, ingest.py dedupe, vault
  merge/idempotency, draft validator, slug rules — pure functions, no I/O. (2) Fixture
  integration: recorded HTML pages (checked into tests/fixtures/) + stubbed
  OpenRouter responses (respx transport mock) drive a full `run` over a sample CSV;
  asserts vault contents, byte-idempotency on second run, zero requests to blocked
  hosts (mock transport records every URL). (3) Live smoke: manual `prospector run`
  on a 3–5 row real list with real keys — the Constitution VII acceptance gate, run by
  the implementer and recorded in the run summary.
- **Rationale**: Honesty rules are the product; they must be provable offline and
  repeatable. respx intercepts at the httpx-transport level, which also proves the FB
  block fires before any socket.
- **Alternatives**: VCR-style cassette recording (records live traffic — flaky, and
  we'd be fetching real small-business sites in CI); live-only testing (violates
  repeatability and Constitution VII's "actually run" in an automatable way).

## R10. Politeness & rate limits

- **Decision**: Per-host serial fetching with 1s spacing between requests to the same
  host; global concurrency ≤4 hosts at a time (async httpx); 2 retries max with
  exponential backoff on 5xx/timeouts only; custom User-Agent identifying the tool;
  robots.txt checked for the extra paths (`/about` etc.) — homepage always allowed
  fetch. DDG queries spaced ≥2s.
- **Rationale**: FR-023 / constitution "rate courtesy"; targets are small-business
  sites.
- **Alternatives**: no robots handling (rude, and constitution names it); full
  robots-for-everything (blocks the homepage on misconfigured sites — homepage fetch is
  the product's floor, and a single page-load matches normal browser behavior).
