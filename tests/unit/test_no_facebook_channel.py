"""008 US1: Facebook is not a communication channel.

These assertions are the standing guard on the removal. They fail loudly if a
Messenger/DM path, channel enum, or Facebook note field is ever reintroduced —
so the simplification cannot quietly regress (Constitution v7.0.0, Principle I).
"""

import pytest
from typer.testing import CliRunner

import prospector.models as models
from prospector.cli import app
from prospector.models import Company, Confidence, Draft, Prospect, ResearchResult
from prospector.vault import DASHBOARD_CONTENT, FRONTMATTER_KEYS, parse_note, render_note

runner = CliRunner()


class TestRemovedSymbols:
    @pytest.mark.parametrize("name", ["Channel", "Variant", "FbSignal", "DmCandidate", "DmOutcome", "DmResult", "DmRunReport"])
    def test_channel_types_are_gone(self, name):
        assert not hasattr(models, name), f"{name} should not exist: email is the only channel"

    @pytest.mark.parametrize("name", ["FB_LINK", "FB_EMBED", "FB_WIDGET", "FB_SEARCH_ACTIVE", "FB_URL_INPUT"])
    def test_facebook_evidence_kinds_are_gone(self, name):
        assert not hasattr(models.EvidenceKind, name)

    def test_modules_are_gone(self):
        for mod in ("prospector.dm", "prospector.clipboard"):
            with pytest.raises(ImportError):
                __import__(mod)


class TestCommandSurface:
    def test_dm_command_does_not_exist(self):
        result = runner.invoke(app, ["dm", "--help"])
        assert result.exit_code != 0

    def test_email_commands_still_exist(self):
        for cmd in ("run", "source", "send", "dashboard"):
            assert runner.invoke(app, [cmd, "--help"]).exit_code == 0, cmd


class TestNoteSchema:
    def _note(self):
        company = Company(company="Acme Duct", email="info@acme.com", raw_email_field="info@acme.com")
        research = ResearchResult(website="https://acme.com", hook="Denver service area")
        return render_note(Prospect(company=company, research=research), "d", "r")

    @pytest.mark.parametrize("key", ["fb_signal", "facebook_url"])
    def test_removed_keys_are_not_written(self, key):
        assert key not in FRONTMATTER_KEYS
        assert key not in parse_note(self._note())[0]

    def test_channel_is_always_email(self):
        assert parse_note(self._note())[0]["channel"] == "email"


class TestDashboard:
    def test_no_messenger_queue(self):
        assert "messenger" not in DASHBOARD_CONTENT.lower()

    def test_to_send_queue_no_longer_filters_on_channel(self):
        assert 'channel = "email"' not in DASHBOARD_CONTENT


class TestDraftingHasNoMessengerPath:
    def test_messenger_template_is_gone(self):
        import prospector.draft as draft

        for name in ("MESSENGER_DM_TEMPLATE", "MESSENGER_INVARIANTS", "build_messenger_draft"):
            assert not hasattr(draft, name), name

    def test_possessive_channel_claims_are_unconditionally_rejected(self):
        """With no channel signal researched, no evidence can justify "your page"."""
        from prospector.agent_draft import validate_channel_claims
        from prospector.models import AgentResponse, DraftBlock

        company = Company(company="Acme Duct", email="a@b.com", raw_email_field="a@b.com")
        prospect = Prospect(company=company, research=ResearchResult())
        response = AgentResponse(
            subject="s",
            blocks=[DraftBlock("It answers your Facebook page messages.", ["offer"])],
        )
        assert validate_channel_claims(response, prospect)
