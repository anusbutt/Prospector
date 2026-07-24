"""place_id + domain dedupe (T007)."""

from prospector.source import Candidate, SourcingSummary, dedupe


def cand(pid, company, domain=None):
    return Candidate(place_id=pid, company=company, domain=domain,
                     website=f"https://{domain}" if domain else None)


def test_same_place_id_across_metros_collapses():
    summary = SourcingSummary()
    out = dedupe([cand("p1", "Acme", "acme.com"), cand("p1", "Acme", "acme.com")], summary)
    assert [c.company for c in out] == ["Acme"]
    assert summary.duplicates_collapsed == 1


def test_shared_domain_collapses_different_listings():
    summary = SourcingSummary()
    out = dedupe([cand("p1", "Acme HQ", "acme.com"), cand("p2", "Acme South", "acme.com")], summary)
    assert [c.company for c in out] == ["Acme HQ"]  # first seen wins
    assert summary.duplicates_collapsed == 1


def test_no_website_rows_dedupe_by_id_only():
    summary = SourcingSummary()
    out = dedupe([cand("p1", "Alpha"), cand("p2", "Beta"), cand("p2", "Beta again")], summary)
    assert [c.company for c in out] == ["Alpha", "Beta"]
    assert summary.duplicates_collapsed == 1


def test_distinct_candidates_all_kept():
    summary = SourcingSummary()
    out = dedupe([cand("p1", "A", "a.com"), cand("p2", "B", "b.com")], summary)
    assert len(out) == 2
    assert summary.duplicates_collapsed == 0
