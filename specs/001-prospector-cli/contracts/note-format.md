# Vault Note Contract

The vault is the tool's entire output surface (Constitution III). One note per company
+ `_Dashboard.md`, in `--vault` dir (default `Vault/Outreach/`).

## Note file: `<slug>.md`

Canonical rendering (identical data MUST produce identical bytes — SC-006):

```markdown
---
company: Boston Air Duct Cleaning
email: info@bostonairduct.com
channel: email
status: to-send
name_used: team
name_confidence: none
name_candidate:
hook: Boston service area
website: bostonairduct.com
angle: offer-led
fb_signal: none
duplicate_of:
needs_review: false
tags: [outreach, duct-cleaning, prospector]
---

## Draft
**Subject:** free setup for Boston Air Duct, you keep the bookings

Hi Boston Air Duct team,
...full assembled body...

## Research
- Owner name: not found (no /about page)
- Sources: https://bostonairduct.com, https://bostonairduct.com/contact, DDG search
- Hook: Boston metro service area (homepage: "serving the Boston metro area")
- fb_signal: none — no FB link/widget/search presence found
- Failures: (none)

## Log
-
```

### Frontmatter rules

- Key order fixed as shown (§6 schema + `duplicate_of` — empty when not a duplicate).
- `channel`: `email` | `messenger`. `status`: `to-send` | `sent` | `replied` | `pilot`
  | `dead`. `name_confidence`: `high` | `medium` | `none`. `fb_signal`: `strong` |
  `weak` | `none`.
- `name_used`: first name only at high confidence, else `team`.
- `name_candidate`: populated iff `name_confidence: medium`.
- Empty values render as bare `key:` (no `null`, no quotes) for Obsidian friendliness.
- `tags` always `[outreach, duct-cleaning, prospector]` inline-list form.

### Section ownership (merge contract)

| Region | Owner | Re-run behavior |
|--------|-------|-----------------|
| frontmatter except `status` | machine | recomputed & merged |
| `status` | human | machine writes `to-send` once; never modifies after |
| `## Draft` | machine | regenerated (only if inputs/research changed) |
| `## Research` | machine | regenerated |
| `## Log` | human | preserved verbatim, always |
| unrecognized `## ` sections | human | preserved verbatim, in position after known sections |

- Messenger notes: `## Draft` has no `**Subject:**` line (DM body only).
- `--no-llm` runs: `## Draft` contains `*(not drafted — run without LLM)*`.
- Draft-validation failure: best-effort draft is NOT written; `## Draft` contains
  `*(draft failed validation: <reasons>)*` and `needs_review: true`.

## Dashboard file: `_Dashboard.md`

Entirely machine-owned; regenerated every run; content depends only on static template
(byte-idempotent). Contains, in order:

1. Plain-markdown header noting Dataview requirement + link counts fallback text.
2. **To-send queue**: dataview `TABLE company, hook, fb_signal FROM "Outreach" WHERE
   status = "to-send" AND channel = "email" AND !duplicate_of`.
3. **Needs review**: `WHERE needs_review = true OR name_confidence = "medium"` showing
   `name_candidate`.
4. **Messenger bucket**: `WHERE channel = "messenger"`.
5. **Pipeline**: `TABLE ... GROUP BY status`.

(Exact Dataview syntax finalized in implementation; queries MUST filter on the
frontmatter fields named above so human `status` edits re-bucket notes live.)
