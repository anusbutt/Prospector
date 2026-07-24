"""Meta Pixel string-inspection detector (T010, research.md R3)."""

from prospector.source import detect_pixel

LOADER = '<script async src="https://connect.facebook.net/en_US/fbevents.js"></script>'
FBQ = "<script>fbq('init', '1234567890');fbq('track', 'PageView');</script>"
NOSCRIPT = '<noscript><img src="https://www.facebook.com/tr?id=123&ev=PageView&noscript=1"/></noscript>'


def page(body):
    return f"<html><head></head><body>{body}</body></html>"


def test_each_marker_alone_detects():
    assert detect_pixel(page(LOADER)) == "pixel"
    assert detect_pixel(page(FBQ)) == "pixel"
    assert detect_pixel(page(NOSCRIPT)) == "pixel"


def test_full_standard_snippet_detects():
    assert detect_pixel(page(LOADER + FBQ + NOSCRIPT)) == "pixel"


def test_case_insensitive():
    assert detect_pixel(page(LOADER.upper())) == "pixel"
    assert detect_pixel(page("<script>FBQ('init', '1');</script>")) == "pixel"


def test_plain_facebook_profile_link_is_none():
    html = page('<a href="https://www.facebook.com/acmeducts">Find us on Facebook</a>')
    assert detect_pixel(html) == "none"


def test_prose_mentioning_facebook_is_none():
    assert detect_pixel(page("<p>Follow our facebook page for coupons!</p>")) == "none"


def test_empty_and_plain_pages_are_none():
    assert detect_pixel("") == "none"
    assert detect_pixel(page("<h1>Acme Duct Cleaning</h1><p>Call now.</p>")) == "none"


# --- GTM container id extraction (T018, R3 amendment) ---

from prospector.source import extract_gtm_ids

GTM_SNIPPET = (
    "<script>(function(w,d,s,l,i){...})(window,document,'script','dataLayer','GTM-ABC123');</script>"
    '<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-ABC123"></iframe></noscript>'
)


def test_gtm_id_extracted():
    assert extract_gtm_ids(page(GTM_SNIPPET)) == ["GTM-ABC123"]


def test_gtm_ids_deduped_and_capped_at_two():
    html = page(
        '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-AAAA1"></script>'
        '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-AAAA1"></script>'
        '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-BBBB2"></script>'
        '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-CCCC3"></script>'
    )
    assert extract_gtm_ids(html) == ["GTM-AAAA1", "GTM-BBBB2"]


def test_gtm_id_without_tagmanager_reference_ignored():
    # A bare "GTM-XXXX" string in prose without any googletagmanager.com reference
    assert extract_gtm_ids(page("<p>Our SKU GTM-12345 is popular</p>")) == []


def test_no_gtm_returns_empty():
    assert extract_gtm_ids(page("<h1>plain site</h1>")) == []
