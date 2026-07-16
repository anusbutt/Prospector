"""Approved-send pipeline (contracts/send-command.md, data-model.md).

Selects `status: approved` notes, enforces the ramped daily cap against the
ledger, paces real sends, sends via Gmail, flips delivered notes to `sent`, and
records every send. Dry-run is the caller's default; identity verification lives
in the CLI wrapper (only verified creds reach `run_send`).
"""

import random
import time
from datetime import date, datetime
from pathlib import Path

from prospector import gmail, ledger, vault
from prospector.config import Settings
from prospector.models import (
    LedgerRecord,
    RunReport,
    SendCandidate,
    SendOutcome,
    SendResult,
)


class IdentityError(Exception):
    """Raised when the authorized account is not the configured Nestaro sender."""

    def __init__(self, actual: str, expected: str):
        self.actual = actual
        self.expected = expected
        super().__init__(
            f"refusing to send: authorized account {actual!r} is not the configured "
            f"send_from {expected!r} (never send from the personal account)"
        )


def authorize_and_verify(settings: Settings, *, load=None, whoami=None):
    """Load/authorize Gmail creds and verify the account is `settings.send_from`.

    Raises IdentityError on mismatch (FR-004). `load`/`whoami` are injectable for
    tests so no real consent/network is needed."""
    load = load or gmail.load_or_authorize
    whoami = whoami or gmail.account_email
    creds = load(settings.gmail_client_secret_path, settings.gmail_token_path)
    account = whoami(creds)
    if (account or "").strip().lower() != settings.send_from.strip().lower():
        raise IdentityError(account, settings.send_from)
    return creds


class CapSchedule:
    """Ramped daily cap. `cap_for` picks the weekly step from the ramp anchor
    (first ledger send); the last value applies to all later weeks."""

    def __init__(self, weekly_caps: list[int]):
        self.weekly_caps = list(weekly_caps) or [0]

    def cap_for(self, today: date, first_send: date | None) -> int:
        week = 0 if first_send is None else max(0, (today - first_send).days // 7)
        return self.weekly_caps[min(week, len(self.weekly_caps) - 1)]

    def remaining(self, today: date, first_send: date | None, sent_today: int) -> int:
        return max(0, self.cap_for(today, first_send) - sent_today)


def collect_candidates(vault_dir: str | Path) -> tuple[list[SendCandidate], list[SendResult]]:
    """Return (approved & sendable candidates, skip-results for approved-but-unsendable).

    Non-approved notes are ignored silently (not skip events). Approved notes that
    are messenger-channel, lack a valid email, or lack a subject/body become
    SKIPPED_NOT_SENDABLE results (FR-005, FR-013)."""
    vault_dir = Path(vault_dir)
    candidates: list[SendCandidate] = []
    skipped: list[SendResult] = []
    if not vault_dir.is_dir():
        return candidates, skipped
    for path in sorted(vault_dir.glob("*.md")):
        if path.name == "_Dashboard.md":
            continue
        text = path.read_text(encoding="utf-8")
        fm, _ = vault.parse_note(text)
        if fm.get("status") != "approved":
            continue  # FR-001: only approved notes are considered
        draft = vault.parse_draft(text)
        subject, body = draft if draft else (None, None)
        cand = SendCandidate(
            slug=path.stem,
            company=fm.get("company") or path.stem,
            recipient=(fm.get("email") or None),
            channel=fm.get("channel") or "email",
            subject=subject,
            body=body,
            note_path=path,
            approved_at=path.stat().st_mtime,
        )
        error = cand.sendable_error()
        if error:
            skipped.append(
                SendResult(cand.slug, cand.recipient, SendOutcome.SKIPPED_NOT_SENDABLE, error)
            )
        else:
            candidates.append(cand)
    return candidates, skipped


def _ts_for(day: date) -> str:
    """Ledger timestamp: the accounting day (`day`) plus the current wall-clock time.
    Tying the date to `day` keeps the ledger's daily count consistent with the cap
    accounting and avoids a midnight boundary splitting a single run."""
    return datetime.combine(day, datetime.now().time()).isoformat(timespec="seconds")


def run_send(
    settings: Settings,
    *,
    vault_dir: str | Path | None = None,
    dry_run: bool = True,
    limit: int | None = None,
    creds=None,
    sleep=time.sleep,
    rng: random.Random | None = None,
    today: date | None = None,
) -> RunReport:
    """Core send pipeline. `creds` may be None in dry-run. Callers must have already
    verified the sending identity before passing real creds (see CLI wrapper)."""
    rng = rng or random.Random()
    today = today or date.today()
    vault_dir = Path(vault_dir or settings.vault_dir)
    ledger_path = settings.ledger_path

    report = RunReport(dry_run=dry_run)

    candidates, skipped = collect_candidates(vault_dir)
    report.results.extend(skipped)

    # Drop already-sent (recipient OR slug) and collapse duplicate inboxes in-run.
    sent_recipients, sent_slugs = ledger.already_sent(ledger_path)
    seen_in_run: set[str] = set()
    eligible: list[SendCandidate] = []
    for cand in candidates:
        rec = cand.recipient.strip().lower()
        if rec in sent_recipients or cand.slug in sent_slugs:
            report.results.append(
                SendResult(cand.slug, cand.recipient, SendOutcome.SKIPPED_ALREADY_SENT, "already in ledger")
            )
            continue
        if rec in seen_in_run:
            report.results.append(
                SendResult(cand.slug, cand.recipient, SendOutcome.SKIPPED_ALREADY_SENT, "duplicate inbox in this run")
            )
            continue
        seen_in_run.add(rec)
        eligible.append(cand)

    # Ramped daily cap enforced against the ledger.
    first_send = ledger.first_send_date(ledger_path)
    sent_today = ledger.daily_count(ledger_path, today)
    schedule = CapSchedule(settings.send_caps)
    report.cap_today = schedule.cap_for(today, first_send)
    report.already_today = sent_today
    allowance = schedule.remaining(today, first_send, sent_today)
    if limit is not None:
        allowance = min(allowance, max(0, limit))

    eligible.sort(key=lambda c: c.approved_at)  # oldest-approved-first
    to_send = eligible[:allowance]
    for cand in eligible[allowance:]:
        report.results.append(
            SendResult(cand.slug, cand.recipient, SendOutcome.DEFERRED_CAP, "daily cap reached")
        )

    if dry_run:
        for cand in to_send:
            report.results.append(
                SendResult(cand.slug, cand.recipient, SendOutcome.SENT, "would send (dry-run)")
            )
        return report

    from_addr = settings.send_from
    for i, cand in enumerate(to_send):
        rec_norm = cand.recipient.strip().lower()
        try:
            message_id = gmail.send_message(creds, from_addr, cand.recipient, cand.subject, cand.body)
        except Exception as exc:  # failure isolation (FR-011): log, keep approved, continue
            ledger.append(
                ledger_path,
                LedgerRecord(
                    ts=_ts_for(today), slug=cand.slug, recipient=rec_norm, company=cand.company,
                    message_id=None, result="failed", error=str(exc), from_account=from_addr,
                ),
            )
            report.results.append(SendResult(cand.slug, cand.recipient, SendOutcome.FAILED, str(exc)))
            continue
        # Success: ledger first (source of truth), THEN flip status (FR-008).
        ledger.append(
            ledger_path,
            LedgerRecord(
                ts=_ts_for(today), slug=cand.slug, recipient=rec_norm, company=cand.company,
                message_id=message_id, result="sent", error=None, from_account=from_addr,
            ),
        )
        vault.set_status(
            cand.note_path, "sent", f"{today.isoformat()} sent via prospector (gmail {message_id})"
        )
        report.results.append(SendResult(cand.slug, cand.recipient, SendOutcome.SENT, message_id))
        if i < len(to_send) - 1:  # pace between sends, not after the last
            sleep(rng.randint(settings.send_delay[0], settings.send_delay[1]))

    return report
