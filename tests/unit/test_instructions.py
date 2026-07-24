"""Instruction loading, bounding, and loud failure (006, FR-321..FR-325)."""

import pytest

from prospector.config import ConfigError
from prospector.instructions import (
    MAX_INSTRUCTION_CHARS,
    REQUIRED_FILES,
    load_instructions,
)


@pytest.fixture
def fixture_root(tmp_path):
    """A minimal but complete instruction tree."""
    for relative in REQUIRED_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n\nContent of {relative}.\n", encoding="utf-8")
    return tmp_path


class TestLoading:
    def test_loads_all_four(self, fixture_root):
        result = load_instructions(fixture_root)
        assert len(result.sources) == 4
        assert result.sources == list(REQUIRED_FILES)
        for relative in REQUIRED_FILES:
            assert f"Content of {relative}." in result.text

    def test_load_order_is_fixed(self, fixture_root):
        """Constraints must precede the writing guidance, so rules frame craft."""
        text = load_instructions(fixture_root).text
        assert text.index("IDENTITY") < text.index("OFFER")
        assert text.index("OFFER") < text.index("CONSTRAINTS")
        assert text.index("CONSTRAINTS") < text.index("write-cold-email")

    def test_real_package_files_load(self):
        """The shipped files must actually load — not just fixtures."""
        result = load_instructions()
        assert result.char_count > 1000
        assert "Omniveer" in result.text
        assert "https://www.omniveer.com/duct-lead-qualifier" in result.text

    def test_real_package_files_are_within_bound(self):
        assert load_instructions().char_count <= MAX_INSTRUCTION_CHARS


class TestFailsLoudly:
    @pytest.mark.parametrize("missing", REQUIRED_FILES)
    def test_missing_file_names_it(self, fixture_root, missing):
        (fixture_root / missing).unlink()
        with pytest.raises(ConfigError) as exc:
            load_instructions(fixture_root)
        assert missing in str(exc.value)

    def test_empty_file_names_it(self, fixture_root):
        (fixture_root / "agent/OFFER.md").write_text("   \n", encoding="utf-8")
        with pytest.raises(ConfigError) as exc:
            load_instructions(fixture_root)
        assert "agent/OFFER.md" in str(exc.value)
        assert "empty" in str(exc.value)

    def test_oversize_fails_loudly(self, fixture_root):
        """FR-325: exceeding the cap fails; it MUST NOT truncate silently.

        A truncated CONSTRAINTS.md would drop hard rules invisibly."""
        (fixture_root / "agent/OFFER.md").write_text("x" * (MAX_INSTRUCTION_CHARS + 1), encoding="utf-8")
        with pytest.raises(ConfigError) as exc:
            load_instructions(fixture_root)
        message = str(exc.value)
        assert str(f"{MAX_INSTRUCTION_CHARS:,}") in message
        assert "truncated" in message or "never truncated" in message

    def test_no_truncated_result_is_ever_returned(self, fixture_root):
        (fixture_root / "agent/OFFER.md").write_text("x" * (MAX_INSTRUCTION_CHARS + 1), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_instructions(fixture_root)


class TestContentIsNotCode:
    def test_shipped_files_contain_no_secrets(self):
        """Constitution: instruction files MUST NOT contain credentials."""
        import re

        text = load_instructions().text
        assert not re.search(r"(api[_-]?key|password|secret|bearer\s+\w)", text, re.I)

    def test_shipped_offer_carries_exactly_one_product_url(self):
        from prospector.instructions import _read

        offer = _read(None, "agent/OFFER.md")
        assert offer.count("http") == 1
        assert "https://www.omniveer.com/duct-lead-qualifier" in offer
