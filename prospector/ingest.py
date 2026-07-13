"""Input parsing: CSV or markdown table -> normalized Company rows + warnings.

Bucketing (contracts/cli.md): valid email -> email channel; blank / "messenger" /
Facebook URL -> messenger; anything else -> messenger + needs_review.
"""

import csv
import io
import re
from functools import lru_cache
from pathlib import Path

from prospector.models import Channel, Company

KNOWN_COLUMNS = ("company", "email", "website", "facebook_url", "city", "owner_name", "notes")
REQUIRED_COLUMNS = ("company", "email")

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
FB_URL_RE = re.compile(r"(?:^|//|www\.)(?:facebook\.com|fb\.com|fb\.me)/", re.IGNORECASE)


class IngestError(Exception):
    """Fatal input problem (missing file, bad header) -> pre-flight exit 1."""


def load_companies(path: str | Path) -> tuple[list[Company], list[str]]:
    """Parse an input file. Returns (companies, warnings). Raises IngestError on fatal problems."""
    path = Path(path)
    if not path.is_file():
        raise IngestError(f"input file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in (".md", ".markdown"):
        header, rows = _parse_markdown_table(text)
    else:
        header, rows = _parse_csv(text)
    return _build_companies(header, rows)


def _parse_csv(text: str) -> tuple[list[str], list[list[str]]]:
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise IngestError("input file is empty")
    return rows[0], rows[1:]


def _parse_markdown_table(text: str) -> tuple[list[str], list[list[str]]]:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        raise IngestError("no markdown table found in input file")
    def split_row(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip("|").split("|")]
    header = split_row(lines[0])
    body = lines[1:]
    if body and re.fullmatch(r"[\s|:-]+", body[0]):
        body = body[1:]  # separator row
    return header, [split_row(line) for line in body]


def _build_companies(header: list[str], rows: list[list[str]]) -> tuple[list[Company], list[str]]:
    warnings: list[str] = []
    columns = [name.strip().lower() for name in header]
    for required in REQUIRED_COLUMNS:
        if required not in columns:
            raise IngestError(f"input header is missing required column '{required}' (got: {', '.join(columns)})")
    for name in columns:
        if name and name not in KNOWN_COLUMNS:
            warnings.append(f"ignoring unknown column '{name}'")

    companies: list[Company] = []
    for i, row in enumerate(rows):
        row_num = i + 2  # 1-based, after header
        values = {columns[j]: row[j].strip() for j in range(min(len(columns), len(row)))}
        company_name = values.get("company", "")
        if not company_name:
            warnings.append(f"row {row_num}: missing company name, skipped")
            continue
        raw_email = values.get("email", "")
        email, channel, reason, needs_review = _bucket_email(raw_email)
        if needs_review:
            warnings.append(f"row {row_num}: unrecognized email field {raw_email!r}, routed to messenger and flagged")
        companies.append(
            Company(
                company=company_name,
                email=email,
                raw_email_field=raw_email,
                website=_normalize_website(values.get("website", "")),
                facebook_url=values.get("facebook_url") or None,
                city=values.get("city") or None,
                owner_name=values.get("owner_name") or None,
                notes=values.get("notes") or None,
                row_num=row_num,
                channel=channel,
                bucket_reason=reason,
                needs_review=needs_review,
            )
        )
    return companies, warnings


def _bucket_email(raw: str) -> tuple[str | None, Channel, str | None, bool]:
    """Returns (email, channel, bucket_reason, needs_review)."""
    value = raw.strip()
    if not value:
        return None, Channel.MESSENGER, "blank email", False
    if value.lower() == "messenger":
        return None, Channel.MESSENGER, "marked messenger", False
    if FB_URL_RE.search(value):
        return None, Channel.MESSENGER, "facebook url in email field", False
    if EMAIL_RE.fullmatch(value):
        return value.lower(), Channel.EMAIL, None, False
    return None, Channel.MESSENGER, f"unrecognized email field: {value!r}", True


@lru_cache(maxsize=1)
def free_providers() -> frozenset[str]:
    path = Path(__file__).parent / "data" / "free_providers.txt"
    return frozenset(line.strip().lower() for line in path.read_text().splitlines() if line.strip())


def mark_duplicates(companies: list[Company]) -> None:
    """Detect shared inboxes (FR-003): identical email always groups; identical
    email domain groups only for non-free providers (two businesses on gmail.com
    are unrelated). First row in input order is primary; the rest reference it.
    Call after slugs are assigned."""
    primary_by_email: dict[str, Company] = {}
    primary_by_domain: dict[str, Company] = {}
    for company in companies:
        if not company.email:
            continue
        domain = company.email.rsplit("@", 1)[1]
        primary = primary_by_email.get(company.email)
        if primary is None and domain not in free_providers():
            primary = primary_by_domain.get(domain)
        if primary is not None:
            company.duplicate_of = primary.slug
            company.needs_review = True
        else:
            primary_by_email[company.email] = company
            primary_by_domain.setdefault(domain, company)


def _normalize_website(raw: str) -> str | None:
    value = raw.strip().rstrip("/")
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value
