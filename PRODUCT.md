# PRODUCT.md — Prospector

**What this file is for:** the product spec — the *what* and *why*. This is the source of truth spec-kit reads to generate the spec / plan / tasks. It does **not** contain a task list or build phases; those are generated and tracked by spec-kit (`tasks.md`). If reality forces a change to intent, update this file first, then let the plan regenerate.

## 1. Problem

Cold outreach to home service companies (duct cleaning first) converts far better when each message carries the owner's first name and one specific hook. Producing that by hand across a list is slow, repetitive research: find the site, dig for a name, note the city/service, catch duplicate inboxes, sort out who has no email. Sending is trivial and already solved. **The research and personalization is the expensive part — that is what this tool automates.**

Target lift: move a batch from ~2/20 named to ~10/20 named, auto-dedupe, and channel-sort — producing paste-ready drafts.

## 2. What it is

A **CLI batch tool** that takes a list of companies and, per company: finds the owner's first name (open web only), grabs one personalization hook, detects channel (email vs Messenger-only) and catches duplicate inboxes, scores name confidence, drafts a paste-ready message in the owner's locked voice, and writes one Obsidian note per company plus a dashboard note. The human reviews the vault, fixes low-confidence rows, and sends manually.

## 3. Non-goals (do not build)

- **No email sender.** Sending is manual, by the human, from their real inbox. A DIY sender saves nothing and risks domain reputation.
- **No Facebook API / MCP / scraping.** (See §5.)
- **No web UI / dashboard app.** Obsidian is the interface.
- **No agent framework** (no LangChain). Direct single-shot LLM calls.
- **No CRM features** beyond what the Obsidian notes provide for free.

## 4. Flow (conceptual — spec-kit turns this into tasks)

`ingest → dedupe/bucket → resolve → scrape/extract → enrich → score → draft → write vault → (human review)`

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
status: to-send           # to-send | sent | replied | pilot | dead
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

- **strong** → two or more of: website prominently links to / embeds their Facebook page; site has a Messenger/FB chat widget; Google/search results show an active FB page (recent posts or reviews); `facebook_url` given as input and the page resolves as active in search. → Draft the **Facebook variant** (mentions the page directly).
- **weak** → one soft signal, or a stale/low-activity FB presence. → Draft the **channel-agnostic variant**; mention Facebook only as one example ("on Facebook or wherever your leads come in").
- **none** → no findable FB usage signal. → Draft the **channel-agnostic variant**; don't mention Facebook at all. Lead with lead-response value.

Honesty rule mirrors §7: when unsure, **default down** (`weak`/`none`), never up. Better to under-claim the channel than pitch a Facebook assistant to someone who doesn't use Facebook.

## 8. Locked message templates

Model fills bracketed slots only. Voice: short, human, practitioner. No hashtags. No AI-sounding language. No em-dash pile-ups.

**Variant selection:** `fb_signal: strong` → Facebook variant. `weak` / `none` → channel-agnostic variant. Messenger bucket → Messenger DM.

### Email — Facebook variant (`fb_signal: strong`)
```
Subject: free setup for [Company], you keep the bookings

Hi [Name or "[Company] team"],

[If info@ inbox: "Straight to it, and if this isn't your department, please forward it to whoever handles your bookings."  Else: "Straight to it."]

I'll set up an AI assistant on your Facebook page for free, and you keep every job it books. No contract, no cost.

Here's what it does. The moment a lead messages or fills out a form, it replies day or night, figures out whether they're a real customer [hook: "in your service area" / "around [city]"], and hands the good ones straight to you. The junk never touches your phone.

I'm doing this with a small group of duct cleaning companies to build real case studies. That's the whole catch: it works for you, and if it does, I get to point to the results. If it doesn't, you've lost nothing.

Open to it? Reply here and I'll have you running this week.

Anas
x.com/iamanusbutt
linkedin.com/in/anus-yousuf
```

### Email — channel-agnostic variant (`fb_signal: weak` / `none`)
Same offer, but the pitch rests on lead response, not on Facebook.
```
Subject: free setup for [Company], you keep the bookings

Hi [Name or "[Company] team"],

[If info@ inbox: "Straight to it, and if this isn't your department, please forward it to whoever handles your bookings."  Else: "Straight to it."]

I'll set up an AI assistant that answers your new leads for free, and you keep every job it books. No contract, no cost.

Here's what it does. However a lead reaches you — a form, a message[, or Facebook if you use it] — it replies in seconds, day or night, figures out whether they're a real customer [hook: "in your service area" / "around [city]"], and hands the good ones straight to you. The junk never touches your phone.

I'm doing this with a small group of duct cleaning companies to build real case studies. That's the whole catch: it works for you, and if it does, I get to point to the results. If it doesn't, you've lost nothing.

Open to it? Reply here and I'll have you running this week.

Anas
x.com/iamanusbutt
linkedin.com/in/anus-yousuf
```
(`fb_signal: none` → drop the "or Facebook if you use it" clause entirely.)

### Messenger DM (messenger bucket)
```
Hey! I build AI assistants for duct cleaning companies. This one answers every new lead on your page in seconds, filters out the time-wasters, and flags the ready-to-book ones for you[, around [city]]. I'm setting it up free for a few companies right now to build case studies. Want me to run yours? (My work: x.com/iamanusbutt)
```

## 9. Success criteria

- Feeds a raw company list, returns an Obsidian vault of paste-ready, personalized drafts.
- Names used only when confidence is high; nothing fabricated.
- Duplicates caught; messenger-only companies sorted and given DM drafts.
- The Facebook pitch is only used when open-web signals support it; otherwise the draft is channel-agnostic. Ad-running is never claimed or assumed.
- Re-running is safe (idempotent, non-destructive).
- Build stayed in scope: no sender, no FB scraping, no web UI.
