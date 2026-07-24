"""Places JSON -> Candidate parsing (T006)."""

from prospector.source import candidate_from_place


def test_full_place_parses():
    c = candidate_from_place(
        {
            "id": "p1",
            "displayName": {"text": "  Acme Duct Cleaning  "},
            "formattedAddress": "123 Main St, Boston, MA 02101, USA",
            "websiteUri": "https://WWW.AcmeDuct.com/home",
        },
        "Boston, MA",
    )
    assert c.company == "Acme Duct Cleaning"
    assert c.place_id == "p1"
    assert c.city == "Boston, MA"
    assert c.website == "https://WWW.AcmeDuct.com/home"  # fetch URL kept as listed
    assert c.domain == "acmeduct.com"  # lowercased, www.-stripped


def test_city_falls_back_to_metro():
    c = candidate_from_place(
        {"id": "p2", "displayName": {"text": "Beta"}, "formattedAddress": "Colorado"},
        "Denver, CO",
    )
    assert c.city == "Denver, CO"


def test_empty_company_dropped():
    assert candidate_from_place({"id": "p3", "displayName": {"text": "   "}}, "X, YZ") is None
    assert candidate_from_place({"id": "p4"}, "X, YZ") is None


def test_missing_website_is_none():
    c = candidate_from_place({"id": "p5", "displayName": {"text": "Gamma"}}, "X, YZ")
    assert c.website is None
    assert c.domain is None
    assert c.ad_signal == "none"


def test_facebook_page_as_website_treated_as_no_website():
    c = candidate_from_place(
        {
            "id": "p6",
            "displayName": {"text": "Delta"},
            "websiteUri": "https://www.facebook.com/deltaducts",
        },
        "X, YZ",
    )
    assert c.website is None  # never fetched, never a domain (Constitution II)
    assert c.domain is None
