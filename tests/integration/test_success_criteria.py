"""Mechanical audit of spec.md success criteria SC-002..SC-006 on the fixture
batch. SC-001 (name lift on a representative 20-company list) and SC-007
(unattended batch, review-ready dashboard) are observed on live runs."""

from helpers import company_notes, frontmatter, run_fixture_batch

AD_CLAIM_SUBSTRINGS = ("your ads", "ad campaign", "running ads", "advertis", "ad spend")


def load_notes(vault_dir):
    return {
        p.name: p.read_text()
        for p in vault_dir.glob("*.md")
        if not p.name.startswith("_")
    }


class TestSuccessCriteria:
    def test_sc002_every_valid_row_produces_a_note(self, tmp_path, stubbed_network):
        summary, vault_dir = run_fixture_batch(tmp_path)
        assert len(company_notes(vault_dir)) == summary.total == 7

    def test_sc003_duplicates_leave_one_to_send_per_inbox(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        primaries_per_inbox = {}
        for name, text in load_notes(vault_dir).items():
            fm = frontmatter(text)
            if fm["email"] and not fm["duplicate_of"]:
                assert fm["email"] not in primaries_per_inbox
                primaries_per_inbox[fm["email"]] = name
        duplicates = [n for n, t in load_notes(vault_dir).items() if frontmatter(t)["duplicate_of"]]
        assert duplicates == ["acme-duct-south.md"]

    def test_sc004_messenger_rows_get_dm_and_queue(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        messenger = {
            n: t for n, t in load_notes(vault_dir).items()
            if frontmatter(t)["channel"] == "messenger"
        }
        assert messenger, "fixture batch must include a messenger row"
        for text in messenger.values():
            assert "Hey! I'm giving 5 duct cleaning companies a free 10-day pilot of the Omniveer Duct Lead Qualifier." in text

    def test_sc005_channel_honesty(self, tmp_path, stubbed_network):
        _, vault_dir = run_fixture_batch(tmp_path)
        assert stubbed_network["blocked"].call_count == 0, "a request reached a Facebook host"
        for name, text in load_notes(vault_dir).items():
            draft = text.split("## Draft")[1].split("## Research")[0].lower()
            for banned in AD_CLAIM_SUBSTRINGS:
                assert banned not in draft, f"{name}: ad claim {banned!r}"
            # constitution v2.0.0: product-fact FB mentions are allowed in
            # every variant; THEIR-page-activity phrasing needs a strong signal
            if "when someone messages your page" in draft:
                assert frontmatter(text)["fb_signal"] == "strong", (
                    f"{name} claims page activity without a strong signal"
                )

    def test_sc006_rerun_changes_zero_bytes(self, tmp_path, stubbed_network):
        run_fixture_batch(tmp_path)
        vault_dir = tmp_path / "Vault" / "Outreach"
        before = {p.name: p.read_bytes() for p in vault_dir.glob("*.md")}
        run_fixture_batch(tmp_path)
        after = {p.name: p.read_bytes() for p in vault_dir.glob("*.md")}
        assert before == after
