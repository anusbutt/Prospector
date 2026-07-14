# File Contracts: candidate CSV & metro list

## Output: candidate CSV

UTF-8, stdlib-csv quoting, exactly this header:

```csv
company,email,website,city,ad_signal
```

| Column | Required | Content |
|--------|----------|---------|
| `company` | yes | Places display name, stripped |
| `email` | no | publicly listed email (mailto > plaintext, lowercased) or blank — never inferred |
| `website` | no | bare domain (lowercase host, `www.` stripped) or blank |
| `city` | no | `City, ST` parsed from the Places address, else the queried metro |
| `ad_signal` | yes | `pixel` \| `none` |

**Compatibility guarantee**: columns 1–4 are exactly feature 001's input format, so the
file feeds `prospector run` unmodified. `ad_signal` is an unknown column to 001's
ingest and MUST produce only its standard unknown-column warning — this is covered by a
contract test. Blank `email` routes the row to 001's messenger bucket, as already
specified there.

**Filter rule**: default output contains only `ad_signal: pixel` rows. With `--all`,
every unique discovered candidate appears (including website-less ones, `ad_signal:
none`). Zero qualifying rows → header-only CSV is still written (and the summary says
how many rows `--all` would have kept).

**Row order**: bundled/override metro-list order, then Places result order within a
metro — deterministic for a given set of API responses.

## Input: metro list file (`--metros FILE`, and the bundled default)

```text
# comment lines allowed
New York, NY
Los Angeles, CA
...
```

- One `City, ST` per line; whitespace trimmed; blank lines and `#`-prefixed lines
  ignored.
- Must yield ≥1 metro after parsing, else pre-flight error (exit 1, nothing written).
- The bundled default (`prospector/data/us_metros.txt`) contains the 30 largest US
  metros (list in [research.md R5](../research.md)) and ships as package data.
