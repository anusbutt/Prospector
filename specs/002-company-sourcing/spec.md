# Feature Specification: Company Sourcing (`prospector source`)

**Feature Branch**: `002-company-sourcing`
**Created**: 2026-07-14
**Status**: Draft
**Input**: User description: "Company sourcing stage (prospector source) per PRODUCT.md §10: discover duct-cleaning companies via Google Places Text Search (New) across a configurable bundled list of ~30 US metro areas; dedupe by place_id and website domain; politely fetch each candidate homepage (Facebook-host block in force) and detect the Meta Pixel by string inspection producing ad_signal pixel|none; extract publicly listed contact email; output CSV in existing input format filtered to pixel-positive rows by default; GOOGLE_PLACES_API_KEY required with pre-flight error; bounded query count; ad_signal is a targeting filter only, never an ad-running claim in drafts"

## Context

Prospector's existing pipeline (feature 001) assumes an input list of companies already exists. This feature builds that list. The outreach offer is free setup of the **Lead Qualifier agent** — an assistant that answers incoming leads instantly, qualifies them, books the good ones into a dashboard, and notifies the owner. Its best first users are duct-cleaning companies already investing in Meta ads, because they have paid lead flow worth qualifying. Sourcing finds those companies nationwide and hands them to the existing `run` pipeline unchanged.

Intent lives in PRODUCT.md §10. Constitution v1.1.0 applies in full — notably Principle II (no Facebook host is ever contacted; the ad signal is read from the candidate's own website source) and Principle V (the ad signal filters the list and is never claimed in outreach copy).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Nationwide candidate discovery (Priority: P1)

As the operator, I run one command with a service keyword (default: duct cleaning) and get back a deduplicated list of real companies — name, city, website — gathered across ~30 major US metro areas, without doing any manual searching.

**Why this priority**: Everything else in this feature refines this list; without discovery there is nothing to filter or enrich. It is independently valuable even unfiltered — it replaces hours of manual directory searching.

**Independent Test**: Run `prospector source` with a valid key and a small metro subset; verify a CSV of unique companies with name/city/website appears and the reported counts are consistent.

**Acceptance Scenarios**:

1. **Given** a valid Places key and the bundled metro list, **When** the operator runs `prospector source --all`, **Then** a CSV is produced containing one row per unique discovered company with `company`, `website`, and `city` populated where available.
2. **Given** the same business is returned in two metro searches (or under two listings sharing one website domain), **When** sourcing completes, **Then** it appears exactly once in the output.
3. **Given** no `GOOGLE_PLACES_API_KEY` is configured, **When** the operator runs `prospector source`, **Then** the command fails before any network activity with a clear message naming the missing variable, and no output file is written.
4. **Given** the discovery service rejects or throttles a metro's query mid-run, **When** sourcing continues, **Then** the failure is reported per-metro in the summary and the remaining metros still complete.

---

### User Story 2 - Meta-ads targeting filter (Priority: P2)

As the operator, I want the output filtered to companies whose own websites carry Meta advertising tracking, so my first outreach batch targets businesses already paying for Meta leads — the ones with the strongest need for lead qualification.

**Why this priority**: This is the core targeting insight of the feature — but it only refines the P1 list, so it ships second.

**Independent Test**: Point the detector at fixture pages with and without Meta tracking markup; verify classification, and verify by transport-level assertion that no Facebook host is ever contacted.

**Acceptance Scenarios**:

1. **Given** a candidate website whose page source contains Meta Pixel tracking markup, **When** its homepage is inspected, **Then** the candidate is marked `ad_signal: pixel`.
2. **Given** a candidate website with no Meta tracking markup, **When** inspected, **Then** the candidate is marked `ad_signal: none` and is excluded from default output (kept with `--all`).
3. **Given** any candidate site (including ones full of Facebook links), **When** the entire sourcing run completes, **Then** zero requests were made to any Facebook host — detection is string inspection of the candidate's own page source only.
4. **Given** a candidate whose website is unreachable or has no website listed, **When** sourcing completes, **Then** the candidate is marked `ad_signal: none` (never guessed up), the failure is recorded, and the run continues.
5. **Given** a candidate whose homepage has no inline pixel markup but references a Google Tag Manager container whose public configuration contains Meta Pixel markers, **When** inspected, **Then** the candidate is marked `ad_signal: pixel` — and still zero requests were made to any Facebook host. *(Added 2026-07-14: live validation showed GTM-mediated installs are the dominant case.)*

---

### User Story 3 - Contact email capture (Priority: P3)

As the operator, I want each candidate's publicly listed email captured when one exists, so that downstream `run` routes them to the email channel instead of everything landing in the Messenger bucket.

**Why this priority**: Improves downstream channel routing but the list is usable without it — blank emails already have a defined path (messenger bucket).

**Independent Test**: Fixture pages with a `mailto:` link, a plain-text email, and no email; verify extraction picks the right value or leaves blank.

**Acceptance Scenarios**:

1. **Given** a candidate homepage (or its discoverable contact page) showing a public email address, **When** sourcing completes, **Then** that email appears in the candidate's `email` field.
2. **Given** no public email is found, **When** sourcing completes, **Then** the `email` field is blank and downstream `run` buckets the row as messenger, unchanged.
3. **Given** multiple emails on a page, **When** extracted, **Then** one is chosen by a deterministic preference order (documented in the plan) — never invented, never guessed from patterns.

---

### Edge Cases

- Zero pixel-positive candidates across the whole sweep → default output is an empty CSV with headers plus a summary explaining that `--all` would have kept N rows.
- Query budget exhausted mid-sweep → sourcing stops issuing new queries, reports which metros were covered, and writes the partial result.
- A candidate's site blocks fetching via robots.txt or errors → treated as `ad_signal: none` + recorded failure; never retried aggressively.
- Custom metro list file that is empty or malformed → pre-flight error naming the file, nothing written.
- Discovered business with no website at all → kept only with `--all` (no site means no pixel signal and nothing for downstream research to fetch).
- Re-running with the same parameters → output is regenerated deterministically from fresh queries; the output CSV is a plain file, not a merged store (the vault, downstream, is the idempotent store).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The tool MUST provide a `source` command that discovers companies for a service keyword (default: `duct cleaning`) across a set of US metro areas.
- **FR-002**: The tool MUST ship a bundled default list of approximately 30 major US metro areas, and MUST accept a user-supplied metro list as configuration (file), not code changes.
- **FR-003**: `source` MUST fail pre-flight with a clear error when `GOOGLE_PLACES_API_KEY` is absent, writing nothing; there is no fallback discovery mechanism.
- **FR-004**: Discovery MUST record, per candidate: company name, city/metro, website (when listed), and the provider's stable place identifier.
- **FR-005**: Candidates MUST be deduplicated across metros by place identifier and by website domain, collapsing multi-listing businesses to one row.
- **FR-006**: For each candidate with a website, the tool MUST fetch the homepage using the existing polite-fetch rules (bounded timeouts, limited retries, per-host spacing, robots.txt respected), with the Facebook-host block fully in force.
- **FR-007**: The tool MUST classify each candidate `ad_signal: pixel` when Meta Pixel tracking markup is present in the fetched page source, else `ad_signal: none`. Detection is string inspection only; no URL found in the page is ever fetched as part of detection, **except** that when the page references a Google Tag Manager container, the container's public configuration JS MAY be fetched (from the tag-manager host — never a Facebook host) and string-inspected the same way, since most modern pixel installs live there (amended 2026-07-14 after live validation found ~0% inline installs). Unreachable or missing websites classify as `none`; a failed container fetch also classifies as `none` (down, never up).
- **FR-008**: The tool MUST capture a publicly listed contact email (visible link or plain text on fetched pages) when present, choosing among multiple candidates by a deterministic preference order; absent → blank. Emails are never inferred or constructed.
- **FR-009**: Output MUST be a CSV in the existing feature-001 input format (`company`, `email`, `website`, `city`) plus an `ad_signal` column (which `run` ignores as an unknown column), so the file feeds `prospector run` without modification.
- **FR-010**: Default output MUST include only `ad_signal: pixel` rows; a `--all` flag keeps every discovered candidate.
- **FR-011**: Each run MUST enforce a configurable discovery-query budget with a default that keeps a full default sweep inside the provider's monthly free tier, and MUST report the number of queries used.
- **FR-012**: The run summary MUST report: metros covered, candidates discovered, duplicates collapsed, pixel-positive count, emails found, and per-candidate failures. Individual candidate failures MUST NOT abort the batch.
- **FR-013**: `ad_signal` MUST have no effect on drafting: it never selects templates, never alters copy, and never appears as a claim in any outreach draft (`fb_signal` rules from feature 001 are unchanged).
- **FR-014**: Exit codes MUST follow the existing convention: 0 = completed (with isolated failures reported), 1 = pre-flight failure (nothing written), 2 = unexpected mid-run crash.

### Key Entities

- **Candidate**: one discovered business — name, metro/city, website, stable place identifier, `ad_signal`, contact email (optional), failure notes. Exists only for the duration of sourcing; its durable form is a CSV row.
- **Metro list**: ordered set of US metro areas to sweep — bundled default (~30), overridable by config file.
- **Sourcing summary**: per-run report — metros covered, query count vs. budget, discovery/dedupe/filter/email counts, failures.

## Assumptions

- Results per metro are capped at a sensible default (the provider's standard page size) rather than exhaustively paginated — breadth across metros beats depth per metro for a first-users list; the cap may be made configurable later.
- Pixel detection inspects the homepage only; the contact page is additionally fetched only for email extraction when discoverable from the homepage.
- "Meta Pixel tracking markup" means the standard, publicly documented pixel installation patterns, inspected in the page source **and** in a referenced Google Tag Manager container's public configuration (amended 2026-07-14 — live validation showed GTM-mediated installs dominate; inline-only inspection found ~0%). Server-side-tagged installs may still be missed — misses are acceptable (a false `none` costs a candidate; a false `pixel` only costs one wasted outreach, and neither affects draft honesty).
- The output CSV is not a persistent store; re-runs regenerate it. Idempotent merging remains the vault's job downstream.
- The existing `run` pipeline needs no changes; the unknown-column warning for `ad_signal` is acceptable and already-specified behavior.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a single command, the operator obtains a ready-to-use candidate CSV covering the default nationwide metro set with zero manual searching, in one sitting (under ~30 minutes end to end for the default sweep).
- **SC-002**: Zero requests reach any Facebook host during a full sourcing run — mechanically verifiable, same standard as feature 001.
- **SC-003**: No business appears more than once in the output (verified across at least one known multi-metro/multi-listing case in live validation).
- **SC-004**: Default output contains only candidates with observed Meta-ad tracking on their own site; with `--all`, every discovered candidate is present with its `ad_signal` value.
- **SC-005**: A full default sweep stays within the configured query budget and the summary reports usage accurately.
- **SC-006**: The output CSV loads into `prospector run` unmodified, with `ad_signal` producing only the standard unknown-column warning.
- **SC-007**: No outreach draft produced from a sourced list contains an ad-running claim attributable to `ad_signal` (validator standard from feature 001 holds).
