"""Sourced CSV feeds feature 001's ingest unmodified (T015, contracts/csv-format.md)."""

from prospector.ingest import load_companies
from prospector.source import Candidate, write_candidates_csv


def test_sourced_csv_loads_into_001_ingest(tmp_path):
    out = tmp_path / "candidates.csv"
    write_candidates_csv(
        [
            Candidate(place_id="p1", company="Acme Duct", email="info@acme.com",
                      domain="acme.com", city="Boston, MA", ad_signal="pixel"),
            Candidate(place_id="p2", company="No Mail Cleaners",
                      domain="nomail.com", city="Denver, CO", ad_signal="pixel"),
        ],
        out,
    )
    companies, warnings = load_companies(out)

    # ad_signal is unknown to 001 and produces exactly the standard warning.
    assert any("unknown column 'ad_signal'" in w for w in warnings)
    assert len([w for w in warnings if "ad_signal" in w]) == 1

    assert [c.company for c in companies] == ["Acme Duct", "No Mail Cleaners"]
    emailed, silent = companies
    assert emailed.channel == "email"
    assert emailed.email == "info@acme.com"
    assert emailed.website is not None and "acme.com" in emailed.website
    assert emailed.city == "Boston, MA"
    # Blank email routes to the messenger bucket, unchanged 001 behavior.
    assert silent.channel == "messenger"
