"""Public email extraction (T013, research.md R4)."""

from prospector.source import extract_public_email


def page(body):
    return f"<html><body>{body}</body></html>"


def test_mailto_extracted():
    html = page('<a href="mailto:Info@AcmeDuct.com">Email us</a>')
    assert extract_public_email(html) == "info@acmeduct.com"


def test_mailto_query_params_stripped():
    html = page('<a href="mailto:booking@acme.com?subject=Quote%20request">Book</a>')
    assert extract_public_email(html) == "booking@acme.com"


def test_mailto_tier_beats_plaintext_tier():
    html = page('<p>Reach us: text@acme.com</p><a href="mailto:link@acme.com">mail</a>')
    assert extract_public_email(html) == "link@acme.com"


def test_first_mailto_in_document_order_wins():
    html = page('<a href="mailto:first@acme.com">a</a><a href="mailto:second@acme.com">b</a>')
    assert extract_public_email(html) == "first@acme.com"


def test_plaintext_fallback():
    html = page("<p>Call us or write to office@acmeduct.com today.</p>")
    assert extract_public_email(html) == "office@acmeduct.com"


def test_asset_false_positive_rejected():
    html = page('<p>See our logo photo@2x.png and mail hello@acme.com</p>')
    assert extract_public_email(html) == "hello@acme.com"


def test_no_email_returns_none():
    assert extract_public_email(page("<p>No contact info here.</p>")) is None


def test_invalid_mailto_skipped_plaintext_used():
    html = page('<a href="mailto:not-an-email">bad</a><p>real@acme.com</p>')
    assert extract_public_email(html) == "real@acme.com"
