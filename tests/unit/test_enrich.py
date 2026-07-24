from pathlib import Path

import httpx
import respx

from prospector.config import Settings
from prospector.enrich import first_names, hunter_lookup, infer_from_email
from prospector.models import EvidenceKind


def settings(hunter_key=None):
    return Settings(
        openrouter_key="sk", openrouter_model="m", places_key=None,
        hunter_key=hunter_key, vault_dir=Path("Vault/Outreach"),
    )


class TestEmailPatterns:
    def test_scottb_high(self):
        inference = infer_from_email("scottb@acmeduct.com")
        assert inference.first_name == "Scott"
        assert inference.candidate is None
        assert inference.evidence.kind is EvidenceKind.EMAIL_PATTERN
        assert "scottb" in inference.evidence.excerpt

    def test_first_dot_last_high(self):
        assert infer_from_email("john.smith@x.com").first_name == "John"
        assert infer_from_email("mary_jones@x.com").first_name == "Mary"

    def test_firstlast_concatenated_high(self):
        assert infer_from_email("johnsmith@x.com").first_name == "John"

    def test_bare_first_name_high(self):
        assert infer_from_email("scott@x.com").first_name == "Scott"

    def test_derickson_is_candidate_only(self):
        inference = infer_from_email("derickson@x.com")
        assert inference.first_name is None
        assert inference.candidate == "Derickson"
        assert "surname-likely" in inference.evidence.excerpt

    def test_initial_dot_surname_is_candidate(self):
        inference = infer_from_email("j.smithers@x.com")
        assert inference.first_name is None
        assert inference.candidate == "Smithers"

    def test_generic_inboxes_yield_nothing(self):
        for prefix in ("info", "office", "bookings", "system", "noreply"):
            inference = infer_from_email(f"{prefix}@x.com")
            assert inference.first_name is None and inference.candidate is None, prefix

    def test_no_email_yields_nothing(self):
        assert infer_from_email(None).first_name is None
        assert infer_from_email("not-an-email").first_name is None

    def test_digits_yield_nothing(self):
        inference = infer_from_email("duct247@x.com")
        assert inference.first_name is None and inference.candidate is None

    def test_names_list_loaded(self):
        names = first_names()
        assert len(names) > 500
        assert "scott" in names and "derick" not in names


class TestHunter:
    def test_skipped_without_key(self):
        assert hunter_lookup("x@y.com", settings()).candidate is None

    @respx.mock
    def test_hunter_result_is_candidate_tier_only(self):
        respx.get(url__startswith="https://api.hunter.io/v2/people/find").mock(
            return_value=httpx.Response(200, json={"data": {"name": {"givenName": "Scott"}}})
        )
        inference = hunter_lookup("scott@acme.com", settings(hunter_key="h-key"))
        assert inference.first_name is None  # never high from third parties
        assert inference.candidate == "Scott"
        assert inference.evidence.kind is EvidenceKind.HUNTER

    @respx.mock
    def test_hunter_error_yields_nothing(self):
        respx.get(url__startswith="https://api.hunter.io/v2/people/find").mock(
            return_value=httpx.Response(500)
        )
        assert hunter_lookup("x@y.com", settings(hunter_key="h-key")).candidate is None
