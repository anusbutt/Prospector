"""The locked template always answers (006 US2, FR-315..FR-320).

Every way the agent path can fail must land on a usable, honest draft. A run
with the model entirely unavailable must reproduce today's output (SC-305).
"""

import json

import httpx
import pytest
import respx

from prospector.agent_draft import draft_email
from prospector.config import Settings
from prospector.draft import PRODUCT_URL, SIGNATURE
from prospector.instructions import InstructionSet
from prospector.models import (
    Company,
    Evidence,
    EvidenceKind,
    Prospect,
    ResearchResult,
)

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

TEMPLATE_SLOTS = json.dumps({"greeting_name": "Acme Duct Cleaning team", "subject_company": "Acme Duct"})


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
    return InstructionSet(text="INSTRUCTIONS", sources=["agent/IDENTITY.md"])


def make_prospect(*, with_evidence=True) -> Prospect:
    company = Company(
        company="Acme Duct Cleaning",
        email="scott@acmeduct.com",
        raw_email_field="scott@acmeduct.com",
        city="Dallas",
    )
    research = ResearchResult(website="https://acmeduct.com", city="Dallas", hook="22 years in business")
    if with_evidence:
        research.hook_evidence = Evidence(
            kind=EvidenceKind.HOOK_SOURCE,
            value="22 years in business",
            source="https://acmeduct.com/about",
            excerpt="serving Dallas for 22 years",
        )
    return Prospect(company=company, research=research)


def agent_reply(blocks) -> dict:
    return {"choices": [{"message": {"content": json.dumps({"subject": "Free 10-day pilot for Acme Duct", "blocks": blocks})}}]}


def template_reply() -> dict:
    return {"choices": [{"message": {"content": TEMPLATE_SLOTS}}]}


VALID_BLOCKS = [
    {"text": "Twenty-two years is a long time in this trade.", "cites": ["hook_source_1"]},
    {"text": "I'm giving 5 duct-cleaning companies a free 10-day pilot.", "cites": ["offer"]},
    {"text": f"Short demo here: {PRODUCT_URL}", "cites": ["offer"]},
    {"text": "Want one of the five spots?", "cites": ["offer"]},
]


class TestHappyPath:
    @respx.mock
    def test_valid_agent_response_is_used(self, settings, instructions):
        respx.post(OPENROUTER).mock(return_value=httpx.Response(200, json=agent_reply(VALID_BLOCKS)))
        draft = draft_email(make_prospect(), settings, instructions)
        assert draft.source == "agent"
        assert draft.validated
        assert "Twenty-two years" in draft.body
        assert draft.body.rstrip().endswith(SIGNATURE)


class TestNeverRaises:
    """G1: every failure path returns a usable Draft, never an exception."""

    @respx.mock
    def test_transport_error(self, settings, instructions):
        respx.post(OPENROUTER).mock(side_effect=httpx.ConnectError("boom"))
        draft = draft_email(make_prospect(), settings, instructions)
        assert draft.source == "template"
        assert any("agent call failed" in e for e in draft.validation_errors)

    @respx.mock
    def test_http_500(self, settings, instructions):
        route = respx.post(OPENROUTER)
        route.side_effect = [httpx.Response(500, text="upstream down"), httpx.Response(200, json=template_reply())]
        draft = draft_email(make_prospect(), settings, instructions)
        assert draft.source == "template"

    @respx.mock
    def test_malformed_json(self, settings, instructions):
        route = respx.post(OPENROUTER)
        route.side_effect = [
            httpx.Response(200, json={"choices": [{"message": {"content": "not json at all"}}]}),
            httpx.Response(200, json=template_reply()),
        ]
        draft = draft_email(make_prospect(), settings, instructions)
        assert draft.source == "template"
        assert any("malformed" in e for e in draft.validation_errors)

    @respx.mock
    def test_bad_block_count(self, settings, instructions):
        route = respx.post(OPENROUTER)
        route.side_effect = [
            httpx.Response(200, json=agent_reply(VALID_BLOCKS * 3)),  # 12 blocks
            httpx.Response(200, json=template_reply()),
        ]
        draft = draft_email(make_prospect(), settings, instructions)
        assert draft.source == "template"
        assert any("expected 3-6" in e for e in draft.validation_errors)

    @respx.mock
    def test_citation_failure(self, settings, instructions):
        bad = [dict(b) for b in VALID_BLOCKS]
        bad[0] = {"text": "You have been at this 22 years.", "cites": ["about_page_9"]}
        route = respx.post(OPENROUTER)
        route.side_effect = [
            httpx.Response(200, json=agent_reply(bad)),
            httpx.Response(200, json=template_reply()),
        ]
        draft = draft_email(make_prospect(), settings, instructions)
        assert draft.source == "template"
        assert any("unknown id 'about_page_9'" in e for e in draft.validation_errors)

    @respx.mock
    def test_retained_check_failure(self, settings, instructions):
        bad = [dict(b) for b in VALID_BLOCKS]
        bad[1] = {"text": "Your ads deserve better follow-up.", "cites": ["offer"]}
        route = respx.post(OPENROUTER)
        route.side_effect = [
            httpx.Response(200, json=agent_reply(bad)),
            httpx.Response(200, json=template_reply()),
        ]
        draft = draft_email(make_prospect(), settings, instructions)
        assert draft.source == "template"
        assert any("ad-running claim" in e for e in draft.validation_errors)

    @respx.mock
    def test_never_raises_across_all_modes(self, settings, instructions):
        """Parametrized safety net: nothing here may propagate."""
        for side_effect in (
            httpx.ConnectError("x"),
            httpx.ReadTimeout("x"),
            httpx.Response(401, text="unauthorized"),
            httpx.Response(200, text="{}"),
        ):
            respx.post(OPENROUTER).mock(side_effect=[side_effect, httpx.Response(200, json=template_reply())])
            draft = draft_email(make_prospect(), settings, instructions)
            assert draft is not None


class TestNoRequestWhenPointless:
    @respx.mock
    def test_no_evidence_no_request(self, settings, instructions):
        """G3/FR-317: nothing to cite means the agent call is pure cost."""
        route = respx.post(OPENROUTER).mock(return_value=httpx.Response(200, json=template_reply()))
        draft = draft_email(make_prospect(with_evidence=False), settings, instructions)
        assert draft.source == "template"
        assert any("no evidence to cite" in e for e in draft.validation_errors)
        # exactly one call: the template's own slot fill, never the agent's
        assert route.call_count == 1

    @respx.mock
    def test_no_instructions_no_agent_request(self, settings):
        route = respx.post(OPENROUTER).mock(return_value=httpx.Response(200, json=template_reply()))
        draft = draft_email(make_prospect(), settings, instructions=None)
        assert draft.source == "template"
        assert route.call_count == 1


class TestTotalOutage:
    @respx.mock
    def test_total_outage_matches_template_output(self, settings, instructions):
        """SC-305: with the model unavailable, output equals today's behavior.

        Today, an outage means the template's slot call also fails and the note
        records that no draft was produced. Equivalence with today is the bar —
        offline drafting was never the promise."""
        respx.post(OPENROUTER).mock(side_effect=httpx.ConnectError("network unreachable"))
        draft = draft_email(make_prospect(), settings, instructions)
        assert draft.source == "template"
        assert not draft.validated
        assert any("agent call failed" in e for e in draft.validation_errors)
        assert any("template fallback failed" in e for e in draft.validation_errors)

    @respx.mock
    def test_template_still_works_when_only_agent_output_is_bad(self, settings, instructions):
        """The realistic outage: model reachable, agent output unusable."""
        route = respx.post(OPENROUTER)
        route.side_effect = [
            httpx.Response(200, json=agent_reply([{"text": "x", "cites": []}] * 4)),
            httpx.Response(200, json=template_reply()),
        ]
        draft = draft_email(make_prospect(), settings, instructions)
        assert draft.source == "template"
        assert draft.validated, "template copy itself must still be valid"
        assert "free 10-day pilot" in draft.body
