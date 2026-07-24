"""Candidate CSV contract (T008, contracts/csv-format.md)."""

from prospector.source import Candidate, write_candidates_csv


def cand(company, email=None, domain=None, city="", ad_signal="none"):
    return Candidate(place_id="p-" + company, company=company, email=email,
                     domain=domain, city=city, ad_signal=ad_signal)


def test_header_exact_and_rows_in_order(tmp_path):
    out = tmp_path / "c.csv"
    n = write_candidates_csv(
        [
            cand("Acme Duct", email="info@acme.com", domain="acme.com", city="Boston, MA", ad_signal="pixel"),
            cand("Beta Vents", city="Denver, CO"),
        ],
        out,
    )
    lines = out.read_text(encoding="utf-8").splitlines()
    assert n == 2
    assert lines[0] == "company,email,website,city,ad_signal"
    assert lines[1] == 'Acme Duct,info@acme.com,acme.com,"Boston, MA",pixel'
    assert lines[2] == 'Beta Vents,,,"Denver, CO",none'


def test_zero_rows_writes_header_only(tmp_path):
    out = tmp_path / "c.csv"
    assert write_candidates_csv([], out) == 0
    assert out.read_text(encoding="utf-8").splitlines() == ["company,email,website,city,ad_signal"]


def test_deterministic_bytes(tmp_path):
    rows = [cand("Acme", domain="acme.com", city="Boston, MA")]
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    write_candidates_csv(rows, a)
    write_candidates_csv(rows, b)
    assert a.read_bytes() == b.read_bytes()
