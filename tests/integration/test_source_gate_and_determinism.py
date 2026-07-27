"""Sourcing finds only NEW companies, and finds them in a stable order.

Two properties, both about repeat runs:

- **The gate.** A company already in the vault has been researched, drafted and
  possibly emailed. Re-finding it spends Places quota and a homepage fetch to
  produce a row that gets thrown away, so it is dropped before the fetch loop.
- **Determinism.** Places can return the same businesses in a different order on
  different days. The output file must depend on *what* was found, not on the
  order it arrived in — otherwise a diff of two candidate CSVs is noise.

The determinism test shuffles the API response rather than simply running twice:
a run-twice test passes today and proves nothing.
"""

from pathlib import Path

import httpx
import pytest
import respx

from prospector.config import Settings
from prospector.fetch import Fetcher
from prospector.source import PLACES_URL, run_sourcing

PIXEL_HTML = (
    "<html><head><script>fbq('init','1');</script></head>"
    "<body>Co <a href='mailto:hi@{host}'>mail</a></body></html>"
)


def settings(tmp_path):
    return Settings(
        openrouter_key=None, openrouter_model="test/model", places_key="places-x",
        hunter_key=None, vault_dir=tmp_path / "Vault" / "Outreach",
    )


def quick_fetcher():
    return Fetcher(client=httpx.Client(follow_redirects=True), host_interval=0.0, sleep=lambda s: None)


def place(pid, name, host):
    return {
        "id": pid,
        "displayName": {"text": name},
        "websiteUri": f"https://{host}",
        "formattedAddress": "1 Main St, Denver, CO 80202, USA",
    }


PLACES = [
    place("p1", "Acme Duct Cleaning", "acme.com"),
    place("p2", "Beta Vents", "beta.com"),
    place("p3", "Gamma Air Care", "gamma.com"),
]


def stub(places):
    respx.post(PLACES_URL).mock(return_value=httpx.Response(200, json={"places": places}))
    for p in places:
        host = p["websiteUri"].removeprefix("https://")
        respx.get(f"https://{host}/").mock(
            return_value=httpx.Response(200, text=PIXEL_HTML.format(host=host))
        )


def note(vault_dir: Path, slug: str, company: str, website: str = "") -> None:
    """A vault note as `run` would have written it."""
    vault_dir.mkdir(parents=True, exist_ok=True)
    (vault_dir / f"{slug}.md").write_text(
        f"---\ncompany: {company}\nemail: x@y.com\nchannel: email\nstatus: to-send\n"
        f"website: {website}\ntags: [outreach]\n---\n\n## Draft\n**Subject:** S\n\nB\n\n## Log\n-\n",
        encoding="utf-8",
    )


def source(tmp_path, out_name="c.csv", **kwargs):
    out = tmp_path / out_name
    summary = run_sourcing(
        settings(tmp_path), keyword="duct cleaning", metros=["Denver, CO"], out=out,
        keep_all=True, fetcher=quick_fetcher(), **kwargs
    )
    return summary, out.read_text(encoding="utf-8")


class TestGateDropsAlreadyKnownCompanies:
    @respx.mock
    def test_company_in_the_vault_is_dropped(self, tmp_path):
        stub(PLACES)
        vault = tmp_path / "Vault" / "Outreach"
        note(vault, "acme-duct-cleaning", "Acme Duct Cleaning", "acme.com")

        summary, csv_text = source(tmp_path, vault_dir=vault)

        assert summary.already_known == 1
        assert "Acme Duct Cleaning" not in csv_text
        assert "Beta Vents" in csv_text and "Gamma Air Care" in csv_text

    @respx.mock
    def test_known_company_is_never_fetched(self, tmp_path):
        """The whole point of gating before the fetch loop."""
        stub(PLACES)
        acme = respx.get("https://acme.com/")
        vault = tmp_path / "Vault" / "Outreach"
        note(vault, "acme-duct-cleaning", "Acme Duct Cleaning", "acme.com")

        source(tmp_path, vault_dir=vault)

        assert acme.call_count == 0

    @respx.mock
    def test_renamed_company_still_caught_by_domain(self, tmp_path):
        """Slug misses a renamed business; the website domain catches it."""
        stub(PLACES)
        vault = tmp_path / "Vault" / "Outreach"
        note(vault, "acme-duct-cleaning-llc", "Acme Duct Cleaning LLC", "acme.com")

        summary, csv_text = source(tmp_path, vault_dir=vault)

        assert summary.already_known == 1
        assert "Acme Duct Cleaning" not in csv_text

    @respx.mock
    def test_second_sweep_returns_nothing_new(self, tmp_path):
        """Every company known -> empty result, and it is reported, not silent."""
        stub(PLACES)
        vault = tmp_path / "Vault" / "Outreach"
        for pid, name, host in [("p1", "Acme Duct Cleaning", "acme.com"),
                                ("p2", "Beta Vents", "beta.com"),
                                ("p3", "Gamma Air Care", "gamma.com")]:
            note(vault, name.lower().replace(" ", "-"), name, host)

        summary, csv_text = source(tmp_path, vault_dir=vault)

        assert summary.already_known == 3
        assert summary.kept_with_all == 0
        assert summary.written == 0
        assert csv_text.strip() == "company,email,website,city,ad_signal"

    @respx.mock
    def test_include_known_bypasses_the_gate(self, tmp_path):
        stub(PLACES)
        vault = tmp_path / "Vault" / "Outreach"
        note(vault, "acme-duct-cleaning", "Acme Duct Cleaning", "acme.com")

        summary, csv_text = source(tmp_path, vault_dir=vault, include_known=True)

        assert summary.already_known == 0
        assert "Acme Duct Cleaning" in csv_text

    @respx.mock
    def test_missing_vault_suppresses_nothing(self, tmp_path):
        """A first run has no vault yet; that is not an error."""
        stub(PLACES)
        summary, csv_text = source(tmp_path, vault_dir=tmp_path / "nope")

        assert summary.already_known == 0
        assert summary.kept_with_all == 3

    @respx.mock
    def test_dashboard_note_is_not_treated_as_a_company(self, tmp_path):
        stub(PLACES)
        vault = tmp_path / "Vault" / "Outreach"
        note(vault, "acme-duct-cleaning", "Acme Duct Cleaning", "acme.com")
        (vault / "_Dashboard.md").write_text("# Outreach Dashboard\n", encoding="utf-8")

        summary, _ = source(tmp_path, vault_dir=vault)

        assert summary.already_known == 1  # the dashboard is not a 4th company


class TestOutputIsDeterministic:
    @respx.mock
    def test_shuffled_places_order_yields_an_identical_file(self, tmp_path):
        """The file depends on WHAT was found, not the order it arrived in."""
        stub(PLACES)
        _, first = source(tmp_path, "a.csv", vault_dir=None)
        respx.reset()
        stub(list(reversed(PLACES)))
        _, second = source(tmp_path, "b.csv", vault_dir=None)

        assert first == second

    @respx.mock
    def test_rows_are_sorted_by_company(self, tmp_path):
        stub(list(reversed(PLACES)))
        _, csv_text = source(tmp_path, vault_dir=None)

        companies = [line.split(",")[0] for line in csv_text.strip().splitlines()[1:]]
        assert companies == sorted(companies, key=str.casefold)

    @respx.mock
    def test_duplicate_domain_collapses_to_the_same_winner_either_way(self, tmp_path):
        """Two listings sharing a domain must not swap winners on reordering."""
        dupes = [
            place("p9", "Zed Ducts", "shared.com"),
            place("p1", "Acme Ducts", "shared.com"),
        ]
        stub(dupes)
        _, first = source(tmp_path, "a.csv", vault_dir=None)
        respx.reset()
        stub(list(reversed(dupes)))
        _, second = source(tmp_path, "b.csv", vault_dir=None)

        assert first == second
