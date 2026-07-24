"""Assisted-manual Messenger delivery (007; Constitution v6.0.0, Principle I
"Assisted-manual Messenger delivery").

Walks `approved` messenger-channel notes one at a time. In real mode it copies
the deterministic draft to the operator's clipboard and opens the note's
`facebook_url` in the operator's OWN browser, then — only after a per-note human
confirmation — records a human-performed delivery in a dedicated ledger and flips
the note `approved → sent`. Preview (dry-run) is the default and mutates nothing.

The tool NEVER transmits a Messenger message, NEVER automates a browser, and
NEVER issues an HTTP request to Facebook: `webbrowser.open` merely hands the URL
to the operator's browser (Principle II clarification). No LLM call occurs; the
body delivered is the deterministic template verbatim.
"""

import webbrowser
from datetime import date, datetime
from pathlib import Path

from prospector import clipboard, ledger, vault
from prospector.config import Settings
from prospector.models import (
    Channel,
    DmCandidate,
    DmOutcome,
    DmResult,
    DmRunReport,
    LedgerRecord,
)


def _unquote(value: str) -> str:
    """Strip the surrounding double-quotes _yaml_value adds to values containing
    a colon (full URLs like https://... are quoted on write)."""
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def collect_dm_candidates(
    vault_dir: str | Path,
) -> tuple[list[DmCandidate], list[DmResult]]:
    """Return (deliverable approved messenger candidates, skip-results for
    approved-but-unsendable). Non-approved and non-messenger notes are ignored
    silently (not skip events), mirroring send.collect_candidates."""
    vault_dir = Path(vault_dir)
    candidates: list[DmCandidate] = []
    skipped: list[DmResult] = []
    if not vault_dir.is_dir():
        return candidates, skipped
    for path in sorted(vault_dir.glob("*.md")):
        if path.name == "_Dashboard.md":
            continue
        text = path.read_text(encoding="utf-8")
        fm, _ = vault.parse_note(text)
        if fm.get("status") != "approved":
            continue  # only approved notes are considered
        if (fm.get("channel") or "email") != Channel.MESSENGER.value:
            continue  # email-channel notes belong to the `send` path
        fb = _unquote(fm.get("facebook_url") or "")
        cand = DmCandidate(
            slug=path.stem,
            company=fm.get("company") or path.stem,
            facebook_url=fb or None,
            body=vault.parse_messenger_body(text),
            note_path=path,
            approved_at=path.stat().st_mtime,
        )
        error = cand.sendable_error()
        if error:
            skipped.append(
                DmResult(cand.slug, cand.facebook_url, DmOutcome.SKIPPED_NOT_SENDABLE, error)
            )
        else:
            candidates.append(cand)
    return candidates, skipped


def already_delivered_slugs(dm_ledger_path: str | Path) -> set[str]:
    """Slugs already recorded in the DM ledger. Every record in this ledger is a
    confirmed human-performed delivery, so (unlike ledger.already_sent, which
    filters result=='sent') we key on slug across all records (schema:
    result=='dm_sent_manual')."""
    return {r.slug for r in ledger.read_all(dm_ledger_path) if r.slug}


def _ts_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_confirm(cand: DmCandidate, *, copied: bool, opened: bool) -> str:
    """Overridden by the CLI (which prints + prompts) and by tests. The default
    is conservative: decline, so a mis-wired caller never records a send."""
    return "n"


def run_dm(
    settings: Settings,
    *,
    vault_dir: str | Path | None = None,
    dry_run: bool = True,
    limit: int | None = None,
    confirm=_default_confirm,
    opener=webbrowser.open,
    copier=clipboard.copy_to_clipboard,
    today: date | None = None,
) -> DmRunReport:
    """Core assisted-manual Messenger walk. In dry-run nothing is copied, opened,
    ledgered, or flipped. `confirm(cand, copied=, opened=)` returns 'y'/'n'/'q';
    `opener`/`copier` are injectable so tests never open a browser or clipboard."""
    today = today or date.today()
    vault_dir = Path(vault_dir or settings.vault_dir)
    dm_ledger_path = settings.dm_ledger_path

    report = DmRunReport(dry_run=dry_run)

    candidates, skipped = collect_dm_candidates(vault_dir)
    report.results.extend(skipped)

    # Drop already-delivered (DM ledger) and collapse duplicate targets in-run.
    delivered = already_delivered_slugs(dm_ledger_path)
    seen_targets: set[str] = set()
    eligible: list[DmCandidate] = []
    for cand in candidates:
        if cand.slug in delivered:
            report.results.append(
                DmResult(cand.slug, cand.facebook_url, DmOutcome.SKIPPED_ALREADY_SENT, "already in DM ledger")
            )
            continue
        target = (cand.facebook_url or "").strip().lower()
        if target and target in seen_targets:
            report.results.append(
                DmResult(cand.slug, cand.facebook_url, DmOutcome.SKIPPED_ALREADY_SENT, "duplicate Facebook target in this run")
            )
            continue
        if target:
            seen_targets.add(target)
        eligible.append(cand)

    eligible.sort(key=lambda c: c.approved_at)  # oldest-approved-first
    if limit is not None:
        eligible = eligible[: max(0, limit)]

    if dry_run:
        for cand in eligible:
            report.results.append(
                DmResult(cand.slug, cand.facebook_url, DmOutcome.WOULD_DELIVER, "would deliver (preview)")
            )
        return report

    for cand in eligible:
        copied = copier(cand.body or "")
        opened = bool(cand.facebook_url) and bool(opener(cand.facebook_url))
        decision = (confirm(cand, copied=copied, opened=opened) or "n").strip().lower()
        if decision == "q":
            break
        if decision != "y":
            report.results.append(
                DmResult(cand.slug, cand.facebook_url, DmOutcome.DECLINED, "operator declined")
            )
            continue
        # Confirmed: ledger first (source of truth), THEN flip status.
        ledger.append(
            dm_ledger_path,
            LedgerRecord(
                ts=_ts_now(), slug=cand.slug, recipient=cand.facebook_url or "",
                company=cand.company, message_id=None, result="dm_sent_manual",
                error=None, from_account="",
            ),
        )
        vault.set_status(
            cand.note_path,
            "sent",
            f"{today.isoformat()} messenger delivered manually (assisted)",
        )
        report.results.append(
            DmResult(cand.slug, cand.facebook_url, DmOutcome.DELIVERED, "delivered (manual)")
        )

    return report
