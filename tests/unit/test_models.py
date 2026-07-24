from prospector.models import (
    OFFER_CITE,
    AgentResponse,
    Channel,
    Company,
    Confidence,
    Draft,
    DraftBlock,
    Evidence,
    EvidenceKind,
    EvidenceRef,
    FbSignal,
    Prospect,
    ResearchResult,
    RunSummary,
    Variant,
)


def test_enum_values_match_product_vocab():
    # §6 frontmatter vocabulary
    assert {c.value for c in Channel} == {"email", "messenger"}
    assert {c.value for c in Confidence} == {"high", "medium", "none"}
    assert {s.value for s in FbSignal} == {"strong", "weak", "none"}
    assert {v.value for v in Variant} == {"email_fb", "email_agnostic", "messenger_dm"}


def test_construction_and_defaults():
    company = Company(company="Acme Duct", email="info@acme.com", raw_email_field="info@acme.com", row_num=1)
    research = ResearchResult(website="https://acme.com")
    prospect = Prospect(company=company, research=research)
    assert prospect.name_used == "team"
    assert prospect.name_confidence is Confidence.NONE
    assert prospect.fb_signal is FbSignal.NONE
    assert prospect.variant is Variant.EMAIL_AGNOSTIC
    assert prospect.angle == "offer-led"
    assert not prospect.needs_review
    assert company.facebook_url is None


def test_evidence_carries_source():
    ev = Evidence(kind=EvidenceKind.ABOUT_PAGE, value="Scott Brown", source="https://acme.com/about", excerpt="Owner Scott Brown founded...")
    assert ev.kind is EvidenceKind.ABOUT_PAGE
    assert ev.source.startswith("https://")


def test_draft_defaults_valid():
    d = Draft(subject="s", body="b", model="m")
    assert d.validated and d.validation_errors == []


def test_run_summary_reconciliation():
    s = RunSummary(total=5, processed=4, failed=1)
    assert s.reconciles()
    s.failed = 2
    assert not s.reconciles()


# --- Agentic drafting (006) -------------------------------------------------


def test_draft_defaults_to_template_source():
    """Pre-006 construction sites keep their meaning: template unless stated."""
    d = Draft(subject="s", body="b", model="m")
    assert d.source == "template"
    assert Draft(subject="s", body="b", model="m", source="agent").source == "agent"


def test_evidence_ref_carries_id_and_provenance():
    ref = EvidenceRef(
        id="about_page_1",
        kind="about_page",
        value="Scott Brenner",
        source="https://acme.com/about",
        excerpt="Owner Scott Brenner founded Acme in 2003",
    )
    assert ref.id == "about_page_1"
    assert ref.source.startswith("https://")


def test_draft_block_cites_default_empty():
    """An empty cites list is representable so the validator can REJECT it."""
    assert DraftBlock(text="hello").cites == []
    assert DraftBlock(text="hi", cites=["hook_source_1"]).cites == ["hook_source_1"]


def test_offer_cite_is_reserved_constant():
    assert OFFER_CITE == "offer"


def test_agent_response_shape():
    r = AgentResponse(subject="Free pilot for Acme", blocks=[DraftBlock("x", ["offer"])])
    assert r.subject and len(r.blocks) == 1


def test_run_summary_drafting_path_counters_default_zero():
    s = RunSummary(total=1)
    assert s.drafted_agent == 0 and s.drafted_template == 0
    assert s.fallback_reasons == []


def test_drafting_counters_need_not_sum_to_processed():
    """messenger / --no-llm / frozen notes are drafted by neither path."""
    s = RunSummary(total=3, processed=3, drafted_agent=1, drafted_template=1)
    assert s.reconciles()
    assert s.drafted_agent + s.drafted_template < s.processed
