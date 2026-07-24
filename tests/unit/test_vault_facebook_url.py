"""007 US4: messenger notes carry a machine-readable `facebook_url` header,
resolved from the input facebook_url or a discovered facebook.com signal, and
appended to the key order so pre-007 notes don't reorder on first re-run."""

from prospector.models import (
    Channel,
    Company,
    Evidence,
    EvidenceKind,
    Prospect,
    ResearchResult,
)
from prospector.vault import FRONTMATTER_KEYS, parse_note, render_note


def _messenger_prospect(*, facebook_url=None, fb_evidence=None):
    company = Company(
        company="Acme Ducts",
        email="",
        channel=Channel.MESSENGER,
        facebook_url=facebook_url,
    )
    research = ResearchResult(website=None, hook="Denver service area")
    if fb_evidence:
        research.fb_evidence = fb_evidence
    return Prospect(company=company, research=research)


def test_input_facebook_url_wins(tmp_path):
    p = _messenger_prospect(facebook_url="https://facebook.com/AcmeDucts")
    fm, _ = parse_note(render_note(p, "d", "r"))
    assert fm["facebook_url"] == '"https://facebook.com/AcmeDucts"'  # quoted (has ://)


def test_discovered_signal_used_when_no_input(tmp_path):
    ev = Evidence(
        kind=EvidenceKind.FB_SEARCH_ACTIVE,
        value="https://www.facebook.com/AcmeDuctsCO/",
        source="ddg",
        excerpt="found",
    )
    p = _messenger_prospect(fb_evidence=[ev])
    fm, _ = parse_note(render_note(p, "d", "r"))
    assert "facebook.com/AcmeDuctsCO" in fm["facebook_url"]


def test_widget_marker_is_not_used_as_target(tmp_path):
    # FB_WIDGET value is a script marker, not a page URL — must NOT be the target.
    ev = Evidence(
        kind=EvidenceKind.FB_WIDGET,
        value="connect.facebook.net",
        source="site",
        excerpt="widget",
    )
    p = _messenger_prospect(fb_evidence=[ev])
    fm, _ = parse_note(render_note(p, "d", "r"))
    assert fm["facebook_url"] == ""  # empty, not the marker


def test_empty_when_no_link(tmp_path):
    p = _messenger_prospect()
    fm, _ = parse_note(render_note(p, "d", "r"))
    assert fm["facebook_url"] == ""


def test_field_appended_before_tags():
    keys = list(FRONTMATTER_KEYS)
    assert keys.index("facebook_url") < keys.index("tags")
    assert keys.index("outcome") < keys.index("facebook_url")  # appended after 006 keys
