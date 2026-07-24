"""End-to-end sourcing against stubbed transport (T009/T012)."""

from pathlib import Path

import httpx
import respx

from prospector.config import Settings
from prospector.fetch import Fetcher
from prospector.source import PLACES_URL, run_sourcing

PIXEL_HTML = (
    '<html><head><script src="https://connect.facebook.net/en_US/fbevents.js"></script>'
    "</head><body>hi</body></html>"
)
PLAIN_HTML = "<html><body><h1>Just a website</h1></body></html>"


def settings():
    return Settings(
        openrouter_key=None, openrouter_model="test/model",
        places_key="places-x", hunter_key=None, vault_dir=Path("Vault/Outreach"),
    )


def quick_fetcher():
    return Fetcher(client=httpx.Client(follow_redirects=True), host_interval=0.0, sleep=lambda s: None)


def place(pid, name, website=None, address="1 Main St, Denver, CO 80202, USA"):
    p = {"id": pid, "displayName": {"text": name}, "formattedAddress": address}
    if website:
        p["websiteUri"] = website
    return p


METRO_RESULTS = {
    "Denver, CO": [
        place("p1", "Acme Duct", website="https://acme.com"),  # pixel
        place("p2", "Beta Vents", website="https://www.beta.com"),  # no pixel
    ],
    "Boston, MA": [
        place("p1", "Acme Duct", website="https://acme.com"),  # same listing again
        place("p3", "Acme Duct East", website="https://acme.com"),  # shared domain
        place("p4", "No Site Cleaners"),  # no website
    ],
    # "Erie, PA" responds 403 (injected failure)
}


def places_responder(request):
    import json

    query = json.loads(request.content)["textQuery"]  # "duct cleaning in <metro>"
    metro = query.split(" in ", 1)[1]
    if metro == "Erie, PA":
        return httpx.Response(403, json={"error": {"message": "denied"}})
    return httpx.Response(200, json={"places": METRO_RESULTS.get(metro, [])})


def install_stubs():
    respx.post(PLACES_URL).mock(side_effect=places_responder)
    respx.get("https://acme.com/").mock(return_value=httpx.Response(200, text=PIXEL_HTML))
    respx.get("https://www.beta.com/").mock(return_value=httpx.Response(200, text=PLAIN_HTML))


METROS = ["Denver, CO", "Boston, MA", "Erie, PA"]


@respx.mock
def test_all_keeps_everything_and_summary_is_consistent(tmp_path):
    install_stubs()
    out = tmp_path / "candidates.csv"
    summary = run_sourcing(
        settings(), keyword="duct cleaning", metros=METROS, out=out,
        keep_all=True, max_queries=60, fetcher=quick_fetcher(),
    )
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "company,email,website,city,ad_signal"
    companies = [line.split(",")[0] for line in lines[1:]]
    # p1 dup collapsed by id, p3 collapsed by domain; no-site row kept with --all
    assert companies == ["Acme Duct", "Beta Vents", "No Site Cleaners"]

    assert summary.metros_total == 3
    assert summary.metros_covered == 3
    assert summary.queries_used == 3
    assert summary.discovered == 5
    assert summary.duplicates_collapsed == 2
    assert summary.kept_with_all == 3
    assert summary.pixel_positive == 1
    assert summary.written == 3
    assert ("Erie, PA", summary.failures[0][1]) in summary.failures
    assert "places query failed" in summary.failures[0][1]


@respx.mock
def test_default_filter_keeps_only_pixel_rows(tmp_path):
    install_stubs()
    out = tmp_path / "candidates.csv"
    summary = run_sourcing(
        settings(), keyword="duct cleaning", metros=METROS, out=out,
        keep_all=False, max_queries=60, fetcher=quick_fetcher(),
    )
    lines = out.read_text(encoding="utf-8").splitlines()
    assert [line.split(",")[0] for line in lines[1:]] == ["Acme Duct"]
    assert lines[1].rsplit(",", 1)[1] == "pixel"
    assert summary.written == 1
    assert summary.kept_with_all == 3


@respx.mock
def test_zero_pixel_hits_writes_header_only(tmp_path):
    respx.post(PLACES_URL).mock(
        return_value=httpx.Response(
            200, json={"places": [place("p2", "Beta Vents", website="https://www.beta.com")]}
        )
    )
    respx.get("https://www.beta.com/").mock(return_value=httpx.Response(200, text=PLAIN_HTML))
    out = tmp_path / "candidates.csv"
    summary = run_sourcing(
        settings(), keyword="duct cleaning", metros=["Denver, CO"], out=out,
        keep_all=False, max_queries=60, fetcher=quick_fetcher(),
    )
    assert out.read_text(encoding="utf-8").splitlines() == ["company,email,website,city,ad_signal"]
    assert summary.written == 0
    assert summary.kept_with_all == 1  # what "--all would have kept"
