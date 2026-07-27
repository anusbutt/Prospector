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


def _resolve_profile(settings, requested: str | None):
    """Select and validate the offer profile before any work happens (008).

    An explicit name wins; otherwise the operator is asked. A non-interactive
    run (CI, a pipe, cron) must FAIL rather than block on a prompt nobody can
    answer, so the available names are printed and the run stops."""
    import sys

    from prospector.profiles import discover

    name = requested or settings.profile
    if not name:
        available = discover()
        if not available:
            raise ConfigError(
                "no profiles found. Create profiles/<name>/ with OFFER.md, "
                "IDENTITY.md, CONSTRAINTS.md, skills/write-cold-email.md, "
                "fallback.md and profile.toml."
            )
        if not sys.stdin.isatty():
            raise ConfigError(
                f"no profile selected. Pass --profile <name> "
                f"(available: {', '.join(available)})."
            )
        typer.echo("Available profiles:")
        for i, candidate in enumerate(available, start=1):
            typer.echo(f"  {i}) {candidate}")
        choice = typer.prompt("Which profile?", default="1")
        name = available[int(choice) - 1] if choice.isdigit() else choice
    return settings.require_profile(name)


@app.command()
def run(
    input: Path = typer.Argument(..., help="CSV or markdown-table file of companies"),
    profile: str = typer.Option(None, "--profile", help="Offer profile to use (prompts when omitted)"),
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
        # FR-018: the profile is validated first — a broken one costs nothing.
        selected = _resolve_profile(settings, profile)
        if not no_llm:
            settings.require_llm()
            instructions = selected.instructions
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
            profile=selected,
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
    profile: str = typer.Option(None, "--profile", help="Offer profile to use (prompts when omitted)"),
    keyword: str = typer.Option(None, "--keyword", help="Service keyword (default: the profile's first keyword)"),
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
        selected = _resolve_profile(settings, profile)
        if not keyword:
            keyword = selected.keywords[0]
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


# A skipped note used to report as a bare count, which is the least actionable
# thing the command could say: "skipped: 47" reads like a malfunction when it
# usually means a guarantee is working. Each skip already carries a reason, so
# group and show them. The hints translate the internal reason into what it
# means for the operator's list.
SKIP_HINTS = {
    "already in ledger": "already emailed — the ledger prevents a repeat",
    "duplicate inbox in this run": "shares an inbox with another note in this batch",
    "not an email-channel note": "note has no email channel (pre-existing note, or address never recovered)",
    "missing or invalid email address": "no usable recipient on the note",
    "draft has no subject": "add a **Subject:** line, or re-draft the note",
    "draft has no body": "the ## Draft section is empty — re-draft the note",
}
MAX_LISTED_SLUGS = 6


def _print_skips(results) -> None:
    """Explain every skipped note, grouped by reason (most common first)."""
    skips = [r for r in results if r.outcome.value.startswith("skipped")]
    if not skips:
        return
    grouped: dict[str, list[str]] = {}
    for result in skips:
        grouped.setdefault(result.detail or "unspecified", []).append(result.slug)
    typer.echo("\n  skipped:")
    for reason, slugs in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        hint = SKIP_HINTS.get(reason)
        typer.echo(f"    {len(slugs):>3}  {reason}" + (f"  ({hint})" if hint else ""))
        shown = slugs[:MAX_LISTED_SLUGS]
        more = len(slugs) - len(shown)
        typer.echo(f"         {', '.join(shown)}" + (f", and {more} more" if more else ""))


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
    _print_skips(report.results)
    # A run that selects nothing is the case most likely to be read as a bug.
    if report.sent == 0 and report.skipped and not report.failed:
        typer.echo(
            "\n  Nothing to send: every approved note was skipped for a reason above."
        )


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
        f"  duplicates: {summary.duplicates}   needs review: {summary.needs_review}"
    )
    # 008 FR-010: no company is silently bucketed — each is either processed or
    # named here as unreachable.
    typer.echo(
        f"  email recovered: {summary.email_recovered}   no email found: {summary.no_email_skipped}"
    )
    if summary.skipped_companies:
        typer.echo("\n  no email found:")
        width = max(len(name) for name, _ in summary.skipped_companies)
        for name, reason in summary.skipped_companies:
            typer.echo(f"    {name.ljust(width)}  {reason}")
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
