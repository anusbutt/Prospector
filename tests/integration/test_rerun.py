"""US5: re-runs are byte-idempotent and never clobber human edits (SC-006)."""

import httpx

from helpers import PLAIN_WITH_OWNER_HTML, frontmatter, run_fixture_batch


def vault_bytes(vault_dir):
    return {p.name: p.read_bytes() for p in sorted(vault_dir.glob("*.md"))}


class TestRerun:
    def test_unchanged_rerun_changes_zero_bytes(self, tmp_path, stubbed_network):
        run_fixture_batch(tmp_path)
        vault_dir = tmp_path / "Vault" / "Outreach"
        before = vault_bytes(vault_dir)
        run_fixture_batch(tmp_path)
        assert vault_bytes(vault_dir) == before

    def test_human_edits_survive_while_new_research_lands(self, tmp_path, stubbed_network):
        run_fixture_batch(tmp_path)
        vault_dir = tmp_path / "Vault" / "Outreach"

        # Human works the vault: marks acme sent, logs it, adds a section
        acme = vault_dir / "acme-duct-cleaning.md"
        edited = acme.read_text().replace("status: to-send", "status: sent")
        edited = edited.replace("## Log\n-", "## Log\n- 2026-07-13 sent from real inbox")
        edited += "\n## My notes\ncall back Tuesday\n"
        acme.write_text(edited)

        # Meanwhile plainducts.com publishes an owner name
        stubbed_network["plainducts"].mock(
            return_value=httpx.Response(200, text=PLAIN_WITH_OWNER_HTML)
        )

        summary, _ = run_fixture_batch(tmp_path)

        # human-owned regions intact
        merged = acme.read_text()
        assert "status: sent" in merged
        assert "- 2026-07-13 sent from real inbox" in merged
        assert "## My notes\ncall back Tuesday" in merged

        # newly found name updates frontmatter AND draft, honestly sourced
        plain = (vault_dir / "plain-ducts.md").read_text()
        fm = frontmatter(plain)
        assert fm["name_used"] == "Sarah"
        assert fm["name_confidence"] == "high"
        assert "Hi Sarah," in plain
        assert "Sarah Miller" in plain.split("## Research")[1]  # evidence recorded

    def test_second_run_reports_all_unchanged(self, tmp_path, stubbed_network):
        run_fixture_batch(tmp_path)
        summary, _ = run_fixture_batch(tmp_path)
        details = [detail for _, _, detail in summary.per_company]
        assert all("unchanged" in d for d in details), details
