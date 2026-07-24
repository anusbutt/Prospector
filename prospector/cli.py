"""Typer CLI — the tool's entire input surface (contracts/cli.md).

Exit codes (run/source): 0 = batch completed (per-company failures allowed);
1 = pre-flight failure (nothing written); 2 = unexpected mid-run crash.

The `send` command (features 003/004, Constitution v4.0.0 Principle I) delivers
only human-approved notes through the configured provider (Gmail API or
authenticated SMTP), dry-run by default. Its exit codes: 0 = completed;
1 = pre-flight failure (incl. missing/invalid provider or SMTP config);
2 = identity mismatch (wrong account, nothing sent); 3 = authentication failure
(OAuth or SMTP login). Per-message send failures are non-fatal (exit 0).
"""

from pathlib import Path

import typer

from prospector.config import ConfigError, load_settings
from prospector.ingest import IngestError
from prospector.models import RunSummary

app = typer.Typer(
    help="Prospector: research companies on the open web, draft outreach into an Obsidian vault.",
    add_completion=False,
)


@app.callback()
def main():
    """Prospector: research companies on the open web, draft outreach into an Obsidian vault."""


@app.command()
def run(
    input: Path = typer.Argument(..., help="CSV or markdown-table file of companies"),
    vault: Path = typer.Option(None, "--vault", help="Vault output folder (default: Vault/Outreach)"),
    limit: int = typer.Option(None, "--limit", help="Process only the first N companies"),
    only: str = typer.Option(None, "--only", help="Re-run a single company by slug"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip drafting; research and score only"),
    verbose: bool = typer.Option(False, "--verbose", help="Per-step logging to stderr"),
):
    """Process a company list end-to-end and write the vault."""
    from prospector.pipeline import run_batch  # deferred: keeps --help fast

    settings = load_settings()
    instructions = None
    try:
        if not no_llm:
            settings.require_llm()
            # FR-323: a missing or oversized instruction file stops the run
            # before any company is processed and before anything is written.
            instructions = settings.require_instructions()
        if not input.is_file():
            raise IngestError(f"input file not found: {input}")
        summary = run_batch(
            input,
            settings,
            vault_dir=vault,
            limit=limit,
            only=only,
            no_llm=no_llm,
            verbose=verbose,
            instructions=instructions,
        )
    except (ConfigError, IngestError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"unexpected error: {exc}", err=True)
        raise typer.Exit(2)
    _print_summary(summary)


@app.command()
def source(
    keyword: str = typer.Option("duct cleaning", "--keyword", help="Service keyword for the Places text query"),
    metros: Path = typer.Option(None, "--metros", help="Metro list file (City, ST per line; default: bundled 30-metro list)"),
    out: Path = typer.Option(Path("candidates.csv"), "--out", help="Output CSV path"),
    keep_all: bool = typer.Option(False, "--all", help="Keep every discovered candidate (default: only ad_signal: pixel)"),
    max_queries: int = typer.Option(60, "--max-queries", help="Places request budget for this run"),
    limit: int = typer.Option(None, "--limit", help="Stop after N metros (testing)"),
    verbose: bool = typer.Option(False, "--verbose", help="Per-step logging to stderr"),
):
    """Discover companies for a keyword across US metros and write a candidate CSV."""
    from prospector.source import load_metros, run_sourcing  # deferred: keeps --help fast

    settings = load_settings()
    try:
        settings.require_places()
        metro_list = load_metros(metros)
        out_parent = out.resolve().parent
        if not out_parent.is_dir():
            raise ConfigError(f"output directory not found: {out_parent}")
        summary = run_sourcing(
            settings,
            keyword=keyword,
            metros=metro_list,
            out=out,
            keep_all=keep_all,
            max_queries=max_queries,
            limit=limit,
            verbose=verbose,
        )
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"unexpected error: {exc}", err=True)
        raise typer.Exit(2)
    _print_sourcing_summary(summary)


@app.command()
def dashboard(
    vault_dir: Path = typer.Option(None, "--vault", help="Vault folder to refresh (default: Vault/Outreach)"),
):
    """Regenerate _Dashboard.md only (no research, no LLM)."""
    from prospector.vault import write_dashboard

    settings = load_settings()
    target = vault_dir or settings.vault_dir
    if not target.is_dir():
        typer.echo(f"error: vault folder not found: {target}", err=True)
        raise typer.Exit(1)
    result = write_dashboard(target)
    typer.echo(f"_Dashboard.md {result} in {target}")


@app.command()
def send(
    real: bool = typer.Option(False, "--send", help="Actually send. Default is a dry-run preview."),
    limit: int = typer.Option(None, "--limit", help="Send at most N notes this run (still capped)"),
    vault: Path = typer.Option(None, "--vault", help="Vault folder (default: Vault/Outreach)"),
    yes: bool = typer.Option(False, "--yes", help="Skip the pre-send confirmation prompt"),
):
    """Send human-approved notes via the configured provider (Gmail API or
    authenticated SMTP). Dry-run by default — no auth, no connection."""
    from prospector.send import IdentityError, run_send, verified_sender
    from prospector.transport import AuthError

    settings = load_settings()
    target = vault or settings.vault_dir
    if not target.is_dir():
        typer.echo(f"error: vault folder not found: {target}", err=True)
        raise typer.Exit(1)
    try:
        settings.require_send()  # provider/identity/SMTP pre-flight; no network
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    sender = None
    if real:
        try:
            sender = verified_sender(settings)
        except IdentityError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(2)
        except AuthError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(3)
        if not yes:
            preview = run_send(settings, vault_dir=target, dry_run=True, limit=limit)
            typer.echo(
                f"About to really send {preview.sent} email(s) from {settings.send_from} "
                f"via {settings.send_provider} "
                f"(today's cap {preview.cap_today}, already sent {preview.already_today})."
            )
            if not typer.confirm("Proceed?"):
                typer.echo("aborted; nothing sent.")
                raise typer.Exit(0)

    try:
        report = run_send(settings, vault_dir=target, dry_run=not real, limit=limit, sender=sender)
    except Exception as exc:
        typer.echo(f"unexpected error: {exc}", err=True)
        raise typer.Exit(1)
    _print_send_report(report)


def _print_send_report(report) -> None:
    from prospector.models import SendOutcome

    mode = "SENT" if not report.dry_run else "WOULD SEND (dry-run)"
    typer.echo(f"\nProspector send [{mode}]")
    typer.echo(f"  today's cap: {report.cap_today}   already sent today: {report.already_today}")
    typer.echo(
        f"  {'sent' if not report.dry_run else 'to send'}: {report.sent}   "
        f"deferred (cap): {report.deferred}   skipped: {report.skipped}   failed: {report.failed}"
    )
    interesting = {
        SendOutcome.SENT,
        SendOutcome.FAILED,
        SendOutcome.DEFERRED_CAP,
    }
    rows = [r for r in report.results if r.outcome in interesting]
    if rows:
        typer.echo("")
        width = max(len(r.slug) for r in rows)
        for r in rows:
            typer.echo(f"  {r.slug.ljust(width)}  {r.outcome.value:12}  {r.detail}")


@app.command()
def dm(
    real: bool = typer.Option(False, "--send", help="Assist a real send (clipboard + browser + confirm). Default is preview."),
    limit: int = typer.Option(None, "--limit", help="Walk at most N approved messenger notes this run"),
    vault: Path = typer.Option(None, "--vault", help="Vault folder (default: Vault/Outreach)"),
    yes: bool = typer.Option(False, "--yes", help="Skip the one upfront confirmation (per-note confirms still apply)"),
):
    """Assist manual Messenger delivery of approved messenger-channel notes
    (Constitution v6.0.0 Principle I). The tool copies the draft to your
    clipboard and opens the company's Facebook page in YOUR browser; you send it
    yourself and confirm. Preview by default — nothing is opened or recorded."""
    import webbrowser

    from prospector import clipboard
    from prospector.dm import run_dm
    from prospector.models import DmCandidate

    settings = load_settings()
    target = vault or settings.vault_dir
    if not target.is_dir():
        typer.echo(f"error: vault folder not found: {target}", err=True)
        raise typer.Exit(1)

    if real and not yes:
        preview = run_dm(settings, vault_dir=target, dry_run=True, limit=limit)
        typer.echo(
            f"About to walk {preview.would_deliver} approved messenger note(s); "
            f"you will confirm each send yourself."
        )
        if not typer.confirm("Proceed?"):
            typer.echo("aborted; nothing done.")
            raise typer.Exit(0)

    def _confirm(cand: "DmCandidate", *, copied: bool, opened: bool) -> str:
        typer.echo("")
        typer.echo(f"── {cand.company} ({cand.slug}) ──")
        if opened:
            typer.echo(f"  opened in your browser: {cand.facebook_url}")
        elif cand.facebook_url:
            typer.echo(f"  could not open a browser — open this yourself: {cand.facebook_url}")
        else:
            typer.echo("  no Facebook link on file — locate the company manually")
        if copied:
            typer.echo("  draft copied to your clipboard — paste it into Messenger")
        else:
            typer.echo("  (clipboard unavailable — copy the message below)")
            typer.echo("")
            typer.echo(cand.body or "")
        answer = typer.prompt("  Did you send this message? [y/N/q]", default="n", show_default=False)
        return answer

    report = run_dm(
        settings,
        vault_dir=target,
        dry_run=not real,
        limit=limit,
        confirm=_confirm,
        opener=webbrowser.open,
        copier=clipboard.copy_to_clipboard,
    )
    _print_dm_report(report, target)


def _print_dm_report(report, vault_dir) -> None:
    from prospector.models import DmOutcome

    mode = "ASSISTED SEND" if not report.dry_run else "WOULD WALK (preview)"
    typer.echo(f"\nProspector dm [{mode}]")
    typer.echo(f"  vault: {vault_dir}")
    head = "delivered" if not report.dry_run else "to walk"
    head_n = report.delivered if not report.dry_run else report.would_deliver
    typer.echo(
        f"  {head}: {head_n}   skipped (already): {report.skipped_already}   "
        f"skipped (not sendable): {report.skipped_not_sendable}   declined: {report.declined}"
    )
    interesting = {
        DmOutcome.DELIVERED,
        DmOutcome.WOULD_DELIVER,
        DmOutcome.SKIPPED_NOT_SENDABLE,
        DmOutcome.SKIPPED_ALREADY_SENT,
    }
    rows = [r for r in report.results if r.outcome in interesting]
    if rows:
        typer.echo("")
        width = max(len(r.slug) for r in rows)
        for r in rows:
            detail = r.facebook_url or r.detail
            typer.echo(f"  {r.slug.ljust(width)}  {r.outcome.value:20}  {detail}")


def _print_sourcing_summary(summary) -> None:
    typer.echo(f"\nProspector source: {summary.metros_covered}/{summary.metros_total} metros covered")
    typer.echo(f"  queries used: {summary.queries_used}/{summary.query_budget}")
    typer.echo(
        f"  discovered: {summary.discovered}   duplicates collapsed: {summary.duplicates_collapsed}"
    )
    typer.echo(
        f"  pixel-positive: {summary.pixel_positive}   emails found: {summary.emails_found}   rows written: {summary.written}"
    )
    if summary.written == 0 and summary.kept_with_all > 0:
        typer.echo(f"  note: 0 rows written; --all would have kept {summary.kept_with_all}")
    if summary.failures:
        typer.echo("")
        for name, reason in summary.failures:
            typer.echo(f"  failed: {name}  {reason}")


def _print_summary(summary: RunSummary) -> None:
    typer.echo(f"\nProspector run: {summary.total} companies")
    typer.echo(f"  processed: {summary.processed}   failed: {summary.failed}")
    typer.echo(
        f"  named high: {summary.named_high}   medium: {summary.named_medium}   none: {summary.named_none}"
    )
    typer.echo(
        f"  messenger: {summary.messenger}   duplicates: {summary.duplicates}   needs review: {summary.needs_review}"
    )
    typer.echo(
        f"  drafted by agent: {summary.drafted_agent}   by template: {summary.drafted_template}"
    )
    if summary.fallback_reasons:
        # FR-320: a degraded drafting path must be visible within one batch,
        # not discovered later as "the copy got boring".
        typer.echo("\n  fallbacks:")
        width = max(len(slug) for slug, _ in summary.fallback_reasons)
        for slug, reason in summary.fallback_reasons:
            typer.echo(f"    {slug.ljust(width)}  {reason}")
    if summary.per_company:
        typer.echo("")
        width = max(len(slug) for slug, _, _ in summary.per_company)
        for slug, outcome, detail in summary.per_company:
            typer.echo(f"  {slug.ljust(width)}  {outcome:6}  {detail}")


if __name__ == "__main__":
    app()
