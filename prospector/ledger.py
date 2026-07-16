"""Append-only JSONL send ledger (contracts/ledger.schema.md).

The ledger is the authoritative record of every send: it drives the daily cap
count (FR-007) and prevents double-sends (FR-010). It is only ever appended to;
existing lines are never modified or deleted.
"""

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from prospector.models import LedgerRecord


def append(path: str | Path, record: LedgerRecord) -> None:
    """Append one record as a single JSON line. Never rewrites the file."""
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(record), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


def read_all(path: str | Path) -> list[LedgerRecord]:
    """Parse every complete line. A trailing partial/malformed line (e.g. from a
    crash mid-write) is silently skipped for crash-safety. Missing file → []."""
    path = Path(path)
    if not path.exists():
        return []
    records: list[LedgerRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue  # crash-safety: skip a partial/corrupt line
        records.append(
            LedgerRecord(
                ts=data.get("ts", ""),
                slug=data.get("slug", ""),
                recipient=data.get("recipient", ""),
                company=data.get("company", ""),
                message_id=data.get("message_id"),
                result=data.get("result", ""),
                error=data.get("error"),
                from_account=data.get("from_account", ""),
            )
        )
    return records


def _record_date(record: LedgerRecord) -> date | None:
    try:
        return datetime.fromisoformat(record.ts).date()
    except (ValueError, TypeError):
        return None


def daily_count(path: str | Path, day: date) -> int:
    """Number of successful sends whose timestamp falls on `day`."""
    return sum(
        1
        for r in read_all(path)
        if r.result == "sent" and _record_date(r) == day
    )


def already_sent(path: str | Path) -> tuple[set[str], set[str]]:
    """Return (recipients, slugs) for successful sends — for O(1) skip lookups.
    Recipients are normalized to lowercase (duplicate-inbox / case safety)."""
    recipients: set[str] = set()
    slugs: set[str] = set()
    for r in read_all(path):
        if r.result != "sent":
            continue
        if r.recipient:
            recipients.add(r.recipient.strip().lower())
        if r.slug:
            slugs.add(r.slug)
    return recipients, slugs


def first_send_date(path: str | Path) -> date | None:
    """Earliest successful-send date (the ramp anchor). None if no sends yet."""
    dates = [
        d
        for r in read_all(path)
        if r.result == "sent" and (d := _record_date(r)) is not None
    ]
    return min(dates) if dates else None
