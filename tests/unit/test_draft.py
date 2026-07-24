import json
from pathlib import Path

import httpx
import pytest
import respx

from prospector.config import Settings
from prospector.draft import (
    DraftError,
    assemble_email,
    build_email_draft,
    build_messenger_draft,
    expected_greeting,
    is_generic_inbox,
    request_slots,
    validate_email_draft,
)
from prospector.models import Company, FbSignal, Prospect, ResearchResult, Variant

PRODUCT_URL = "https://www.omniveer.com/duct-lead-qualifier"
SIGNATURE = "Anas\nFounder, Omniveer"


def make_prospect(email="scott@acmeduct.com", hook="Boston service area"):
    company = Company(company="Acme Duct Cleaning", email=email, raw_email_field=email or "")
    research = ResearchResult(website="https://acmeduct.com", hook=hook, city="Boston")
    return Prospect(company=company, research=research)


def settings():
    return Settings(
        openrouter_key="sk-test", openrouter_model="test/model",
        places_key=None, hunter_key=None, vault_dir=Path("Vault/Outreach"),
    )


GOOD_SLOTS = {
    "greeting_name": "Acme Duct Cleaning team",
    "subject_company": "Acme Duct",
}


class TestAssembly:
    def test_golden_email_draft(self):
        """Rev. 2 (2026-07-17): the operator-supplied copy, locked byte-for-byte."""
        draft = assemble_email(make_prospect(email="info@acmeduct.com"), GOOD_SLOTS)
        assert draft.validated, draft.validation_errors
        assert draft.subject == "Free 10-day pilot for Acme Duct"
        assert draft.body == (
            "Hi Acme Duct Cleaning team,\n"
            "\n"
            "I'm giving 5 duct-cleaning companies a free 10-day pilot of the "
            "Omniveer Duct Lead Qualifier.\n"
            "\n"
            "It responds to new leads, qualifies them, books appointments when "
            "they're ready, sends the full details to your email, and keeps every "
            "lead organized in a dashboard.\n"
            "\n"
            "You can see the short demo here:\n"
            "https://www.omniveer.com/duct-lead-qualifier\n"
            "\n"
            "Reply to this email if you'd like one of the five pilot spots, or "
            "book a demo through the page.\n"
            "\n"
            "Anas\n"
            "Founder, Omniveer"
        )

    def test_same_body_for_generic_and_direct_inboxes(self):
        # rev. 2 dropped the generic-inbox forward-line opener
        generic = assemble_email(make_prospect(email="info@acmeduct.com"), GOOD_SLOTS)
        direct = assemble_email(make_prospect(email="scott@acmeduct.com"), GOOD_SLOTS)
        assert generic.body == direct.body
        assert "forward it to whoever" not in generic.body

    def test_channel_neutral_no_facebook_mention(self):
        draft = assemble_email(make_prospect(), GOOD_SLOTS)
        assert "facebook" not in draft.body.lower()
        assert "messages your page" not in draft.body.lower()


class TestSignalNeutrality:
    """Rev. 2: one channel-neutral body for every fb_signal level — the §7.5
    honesty gate is satisfied by making no channel claims at all."""

    def test_strong_signal_gets_the_same_neutral_body(self):
        strong = make_prospect()
        strong.fb_signal = FbSignal.STRONG
        strong.variant = Variant.EMAIL_FB
        neutral = assemble_email(make_prospect(), GOOD_SLOTS)
        draft = assemble_email(strong, GOOD_SLOTS)
        assert draft.validated, draft.validation_errors
        assert draft.body == neutral.body

    def test_weak_and_none_signals_identical(self):
        weak = make_prospect()
        weak.fb_signal = FbSignal.WEAK
        none_p = make_prospect()
        assert assemble_email(weak, GOOD_SLOTS).body == assemble_email(none_p, GOOD_SLOTS).body

    def test_never_claims_ads_at_any_signal(self):
        for signal in (FbSignal.STRONG, FbSignal.WEAK, FbSignal.NONE):
            prospect = make_prospect()
            prospect.fb_signal = signal
            draft = assemble_email(prospect, GOOD_SLOTS)
            for banned in ("your ads", "ad campaign", "running ads", "advertis"):
                assert banned not in draft.body.lower()


class TestMessengerDm:
    def test_dm_with_city_clause(self):
        prospect = make_prospect()
        prospect.variant = Variant.MESSENGER_DM
        prospect.research.city = "Boston"
        draft = build_messenger_draft(prospect)
        assert draft.validated, draft.validation_errors
        assert draft.subject is None
        assert "It checks customers are real, around Boston, quotes your real prices" in draft.body
        assert draft.body.startswith("Hey! I'm giving 5 duct cleaning companies")
        assert draft.body.endswith("(See it working: https://www.omniveer.com/duct-lead-qualifier)")

    def test_dm_without_city_drops_clause(self):
        prospect = make_prospect()
        prospect.variant = Variant.MESSENGER_DM
        prospect.research.city = None
        prospect.company.city = None
        draft = build_messenger_draft(prospect)
        assert draft.validated
        assert ", around" not in draft.body
        assert "It checks customers are real, quotes your real prices" in draft.body

    def test_dm_is_deterministic_no_llm(self):
        prospect = make_prospect()
        prospect.variant = Variant.MESSENGER_DM
        assert build_messenger_draft(prospect).body == build_messenger_draft(prospect).body
        assert build_messenger_draft(prospect).model == "deterministic"


class TestValidator:
    def test_unfilled_slot_rejected(self):
        slots = dict(GOOD_SLOTS, subject_company="Acme [Duct]")
        draft = assemble_email(make_prospect(), slots)
        assert not draft.validated
        assert any("unfilled" in e for e in draft.validation_errors)

    def test_ad_claim_in_tampered_body_rejected(self):
        prospect = make_prospect()
        good = assemble_email(prospect, GOOD_SLOTS)
        tampered = good.body.replace("It responds to new leads", "It responds to your ads")
        errors = validate_email_draft(good.subject, tampered, prospect, GOOD_SLOTS)
        assert any("ad-running claim" in e for e in errors)

    def test_wrong_greeting_rejected(self):
        slots = dict(GOOD_SLOTS, greeting_name="Steve")
        draft = assemble_email(make_prospect(), slots)
        assert not draft.validated
        assert any("greeting" in e for e in draft.validation_errors)

    def test_subject_company_with_foreign_words_rejected(self):
        slots = dict(GOOD_SLOTS, subject_company="Acme Duct Experts")
        draft = assemble_email(make_prospect(), slots)
        assert not draft.validated
        assert any("subject_company" in e for e in draft.validation_errors)

    def test_their_page_activity_phrasing_always_rejected(self):
        # rev. 2 template is channel-neutral: their-activity phrasing may not
        # appear at ANY signal level, even via tampering
        prospect = make_prospect()
        good = assemble_email(prospect, GOOD_SLOTS)
        tampered = good.body.replace(
            "It responds to new leads", "When someone messages your page, it responds"
        )
        errors = validate_email_draft(good.subject, tampered, prospect, GOOD_SLOTS)
        assert any("their-page-activity" in e for e in errors)

    def test_altered_template_prose_rejected(self):
        prospect = make_prospect()
        good = assemble_email(prospect, GOOD_SLOTS)
        tampered = good.body.replace("free 10-day pilot", "free 30-day trial")
        errors = validate_email_draft(good.subject, tampered, prospect, GOOD_SLOTS)
        assert any("template prose altered" in e for e in errors)

    def test_missing_signature_rejected(self):
        prospect = make_prospect()
        good = assemble_email(prospect, GOOD_SLOTS)
        tampered = good.body.replace(SIGNATURE, "Cheers,\nThe Omniveer Team")
        errors = validate_email_draft(good.subject, tampered, prospect, GOOD_SLOTS)
        assert any("signature" in e for e in errors)

    def test_unsourced_name_rejected_even_when_greeting_matches(self):
        # name_used set without any recorded evidence -> fabrication guard fires
        prospect = make_prospect()
        prospect.name_used = "Steve"
        slots = dict(GOOD_SLOTS, greeting_name="Steve")
        draft = assemble_email(prospect, slots)
        assert not draft.validated
        assert any("does not trace to a recorded source" in e for e in draft.validation_errors)

    def test_sourced_name_accepted(self):
        from prospector.models import Evidence, EvidenceKind

        prospect = make_prospect()
        prospect.name_used = "Scott"
        prospect.research.name_evidence.append(
            Evidence(kind=EvidenceKind.ABOUT_PAGE, value="Scott Brown", source="https://acmeduct.com/about")
        )
        slots = dict(GOOD_SLOTS, greeting_name="Scott")
        draft = assemble_email(prospect, slots)
        assert draft.validated, draft.validation_errors
        assert draft.body.startswith("Hi Scott,")


class TestLinkStrategy:
    """005 FR-201..205: Omniveer branding + exactly one promotional link (the
    product page), no homepage combo, no LinkedIn in the pitch, no legacy brand."""

    def all_golden_bodies(self):
        email = assemble_email(make_prospect(email="info@acmeduct.com"), GOOD_SLOTS)
        dm_prospect = make_prospect()
        dm_prospect.variant = Variant.MESSENGER_DM
        dm = build_messenger_draft(dm_prospect)
        return {"email": email, "dm": dm}

    def test_nestaro_branding_is_gone(self):
        for name, draft in self.all_golden_bodies().items():
            assert "nestaro" not in draft.body.lower(), name
            if draft.subject:
                assert "nestaro" not in draft.subject.lower(), name

    def test_product_page_is_the_single_promotional_link(self):
        for name, draft in self.all_golden_bodies().items():
            assert draft.validated, (name, draft.validation_errors)
            assert PRODUCT_URL in draft.body, name
            assert draft.body.count("http") == 1, name  # one link, no homepage combo

    def test_homepage_never_appears_as_its_own_link(self):
        for name, draft in self.all_golden_bodies().items():
            body_without_product = draft.body.replace(PRODUCT_URL, "")
            assert "omniveer.com" not in body_without_product.lower(), name

    def test_linkedin_never_in_any_pitch(self):
        for name, draft in self.all_golden_bodies().items():
            assert "linkedin.com" not in draft.body.lower(), name

    def test_second_promotional_link_is_rejected(self):
        prospect = make_prospect(email="info@acmeduct.com")
        good = assemble_email(prospect, GOOD_SLOTS)
        tampered = good.body.replace(
            PRODUCT_URL, PRODUCT_URL + " and https://www.omniveer.com"
        )
        errors = validate_email_draft(good.subject, tampered, prospect, GOOD_SLOTS)
        assert any("exactly one promotional link" in e for e in errors)

    def test_linkedin_injection_is_rejected(self):
        prospect = make_prospect(email="info@acmeduct.com")
        good = assemble_email(prospect, GOOD_SLOTS)
        tampered = good.body.replace(
            PRODUCT_URL, "https://www.linkedin.com/company/omniveer/"
        )
        errors = validate_email_draft(good.subject, tampered, prospect, GOOD_SLOTS)
        assert any("LinkedIn" in e for e in errors)

    def test_founder_led_signature_and_low_pressure_close(self):
        draft = self.all_golden_bodies()["email"]
        assert draft.body.rstrip().endswith(SIGNATURE)
        assert (
            "Reply to this email if you'd like one of the five pilot spots, "
            "or book a demo through the page." in draft.body
        )
        # no urgency or guarantee language
        for banned in ("first come", "this week only", "guarantee"):
            assert banned not in draft.body.lower()


class TestOpenRouterCall:
    @respx.mock
    def test_slots_requested_single_shot(self):
        route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(GOOD_SLOTS)}}]},
            )
        )
        slots = request_slots(make_prospect(), settings())
        assert slots == GOOD_SLOTS
        assert route.call_count == 1
        request_payload = json.loads(route.calls[0].request.content)
        assert request_payload["model"] == "test/model"
        assert request_payload["response_format"] == {"type": "json_object"}
        user_content = json.loads(request_payload["messages"][1]["content"])
        assert user_content["name_or_team"] == "Acme Duct Cleaning team"

    @respx.mock
    def test_api_failure_raises_draft_error(self):
        respx.post("https://openrouter.ai/api/v1/chat/completions").mock(return_value=httpx.Response(500))
        with pytest.raises(DraftError, match="OpenRouter call failed"):
            request_slots(make_prospect(), settings())

    @respx.mock
    def test_code_fenced_json_content_parsed(self):
        # Some providers (e.g. Bedrock via OpenRouter) ignore response_format
        fenced = "```json\n" + json.dumps(GOOD_SLOTS) + "\n```"
        respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": fenced}}]})
        )
        assert request_slots(make_prospect(), settings()) == GOOD_SLOTS

    @respx.mock
    def test_invalid_json_content_raises_draft_error(self):
        respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})
        )
        with pytest.raises(DraftError):
            request_slots(make_prospect(), settings())

    @respx.mock
    def test_build_email_draft_end_to_end(self):
        respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(GOOD_SLOTS)}}]}
            )
        )
        draft = build_email_draft(make_prospect(email="info@acmeduct.com"), settings())
        assert draft.validated
        assert draft.model == "test/model"


class TestHelpers:
    def test_generic_inbox_detection(self):
        assert is_generic_inbox("info@x.com")
        assert is_generic_inbox("OFFICE@x.com")
        assert not is_generic_inbox("scott@x.com")
        assert not is_generic_inbox(None)

    def test_expected_greeting(self):
        prospect = make_prospect()
        assert expected_greeting(prospect) == "Acme Duct Cleaning team"
        prospect.name_used = "Scott"
        assert expected_greeting(prospect) == "Scott"
