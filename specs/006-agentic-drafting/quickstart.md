# Quickstart: Agentic Drafting

**Feature**: 006-agentic-drafting | **Date**: 2026-07-20

How the operator uses this once it ships. Nothing here requires new
configuration — the feature reuses `OPENROUTER_API_KEY` and
`OPENROUTER_MODEL`.

---

## 1. Tune the voice

The copy strategy lives in four markdown files inside the package. Edit them
like prose; no code, no tests, no reinstall.

```
prospector/agent/
├── IDENTITY.md              who you are, your company, your voice
├── OFFER.md                 the pilot, the product, the one permitted link
├── CONSTRAINTS.md           hard rules, in the model's own language
└── skills/
    └── write-cold-email.md  structure, openings, length, what good looks like
```

Change the offer wording:

```bash
$EDITOR prospector/agent/OFFER.md
prospector run candidates.csv --only acme-duct-cleaning --verbose
```

Read the result in Obsidian. That loop is the point of the feature — SC-307
targets under five minutes.

**What these files cannot do**: grant the model tools, network access, or a
second call. They are content. The guarantees live in code.

---

## 2. Run the batch

Unchanged command:

```bash
prospector run candidates.csv
```

New summary lines:

```
Prospector run: 30 companies
  processed: 30   failed: 0
  named high: 11   medium: 6   none: 13
  messenger: 8   duplicates: 2   needs review: 9
  drafted by agent: 19   by template: 3   frozen: 0

  fallbacks:
    dustless-duct         agent response malformed: expected 3-6 blocks, got 8
    monster-vac           block 2 cites unknown id 'about_page_9'
    sonic-air-duct        no evidence to cite
```

The fallback list is the health signal. A run where most companies fall back
means the drafting path is broken — investigate before approving anything.

---

## 3. Review a draft

The note now records which path wrote the copy:

```yaml
draft_source: agent
outcome:
```

Read the `## Draft` section as before. To check a personalized claim, look at
`## Research` in the same note — every citable fact is listed with its source
URL and the excerpt it came from.

**What to check that the validator cannot**: the validator proves a cited record
*exists* for this company. It cannot prove the record actually *supports* the
sentence. If a draft says "serving Dallas since 2003" and the cited excerpt only
mentions Dallas, that is yours to catch. This is why approval is still manual.

Approve as always:

```yaml
status: approved
```

---

## 4. Re-running is now safe

| Note status | On re-run |
|---|---|
| new / `to-send` | re-drafted |
| `approved` | **frozen** — draft untouched, no model call |
| `sent` | **frozen** — draft untouched, no model call |
| anything else | **frozen** |

So a full re-run refreshes everything still awaiting review, and cannot touch
copy you approved or copy that already went out. Research sections refresh on
every note, including frozen ones.

Staged rollout, if you'd rather not re-draft 130 notes at once:

```bash
prospector run candidates.csv --limit 10          # first ten only
prospector run candidates.csv --only acme-duct    # one company
```

---

## 5. Record what came back

When a prospect replies, open the note and fill in:

```yaml
outcome: replied      # or: interested | bounced | no
```

The tool never writes this field again — it is yours, preserved across every
re-run, exactly like `status`.

Then `_Dashboard.md` answers the question the whole measurement exists for:

```dataview
TABLE rows.company AS Companies
FROM #prospector
WHERE outcome
GROUP BY draft_source + " / " + outcome
```

Agent-written copy versus template copy, by reply rate. That comparison is
impossible to reconstruct later, which is why the field ships with the feature
rather than after it.

---

## 6. Turning the agent off

```bash
prospector run candidates.csv --no-llm     # no drafting at all
```

Or delete/rename an instruction file to force a pre-flight stop — the run
refuses to start and names the missing file rather than drafting without its
constraints.

If the model is unreachable, nothing special is needed: every company falls back
to the locked template and you get today's output, marked
`draft_source: template`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `error: instruction file not found: OFFER.md` | File missing or renamed | Restore it; the run stops before writing anything |
| `error: instruction context is 24,113 chars (max 20,000)` | Instruction files grew too large | Trim them; truncation is deliberately not silent |
| Every company falls back | Model unreachable, or key missing | Check `OPENROUTER_API_KEY`; output is still valid, just unpersonalized |
| One company falls back with `no evidence to cite` | Research found nothing — no website resolved | Expected. Nothing to personalize from; the template is correct here |
| A draft you approved changed | Should be impossible | File a bug — FR-326 forbids it and `test_vault_freeze.py` covers it |
