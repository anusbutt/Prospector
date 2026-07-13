# CLI Contract: prospector

The CLI is the tool's entire input surface (Constitution III). Typer app, installed as
`prospector` (also runnable via `python -m prospector`).

## `prospector run <input>`

Process a company list end-to-end and write the vault.

**Arguments**
| Arg | Type | Required | Meaning |
|-----|------|----------|---------|
| input | path | yes | CSV or .md file containing a markdown table |

**Options**
| Option | Default | Meaning |
|--------|---------|---------|
| `--vault DIR` | `Vault/Outreach` | output vault folder (created if missing) |
| `--limit N` | none | process only first N companies (testing) |
| `--only SLUG` | none | re-run a single company by slug |
| `--no-llm` | false | skip drafting; research/score only (notes get research + frontmatter, `needs_review: true`, no `## Draft` body) |
| `--verbose` | false | per-step logging to stderr |

**Behavior contract**
- Exit 0: batch completed (individual company failures allowed, reported in summary).
- Exit 1: pre-flight failure (missing/unreadable input, missing `OPENROUTER_API_KEY`
  unless `--no-llm`, malformed header row) — nothing written.
- Exit 2: batch aborted mid-run (unexpected crash) — already-written notes remain valid.
- stdout: run summary table (counts per data-model RunSummary + per-company outcomes).
- stderr: warnings (malformed rows w/ row numbers, fetch failures, degraded steps).
- Never prompts interactively. Never sends anything. Never contacts Facebook hosts.

**Environment (.env or process env)**
| Var | Required | Degradation if absent |
|-----|----------|----------------------|
| `OPENROUTER_API_KEY` | yes (unless `--no-llm`) | exit 1 pre-flight |
| `OPENROUTER_MODEL` | no | default `anthropic/claude-sonnet-4.5` |
| `GOOGLE_PLACES_API_KEY` | no | skip Places; DDG-only resolution |
| `HUNTER_API_KEY` | no | skip Hunter enrichment |

## `prospector dashboard`

Regenerate `_Dashboard.md` only (no research, no LLM).

| Option | Default | Meaning |
|--------|---------|---------|
| `--vault DIR` | `Vault/Outreach` | vault folder to scan |

Exit 0 on success; exit 1 if vault dir missing.

## Input file contract

- CSV: header row required; columns matched case-insensitively; minimum `company`,
  `email`; optional `website`, `facebook_url`, `city`, `owner_name`, `notes`; unknown
  columns ignored with a stderr warning.
- Markdown: first `|`-table in the file, same column rules.
- Email field routing: valid email → email bucket; blank / `messenger` (case-insensitive)
  / facebook URL → messenger bucket; anything else → messenger bucket + `needs_review`.

## Explicitly absent (constitutional)

No `send` command. No server/watch mode. No Facebook fetching. No interactive TUI.
