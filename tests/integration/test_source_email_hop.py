"""Email capture with one contact-page hop (T014)."""

from pathlib import Path

import httpx
import respx

from prospector.config import Settings
from prospector.fetch import Fetcher
from prospector.source import PLACES_URL, run_sourcing


def settings():
    return Settings(
        openrouter_key=None, openrouter_model="test/model",
        places_key="places-x", hunter_key=None, vault_dir=Path("Vault/Outreach"),
    )


def quick_fetcher():
    return Fetcher(client=httpx.Client(follow_redirects=True), host_interval=0.0, sleep=lambda s: None)


def place(pid, name, website):
    return {"id": pid, "displayName": {"text": name}, "websiteUri": website,
            "formattedAddress": "1 Main St, Denver, CO 80202, USA"}


HOME_WITH_EMAIL = '<html><body><a href="mailto:office@direct.com">mail</a></body></html>'
HOME_WITH_CONTACT_LINK = '<html><body><a href="/contact-us">Contact</a></body></html>'
HOME_WITH_CROSS_HOST_CONTACT = (
    '<html><body><a href="https://other.example.com/contact">Contact</a></body></html>'
)
CONTACT_PAGE = '<html><body><p>Write to team@hoppy.com</p></body></html>'
NO_EMAIL_PAGE = "<html><body><p>nothing here</p></body></html>"


def run(tmp_path):
    return run_sourcing(
        settings(), keyword="duct cleaning", metros=["Denver, CO"],
        out=tmp_path / "c.csv", keep_all=True, max_queries=60, fetcher=quick_fetcher(),
    )


def emails_from_csv(tmp_path):
    lines = (tmp_path / "c.csv").read_text(encoding="utf-8").splitlines()[1:]
    return {line.split(",")[0]: line.split(",")[1] for line in lines}


@respx.mock
def test_homepage_email_direct(tmp_path):
    respx.post(PLACES_URL).mock(
        return_value=httpx.Response(200, json={"places": [place("p1", "Direct Co", "https://direct.com")]})
    )
    respx.get("https://direct.com/").mock(return_value=httpx.Response(200, text=HOME_WITH_EMAIL))
    summary = run(tmp_path)
    assert emails_from_csv(tmp_path) == {"Direct Co": "office@direct.com"}
    assert summary.emails_found == 1


@respx.mock
def test_contact_page_hop_finds_email(tmp_path):
    respx.post(PLACES_URL).mock(
        return_value=httpx.Response(200, json={"places": [place("p1", "Hoppy Co", "https://hoppy.com")]})
    )
    respx.get("https://hoppy.com/").mock(return_value=httpx.Response(200, text=HOME_WITH_CONTACT_LINK))
    respx.get("https://hoppy.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://hoppy.com/contact-us").mock(return_value=httpx.Response(200, text=CONTACT_PAGE))
    summary = run(tmp_path)
    assert emails_from_csv(tmp_path) == {"Hoppy Co": "team@hoppy.com"}
    assert summary.emails_found == 1


@respx.mock
def test_no_contact_link_leaves_email_blank(tmp_path):
    respx.post(PLACES_URL).mock(
        return_value=httpx.Response(200, json={"places": [place("p1", "Silent Co", "https://silent.com")]})
    )
    respx.get("https://silent.com/").mock(return_value=httpx.Response(200, text=NO_EMAIL_PAGE))
    summary = run(tmp_path)
    assert emails_from_csv(tmp_path) == {"Silent Co": ""}
    assert summary.emails_found == 0


@respx.mock
def test_cross_host_contact_link_ignored(tmp_path):
    respx.post(PLACES_URL).mock(
        return_value=httpx.Response(200, json={"places": [place("p1", "Xhost Co", "https://xhost.com")]})
    )
    respx.get("https://xhost.com/").mock(
        return_value=httpx.Response(200, text=HOME_WITH_CROSS_HOST_CONTACT)
    )
    # other.example.com is NOT stubbed: if the hop followed it, respx would error.
    summary = run(tmp_path)
    assert emails_from_csv(tmp_path) == {"Xhost Co": ""}
    assert summary.emails_found == 0
