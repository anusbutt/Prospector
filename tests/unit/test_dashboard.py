from typer.testing import CliRunner

from prospector.cli import app
from prospector.vault import DASHBOARD_CONTENT, write_dashboard

runner = CliRunner()


class TestDashboardContent:
    def test_six_dataview_query_blocks(self):
        # 4 original queues + 2 added by 006 (draft source, outcome by source)
        assert DASHBOARD_CONTENT.count("```dataview") == 6

    def test_queries_filter_on_documented_fields(self):
        # to-send queue excludes duplicates and non-email channels
        assert 'WHERE status = "to-send" AND channel = "email" AND !duplicate_of' in DASHBOARD_CONTENT
        # needs-review includes medium-confidence candidates
        assert 'WHERE needs_review = true OR name_confidence = "medium"' in DASHBOARD_CONTENT
        assert "name_candidate" in DASHBOARD_CONTENT
        # messenger bucket
        assert 'WHERE channel = "messenger"' in DASHBOARD_CONTENT
        # pipeline grouped by status
        assert "GROUP BY status" in DASHBOARD_CONTENT
        # 006 measurement queries
        assert DASHBOARD_CONTENT.count("GROUP BY draft_source") == 2
        assert 'GROUP BY draft_source + " / " + outcome' in DASHBOARD_CONTENT
        # folder-agnostic tag scope on every query
        assert DASHBOARD_CONTENT.count("FROM #prospector") == 6

    def test_plain_markdown_fallback_note_present(self):
        assert "Without Dataview this note still renders" in DASHBOARD_CONTENT
        assert "browse notes by their frontmatter instead" in DASHBOARD_CONTENT


class TestWriteDashboard:
    def test_idempotent_bytes(self, tmp_path):
        assert write_dashboard(tmp_path) == "created"
        assert write_dashboard(tmp_path) == "unchanged"
        assert (tmp_path / "_Dashboard.md").read_text() == DASHBOARD_CONTENT


class TestDashboardCommand:
    def test_regenerates_into_existing_vault(self, tmp_path):
        result = runner.invoke(app, ["dashboard", "--vault", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "_Dashboard.md").is_file()

    def test_missing_vault_dir_exits_1(self, tmp_path):
        result = runner.invoke(app, ["dashboard", "--vault", str(tmp_path / "nope")])
        assert result.exit_code == 1
        assert "not found" in result.output
