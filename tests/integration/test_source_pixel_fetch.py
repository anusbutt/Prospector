"""Homepage fetch + ad_signal classification, incl. the FB-host guarantee (T011)."""

from pathlib import Path

import httpx
import respx

from prospector.config import Settings
from prospector.fetch import Fetcher
from prospector.source import PLACES_URL, run_sourcing

PIXEL_HTML = (
    "<html><head><script>fbq('init','123');</script>"
    '<script async src="https://connect.facebook.net/en_US/fbevents.js"></script>'
    "</head><body>Acme</body></html>"
)
# A page covered in Facebook URLs — links, embeds, AND pixel markup. Sourcing may
# only ever READ these strings, never request them.
FB_STUFFED_HTML = (
    "<html><body>"
    '<a href="https://www.facebook.com/acme">FB</a>'
    '<a href="https://fb.me/acme">short</a>'
    '<img src="https://www.facebook.com/tr?id=1&ev=PageView"/>'
    '<iframe src="https://www.facebook.com/plugins/page.php?href=acme"></iframe>'
    "</body></html>"
)
PLAIN_HTML = "<html><body><h1>Beta Vents</h1></body></html>"


def settings():
    return Settings(
        openrouter_key=None, openrouter_model="test/model",
        places_key="places-x", hunter_key=None, vault_dir=Path("Vault/Outreach"),
    )


def quick_fetcher():
    return Fetcher(client=httpx.Client(follow_redirects=True), host_interval=0.0, sleep=lambda s: None)


def places_response(places):
    return httpx.Response(200, json={"places": places})


def place(pid, name, website):
    return {"id": pid, "displayName": {"text": name}, "websiteUri": website,
            "formattedAddress": "1 Main St, Denver, CO 80202, USA"}


@respx.mock
def test_pixel_and_plain_classify_and_fb_hosts_never_contacted(tmp_path):
    blocked = respx.route(
        host__regex=r".*(facebook\.com|fb\.com|fb\.me|fbcdn\.net|messenger\.com)$"
    ).mock(return_value=httpx.Response(200))
    respx.post(PLACES_URL).mock(
        return_value=places_response([
            place("p1", "Acme Duct", "https://acme.com"),
            place("p2", "Beta Vents", "https://beta.com"),
            place("p3", "FB Stuffed Co", "https://stuffed.com"),
        ])
    )
    respx.get("https://acme.com/").mock(return_value=httpx.Response(200, text=PIXEL_HTML))
    respx.get("https://beta.com/").mock(return_value=httpx.Response(200, text=PLAIN_HTML))
    respx.get("https://stuffed.com/").mock(return_value=httpx.Response(200, text=FB_STUFFED_HTML))

    out = tmp_path / "c.csv"
    summary = run_sourcing(
        settings(), keyword="duct cleaning", metros=["Denver, CO"], out=out,
        keep_all=True, max_queries=60, fetcher=quick_fetcher(),
    )
    rows = out.read_text(encoding="utf-8").splitlines()[1:]
    signals = {r.split(",")[0]: r.rsplit(",", 1)[1] for r in rows}
    assert signals == {"Acme Duct": "pixel", "Beta Vents": "none", "FB Stuffed Co": "pixel"}
    assert summary.pixel_positive == 2
    # The guarantee: zero requests to any Facebook-owned host, ever.
    assert blocked.call_count == 0


@respx.mock
def test_unreachable_site_classifies_none_and_run_continues(tmp_path):
    respx.post(PLACES_URL).mock(
        return_value=places_response([
            place("p1", "Down Co", "https://down.example.com"),
            place("p2", "Up Co", "https://up.example.com"),
        ])
    )
    respx.get("https://down.example.com/").mock(side_effect=httpx.ConnectError("boom"))
    respx.get("https://up.example.com/").mock(return_value=httpx.Response(200, text=PIXEL_HTML))

    out = tmp_path / "c.csv"
    summary = run_sourcing(
        settings(), keyword="duct cleaning", metros=["Denver, CO"], out=out,
        keep_all=True, max_queries=60, fetcher=quick_fetcher(),
    )
    rows = out.read_text(encoding="utf-8").splitlines()[1:]
    signals = {r.split(",")[0]: r.rsplit(",", 1)[1] for r in rows}
    assert signals == {"Down Co": "none", "Up Co": "pixel"}
    assert any("Down Co" == name for name, _ in summary.failures)


@respx.mock
def test_http_error_page_classifies_none(tmp_path):
    respx.post(PLACES_URL).mock(
        return_value=places_response([place("p1", "Gone Co", "https://gone.example.com")])
    )
    respx.get("https://gone.example.com/").mock(return_value=httpx.Response(404, text="nope"))

    out = tmp_path / "c.csv"
    summary = run_sourcing(
        settings(), keyword="duct cleaning", metros=["Denver, CO"], out=out,
        keep_all=True, max_queries=60, fetcher=quick_fetcher(),
    )
    rows = out.read_text(encoding="utf-8").splitlines()[1:]
    assert rows[0].rsplit(",", 1)[1] == "none"
    assert any("404" in reason for _, reason in summary.failures)


# --- GTM container inspection (T018, R3 amendment) ---

GTM_PAGE = (
    "<html><head>"
    '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-XYZ99"></script>'
    "</head><body>no inline pixel here</body></html>"
)
GTM_JS_WITH_PIXEL = 'var a="https://connect.facebook.net/en_US/fbevents.js";fbq("init","1");'
GTM_JS_NO_PIXEL = 'var tags=[{"function":"__googtag","vtp_measurementId":"G-123"}];'


@respx.mock
def test_gtm_mediated_pixel_detected_and_no_fb_contact(tmp_path):
    blocked = respx.route(
        host__regex=r".*(facebook\.com|fb\.com|fb\.me|fbcdn\.net|messenger\.com)$"
    ).mock(return_value=httpx.Response(200))
    respx.post(PLACES_URL).mock(
        return_value=places_response([place("p1", "GTM Co", "https://gtmco.com")])
    )
    respx.get("https://gtmco.com/").mock(return_value=httpx.Response(200, text=GTM_PAGE))
    respx.get("https://www.googletagmanager.com/gtm.js", params={"id": "GTM-XYZ99"}).mock(
        return_value=httpx.Response(200, text=GTM_JS_WITH_PIXEL)
    )
    out = tmp_path / "c.csv"
    summary = run_sourcing(
        settings(), keyword="duct cleaning", metros=["Denver, CO"], out=out,
        keep_all=True, max_queries=60, fetcher=quick_fetcher(),
    )
    rows = out.read_text(encoding="utf-8").splitlines()[1:]
    assert rows[0].rsplit(",", 1)[1] == "pixel"
    assert summary.pixel_positive == 1
    assert blocked.call_count == 0


@respx.mock
def test_gtm_without_meta_tags_stays_none(tmp_path):
    respx.post(PLACES_URL).mock(
        return_value=places_response([place("p1", "Analytics Only Co", "https://ga.example.com")])
    )
    respx.get("https://ga.example.com/").mock(return_value=httpx.Response(200, text=GTM_PAGE))
    respx.get("https://www.googletagmanager.com/gtm.js", params={"id": "GTM-XYZ99"}).mock(
        return_value=httpx.Response(200, text=GTM_JS_NO_PIXEL)
    )
    out = tmp_path / "c.csv"
    run_sourcing(
        settings(), keyword="duct cleaning", metros=["Denver, CO"], out=out,
        keep_all=True, max_queries=60, fetcher=quick_fetcher(),
    )
    assert out.read_text(encoding="utf-8").splitlines()[1].rsplit(",", 1)[1] == "none"


@respx.mock
def test_gtm_container_fetch_failure_classifies_none(tmp_path):
    respx.post(PLACES_URL).mock(
        return_value=places_response([place("p1", "Broken GTM Co", "https://broken.example.com")])
    )
    respx.get("https://broken.example.com/").mock(return_value=httpx.Response(200, text=GTM_PAGE))
    respx.get("https://www.googletagmanager.com/gtm.js", params={"id": "GTM-XYZ99"}).mock(
        side_effect=httpx.ConnectError("boom")
    )
    out = tmp_path / "c.csv"
    run_sourcing(
        settings(), keyword="duct cleaning", metros=["Denver, CO"], out=out,
        keep_all=True, max_queries=60, fetcher=quick_fetcher(),
    )
    assert out.read_text(encoding="utf-8").splitlines()[1].rsplit(",", 1)[1] == "none"
