import pytest

from prospector.config import ConfigError
from prospector.source import load_metros


def test_bundled_default_has_30_metros():
    metros = load_metros(None)
    assert len(metros) == 30
    assert metros[0] == "New York, NY"
    assert all("," in m for m in metros)


def test_custom_file(tmp_path):
    f = tmp_path / "metros.txt"
    f.write_text("Springfield, IL\n\n# a comment\n  Shelbyville, IL  \n")
    assert load_metros(f) == ["Springfield, IL", "Shelbyville, IL"]


def test_empty_file_errors(tmp_path):
    f = tmp_path / "metros.txt"
    f.write_text("# only comments\n\n")
    with pytest.raises(ConfigError, match="no metros found"):
        load_metros(f)


def test_missing_file_errors(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_metros(tmp_path / "nope.txt")
