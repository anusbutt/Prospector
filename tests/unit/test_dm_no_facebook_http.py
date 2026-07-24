"""SC-004 / FR-007: the assisted-manual Messenger path issues ZERO HTTP requests
to any Facebook host. The tool only hands the URL to the operator's browser via
the injected opener; it never fetches. We assert that (a) the opener received the
target and (b) no httpx client is ever constructed during the walk."""

import httpx

from prospector import dm as dm_mod
from tests.unit.test_dm import Confirm, make_settings, write_messenger_note


def test_run_dm_makes_no_facebook_request(tmp_path, monkeypatch):
    s = make_settings(tmp_path)
    write_messenger_note(s.vault_dir, "acme-ducts",
                         facebook_url="https://www.facebook.com/AcmeDucts/")

    # Trip-wire: any attempt to open an httpx client during the walk fails loudly.
    def _boom(*a, **k):
        raise AssertionError("dm made an HTTP request — it must never contact Facebook")

    monkeypatch.setattr(httpx, "Client", _boom)
    monkeypatch.setattr(httpx, "get", _boom)
    monkeypatch.setattr(httpx, "request", _boom)

    opens = []
    report = dm_mod.run_dm(
        s, dry_run=False,
        confirm=Confirm("y"),
        opener=lambda url: opens.append(url) or True,
        copier=lambda text: True,
    )
    assert report.delivered == 1
    # The browser handoff is the ONLY Facebook interaction, and it goes through
    # the injected opener (in production: webbrowser.open), never httpx.
    assert opens == ["https://www.facebook.com/AcmeDucts/"]


def test_preview_opens_no_browser_and_makes_no_request(tmp_path, monkeypatch):
    s = make_settings(tmp_path)
    write_messenger_note(s.vault_dir, "acme-ducts")

    def _boom(*a, **k):
        raise AssertionError("preview must make no external request")

    monkeypatch.setattr(httpx, "Client", _boom)

    opens = []
    report = dm_mod.run_dm(
        s, dry_run=True,
        opener=lambda url: opens.append(url) or True,
        copier=lambda text: (_ for _ in ()).throw(AssertionError("preview copied clipboard")),
    )
    assert report.would_deliver == 1
    assert opens == []  # preview never opens a browser
