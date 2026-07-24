"""Ledger invariants (contracts/ledger.schema.md) — the safety-critical source of
truth for the daily count and double-send prevention. Written tests-first (T006)."""

from datetime import date

import pytest

from prospector import ledger
from prospector.models import LedgerRecord


def _rec(slug, recipient, result="sent", ts="2026-07-15T10:00:00", message_id="m1"):
    return LedgerRecord(
        ts=ts,
        slug=slug,
        recipient=recipient,
        company=slug.title(),
        message_id=message_id if result == "sent" else None,
        result=result,
        error=None if result == "sent" else "boom",
        from_account="outreach@omniveer.com",
    )


def test_append_is_append_only(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, _rec("acme", "a@acme.com"))
    first = path.read_bytes()
    ledger.append(path, _rec("beta", "b@beta.com"))
    after = path.read_bytes()
    # Prior bytes are preserved verbatim as a prefix; nothing rewritten.
    assert after.startswith(first)
    assert len(ledger.read_all(path)) == 2


def test_missing_file_reads_empty(tmp_path):
    assert ledger.read_all(tmp_path / "none.jsonl") == []
    assert ledger.daily_count(tmp_path / "none.jsonl", date.today()) == 0
    assert ledger.first_send_date(tmp_path / "none.jsonl") is None


def test_partial_last_line_is_skipped(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, _rec("acme", "a@acme.com"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"ts": "2026-07-15T11:00:00", "slug": "trunc"')  # no newline, invalid
    records = ledger.read_all(path)
    assert len(records) == 1
    assert records[0].slug == "acme"


def test_daily_count_only_counts_today_sent(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, _rec("a", "a@x.com", ts="2026-07-15T09:00:00"))
    ledger.append(path, _rec("b", "b@x.com", ts="2026-07-15T10:00:00"))
    ledger.append(path, _rec("c", "c@x.com", result="failed", ts="2026-07-15T11:00:00"))
    ledger.append(path, _rec("d", "d@x.com", ts="2026-07-14T10:00:00"))
    assert ledger.daily_count(path, date(2026, 7, 15)) == 2  # failed + other day excluded


def test_already_sent_matches_recipient_or_slug(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, _rec("acme-duct", "info@acme.com"))
    ledger.append(path, _rec("beta-air", "hello@beta.com", result="failed"))
    recipients, slugs = ledger.already_sent(path)
    assert "info@acme.com" in recipients
    assert "acme-duct" in slugs
    # failed rows do NOT count as already-sent
    assert "hello@beta.com" not in recipients
    assert "beta-air" not in slugs


def test_already_sent_recipient_is_lowercased(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, _rec("acme", "Info@Acme.com"))
    recipients, _ = ledger.already_sent(path)
    assert "info@acme.com" in recipients


def test_first_send_date_is_min_sent_date(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, _rec("a", "a@x.com", ts="2026-07-15T09:00:00"))
    ledger.append(path, _rec("b", "b@x.com", ts="2026-07-10T09:00:00"))
    ledger.append(path, _rec("c", "c@x.com", result="failed", ts="2026-07-01T09:00:00"))
    assert ledger.first_send_date(path) == date(2026, 7, 10)  # failed row ignored
