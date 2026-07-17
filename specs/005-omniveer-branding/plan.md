# Implementation Plan: Omniveer Branding & Strategic Links

**Branch**: `005-omniveer-branding` | **Date**: 2026-07-17 | **Spec**: [spec.md](./spec.md)

## Summary

Content-only rebrand of the locked outreach templates plus new link-safety
validator rules. No architecture change: the slot-filling LLM contract,
deterministic assembly, variant selection, honesty validator structure, vault
approval flow, and guarded send are all untouched (FR-209). No new
dependencies, no new modules, no data-model or research phase needed (all
inputs were confirmed by the operator; decisions are recorded in the spec and
PRODUCT.md §8's new "Link strategy" paragraph).

**Change surface**: `prospector/draft.py` template constants + validator;
PRODUCT.md §7.5/§8/§10 (updated first); constitution v4.0.1 (Principle V
product-name PATCH); `lead_qualifier_feature.md` product name; draft and
integration test golden strings + new link-rule tests.

## Constitution Check (v4.0.1)

- **I. Human-Approved Sending Only** — ✅ untouched; send stage not modified.
- **II. Open Web Only** — ✅ N/A; no fetching changes.
- **III. Obsidian Is the Interface** — ✅ untouched.
- **IV. Name Honesty** — ✅ validator's unsourced-name guard unchanged;
  greeting rules unchanged.
- **V. Channel Honesty** — ✅ rule unchanged (PATCH renamed the product
  reference only); variant framing sentences keep their strong/agnostic split;
  ad-claim bans unchanged.
- **VI. Smallest Viable Build** — ✅ constants + a few validator lines; no
  refactor, no new deps.
- **VII. Verified Claims Only** — ✅ golden tests re-locked on the new prose;
  full suite must pass.

**Result**: PASS.

## Template design (mirrors PRODUCT.md §8, the source of truth)

- Offer paragraph: "…free 10-day run of Duct Lead Qualifier, an AI assistant
  I built at Omniveer that answers your Facebook page messages for you…" —
  Omniveer mentioned naturally, founder-led, prospect stays the focus.
- Body tail gains the single promotional link: "There's a short demo on the
  product page if you want to see it working:
  https://www.omniveer.com/duct-lead-qualifier".
- Closing becomes one low-pressure question: "Would you like one of the five
  spots?" (urgency line removed).
- Signature: `Anas\nFounder at Omniveer`. LinkedIn company link deliberately
  omitted (mechanical templates cannot judge "when appropriate", and forcing
  it into every email is forbidden — recorded decision, FR-204).
- Messenger DM: same rebrand; personal-link parenthetical becomes
  "(See it working: https://www.omniveer.com/duct-lead-qualifier)".

## Validator additions (in the existing validate functions)

1. Exactly-one-link rule: body must contain the product URL and exactly one
   `http` occurrence (blocks homepage+product combos, second links, video
   links, booking links) — FR-202/203/205.
2. LinkedIn ban: any `linkedin.com` in a draft body fails — FR-204.
3. Existing invariant/ad-claim/signature/greeting/name-source checks continue
   unchanged, re-pointed at the new prose constants.

## Decisions needing ADR

None — content rebrand within an existing, unchanged architecture; the only
policy nuance (LinkedIn omitted from locked templates) is recorded in
PRODUCT.md §8 and FR-204.
