"""Per-company orchestration: ingest -> resolve -> fetch -> extract -> score ->
draft -> vault. Individual company failures never abort the batch (FR-021);
every input row yields a note (SC-002).
"""

import sys
from pathlib import Path

from prospector import agent_draft
from prospector import draft as drafting
from prospector import enrich
from prospector import extract as extracting
from prospector import ingest, resolve, score, vault
from prospector.config import Settings
from prospector.fetch import Fetcher, FetchError
from prospector.models import (
    Channel,
    Company,
    Confidence,
    Draft,
    Evidence,
    EvidenceKind,
    FbSignal,
    Prospect,
    ResearchResult,
    RunSummary,
    Variant,
)


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def run_batch(
    input_path: str | Path,
    settings: Settings,
    *,
    vault_dir: str | Path | None = None,
    limit: int | None = None,
    only: str | None = None,
    no_llm: bool = False,
    verbose: bool = False,
    fetcher: Fetcher | None = None,
    instructions=None,
) -> RunSummary:
    """Process a batch. Raises IngestError only for pre-flight problems.

    `instructions` is the pre-flighted InstructionSet for agent drafting; when
    None the drafting path falls back to the locked template (FR-315)."""
    vault_dir = Path(vault_dir) if vault_dir else settings.vault_dir
    fetcher = fetcher or Fetcher()

    companies, warnings = ingest.load_companies(input_path)
    for warning in warnings:
        _log(f"warning: {warning}")
    vault.assign_slugs(companies)
    ingest.mark_duplicates(companies)

    if only:
        companies = [c for c in companies if c.slug == only]
    if limit is not None:
        companies = companies[:limit]

    summary = RunSummary(total=len(companies))
    for company in companies:
        if verbose:
            _log(f"processing {company.slug} ...")
        # FR-326: read status BEFORE drafting. A frozen note must cost no LLM
        # request, so this cannot be deferred to write time.
        frozen = vault.is_frozen(vault.read_status(vault_dir, company.slug))
        try:
            prospect, draft = _process_company(
                company,
                settings,
                fetcher,
                no_llm=no_llm,
                verbose=verbose,
                frozen=frozen,
                instructions=instructions,
            )
            outcome, detail = _write(prospect, draft, vault_dir, no_llm=no_llm, frozen=frozen)
            _count_drafting_path(summary, company.slug, draft)
            summary.processed += 1
        except Exception as exc:  # per-company isolation (FR-021)
            _log(f"error: {company.slug}: {exc}")
            prospect = Prospect(company=company, research=ResearchResult(website=company.website))
            prospect.needs_review = True
            prospect.research.failures.append(f"processing failed: {exc}")
            _write(prospect, None, vault_dir, no_llm=no_llm, frozen=frozen)
            summary.failed += 1
            outcome, detail = "failed", str(exc)
        _count(summary, prospect)
        summary.per_company.append((company.slug, outcome, detail))
    vault.write_dashboard(vault_dir)
    return summary


def _process_company(
    company: Company,
    settings: Settings,
    fetcher: Fetcher,
    *,
    no_llm: bool,
    verbose: bool,
    frozen: bool = False,
    instructions=None,
) -> tuple[Prospect, Draft | None]:
    research = _research(company, settings, fetcher, verbose=verbose)
    prospect = _score(company, research, settings)
    draft: Draft | None = None
    if no_llm:
        return prospect, draft
    if frozen:
        # FR-326: approved/sent copy is never regenerated, so no drafting call
        # is made at all. ## Research still refreshes from the work above.
        return prospect, draft
    if company.channel is Channel.EMAIL:
        # 006: agent path with automatic template fallback. Never raises, so
        # the batch cannot be aborted by a drafting failure (FR-318).
        draft = agent_draft.draft_email(prospect, settings, instructions)
        if draft.validation_errors:
            research.failures.extend(draft.validation_errors)
    else:
        # FR-308: messenger DMs stay fully deterministic — no model call.
        draft = drafting.build_messenger_draft(prospect)
    if draft is not None and not draft.validated:
        prospect.needs_review = True
    return prospect, draft


def _research(company: Company, settings: Settings, fetcher: Fetcher, *, verbose: bool) -> ResearchResult:
    research = ResearchResult(website=company.website)
    info = resolve.resolve(company, settings, fetcher)
    research.website = info.website
    research.gbp_city = info.gbp_city
    research.sources_consulted.extend(info.sources_consulted)
    research.failures.extend(info.failures)

    pages: list[extracting.PageContent] = []
    if research.website:
        homepage_html = _fetch_page(research.website, fetcher, research, check_robots=False)
        if homepage_html is not None:
            pages.append(extracting.PageContent("homepage", research.website, homepage_html))
            for kind, url in extracting.discover_extra_pages(homepage_html, research.website):
                html = _fetch_page(url, fetcher, research, check_robots=True)
                if html is not None:
                    pages.append(extracting.PageContent(kind, url, html))

    if pages:
        outcome = extracting.extract(company, pages)
        research.name_evidence = outcome.name_evidence
        research.hook = outcome.hook
        research.hook_evidence = outcome.hook_evidence
        research.city = outcome.city
        research.fb_evidence.extend(extracting.detect_fb_evidence(pages))

    search_evidence = resolve.fb_search_evidence(company, fetcher, info)
    # fb_search_evidence appended to info; union with page-fetch entries, order-stable
    research.sources_consulted = list(dict.fromkeys(research.sources_consulted + info.sources_consulted))
    research.failures = list(dict.fromkeys(research.failures + info.failures))
    if search_evidence:
        research.fb_evidence.append(search_evidence)
    if company.facebook_url:
        research.fb_evidence.append(
            Evidence(
                kind=EvidenceKind.FB_URL_INPUT, value=company.facebook_url,
                source=f"input row {company.row_num}", excerpt="facebook_url provided as input (never fetched)",
            )
        )

    research.city = company.city or research.city or research.gbp_city
    if not research.hook and research.city:
        source = "input row" if company.city else ("google-places" if research.gbp_city else "site")
        research.hook = f"{research.city} service area"
        research.hook_evidence = Evidence(
            kind=EvidenceKind.HOOK_SOURCE, value=research.hook, source=source, excerpt=f"city: {research.city}"
        )
    return research


def _fetch_page(url: str, fetcher: Fetcher, research: ResearchResult, *, check_robots: bool) -> str | None:
    if url not in research.sources_consulted:
        research.sources_consulted.append(url)
    try:
        response = fetcher.fetch(url, check_robots=check_robots)
    except FetchError as exc:
        research.failures.append(str(exc))
        return None
    if response.status_code != 200:
        research.failures.append(f"{url} returned {response.status_code}")
        return None
    return response.text


def _score(company: Company, research: ResearchResult, settings: Settings) -> Prospect:
    """Name confidence per §7 (score.py). fb_signal §7.5 rules arrive in US3 (T018)."""
    prospect = Prospect(company=company, research=research)

    email_inference = enrich.infer_from_email(company.email)
    if email_inference.evidence:
        research.name_evidence.append(email_inference.evidence)
    hunter_inference = None
    cheap_signals_empty = (
        not research.name_evidence
        and not email_inference.first_name
        and not email_inference.candidate
        and not company.owner_name
    )
    if settings.hunter_key and company.email and cheap_signals_empty:
        hunter_inference = enrich.hunter_lookup(company.email, settings)
        if hunter_inference.evidence:
            research.name_evidence.append(hunter_inference.evidence)
    score.apply_name_scoring(prospect, email_inference, hunter_inference)

    prospect.fb_signal = score.classify_fb_signal(research.fb_evidence)
    prospect.variant = score.select_variant(company.channel, prospect.fb_signal)
    if research.failures and not research.website:
        prospect.needs_review = True
    return prospect


def _write(
    prospect: Prospect, draft: Draft | None, vault_dir: Path, *, no_llm: bool, frozen: bool = False
) -> tuple[str, str]:
    draft_md = vault.draft_markdown_for(draft, prospect, no_llm=no_llm and prospect.company.channel is Channel.EMAIL)
    research_md = vault.build_research_markdown(prospect)
    note = vault.render_note(prospect, draft_md, research_md, draft=draft)
    result = vault.upsert_note(vault_dir, prospect.company.slug, note, freeze_draft=frozen)
    if frozen:
        detail = f"draft frozen (approved/sent), research refreshed, note {result}"
    elif draft is not None and draft.validated:
        detail = f"drafted ({prospect.variant.value}), note {result}"
    elif draft is not None:
        detail = f"draft failed validation, note {result}"
    else:
        detail = f"no draft, note {result}"
    return "ok", detail


def _count_drafting_path(summary: RunSummary, slug: str, draft: Draft | None) -> None:
    """Drafting-path visibility (FR-320).

    Only email-channel drafts have a path: messenger DMs are deterministic and
    frozen/--no-llm companies are not drafted at all, so neither is counted.
    The fallback REASON is recorded, not just the count — a silent 40% fallback
    rate would otherwise look like slightly boring copy rather than a break."""
    if draft is None or draft.source not in ("agent", "template"):
        return
    if draft.model == "deterministic":  # messenger DM
        return
    if draft.source == "agent":
        summary.drafted_agent += 1
        return
    summary.drafted_template += 1
    reason = next(
        (e for e in draft.validation_errors if e.startswith("agent fallback: ")),
        None,
    )
    if reason:
        summary.fallback_reasons.append((slug, reason[len("agent fallback: "):]))


def _count(summary: RunSummary, prospect: Prospect) -> None:
    if prospect.name_confidence is Confidence.HIGH:
        summary.named_high += 1
    elif prospect.name_confidence is Confidence.MEDIUM:
        summary.named_medium += 1
    else:
        summary.named_none += 1
    if prospect.company.channel is Channel.MESSENGER:
        summary.messenger += 1
    if prospect.company.duplicate_of:
        summary.duplicates += 1
    if prospect.needs_review or prospect.company.needs_review:
        summary.needs_review += 1
