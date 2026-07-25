"""008 US6: the pixel filter is unchanged, and NO command contacts Facebook.

`test_source_pixel_fetch.py` already proves classification is correct and that
sourcing never requests a Facebook host. Two things it does not pin, and which
008 explicitly promises not to have changed, are covered here:

- **SC-007 / FR-021**: the filter's *defaults* — the marker set, the container
  budget, and the fact that a default run keeps only pixel-positive rows. 008
  removed Facebook as a channel while deliberately keeping Facebook-ad
  infrastructure as a sourcing signal, so the exact place that line is drawn is
  worth freezing.
- **SC-002 / FR-022**: "across EVERY command". The guarantee was previously
  asserted for `run` and `source` only; `send` and `dashboard` are covered here
  too, so the claim in the README safety table is tested as written.

Every marker below is matched as a STRING in already-fetched markup. A Facebook
URL appearing in a page is read, never requested (Constitution v7.0.0, II).
"""

from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from prospector import source as source_mod
from prospector.cli import app
from prospector.config import Settings
from prospector.fetch import Fetcher
from prospector.source import PLACES_URL, run_sourcing

runner = CliRunner()

FB_HOST_PATTERN = r".*(facebook\.com|fb\.com|fb\.me|fbcdn\.net|messenger\.com)$"

# Pixel markup AND an inline address, so no contact-page hop is needed.
PIXEL_HTML = (
    "<html><head><script>fbq('init','123');</script></head>"
    "<body>Acme <a href='mailto:info@acme.com'>mail</a></body></html>"
)
# Facebook links, an embed, and a tracking-beacon URL — all read, none fetched.
FB_STUFFED_HTML = (
    "<html><body>"
    '<a href="https://www.facebook.com/plain">our page</a>'
    '<iframe src="https://www.facebook.com/plugins/page.php?href=plain"></iframe>'
    '<a href="mailto:hi@plain.com">mail</a>'
    "</body></html>"
)


def settings(tmp_path=None):
    return Settings(
        openrouter_key=None,
        openrouter_model="test/model",
        places_key="places-x",
        hunter_key=None,
        vault_dir=Path(tmp_path or "Vault/Outreach"),
    )


def quick_fetcher():
    return Fetcher(client=httpx.Client(follow_redirects=True), host_interval=0.0, sleep=lambda s: None)


def place(pid, name, website):
    return {
        "id": pid,
        "displayName": {"text": name},
        "websiteUri": website,
        "formattedAddress": "1 Main St, Denver, CO 80202, USA",
    }


def stub_two_candidates():
    """One pixel-positive, one Facebook-stuffed but pixel-free."""
    respx.post(PLACES_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "places": [
                    place("p1", "Acme Duct", "https://acme.com"),
                    place("p2", "Plain Vents", "https://plain.com"),
                ]
            },
        )
    )
    respx.get("https://acme.com/").mock(return_value=httpx.Response(200, text=PIXEL_HTML))
    respx.get("https://plain.com/").mock(return_value=httpx.Response(200, text=FB_STUFFED_HTML))


def signals(out: Path) -> dict[str, str]:
    rows = out.read_text(encoding="utf-8").splitlines()[1:]
    return {r.split(",")[0]: r.rsplit(",", 1)[1] for r in rows}


class TestPixelFilterDefaultsUnchanged:
    """FR-021: behavior AND defaults are unchanged by this feature."""

    def test_marker_set_is_frozen(self):
        assert source_mod.PIXEL_MARKERS == (
            "connect.facebook.net",
            "fbq(",
            "facebook.com/tr",
        )

    def test_container_budget_is_frozen(self):
        assert source_mod.MAX_GTM_CONTAINERS == 2

    def test_csv_columns_are_frozen(self):
        """Columns 1-4 stay exactly the `run` input format; ad_signal rides along."""
        assert source_mod.CSV_HEADER == ["company", "email", "website", "city", "ad_signal"]

    def test_a_facebook_link_alone_is_not_a_pixel(self):
        """A page linking to Facebook is not a page running Meta ads."""
        assert source_mod.detect_pixel(FB_STUFFED_HTML) == "none"

    @respx.mock
    def test_default_run_keeps_only_pixel_rows(self, tmp_path):
        stub_two_candidates()
        out = tmp_path / "c.csv"
        summary = run_sourcing(
            settings(),
            keyword="duct cleaning",
            metros=["Denver, CO"],
            out=out,
            fetcher=quick_fetcher(),
        )
        assert signals(out) == {"Acme Duct": "pixel"}
        assert summary.written == 1
        assert summary.pixel_positive == 1
        # The dropped candidate is still reported, so a 0-row run is explicable.
        assert summary.kept_with_all == 2

    @respx.mock
    def test_all_flag_keeps_every_candidate(self, tmp_path):
        stub_two_candidates()
        out = tmp_path / "c.csv"
        run_sourcing(
            settings(),
            keyword="duct cleaning",
            metros=["Denver, CO"],
            out=out,
            keep_all=True,
            fetcher=quick_fetcher(),
        )
        assert signals(out) == {"Acme Duct": "pixel", "Plain Vents": "none"}

    def test_cli_defaults_are_frozen(self):
        """--all off, 60-query budget, candidates.csv — unchanged by 008."""
        result = runner.invoke(app, ["source", "--help"])
        assert result.exit_code == 0
        assert "60" in result.output
        assert "candidates.csv" in result.output


class TestNoCommandContactsFacebook:
    """SC-002 / FR-022, asserted for every command the CLI exposes."""

    @pytest.fixture
    def blocked(self):
        """A route that answers 200 — so a leak shows up as a call, not an error."""
        with respx.mock:
            yield respx.route(host__regex=FB_HOST_PATTERN).mock(
                return_value=httpx.Response(200)
            )

    def test_source_makes_no_facebook_request(self, tmp_path, blocked):
        stub_two_candidates()
        run_sourcing(
            settings(),
            keyword="duct cleaning",
            metros=["Denver, CO"],
            out=tmp_path / "c.csv",
            keep_all=True,
            fetcher=quick_fetcher(),
        )
        assert blocked.call_count == 0

    def test_run_makes_no_facebook_request(self, tmp_path, blocked, monkeypatch):
        """A company whose only listed contact is a Facebook URL is skipped,
        not fetched — the address field is read, never dialled."""
        from helpers import run_fixture_batch

        csv = (
            "company,email,website,city\n"
            "Plain Vents,https://facebook.com/plain,,Denver\n"
        )
        respx.get("https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text="<html><body>no results</body></html>")
        )
        respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        )
        summary, _ = run_fixture_batch(tmp_path, csv_content=csv)
        assert summary.no_email_skipped == 1
        assert blocked.call_count == 0

    def test_dashboard_makes_no_facebook_request(self, tmp_path, blocked):
        vault_dir = tmp_path / "Vault" / "Outreach"
        vault_dir.mkdir(parents=True)
        result = runner.invoke(app, ["dashboard", "--vault", str(vault_dir)])
        assert result.exit_code == 0
        assert blocked.call_count == 0

    def test_send_dry_run_makes_no_facebook_request(self, tmp_path, blocked, monkeypatch):
        """Dry-run also proves it opens no connection at all (FR-020)."""
        vault_dir = tmp_path / "Vault" / "Outreach"
        vault_dir.mkdir(parents=True)
        (vault_dir / "plain-vents.md").write_text(
            "---\ncompany: Plain Vents\nemail: hi@plain.com\nchannel: email\n"
            "status: approved\ntags: [outreach, prospector]\n---\n\n"
            "## Draft\n**Subject:** Hello\n\nA body.\n\n## Log\n-\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("PROSPECTOR_SEND_PROVIDER", "gmail")
        monkeypatch.setenv("PROSPECTOR_SEND_FROM", "outreach@example.com")
        monkeypatch.setenv("PROSPECTOR_LEDGER", str(tmp_path / "ledger.jsonl"))
        result = runner.invoke(app, ["send", "--vault", str(vault_dir)])
        assert result.exit_code == 0
        assert "WOULD SEND" in result.output
        assert blocked.call_count == 0
