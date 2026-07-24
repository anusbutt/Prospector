"""Shared fixtures/stubs for integration tests: a fixture CSV batch with the
network and LLM mocked at the httpx-transport level."""

import json
from pathlib import Path

import httpx

from prospector.config import Settings
from prospector.fetch import Fetcher
from prospector.pipeline import run_batch

FIXTURES = Path(__file__).parent.parent / "fixtures"
SITES = FIXTURES / "sites"

CSV_CONTENT = """company,email,website,city
Acme Duct Cleaning,info@acmeduct.com,acmeduct.com,
Beta Air Systems,scott@betaair.com,,Denver
Chat Only Cleaners,,,
,orphan@x.com,,
Plain Ducts,info@plainducts.com,plainducts.com,
Gamma Vent Care,derickson@gammavent.com,gammavent.com,
Delta Fresh Air,info@deltafreshair.com,deltafreshair.com,
Acme Duct South,info@acmeduct.com,acmeduct.com,Denver
"""

BARE_HTML = "<html><body><h1>Plain Ducts</h1><p>Welcome.</p></body></html>"
PLAIN_WITH_OWNER_HTML = (
    "<html><body><h1>Plain Ducts</h1>"
    "<p>Plain Ducts was founded by Sarah Miller in 2012.</p></body></html>"
)


def settings(vault_dir):
    return Settings(
        openrouter_key="sk-test", openrouter_model="test/model",
        places_key=None, hunter_key=None, vault_dir=Path(vault_dir),
    )


def openrouter_responder(request):
    payload = json.loads(request.content)
    user = json.loads(payload["messages"][1]["content"])
    slots = {
        "greeting_name": user["name_or_team"],
        "subject_company": user["company"],
    }
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(slots)}}]})


def ddg_responder(request):
    query = request.url.params.get("q", "")
    if "Beta" in query and "facebook" not in query:
        html = '<a class="result__a" href="https://betaair.com">Beta Air Systems</a>'
    else:
        html = "<p>no results</p>"
    return httpx.Response(200, text=f"<html><body>{html}</body></html>")


def install_stubs(mock) -> dict:
    """Register all routes on a respx mock router. Returns named routes."""
    routes = {}
    routes["blocked"] = mock.route(
        host__regex=r".*(facebook\.com|fb\.com|fb\.me|fbcdn\.net|messenger\.com)$"
    ).mock(return_value=httpx.Response(200))
    routes["openrouter"] = mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=openrouter_responder
    )
    mock.get(url__startswith="https://html.duckduckgo.com/html/").mock(side_effect=ddg_responder)

    # NB: pathless respx patterns match every path on the host; use explicit "/"
    mock.get("https://acmeduct.com/robots.txt").mock(return_value=httpx.Response(404))
    mock.get("https://acmeduct.com/about").mock(
        return_value=httpx.Response(200, text=(SITES / "acme" / "about.html").read_text())
    )
    mock.get("https://acmeduct.com/contact").mock(
        return_value=httpx.Response(200, text="<html><body>Contact Acme</body></html>")
    )
    mock.get("https://acmeduct.com/").mock(
        return_value=httpx.Response(200, text=(SITES / "acme" / "index.html").read_text())
    )

    mock.get("https://betaair.com/robots.txt").mock(return_value=httpx.Response(404))
    mock.get("https://betaair.com/").mock(
        return_value=httpx.Response(200, text=(SITES / "footer-name" / "index.html").read_text())
    )

    mock.get("https://plainducts.com/robots.txt").mock(return_value=httpx.Response(404))
    routes["plainducts"] = mock.get("https://plainducts.com/").mock(
        return_value=httpx.Response(200, text=BARE_HTML)
    )

    mock.get("https://gammavent.com/robots.txt").mock(return_value=httpx.Response(404))
    mock.get("https://gammavent.com/").mock(
        return_value=httpx.Response(200, text="<html><body><h1>Gamma Vent Care</h1></body></html>")
    )

    mock.get("https://deltafreshair.com/robots.txt").mock(return_value=httpx.Response(404))
    mock.get("https://deltafreshair.com/").mock(
        return_value=httpx.Response(200, text=(SITES / "fb-widget" / "index.html").read_text())
    )
    return routes


def run_fixture_batch(tmp_path, csv_content=CSV_CONTENT, **kwargs):
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text(csv_content)
    vault_dir = tmp_path / "Vault" / "Outreach"
    fetcher = Fetcher(clock=lambda: 0.0, sleep=lambda s: None)
    summary = run_batch(csv_path, settings(vault_dir), vault_dir=vault_dir, fetcher=fetcher, **kwargs)
    return summary, vault_dir


def frontmatter(note_text: str) -> dict:
    lines = note_text.split("---")[1].strip().splitlines()
    return {line.split(":", 1)[0]: line.split(":", 1)[1].strip() for line in lines}


def company_notes(vault_dir):
    return sorted(p.name for p in vault_dir.glob("*.md") if not p.name.startswith("_"))
