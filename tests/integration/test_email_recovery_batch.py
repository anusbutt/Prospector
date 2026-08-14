"""008 US2 end-to-end: a company with no supplied address either gains one from
its own pages or is reported by name. There is no third outcome and no bucket.

Both companies below arrive with an empty email field — the state that used to
route them to the Messenger bucket.
"""

import httpx
import pytest
import respx

from helpers import settings
from prospector.pipeline import run_batch
from prospector.vault import parse_note

CSV = """company,email,website,city
Recoverable Ducts,,recoverable.com,
Unreachable Ducts,,unreachable.com,
"""

PUBLISHES_EMAIL = (
    "<html><body><h1>Recoverable Ducts</h1>"
    '<a href="mailto:hello@recoverable.com">Email us</a>'
    "</body></html>"
)
NO_EMAIL_ANYWHERE = "<html><body><h1>Unreachable Ducts</h1><p>Call us.</p></body></html>"


@pytest.fixture
def stubs():
    with respx.mock(assert_all_called=False) as mock:
        mock.route(
            host__regex=r".*(facebook\.com|fb\.com|fb\.me|fbcdn\.net|messenger\.com)$"
        ).mock(return_value=httpx.Response(200))
        mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"greeting_name": "team", "subject_company": "X"}'}}]},
            )
        )
        mock.get(url__startswith="https://html.duckduckgo.com/html/").mock(
            return_value=httpx.Response(200, text="<html><body>no results</body></html>")
        )
        for host, html in (("recoverable.com", PUBLISHES_EMAIL), ("unreachable.com", NO_EMAIL_ANYWHERE)):
            mock.get(f"https://{host}/robots.txt").mock(return_value=httpx.Response(404))
            mock.get(f"https://{host}/").mock(return_value=httpx.Response(200, text=html))
        yield mock


def run(tmp_path, stubs):
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text(CSV, encoding="utf-8")
    vault_dir = tmp_path / "vault"
    summary = run_batch(csv_path, settings(vault_dir), vault_dir=vault_dir, no_llm=True)
    return summary, vault_dir


def notes(vault_dir):
    return sorted(p.name for p in vault_dir.glob("*.md") if p.name != "_Dashboard.md")


class TestRecoveryOutcomes:
    def test_exactly_one_note_is_written(self, tmp_path, stubs):
        _, vault_dir = run(tmp_path, stubs)
        assert notes(vault_dir) == ["recoverable-ducts.md"]

    def test_counters_report_both_outcomes(self, tmp_path, stubs):
        summary, _ = run(tmp_path, stubs)
        assert summary.total == 2
        assert summary.processed == 1
        assert summary.email_recovered == 1
        assert summary.no_email_skipped == 1
        assert summary.reconciles()

    def test_unreachable_company_is_named(self, tmp_path, stubs):
        summary, _ = run(tmp_path, stubs)
        assert [name for name, _ in summary.skipped_companies] == ["Unreachable Ducts"]

    def test_skip_reason_describes_the_outcome_not_the_input_row(self, tmp_path, stubs):
        """FR-010: "blank email" restates the CSV. The operator needs to know
        which stage ran out of road — the site was read and published nothing."""
        summary, _ = run(tmp_path, stubs)
        assert summary.skipped_companies[0][1] == "no published address on any fetched page"

    def test_recovered_address_lands_in_the_note(self, tmp_path, stubs):
        _, vault_dir = run(tmp_path, stubs)
        text = (vault_dir / "recoverable-ducts.md").read_text(encoding="utf-8")
        frontmatter, _ = parse_note(text)
        assert frontmatter["email"] == "hello@recoverable.com"
        assert frontmatter["channel"] == "email"

    def test_recovery_is_recorded_as_evidence(self, tmp_path, stubs):
        """FR-007: the adopted address cites the page it came from."""
        _, vault_dir = run(tmp_path, stubs)
        text = (vault_dir / "recoverable-ducts.md").read_text(encoding="utf-8")
        assert "Email recovered: hello@recoverable.com" in text
        assert "https://recoverable.com" in text

    def test_no_note_for_the_unreachable_company(self, tmp_path, stubs):
        _, vault_dir = run(tmp_path, stubs)
        assert not (vault_dir / "unreachable-ducts.md").exists()
