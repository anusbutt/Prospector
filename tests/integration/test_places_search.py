"""PlacesSearcher + discover(): parsing, budget guard, per-metro failure isolation (T005)."""

import httpx
import pytest
import respx

from prospector.source import PLACES_URL, PlacesSearcher, SourcingSummary, discover


def place(pid, name, address="1 Main St, Denver, CO 80202, USA", website="https://example.com"):
    return {
        "id": pid,
        "displayName": {"text": name},
        "formattedAddress": address,
        "websiteUri": website,
    }


@respx.mock
def test_search_parses_results_and_sends_contract_headers():
    route = respx.post(PLACES_URL).mock(
        return_value=httpx.Response(200, json={"places": [place("p1", "Acme Duct")]})
    )
    results = PlacesSearcher("key-x").search("duct cleaning", "Denver, CO")
    assert [p["id"] for p in results] == ["p1"]
    request = route.calls.last.request
    assert request.headers["X-Goog-Api-Key"] == "key-x"
    assert "places.id" in request.headers["X-Goog-FieldMask"]
    assert b"duct cleaning in Denver, CO" in request.content
    assert b'"maxResultCount": 20' in request.content or b'"maxResultCount":20' in request.content


@respx.mock
def test_budget_stops_queries_mid_sweep():
    route = respx.post(PLACES_URL).mock(
        return_value=httpx.Response(200, json={"places": [place("p1", "Acme")]})
    )
    summary = SourcingSummary(metros_total=3, query_budget=2)
    discover(
        PlacesSearcher("k"), "duct cleaning", ["A, AA", "B, BB", "C, CC"],
        max_queries=2, limit=None, summary=summary,
    )
    assert route.call_count == 2
    assert summary.queries_used == 2
    assert summary.metros_covered == 2


@respx.mock
def test_metro_failure_is_isolated():
    calls = {"n": 0}

    def responder(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(403, json={"error": {"message": "denied"}})
        return httpx.Response(200, json={"places": [place("p2", "Beta Vents")]})

    respx.post(PLACES_URL).mock(side_effect=responder)
    summary = SourcingSummary(metros_total=2, query_budget=60)
    candidates = discover(
        PlacesSearcher("k"), "duct cleaning", ["A, AA", "B, BB"],
        max_queries=60, limit=None, summary=summary,
    )
    assert [c.company for c in candidates] == ["Beta Vents"]
    assert summary.metros_covered == 2
    assert len(summary.failures) == 1
    assert "places query failed" in summary.failures[0][1]


@respx.mock
def test_limit_restricts_metros():
    route = respx.post(PLACES_URL).mock(
        return_value=httpx.Response(200, json={"places": []})
    )
    summary = SourcingSummary(metros_total=3, query_budget=60)
    discover(
        PlacesSearcher("k"), "duct cleaning", ["A, AA", "B, BB", "C, CC"],
        max_queries=60, limit=1, summary=summary,
    )
    assert route.call_count == 1
