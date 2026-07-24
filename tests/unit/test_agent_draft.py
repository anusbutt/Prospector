"""Agent drafting: evidence ids, payload, parsing, assembly, validation (006 US1).

The validator is the whole honesty guarantee once the model writes prose, so
these tests are adversarial by design: each one is an attempt to get a
fabricated or uncited claim into a note.
"""

import json

import httpx
import pytest
import respx

from prospector.agent_draft import (
    validate_channel_claims,
    MAX_BLOCKS,
    MIN_BLOCKS,
    AgentDraftError,
    assemble_body,
    build_evidence_refs,
    build_payload,
    draft_email,
    parse_response,
    request_draft,
    validate_citations,
    validate_retained,
)
from prospector.config import Settings
from prospector.draft import PRODUCT_URL, SIGNATURE
from prospector.instructions import InstructionSet
from prospector.models import (
    AgentResponse,
    Company,
    Confidence,
    DraftBlock,
    Evidence,
    EvidenceKind,
    FbSignal,
    Prospect,
    ResearchResult,
)

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"


@pytest.fixture
def settings():
    return Settings(
        openrouter_key="test-key",
        openrouter_model="test/model",
        places_key=None,
        hunter_key=None,
        vault_dir="/tmp/unused",
    )


@pytest.fixture
def instructions():
    return InstructionSet(text="SYSTEM INSTRUCTIONS BODY", sources=["agent/IDENTITY.md"])


def make_prospect(*, name_used="team", city="Dallas", hook="22 years in business") -> Prospect:
    company = Company(
        company="Acme Duct Cleaning",
        email="scott@acmeduct.com",
        raw_email_field="scott@acmeduct.com",
        city=city,
    )
    research = ResearchResult(website="https://acmeduct.com", city=city, hook=hook)
    research.name_evidence.append(
        Evidence(
            kind=EvidenceKind.ABOUT_PAGE,
            value="Scott Brenner",
            source="https://acmeduct.com/about",
            excerpt="Owner Scott Brenner founded Acme in 2003",
        )
    )
    research.fb_evidence.append(
        Evidence(
            kind=EvidenceKind.FB_LINK,
            value="https://facebook.com/acmeduct",
            source="https://acmeduct.com",
            excerpt="site links to a Facebook page",
        )
    )
    research.hook_evidence = Evidence(
        kind=EvidenceKind.HOOK_SOURCE,
        value=hook,
        source="https://acmeduct.com/about",
        excerpt="serving Dallas for 22 years",
    )
    prospect = Prospect(company=company, research=research)
    prospect.name_used = name_used
    if name_used != "team":
        prospect.name_confidence = Confidence.HIGH
    return prospect


def good_response() -> AgentResponse:
    return AgentResponse(
        subject="Free 10-day pilot for Acme Duct",
        blocks=[
            DraftBlock("Twenty-two years around Dallas is a long time.", ["hook_source_1"]),
            DraftBlock(
                "I'm giving 5 duct-cleaning companies a free 10-day pilot. I set it up.",
                ["offer"],
            ),
            DraftBlock(f"Short demo here: {PRODUCT_URL}", ["offer"]),
            DraftBlock("Want one of the five spots?", ["offer"]),
        ],
    )


# --- T023 evidence ids ------------------------------------------------------


class TestEvidenceRefs:
    def test_ids_are_kind_and_ordinal(self):
        refs = build_evidence_refs(make_prospect().research)
        assert [r.id for r in refs] == ["about_page_1", "fb_link_1", "hook_source_1"]

    def test_evidence_ids_stable(self):
        """Identical research must yield identical ids (byte-idempotency)."""
        a = build_evidence_refs(make_prospect().research)
        b = build_evidence_refs(make_prospect().research)
        assert [r.id for r in a] == [r.id for r in b]

    def test_ordinals_increment_per_kind(self):
        research = make_prospect().research
        research.name_evidence.append(
            Evidence(kind=EvidenceKind.ABOUT_PAGE, value="Dana Reed", source="x", excerpt="y")
        )
        assert [r.id for r in build_evidence_refs(research)][:2] == ["about_page_1", "about_page_2"]

    def test_empty_research_yields_no_refs(self):
        assert build_evidence_refs(ResearchResult()) == []


# --- T024 payload -----------------------------------------------------------


class TestPayload:
    def test_payload_excludes_html(self):
        """FR-302: only extracted fields, never raw fetched page content."""
        prospect = make_prospect()
        payload = build_payload(prospect, build_evidence_refs(prospect.research))
        blob = json.dumps(payload)
        assert "<html" not in blob and "<body" not in blob and "<div" not in blob
        assert set(payload["evidence"][0]) == {"id", "kind", "value", "source", "excerpt"}

    def test_greeting_is_resolved_by_code_not_asked_for(self):
        payload = build_payload(make_prospect(name_used="Scott"), [])
        assert payload["greeting"] == "Hi Scott,"

    def test_offer_id_is_advertised(self):
        assert build_payload(make_prospect(), [])["offer_id"] == "offer"


# --- T025/T026 request and parsing -----------------------------------------


class TestRequestAndParse:
    @respx.mock
    def test_single_request(self, settings, instructions):
        route = respx.post(OPENROUTER).mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps({
                    "subject": "s",
                    "blocks": [{"text": "a", "cites": ["offer"]}] * 3,
                })}}]},
            )
        )
        prospect = make_prospect()
        request_draft(prospect, settings, instructions, build_evidence_refs(prospect.research))
        assert route.call_count == 1

    @respx.mock
    def test_instructions_reach_system_message(self, settings, instructions):
        """An edit to an instruction file must not silently stop taking effect."""
        route = respx.post(OPENROUTER).mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps({
                    "subject": "s",
                    "blocks": [{"text": "a", "cites": ["offer"]}] * 3,
                })}}]},
            )
        )
        prospect = make_prospect()
        request_draft(prospect, settings, instructions, build_evidence_refs(prospect.research))
        sent = json.loads(route.calls[0].request.content)
        assert sent["messages"][0]["content"] == "SYSTEM INSTRUCTIONS BODY"

    def test_parse_rejects_non_json(self):
        with pytest.raises(AgentDraftError, match="not JSON"):
            parse_response("this is not json")

    def test_parse_rejects_non_object(self):
        with pytest.raises(AgentDraftError, match="not a JSON object"):
            parse_response("[1, 2, 3]")

    def test_parse_rejects_missing_subject(self):
        with pytest.raises(AgentDraftError, match="missing subject"):
            parse_response(json.dumps({"blocks": [{"text": "a", "cites": ["offer"]}] * 3}))

    @pytest.mark.parametrize("count", [0, 1, 2, 7, 12])
    def test_parse_rejects_bad_block_count(self, count):
        payload = {"subject": "s", "blocks": [{"text": "a", "cites": ["offer"]}] * count}
        with pytest.raises(AgentDraftError, match="blocks"):
            parse_response(json.dumps(payload))

    @pytest.mark.parametrize("count", [MIN_BLOCKS, MAX_BLOCKS])
    def test_parse_accepts_boundary_counts(self, count):
        payload = {"subject": "s", "blocks": [{"text": "a", "cites": ["offer"]}] * count}
        assert len(parse_response(json.dumps(payload)).blocks) == count

    def test_parse_rejects_block_without_text(self):
        payload = {"subject": "s", "blocks": [{"cites": ["offer"]}] * 3}
        with pytest.raises(AgentDraftError, match="no text"):
            parse_response(json.dumps(payload))

    def test_parse_rejects_cites_not_a_list(self):
        payload = {"subject": "s", "blocks": [{"text": "a", "cites": "offer"}] * 3}
        with pytest.raises(AgentDraftError, match="list of strings"):
            parse_response(json.dumps(payload))

    def test_parse_tolerates_code_fences(self):
        inner = json.dumps({"subject": "s", "blocks": [{"text": "a", "cites": ["offer"]}] * 3})
        assert parse_response(f"```json\n{inner}\n```").subject == "s"


# --- T027 assembly ----------------------------------------------------------


class TestAssembly:
    def test_assembly_golden(self):
        body = assemble_body(make_prospect(name_used="Scott"), good_response())
        assert body == (
            "Hi Scott,\n\n"
            "Twenty-two years around Dallas is a long time.\n\n"
            "I'm giving 5 duct-cleaning companies a free 10-day pilot. I set it up.\n\n"
            f"Short demo here: {PRODUCT_URL}\n\n"
            "Want one of the five spots?\n\n"
            f"{SIGNATURE}"
        )

    def test_greeting_and_signature_come_from_code(self):
        body = assemble_body(make_prospect(), good_response())
        assert body.startswith("Hi Acme Duct Cleaning team,")
        assert body.rstrip().endswith(SIGNATURE)


# --- T028-T031 citation rules ----------------------------------------------


class TestCitationRules:
    def refs(self, prospect):
        return build_evidence_refs(prospect.research)

    def test_valid_response_passes(self):
        p = make_prospect()
        assert validate_citations(good_response(), p, self.refs(p)) == []

    def test_v1_empty_cites_rejected(self):
        p = make_prospect()
        response = good_response()
        response.blocks[0].cites = []
        errors = validate_citations(response, p, self.refs(p))
        assert any("no citation" in e for e in errors)

    def test_v2_unknown_id_rejected(self):
        p = make_prospect()
        response = good_response()
        response.blocks[0].cites = ["about_page_9"]
        errors = validate_citations(response, p, self.refs(p))
        assert any("unknown id 'about_page_9'" in e for e in errors)

    def test_v2_other_company_id_rejected(self):
        p = make_prospect()
        response = good_response()
        response.blocks[0].cites = ["team_page_1"]  # real kind, not captured here
        assert any("unknown id" in e for e in validate_citations(response, p, self.refs(p)))

    def test_v3_offer_only_block_with_company_name_rejected(self):
        """The anti-laundering rule: the one loophole this system exists to close."""
        p = make_prospect()
        response = good_response()
        response.blocks[1] = DraftBlock(
            "Acme Duct Cleaning would get every lead answered in seconds.", ["offer"]
        )
        errors = validate_citations(response, p, self.refs(p))
        assert any("mentions the prospect" in e for e in errors)

    @pytest.mark.parametrize(
        "sneaky",
        [
            "Businesses in Dallas lose leads overnight.",  # city
            "Scott, this would answer every message.",  # owner name
            "After 22 years in business you know the drill.",  # hook
            "Acme Duct Cleaning is exactly who this is for.",  # company name
        ],
    )
    def test_v3_catches_prospect_leakage_variants(self, sneaky):
        p = make_prospect(name_used="Scott")
        response = good_response()
        response.blocks[1] = DraftBlock(sneaky, ["offer"])
        errors = validate_citations(response, p, self.refs(p))
        assert any("mentions the prospect" in e for e in errors), sneaky

    def test_v3_allows_trade_words_in_offer_blocks(self):
        """'5 duct-cleaning companies' is the offer's own words, not leakage."""
        p = make_prospect()
        response = good_response()
        response.blocks[1] = DraftBlock(
            "I'm giving 5 duct cleaning companies a free 10-day pilot of the air duct tool.",
            ["offer"],
        )
        errors = validate_citations(response, p, self.refs(p))
        assert not any("mentions the prospect" in e for e in errors)

    def test_v4_all_offer_falls_back(self):
        p = make_prospect()
        response = good_response()
        response.blocks[0].cites = ["offer"]
        response.blocks[0].text = "A short note about the pilot."
        errors = validate_citations(response, p, self.refs(p))
        assert any("not personalized" in e for e in errors)

    def test_all_reasons_collected(self):
        """FR-314: no short-circuiting — the operator sees every reason."""
        p = make_prospect()
        response = good_response()
        response.blocks[0].cites = []
        response.blocks[1].cites = ["bogus_9"]
        errors = validate_citations(response, p, self.refs(p))
        assert len(errors) >= 2
        assert any("no citation" in e for e in errors)
        assert any("unknown id" in e for e in errors)


# --- T032 retained rules ----------------------------------------------------


class TestRetainedRules:
    def body_for(self, prospect, response=None):
        return assemble_body(prospect, response or good_response())

    def test_retained_valid_body_passes(self):
        p = make_prospect()
        assert validate_retained("Free 10-day pilot for Acme Duct", self.body_for(p), p) == []

    def test_retained_rejects_ad_claim(self):
        p = make_prospect()
        response = good_response()
        response.blocks[0].text = "Your ads are bringing in leads you cannot answer."
        errors = validate_retained("Acme Duct", self.body_for(p, response), p)
        assert any("ad-running claim" in e for e in errors)

    def test_retained_rejects_second_link(self):
        p = make_prospect()
        response = good_response()
        response.blocks[3].text = "Book here: https://cal.com/anas"
        errors = validate_retained("Acme Duct", self.body_for(p, response), p)
        assert any("exactly one promotional link" in e for e in errors)

    def test_retained_rejects_zero_links(self):
        p = make_prospect()
        response = good_response()
        response.blocks[2].text = "It books the job for you."
        errors = validate_retained("Acme Duct", self.body_for(p, response), p)
        assert any("exactly one promotional link" in e for e in errors)

    def test_retained_rejects_linkedin(self):
        p = make_prospect()
        response = good_response()
        response.blocks[3].text = "More: https://www.linkedin.com/company/omniveer/"
        errors = validate_retained("Acme Duct", self.body_for(p, response), p)
        assert any("LinkedIn" in e for e in errors)

    def test_retained_rejects_unfilled_slot(self):
        p = make_prospect()
        response = good_response()
        response.blocks[0].text = "Hello [Company Name], quick note."
        errors = validate_retained("Acme Duct", self.body_for(p, response), p)
        assert any("[slot]" in e for e in errors)

    def test_retained_rejects_missing_signature(self):
        p = make_prospect()
        body = self.body_for(p).replace(SIGNATURE, "Cheers, Anas")
        assert any("signature" in e for e in validate_retained("Acme Duct", body, p))

    def test_retained_rejects_wrong_greeting(self):
        p = make_prospect()
        body = self.body_for(p).replace("Hi Acme Duct Cleaning team,", "Hi Bob,")
        assert any("greeting must be" in e for e in validate_retained("Acme Duct", body, p))

    def test_retained_rejects_subject_naming_a_different_company(self):
        """Revised rule (2026-07-20): originality is fine, invention is not."""
        p = make_prospect()
        errors = validate_retained("Quote for Zerorez Industries", self.body_for(p), p)
        assert any("shares no word with the company name" in e for e in errors)

    def test_retained_allows_offer_vocabulary_in_subject(self):
        p = make_prospect()
        assert validate_retained("Free 10-day pilot for Acme Duct", self.body_for(p), p) == []

    def test_retained_name_must_trace_to_evidence(self):
        p = make_prospect(name_used="Marcus")  # not in any evidence record
        errors = validate_retained("Acme Duct", self.body_for(p), p)
        assert any("does not trace" in e for e in errors)

    def test_retained_accepts_sourced_name(self):
        p = make_prospect(name_used="Scott")  # matches about_page_1 evidence
        assert not any("does not trace" in e for e in validate_retained("Acme Duct", self.body_for(p), p))


# --- V13 possessive-channel guard (added after the first live run) ----------


class TestChannelClaims:
    """Regression suite built from real output.

    The first three live drafts produced "your Facebook page" in 2 of 2 agent
    drafts at fb_signal weak, citing only `offer`. V3 could not see it: the
    phrase carries no company, city, name, or hook token.
    """

    def refs(self, prospect):
        return build_evidence_refs(prospect.research)

    def fb_prospect(self, signal):
        p = make_prospect()
        p.fb_signal = signal
        return p

    @pytest.mark.parametrize(
        "text",
        [
            # verbatim from the All Pro live draft
            "It answers your Facebook page messages in seconds, day or night.",
            # verbatim from the Dr. Air live draft
            "When someone messages your Facebook page at 9pm, that is the lead you cannot miss.",
            "It answers your page messages in seconds.",
            "It watches your inbox around the clock.",
            "It replies in your Messenger within seconds.",
            "It clears your DMs overnight.",
        ],
    )
    def test_possessive_channel_claim_rejected_at_weak(self, text):
        p = self.fb_prospect(FbSignal.WEAK)
        response = good_response()
        response.blocks[1] = DraftBlock(text, ["offer"])
        errors = validate_channel_claims(response, p)
        assert any("claims the prospect's own channel" in e for e in errors), text

    def test_possessive_channel_claim_rejected_at_none(self):
        p = self.fb_prospect(FbSignal.NONE)
        response = good_response()
        response.blocks[1] = DraftBlock("It answers your Facebook page messages.", ["offer"])
        assert validate_channel_claims(response, p)

    def test_product_phrasing_is_always_allowed(self):
        """Describing the product's capability is a product fact, at any signal."""
        for signal in (FbSignal.NONE, FbSignal.WEAK, FbSignal.STRONG):
            p = self.fb_prospect(signal)
            response = good_response()
            response.blocks[1] = DraftBlock(
                "It answers Facebook page messages in seconds, day or night.", ["offer"]
            )
            assert validate_channel_claims(response, p) == [], signal

    def test_strong_signal_still_needs_the_citation(self):
        p = self.fb_prospect(FbSignal.STRONG)
        response = good_response()
        response.blocks[1] = DraftBlock("It answers your Facebook page messages.", ["offer"])
        errors = validate_channel_claims(response, p)
        assert any("without citing the observed fb_* signal" in e for e in errors)

    def test_strong_signal_with_fb_citation_is_allowed(self):
        p = self.fb_prospect(FbSignal.STRONG)
        response = good_response()
        response.blocks[1] = DraftBlock("It answers your Facebook page messages.", ["fb_link_1"])
        assert validate_channel_claims(response, p) == []

    def test_live_all_pro_draft_would_now_fall_back(self):
        """End-to-end proof the escaped draft is caught by the full validator."""
        p = self.fb_prospect(FbSignal.WEAK)
        response = AgentResponse(
            subject="All Pro Duct - 10-day pilot",
            blocks=[
                DraftBlock("Twenty years cleaning ducts means you have built this on referrals.", ["hook_source_1"]),
                DraftBlock("I'm giving 5 duct-cleaning companies a free 10-day pilot.", ["offer"]),
                DraftBlock(
                    f"It answers your Facebook page messages in seconds. Short demo here: {PRODUCT_URL}",
                    ["offer"],
                ),
                DraftBlock("Want one of the five spots?", ["offer"]),
            ],
        )
        from prospector.agent_draft import validate

        body = assemble_body(p, response)
        errors = validate(response, body, p, self.refs(p))
        assert any("claims the prospect's own channel" in e for e in errors)


# --- Revised subject rule ---------------------------------------------------


class TestSubjectRule:
    def body_for(self, prospect):
        return assemble_body(prospect, good_response())

    @pytest.mark.parametrize(
        "subject",
        [
            "Free 10-day pilot for Acme Duct",
            "Acme Duct - 10-day pilot",
            "Acme's inbox that answers itself",   # the line that used to be rejected
            "A quieter phone for Acme Duct Cleaning",
        ],
    )
    def test_creative_subjects_are_allowed(self, subject):
        p = make_prospect()
        errors = validate_retained(subject, self.body_for(p), p)
        assert errors == [], f"{subject!r} -> {errors}"

    def test_subject_sharing_no_company_word_is_rejected(self):
        p = make_prospect()
        errors = validate_retained("A quick question about your business", self.body_for(p), p)
        assert any("shares no word with the company name" in e for e in errors)

    def test_empty_subject_rejected(self):
        p = make_prospect()
        assert any("empty" in e for e in validate_retained("   ", self.body_for(p), p))

    def test_overlong_subject_rejected(self):
        p = make_prospect()
        errors = validate_retained("Acme Duct " + "x" * 100, self.body_for(p), p)
        assert any("max 90" in e for e in errors)

    def test_curly_apostrophe_company_matches_straight_subject(self):
        """Regression: 'Drew’s' (scraped) vs "Drew's" (model) must agree."""
        p = make_prospect()
        p.company.company = "Drew’s dryer vent cleaning"
        p.name_used = "team"
        body = assemble_body(p, good_response())
        errors = validate_retained("Drew's inbox that answers itself", body, p)
        assert not any("shares no word" in e for e in errors)


class TestProspectTokenFloor:
    """Junk short values must not turn ordinary prose into a false positive.

    Live run (2026-07-21): extraction captured `city: We` from "Serving We
    Clean Ducts...", so V3 rejected a valid draft for containing the word "we".
    Extraction is fixed at source; this is the guard against the next one.
    """

    def test_short_junk_city_is_not_a_prospect_token(self):
        from prospector.agent_draft import _prospect_tokens

        p = make_prospect()
        p.research.city = "We"
        assert "we" not in _prospect_tokens(p)

    def test_real_city_is_still_a_prospect_token(self):
        from prospector.agent_draft import _prospect_tokens

        p = make_prospect(city="Dallas")
        p.research.city = "Dallas"
        assert "dallas" in _prospect_tokens(p)

    def test_multiword_value_kept_even_when_short_words(self):
        from prospector.agent_draft import _prospect_tokens

        p = make_prospect()
        p.research.hook = "We service area"
        assert "we service area" in _prospect_tokens(p)

    def test_offer_block_with_the_word_we_is_no_longer_rejected(self):
        p = make_prospect()
        p.research.city = "We"
        response = good_response()
        response.blocks[1] = DraftBlock(
            "We set the whole thing up for you, start to finish.", ["offer"]
        )
        errors = validate_citations(response, p, build_evidence_refs(p.research))
        assert not any("mentions the prospect" in e for e in errors)
