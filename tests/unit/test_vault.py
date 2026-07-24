from prospector.models import Company, Confidence, Draft, FbSignal, Prospect, ResearchResult
from prospector.vault import (
    assign_slugs,
    build_research_markdown,
    display_website,
    draft_markdown_for,
    merge_notes,
    parse_note,
    render_note,
    slugify,
    upsert_note,
    write_note,
)


def make_prospect(**company_kwargs) -> Prospect:
    defaults = dict(company="Boston Air Duct Cleaning", email="info@bostonairduct.com", raw_email_field="info@bostonairduct.com")
    defaults.update(company_kwargs)
    company = Company(**defaults)
    research = ResearchResult(website="https://bostonairduct.com", hook="Boston service area")
    return Prospect(company=company, research=research)


class TestSlugify:
    def test_basic(self):
        assert slugify("Boston Air Duct Cleaning") == "boston-air-duct-cleaning"

    def test_unsafe_characters_sanitized(self):
        assert slugify("A/B: Ducts & Vents, Inc. (Boston!)") == "a-b-ducts-vents-inc-boston"

    def test_unicode_folded(self):
        assert slugify("Ducts Café São") == "ducts-cafe-sao"

    def test_stable_across_calls(self):
        assert slugify("Acme Duct") == slugify("Acme Duct")

    def test_length_capped(self):
        assert len(slugify("x" * 300)) <= 80


class TestAssignSlugs:
    def test_no_collision(self):
        companies = [
            Company(company="Acme Duct", email="a@acme.com"),
            Company(company="Beta Air", email="b@beta.com"),
        ]
        assign_slugs(companies)
        assert [c.slug for c in companies] == ["acme-duct", "beta-air"]

    def test_collision_disambiguated_by_city(self):
        companies = [
            Company(company="Acme Duct", email="a@acme1.com", city="Boston"),
            Company(company="Acme Duct", email="a@acme2.com", city="Denver"),
        ]
        assign_slugs(companies)
        assert companies[0].slug == "acme-duct"
        assert companies[1].slug == "acme-duct-denver"

    def test_collision_falls_back_to_domain_then_number(self):
        companies = [
            Company(company="Acme Duct", email="a@acme1.com"),
            Company(company="Acme Duct", email="a@acme2.com"),
            Company(company="Acme Duct", email=None),
        ]
        assign_slugs(companies)
        assert companies[0].slug == "acme-duct"
        assert companies[1].slug == "acme-duct-acme2-com"
        assert companies[2].slug == "acme-duct-2"

    def test_deterministic_by_input_order(self):
        a = [Company(company="X Co", email=None), Company(company="X Co", email=None)]
        b = [Company(company="X Co", email=None), Company(company="X Co", email=None)]
        assign_slugs(a)
        assign_slugs(b)
        assert [c.slug for c in a] == [c.slug for c in b]


class TestRenderNote:
    def test_canonical_bytes_stable(self):
        p1 = make_prospect()
        p2 = make_prospect()
        note1 = render_note(p1, "**Subject:** s\n\nbody", "- Owner name: not found")
        note2 = render_note(p2, "**Subject:** s\n\nbody", "- Owner name: not found")
        assert note1 == note2

    def test_golden_structure_matches_contract_example(self):
        prospect = make_prospect()
        note = render_note(
            prospect,
            "**Subject:** Free 10-day pilot for Boston Air Duct\n\nHi Boston Air Duct team,\n...full assembled body...",
            "- Owner name: not found (no /about page)",
        )
        lines = note.splitlines()
        assert lines[0] == "---"
        # Frontmatter keys in contract order (contracts/note-format.md)
        expected_prefixes = [
            "company: Boston Air Duct Cleaning",
            "email: info@bostonairduct.com",
            "channel: email",
            "status: to-send",
            "name_used: team",
            "name_confidence: none",
            "name_candidate:",
            "hook: Boston service area",
            "website: bostonairduct.com",
            "angle: offer-led",
            "fb_signal: none",
            "duplicate_of:",
            "needs_review: false",
            # 006: appended before tags. Empty here — render_note was called
            # without a draft, so no path produced this note's copy.
            "draft_source:",
            "outcome:",
            # 007: appended before tags. Empty here — email-channel note with no
            # input facebook_url and no discovered facebook.com signal.
            "facebook_url:",
            "tags: [outreach, duct-cleaning, prospector]",
        ]
        assert lines[1:18] == expected_prefixes
        assert lines[18] == "---"
        assert "## Draft" in note and "## Research" in note and "## Log" in note
        assert note.index("## Draft") < note.index("## Research") < note.index("## Log")
        assert note.endswith("## Log\n-\n")

    def test_empty_values_render_bare(self):
        note = render_note(make_prospect(), "d", "r")
        assert "name_candidate:\n" in note
        assert "null" not in note

    def test_value_with_colon_is_quoted(self):
        prospect = make_prospect()
        prospect.research.hook = "Boston: the metro area"
        note = render_note(prospect, "d", "r")
        assert 'hook: "Boston: the metro area"' in note

    def test_needs_review_from_company_or_prospect(self):
        prospect = make_prospect()
        prospect.needs_review = True
        assert "needs_review: true" in render_note(prospect, "d", "r")


class TestWriteNote:
    def test_create_update_unchanged(self, tmp_path):
        assert write_note(tmp_path, "acme", "one\n") == "created"
        assert write_note(tmp_path, "acme", "one\n") == "unchanged"
        assert write_note(tmp_path, "acme", "two\n") == "updated"
        assert (tmp_path / "acme.md").read_text() == "two\n"

    def test_creates_vault_dir(self, tmp_path):
        target = tmp_path / "Vault" / "Outreach"
        write_note(target, "acme", "x\n")
        assert (target / "acme.md").is_file()


class TestMerge:
    def fresh(self, hook="Boston service area", name_used="team"):
        prospect = make_prospect()
        prospect.research.hook = hook
        prospect.name_used = name_used
        if name_used != "team":
            prospect.name_confidence = Confidence.HIGH
        return render_note(prospect, f"**Subject:** s\n\nHi {name_used},\nbody", "- Owner name: not found")

    def test_merge_of_identical_notes_is_byte_identical(self):
        note = self.fresh()
        assert merge_notes(note, note) == note

    def test_human_status_preserved(self):
        existing = self.fresh().replace("status: to-send", "status: sent")
        merged = merge_notes(existing, self.fresh())
        assert "status: sent" in merged
        assert "status: to-send" not in merged

    def test_human_log_preserved_verbatim(self):
        existing = self.fresh().replace(
            "## Log\n-", "## Log\n- 2026-07-13 sent\n\n\t- weird   spacing\n\n- replied!"
        )
        merged = merge_notes(existing, self.fresh())
        assert "- 2026-07-13 sent\n\n\t- weird   spacing\n\n- replied!" in merged

    def test_custom_human_section_preserved(self):
        existing = self.fresh() + "\n## My notes\nkeep me safe\n"
        merged = merge_notes(existing, self.fresh())
        assert "## My notes\nkeep me safe" in merged
        assert merged.index("## Log") < merged.index("## My notes")

    def test_machine_fields_refresh(self):
        existing = self.fresh(hook="old hook").replace("status: to-send", "status: sent")
        merged = merge_notes(existing, self.fresh(hook="new hook", name_used="Scott"))
        assert "hook: new hook" in merged
        assert "name_used: Scott" in merged
        assert "Hi Scott," in merged  # draft is machine-owned, regenerated
        assert "status: sent" in merged  # human field survives

    def test_parse_note_roundtrip_shapes(self):
        note = self.fresh()
        fm, sections = parse_note(note)
        assert fm["company"] == "Boston Air Duct Cleaning"
        assert [h for h, _ in sections] == ["Draft", "Research", "Log"]

    def test_upsert_lifecycle(self, tmp_path):
        note = self.fresh()
        assert upsert_note(tmp_path, "acme", note) == "created"
        assert upsert_note(tmp_path, "acme", note) == "unchanged"
        # human edits status; unchanged machine data must not rewrite the file
        edited = (tmp_path / "acme.md").read_text().replace("status: to-send", "status: sent")
        (tmp_path / "acme.md").write_text(edited)
        assert upsert_note(tmp_path, "acme", note) == "unchanged"
        # machine data changes -> update, but status stays human
        assert upsert_note(tmp_path, "acme", self.fresh(hook="new hook")) == "updated"
        content = (tmp_path / "acme.md").read_text()
        assert "status: sent" in content and "hook: new hook" in content


class TestHelpers:
    def test_display_website_strips_scheme(self):
        assert display_website("https://acme.com") == "acme.com"
        assert display_website("https://acme.com/about/") == "acme.com/about"
        assert display_website(None) is None

    def test_research_markdown_lists_sources(self):
        prospect = make_prospect()
        prospect.research.sources_consulted = ["https://a.com", "https://a.com/about"]
        md = build_research_markdown(prospect)
        assert "- Owner name: not found" in md
        assert "https://a.com, https://a.com/about" in md
        assert "- Failures: (none)" in md

    def test_draft_markdown_variants(self):
        prospect = make_prospect()
        good = Draft(subject="s", body="b", model="m")
        assert draft_markdown_for(good, prospect) == "**Subject:** s\n\nb"
        dm = Draft(subject=None, body="dm body", model="m")
        assert draft_markdown_for(dm, prospect) == "dm body"
        bad = Draft(subject="s", body="b", model="m", validated=False, validation_errors=["unfilled slot"])
        assert "draft failed validation: unfilled slot" in draft_markdown_for(bad, prospect)
        assert "not drafted — run without LLM" in draft_markdown_for(None, prospect, no_llm=True)
