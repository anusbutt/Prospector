# PRODUCT.md — Prospector

**What this file is for:** the product spec — the *what* and *why*. This is the source of truth spec-kit reads to generate the spec / plan / tasks. It does **not** contain a task list or build phases; those are generated and tracked by spec-kit (`tasks.md`). If reality forces a change to intent, update this file first, then let the plan regenerate.

## 1. Problem

Cold outreach to home service companies (duct cleaning first) converts far better when each message carries the owner's first name and one specific hook. Producing that by hand across a list is slow, repetitive research: find the site, dig for a name, note the city/service, catch duplicate inboxes, sort out who has no email. Sending is trivial and already solved. **The research and personalization is the expensive part — that is what this tool automates.**

Target lift: move a batch from ~2/20 named to ~10/20 named, auto-dedupe, and channel-sort — producing paste-ready drafts.

## 2. What it is

A **CLI batch tool** that takes a list of companies and, per company: finds the owner's first name (open web only), grabs one personalization hook, detects channel (email vs Messenger-only) and catches duplicate inboxes, scores name confidence, drafts a paste-ready message in the owner's locked voice, and writes one Obsidian note per company plus a dashboard note. The human reviews the vault and marks a note `status: approved`; an optional **`send` stage** (§11, features 003/004) then delivers only approved notes through the configured email provider — the Gmail API or authenticated SMTP (e.g. a Zoho custom-domain mailbox) — under a ramped daily cap, dry-run by default, with an immutable send ledger.

An optional **`source` stage** (§10) builds that input list in the first place: it discovers companies via Google Places across US metros and filters to those showing Meta-ad infrastructure on their own site.

## 3. Non-goals (do not build)

- **No unguarded / bulk sender.** Sending is limited to the guarded, approval-gated path defined in Principle I and §11 (features 003/004): only `status: approved` notes, only from the configured dedicated outreach mailbox (Gmail API or authenticated SMTP), under a ramped daily cap, dry-run by default. Never the operator's personal account; never an unapproved, off-channel, or over-cap send. A general-purpose or transactional-ESP sender is still out of scope.
- **No Facebook API / MCP / scraping.** (See §5.)
- **No web UI / dashboard app.** Obsidian is the interface.
- **No agent framework** (no LangChain). Direct single-shot LLM calls.
- **No CRM features** beyond what the Obsidian notes provide for free.

## 4. Flow (conceptual — spec-kit turns this into tasks)

`source (optional, §10) → ingest → dedupe/bucket → resolve → scrape/extract → enrich → score → draft → write vault → (human review)`

- **Ingest + dedupe** — load list (CSV / markdown table), normalize, detect duplicate emails/domains (two businesses sharing one inbox → one send), split `emailable` vs `messenger-only`.
- **Resolve** — find each company's website + Google Business listing when a URL isn't given.
- **Scrape + extract** — fetch homepage + `/about`, `/team`, `/contact`; extract owner-name candidates, city/service area, one hook, and a **channel-fit signal** (`fb_signal`, §7.5). Open web only.
- **Enrich (optional)** — infer name from email pattern (`scottb@` → Scott); optionally Hunter.io.
- **Score** — name confidence `high` / `medium` / `none` (§7) gates whether a real name is used; `fb_signal` (§7.5) selects which template variant to draft.
- **Draft (single-shot LLM)** — fill the locked template from `{company, name_or_team, channel, hook, angle, fb_signal}`.
- **Write vault** — one note per company + refresh dashboard.

## 5. Data access (the Facebook question — decided)

**Never access Facebook directly.** The Graph API only returns pages you manage; MCP can't grant access the API refuses; scraping FB is login-walled, brittle, ToS-violating, and reputationally bad for a build-in-public founder.

Owner name + hook come from the **open web**, in priority order: company website (footer, `/about`, `/team`, contact) → Google Business Profile via Places API (business + city/service area) → email-pattern inference → Hunter.io (optional) → state business registry (optional, later). A Facebook link is a valid *input* (confirms the business, vanity URL may hint a name) but is never scraped.

Realistic name hit rate: ~40–60%. That's fine — the job is lift, not perfection.

**On the Facebook-channel assumption:** having an email proves the business exists — nothing more. It does **not** prove they run Facebook ads, use their page for leads, or even keep it active. We do **not** claim to verify ad-running (that isn't observable from outside FB, and we don't touch FB). Instead we read cheap **open-web usage signals** (§7.5) and let them decide whether the pitch mentions Facebook at all. When the signal is weak, the draft leads with lead-response value on a channel-agnostic footing rather than betting the message on Facebook.

## 6. Input & output

**Input:** CSV or markdown table. Minimum: `company`, `email` (may be blank / "messenger"). Optional: `website`, `facebook_url`, `city`, `owner_name`, `notes`. Blank / `messenger` / a facebook URL in the email field → messenger bucket.

**Output:** Obsidian vault folder (default `Vault/Outreach/`), one note per company + one `_Dashboard.md`.

### Note schema (frontmatter + body)

```markdown
---
company: Boston Air Duct Cleaning
email: info@bostonairduct.com
channel: email            # email | messenger
status: to-send           # to-send | approved | sent | replied | pilot | dead  (approved → sent is the only machine-made change; see §11)
name_used: team           # first name, or "team"
name_confidence: none     # high | medium | none
name_candidate:           # populated when medium, for human review
hook: Boston service area
website: bostonairduct.com
angle: offer-led
fb_signal: none           # strong | weak | none  → selects template variant (§7.5)
needs_review: false
tags: [outreach, duct-cleaning, prospector]
---

## Draft
**Subject:** free setup for Boston Air Duct, you keep the bookings

Hi Boston Air Duct team,
...full body...

## Research
- Owner name: not found (no /about page)
- Sources: homepage footer, Google listing
- Hook: Boston metro service area

## Log
-
```

### Dashboard note (`_Dashboard.md`)

Holds **Dataview** queries (community plugin — note in README; plain notes still work without it): to-send queue (`status: to-send`), needs review (`needs_review: true` OR `name_confidence: medium`), messenger bucket (`channel: messenger`), pipeline grouped by `status`.

**Idempotency:** notes keyed by company slug. Re-running updates frontmatter (e.g. fills a newly found name) **without clobbering** the human's `## Log` edits or `status` changes. Merge, don't overwrite.

## 7. Confidence & honesty rules

- **high** → name from `/about`/`/team`, explicit "owner: X" text, or unambiguous email pattern (`johnsmith@`, `scottb@`). Use the first name.
- **medium** → partial/ambiguous (e.g. `derickson@`, likely a surname). Do **not** use in greeting. Keep "team", set `name_candidate`, `needs_review: true`.
- **none** → nothing found. "[Company] team".
- **Never fabricate.** Empty + flagged beats a wrong name.

## 7.5 Channel-fit signal (`fb_signal`)

We can't verify ads, but we can cheaply gauge whether Facebook is even a channel they use — all from the open web, never from inside FB:

- **strong** → two or more of: website prominently links to / embeds their Facebook page; site has a Messenger/FB chat widget; Google/search results show an active FB page (recent posts or reviews); `facebook_url` given as input and the page resolves as active in search.
- **weak** / **none** → one soft signal or nothing findable.

The signal is researched and recorded in frontmatter for review (and remains available to future copy variants). *(Copy revision 2026-07-17: the current email template is **channel-neutral** — it describes what the product does for leads without naming Facebook or asserting anything about the prospect's channels, so both signal levels share one body. This satisfies the honesty gate trivially: a claims-free draft is always "defaulted down".)*

Honesty rule mirrors §7: when unsure, **default down** (`weak`/`none`), never up. *(Amended 2026-07-14, constitution v2.0.0: the offered product is a Facebook-Messenger agent; the signal gates claims about the prospect's usage, not product-fact mentions. Ad-running is still never claimed at any level. Rebranded 2026-07-17: the product is Omniveer's **Duct Lead Qualifier**, formerly "Nestaro"; the rule is unchanged.)*

## 8. Message generation

*(revised 2026-07-20, feature 006 — supersedes "locked message templates")*

The model **writes the email body**, steered by four versioned markdown files in
`prospector/agent/` (`IDENTITY.md`, `OFFER.md`, `CONSTRAINTS.md`,
`skills/write-cold-email.md`). These are content, not code: editing them changes
the copy with no code change. Voice: short, human, practitioner. No hashtags. No
AI-sounding language. No em-dash pile-ups.

**Honesty is enforced by citation, not by locked prose.** The model returns a
subject and 3-6 blocks, each declaring which recorded evidence supports it. A
deterministic validator (never another model) resolves every citation against
records actually captured for that company. Offer, product, and sender facts
cite the reserved id `offer` - and a block citing only `offer` may not mention
the company name, city, owner name, or hook, which is what stops a prospect
claim being laundered through the offer.

The **greeting and signature are assembled in code**, never written by the
model, so a fabricated name has no channel to enter through.

**The locked template below is retained as the automatic fallback.** Any model
failure, malformed response, or validation rejection falls back to it, the note
records `draft_source: template`, and the run summary reports why. The template
path is unchanged and independently tested; it is the honesty floor.

The offer *(rebranded 2026-07-17)*: **Duct Lead Qualifier** by **Omniveer** (`lead_qualifier_feature.md`, https://www.omniveer.com/duct-lead-qualifier) — free 10-day run for 5 duct-cleaning companies, set up entirely by Anas, Founder at Omniveer.

**Link strategy (2026-07-17):** each email body carries **exactly one promotional link** — the product page (it hosts the explanation and demo, so no separate video link and no attachment). The homepage (https://www.omniveer.com) is reserved for messages about Omniveer broadly, never combined with the product link, and does not appear in these product-outreach templates. The LinkedIn company page (https://www.linkedin.com/company/omniveer/) never appears in the pitch; it may appear only in a compact signature when appropriate — the locked templates omit it rather than force it into every email. No booking link unless one is explicitly configured later. Sign-off: "Anas / Founder at Omniveer" — personal and founder-led; Omniveer is mentioned naturally, the prospect stays the focus; no invented problems, compliments, metrics, integrations, or urgency; no guaranteed bookings/revenue/response claims; each email ends with one simple, low-pressure question.

**Variant selection *(copy revision 2026-07-17)*:** email channel → the single **channel-neutral email template** below (both `fb_signal` levels; the copy makes no claims about the prospect's channels, so the §7.5 gate is trivially satisfied — the signal is still researched and recorded). Messenger bucket → Messenger DM.

### Fallback email template — channel-neutral (all `fb_signal` levels)
```
Subject: Free 10-day pilot for [Company Name]

Hi [First Name or "[Company] team"],

I'm giving 5 duct-cleaning companies a free 10-day pilot of the Omniveer Duct Lead Qualifier.

It responds to new leads, qualifies them, books appointments when they're ready, sends the full details to your email, and keeps every lead organized in a dashboard.

You can see the short demo here:
https://www.omniveer.com/duct-lead-qualifier

Reply to this email if you'd like one of the five pilot spots, or book a demo through the page.

Anas
Founder, Omniveer
```

The greeting still follows §7's name-confidence rules ("[Company] team" below high
confidence). The "book a demo through the page" close refers to the product page
already linked — it adds no second URL (link strategy above holds: one link).

### Messenger DM (messenger bucket) - fully deterministic, no model call
```
Hey! I'm giving 5 duct cleaning companies a free 10-day run of Duct Lead Qualifier, an AI assistant that answers your page messages in seconds, day or night. It checks customers are real[, around [city]], quotes your real prices, and books them into open slots on your calendar. You just get the finished lead. I set it all up for you. Want one of the 5 spots? (See it working: https://www.omniveer.com/duct-lead-qualifier)
```

## 9. Success criteria

- Feeds a raw company list, returns an Obsidian vault of paste-ready, personalized drafts.
- Names used only when confidence is high; nothing fabricated.
- Duplicates caught; messenger-only companies sorted and given DM drafts.
- Claims about the prospect's own channels appear only when open-web signals support them — the current email copy makes none (channel-neutral at every signal level). Ad-running is never claimed or assumed.
- Re-running is safe (idempotent, non-destructive).
- Build stayed in scope: no sender, no FB scraping, no web UI.
- Sourcing (§10): from a keyword + metro list, produces a deduped candidate CSV filtered to pixel-positive companies, in the §6 input format, without ever contacting a Facebook host — and `ad_signal` never appears as a claim in any draft.

## 10. Company sourcing (`prospector source`)

**Why:** the outreach in §8 offers free setup of **Duct Lead Qualifier** (Omniveer) — an assistant that answers incoming leads instantly, qualifies them, books the good ones into a dashboard, and notifies the owner. Its best first users are duct-cleaning companies already paying for Meta ads (they have lead flow worth qualifying). §§1–9 assume a list already exists; this stage builds that list.

**What it does:**

- **Discover** — Google Places Text Search (New) for a service keyword (default: `duct cleaning`) across a configurable set of US metro areas. Ships with a bundled default list of ~30 major US metros for nationwide coverage; the metro list is config, not code.
- **Dedupe** — by Places `place_id` and by website domain across metros (franchises/multi-listing businesses collapse to one row).
- **Ad signal (`ad_signal: pixel | none`)** — for each candidate with a website, fetch the homepage politely (same fetch stack and rules as §4; the Facebook-host block is fully in force) and detect the **Meta Pixel** in the page source: `connect.facebook.net/*/fbevents.js`, `fbq('init'…)` calls, or the `facebook.com/tr` noscript image *URL appearing as text in their HTML* (string inspection only — never fetched). When the page instead references a **Google Tag Manager container**, fetch that container's public JS once (`googletagmanager.com` — not a Facebook host) and inspect *it* the same way — live validation (2026-07-14) showed most modern pixel installs are GTM-mediated and invisible in page HTML. Pixel present = the business has Meta-ads tracking infrastructure installed on its own site.
- **Contact email extraction** — capture a publicly listed email (mailto: links or plain-text on the fetched pages) when present. Absent → email stays blank → messenger bucket downstream, as usual (§6).
- **Output** — a CSV in the §6 input format (`company, email, website, city` + `ad_signal` extra column, which `run` ignores with its normal unknown-column warning). Default output keeps only `ad_signal: pixel` rows; `--all` keeps everything.

**Honesty rule (extends §7.5):** `ad_signal` is a **targeting filter only** — it decides who gets *on the list*. A pixel can be dormant, inherited from an old agency, or misconfigured, so pixel-presence is NEVER used to claim or imply ad-running in a draft. §7.5's `fb_signal` rules and template selection are unchanged.

**Requirements & limits:** `GOOGLE_PLACES_API_KEY` is required for `source` (pre-flight error if absent — there is no search-engine fallback for bulk discovery). Each run reports its Places query count; runs are bounded so a nationwide sweep stays inside the Places free tier.

**Non-goals:** no paid lead databases, no directory scraping (Yelp/Angi/etc.), no Facebook Ad Library access (login-walled, and Principle II forbids it).

## 11. Approved send (`prospector send`)

**Why:** at real outreach volume (up to ~100/day) sending each drafted note by hand is impractical, and hand-tracking what was sent invites double-sends. This stage delivers **only** notes a human has explicitly approved, under hard guardrails (Constitution v4.0.0, Principle I). The human is still the sole approver; the tool is only the hands.

**Status lifecycle:** the human reviews a draft in Obsidian and sets its frontmatter `status:` to `approved`. `prospector send` then performs the single machine-owned transition `approved → sent` (with a dated `## Log` line). Every other status stays human-owned.

```
draft / to-send ──(human sets)──▶ approved ──(prospector send --send)──▶ sent
                                     └─(send fails)──▶ stays approved (error logged)
```

**What it does:**

- **Select** — scan the vault for `status: approved`, email-channel notes with a valid recipient and a `## Draft` subject + body. Anything else is skipped and reported (never guessed).
- **Guard the account** — send only through the configured provider (`PROSPECTOR_SEND_PROVIDER`: the **Gmail API** or **authenticated SMTP**, e.g. a Zoho custom-domain mailbox) from the dedicated outreach mailbox (`PROSPECTOR_SEND_FROM` — required; for Omniveer outreach: `anas@omniveer.com`). Before any send the tool resolves the authenticated identity (Gmail: the OAuth account; SMTP: the login username) and **refuses to send** if it does not match `PROSPECTOR_SEND_FROM` — never the operator's personal account, never a spoofed From address.
- **Cap (ramped)** — a configurable weekly ramp (`PROSPECTOR_SEND_CAPS`, default `15,30,60,100`; last value = week 4+), anchored on the first send recorded in the ledger. Today's allowance = cap − sends already logged today; the excess stay `approved` for a later day.
- **Pace** — real sends are spaced by a randomized delay (`PROSPECTOR_SEND_DELAY`, default `30–90s`) to mimic human sending and protect deliverability. Dry-run adds no delay.
- **Dry-run by default** — with no `--send`, nothing is sent, no status changes, no ledger write; the tool previews what it *would* send. Real sends require the explicit `--send` flag.
- **Ledger** — an append-only `send_ledger.jsonl` (gitignored) records recipient, note slug, timestamp, provider message id (Gmail id or SMTP Message-ID), and result. It is the authoritative daily count and the double-send guard (a recipient/slug already sent is never sent again). Resumable after interruption.
- **Failure isolation** — a failed send leaves the note `approved`, logs the error, and the run continues; a failure never marks a note `sent`.

**Providers (feature 004):** sending goes through a provider-neutral transport selected by `PROSPECTOR_SEND_PROVIDER`:

- **`gmail`** — the original Gmail API path (feature 003, kept for backward compatibility): one-time Google OAuth consent (Desktop client in `secrets/`, gitignored) with least-privilege scopes (`gmail.send` + email address for the identity check). A free Gmail account cannot publish SPF/DKIM/DMARC, so warm it up and expect the realistic daily cap to plateau below 100 regardless of the schedule.
- **`smtp`** — authenticated SMTP to a custom-domain mailbox (e.g. Zoho Mail for `anas@omniveer.com`): implicit SSL (465) or STARTTLS (587), password from the environment only (never logged, never committed). A custom domain can publish SPF/DKIM/DMARC, which is the deliverability upgrade motivating this provider. The From identity must equal the authenticated SMTP username — arbitrary From spoofing is refused.

Dry-run performs **no** authentication and opens **no** connection under either provider.

**Non-goals:** no personal-account sending, no non-email channel (no Messenger send), no bulk/unapproved/over-cap send, no transactional-ESP or general-purpose sender, no open/click tracking, no From-alias allowlist (a future feature may add one; until then From == authenticated identity, always).
