"""Typer CLI — the tool's entire input surface (contracts/cli.md).

Exit codes: 0 = batch completed (per-company failures allowed);
1 = pre-flight failure (nothing written); 2 = unexpected mid-run crash.
There is no send command and never will be (Constitution I).
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
    try:
        if not no_llm:
            settings.require_llm()
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
        )
    except (ConfigError, IngestError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"unexpected error: {exc}", err=True)
        raise typer.Exit(2)
    _print_summary(summary)


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


def _print_summary(summary: RunSummary) -> None:
    typer.echo(f"\nProspector run: {summary.total} companies")
    typer.echo(f"  processed: {summary.processed}   failed: {summary.failed}")
    typer.echo(
        f"  named high: {summary.named_high}   medium: {summary.named_medium}   none: {summary.named_none}"
    )
    typer.echo(
        f"  messenger: {summary.messenger}   duplicates: {summary.duplicates}   needs review: {summary.needs_review}"
    )
    if summary.per_company:
        typer.echo("")
        width = max(len(slug) for slug, _, _ in summary.per_company)
        for slug, outcome, detail in summary.per_company:
            typer.echo(f"  {slug.ljust(width)}  {outcome:6}  {detail}")


if __name__ == "__main__":
    app()
