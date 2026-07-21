# Feature Specification: Omniveer Branding & Strategic Links in Outreach

**Feature Branch**: `005-omniveer-branding`
**Created**: 2026-07-17
**Status**: Draft
**Input**: User description: "Update Prospector's existing outreach email
generation so it uses the new Omniveer brand and links strategically. Do not
redesign the email-generation architecture unless necessary."

## Overview

The outreach templates still pitch the offered product under its old name
("Nestaro") and sign off with the founder's personal X/LinkedIn links. The
product is now **Duct Lead Qualifier** by **Omniveer**, with a product page
that hosts the explanation and demo. This feature rebrands the **locked
template prose only** and encodes a deliberate link strategy — the
email-generation architecture (slot-filling LLM, deterministic assembly,
honesty validator, human approval, guarded send) is explicitly unchanged.

Because templates are locked product intent (PRODUCT.md §8) and the
constitution's Principle V names the product, PRODUCT.md was updated first and
the constitution PATCH-bumped to v4.0.1 (name reference only; no rule change).

## Confirmed brand facts (from the operator)

| Item | Value |
|------|-------|
| Company | Omniveer |
| Founder | Anas |
| Sender | anas@omniveer.com (feature 004 config; unchanged here) |
| Product | Duct Lead Qualifier |
| Product URL | https://www.omniveer.com/duct-lead-qualifier |
| Company website | https://www.omniveer.com |
| LinkedIn company page | https://www.linkedin.com/company/omniveer/ |

## Invariants (unchanged, non-negotiable)

- Research grounding: hooks/names/signals come only from recorded evidence;
  the validator still rejects unsourced names, ad-running vocabulary, and
  altered template prose.
- Human approval: drafts land as `status: to-send`; only a human sets
  `approved`; the guarded send stage (003/004) is untouched.
- No invented problems, compliments, metrics, integrations, or urgency; no
  guaranteed bookings, revenue, or response-improvement claims.

## Revision 2 (2026-07-17, operator-supplied final copy)

The operator supplied the final email copy verbatim (subject + greeting + body
+ signature). Deltas against Revision 1:

- **Single channel-neutral email template** replaces the FB/agnostic variant
  pair: the copy no longer names Facebook or the prospect's channels, so both
  `fb_signal` levels share one body (the §7.5 honesty gate is trivially
  satisfied; the signal is still researched and recorded). The location-hook
  sentence and the generic-inbox opener are removed with it; the LLM slot
  contract shrinks to `greeting_name` + `subject_company`.
- **Subject**: `Free 10-day pilot for [Company Name]`.
- **Product name in copy**: "the Omniveer Duct Lead Qualifier".
- **Close**: "Reply to this email if you'd like one of the five pilot spots,
  or book a demo through the page." — the "page" is the product page already
  linked; no second URL (FR-202/203 unchanged). This supersedes FR-207's
  single-question phrasing; the low-pressure intent stands.
- **Signature**: `Anas` / `Founder, Omniveer` (comma form, supersedes FR-206).
- Messenger DM unchanged from Revision 1.
- Typographic apostrophes in the supplied copy normalized to straight ASCII
  (codebase/email convention).

## Requirements

### Functional Requirements

- **FR-201**: All "Nestaro" branding MUST be removed from templates, code
  constants, prompts, docs, and test fixtures; the offered product is named
  **Duct Lead Qualifier**, mentioned with Omniveer naturally (founder-led),
  without turning the email into a company introduction.
- **FR-202**: Each email body MUST carry **exactly one** promotional link —
  the product page (`https://www.omniveer.com/duct-lead-qualifier`), preferred
  because it hosts the explanation and demo. Enforced by the validator.
- **FR-203**: The homepage (`https://www.omniveer.com`) MUST NOT appear in
  product-outreach bodies and MUST NOT be combined with the product link.
  (It is reserved for messages about Omniveer broadly — none of the current
  templates.)
- **FR-204**: The LinkedIn company link MUST NOT appear in the pitch body.
  It may appear only in a compact signature when appropriate; since template
  selection is mechanical and the link must not be forced into every email,
  the locked templates omit it. The validator rejects any LinkedIn URL in a
  draft body.
- **FR-205**: No demo-video attachment, no separate video link (the demo
  lives on the product page), no booking link unless one is explicitly
  configured later.
- **FR-206**: Sign-off is `Anas` / `Founder at Omniveer` (compact, personal).
- **FR-207**: Each email ends with one simple, low-pressure question
  ("Would you like one of the five spots?"); the previous urgency-toned
  closer ("first come… this week") is removed.
- **FR-208**: The old personal links (`x.com/iamanusbutt`,
  `linkedin.com/in/anus-yousuf`) and the old Gmail sending address MUST NOT
  remain anywhere in templates, code, or fixtures (sending address already
  replaced by feature 004; verified again here).
- **FR-209**: The email-generation architecture is unchanged: same slot
  schema, same LLM contract, same variant selection on `fb_signal`, same
  validator structure (with new link rules added), same vault/approval flow.

## Success Criteria

- **SC-201**: `grep -ri nestaro` over templates, prospector/, and tests
  returns nothing.
- **SC-202**: Golden drafts for both email variants and the Messenger DM
  contain the product URL exactly once and no other URL.
- **SC-203**: A draft containing a LinkedIn URL or a second promotional link
  fails validation.
- **SC-204**: Every email golden draft ends with the low-pressure question +
  the new signature.
- **SC-205**: The full test suite passes; approval/send safeguards show no
  behavioral diff.

## Out of Scope

- Any change to drafting architecture, scoring, sourcing, or sending.
- A booking link (explicitly deferred until configured).
- Rebranding the Prospector tool itself (only the offered product changes).
- Broad "about Omniveer" email variants (would use the homepage; not built).
