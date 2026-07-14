# CLI Contract: `prospector source`

Extends the existing Typer app (feature 001 contract remains in
`specs/001-prospector-cli/contracts/cli.md`; `run` and `dashboard` are unchanged).

## `prospector source`

Discover companies for a keyword across US metros and write a candidate CSV.

**Options**
| Option | Default | Meaning |
|--------|---------|---------|
| `--keyword TEXT` | `duct cleaning` | service keyword for the Places text query |
| `--metros FILE` | bundled 30-metro list | override metro list (`City, ST` per line; `#` comments allowed) |
| `--out FILE` | `candidates.csv` | output CSV path |
| `--all` | false | keep every discovered candidate (default: only `ad_signal: pixel`) |
| `--max-queries N` | 60 | Places request budget for this run |
| `--limit N` | none | stop after N metros (testing) |
| `--verbose` | false | per-step logging to stderr |

**Behavior contract**
- Exit 0: sweep completed — including partial sweeps stopped by the query budget and
  runs with per-candidate failures (all reported in the summary).
- Exit 1: pre-flight failure — missing `GOOGLE_PLACES_API_KEY`, missing/empty/malformed
  `--metros` file, unwritable `--out` path. Nothing written, no network activity.
- Exit 2: unexpected mid-run crash.
- stdout: sourcing summary (metros covered, queries used vs budget, discovered,
  duplicates collapsed, pixel-positive, emails found, rows written, failures).
- stderr: warnings and `--verbose` logging.
- Never prompts interactively. Never sends anything. **Never contacts Facebook hosts**
  (all fetches go through the feature-001 `Fetcher` choke point).
- Places is queried once per metro (no pagination); homepage fetches follow the
  feature-001 politeness rules (timeouts, ≤2 retries, per-host spacing, robots.txt).
- The output file is fully rewritten each run (plain artifact, not a merged store).

**Environment (.env or process env)**
| Var | Required | Degradation if absent |
|-----|----------|----------------------|
| `GOOGLE_PLACES_API_KEY` | **yes** | exit 1 pre-flight (no fallback discovery) |

`OPENROUTER_API_KEY` / `HUNTER_API_KEY` are not read by `source`.
