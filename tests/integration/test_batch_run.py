"""Full batch over a fixture CSV with the network and LLM stubbed at the
transport level. Also proves SC-005: zero requests reach Facebook hosts."""

from helpers import company_notes, frontmatter, run_fixture_batch


class TestBatchRun:
    def test_one_note_per_valid_row(self, tmp_path, stubbed_network):
        summary, vault_dir = run_fixture_batch(tmp_path)
        assert company_notes(vault_dir) == [
            "acme-duct-cleaning.md",
            "acme-duct-south.md",
            "beta-air-systems.md",
            "chat-only-cleaners.md",
            "delta-fresh-air.md",
            "gamma-vent-care.md",
            "plain-ducts.md",
        ]
        assert summary.total == 7  # malformed row warned and skipped
        assert summary.processed == 7
        assert summary.failed == 0
        assert summary.reconciles()
        assert summary.named_high == 3  # acme + acme-south (about page), beta (scott@)
        assert summary.named_medium == 1  # gamma (derickson@)
        assert summary.duplicates == 1  # acme-south shares info@acmeduct.com

    def test_zero_requests_to_facebook_hosts(self, tmp_path, stubbed_network):
        run_fixture_batch(tmp_path)
        assert stubbed_network["blocked"].call_count == 0

    def test_email_note_has_complete_draft(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        note = (vault_dir / "acme-duct-cleaning.md").read_text()
        fm = frontmatter(note)
        assert fm["channel"] == "email"
        assert fm["status"] == "to-send"
        assert fm["name_used"] == "Scott"  # sourced from the /about page (US2)
        assert fm["name_confidence"] == "high"
        assert fm["fb_signal"] == "none"
        assert "**Subject:** Free 10-day pilot for Acme Duct Cleaning" in note
        assert "Hi Scott," in note
        draft_section = note.split("## Draft")[1].split("## Research")[0]
        assert "[" not in draft_section, "unfilled slot leaked into the note"
        # rev. 2 copy is channel-neutral: no channel claims at any signal level
        assert "free 10-day pilot of the Omniveer Duct Lead Qualifier" in draft_section
        assert "messages your page" not in draft_section.lower()
        assert "facebook" not in draft_section.lower()

    def test_email_pattern_name_high(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        note = (vault_dir / "beta-air-systems.md").read_text()
        fm = frontmatter(note)
        assert fm["name_used"] == "Scott"  # scott@betaair.com, unambiguous
        assert fm["name_confidence"] == "high"
        assert "Hi Scott," in note

    def test_ambiguous_email_medium_stays_team(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        note = (vault_dir / "gamma-vent-care.md").read_text()
        fm = frontmatter(note)
        assert fm["name_used"] == "team"
        assert fm["name_confidence"] == "medium"
        assert fm["name_candidate"] == "Derickson"
        assert fm["needs_review"] == "true"
        assert "Hi Gamma Vent Care team," in note

    def test_research_section_records_sources(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        note = (vault_dir / "acme-duct-cleaning.md").read_text()
        assert "https://acmeduct.com/about" in note
        assert "Scott Brown" in note

    def test_resolved_website_via_ddg(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        fm = frontmatter((vault_dir / "beta-air-systems.md").read_text())
        assert fm["website"] == "betaair.com"

    def test_messenger_row_gets_dm_draft(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        note = (vault_dir / "chat-only-cleaners.md").read_text()
        fm = frontmatter(note)
        assert fm["channel"] == "messenger"
        assert fm["needs_review"] == "true"  # website unresolved
        assert "Hey! I'm giving 5 duct cleaning companies a free 10-day pilot of the Omniveer Duct Lead Qualifier." in note
        assert "**Subject:**" not in note  # DMs have no subject line

    def test_strong_fb_signal_recorded_but_body_stays_neutral(self, tmp_path, stubbed_network):
        # rev. 2: the signal is still researched and recorded, but the email
        # copy is channel-neutral at every level — no their-activity phrasing
        _, vault_dir = run_fixture_batch(tmp_path)
        note = (vault_dir / "delta-fresh-air.md").read_text()
        fm = frontmatter(note)
        assert fm["fb_signal"] == "strong"  # widget (active) + footer link
        assert "free 10-day pilot of the Omniveer Duct Lead Qualifier" in note
        assert "messages your page" not in note.lower()

    def test_no_hook_row_still_gets_note_and_draft(self, tmp_path, stubbed_network):
        # rev. 2 copy has no locator slot; a hook-less row still drafts cleanly
        _, vault_dir = run_fixture_batch(tmp_path)
        note = (vault_dir / "plain-ducts.md").read_text()
        fm = frontmatter(note)
        assert fm["hook"] == ""
        assert "**Subject:** Free 10-day pilot for" in note
        draft_section = note.split("## Draft")[1].split("## Research")[0]
        assert "[" not in draft_section  # nothing unfilled, nothing invented

    def test_no_llm_skips_openrouter_entirely(self, tmp_path, stubbed_network):
        run_fixture_batch(tmp_path, no_llm=True)
        assert stubbed_network["openrouter"].call_count == 0


class TestDuplicates:
    def test_duplicate_references_primary_and_is_flagged(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        note = (vault_dir / "acme-duct-south.md").read_text()
        fm = frontmatter(note)
        assert fm["duplicate_of"] == "acme-duct-cleaning"
        assert fm["needs_review"] == "true"
        assert "shares inbox with [[acme-duct-cleaning]]" in note

    def test_exactly_one_to_send_note_per_inbox(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        inbox_primaries = {}
        for path in vault_dir.glob("*.md"):
            if path.name.startswith("_"):
                continue
            fm = frontmatter(path.read_text())
            email = fm["email"]
            if email and not fm["duplicate_of"]:
                assert email not in inbox_primaries, f"two primaries share inbox {email}"
                inbox_primaries[email] = path.name
        assert "info@acmeduct.com" in inbox_primaries
