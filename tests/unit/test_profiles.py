"""008 US3/US4: per-vertical profiles supply the offer, and a broken one fails
before any company is processed.

Adding a vertical must need no code change (Constitution v7.0.0, Principle VI),
so profiles are resolved from a search path and validated up front — the locked
fallback is the honesty floor Principle IV falls back to and may never be
silently absent.
"""

import pytest

from prospector.config import ConfigError
from prospector.profiles import discover, load, search_paths

TOML = """tags = ["outreach", "hvac", "prospector"]
signature = "Sam\\nFounder, Example"
product_url = "https://example.com/thing"
keywords = ["hvac repair", "furnace"]
banned_claims = ["running ads", "your ads"]
"""

FALLBACK = """## Template
Hi {greeting_name},

A locked sentence that must survive.

{signature}

## Invariants
- A locked sentence that must survive.
"""


def make_profile(root, name="hvac", *, omit=(), toml=TOML, fallback=FALLBACK):
    d = root / name
    (d / "skills").mkdir(parents=True, exist_ok=True)
    files = {
        "IDENTITY.md": "You are Sam.",
        "OFFER.md": "A thing for HVAC companies.",
        "CONSTRAINTS.md": "Never invent facts.",
        "skills/write-cold-email.md": "Be brief.",
        "fallback.md": fallback,
        "profile.toml": toml,
    }
    for rel, content in files.items():
        if rel in omit:
            continue
        (d / rel).write_text(content, encoding="utf-8")
    return d


class TestResolutionOrder:
    def test_env_var_directory_wins(self, tmp_path, monkeypatch):
        env_dir, local_dir = tmp_path / "env", tmp_path / "local"
        make_profile(env_dir, "hvac")
        make_profile(local_dir, "hvac")
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(env_dir))
        monkeypatch.chdir(tmp_path)
        (tmp_path / "profiles").mkdir(exist_ok=True)
        assert load("hvac").root == env_dir / "hvac"

    def test_local_profiles_dir_is_used_when_no_env_var(self, tmp_path, monkeypatch):
        make_profile(tmp_path / "profiles", "hvac")
        monkeypatch.delenv("PROSPECTOR_PROFILES", raising=False)
        monkeypatch.chdir(tmp_path)
        assert load("hvac").root == tmp_path / "profiles" / "hvac"

    def test_packaged_profiles_are_on_the_search_path(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PROSPECTOR_PROFILES", raising=False)
        monkeypatch.chdir(tmp_path)
        assert any("prospector" in str(p) for p in search_paths())

    def test_bundled_duct_cleaning_profile_loads(self, monkeypatch):
        """The reference profile must keep working (FR-016)."""
        monkeypatch.delenv("PROSPECTOR_PROFILES", raising=False)
        assert "duct-cleaning" in discover()
        assert load("duct-cleaning").product_url.startswith("http")


class TestDiscovery:
    def test_discover_lists_available_names(self, tmp_path, monkeypatch):
        make_profile(tmp_path / "p", "hvac")
        make_profile(tmp_path / "p", "landscaping")
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        assert {"hvac", "landscaping"} <= set(discover())

    def test_unknown_name_lists_valid_ones(self, tmp_path, monkeypatch):
        make_profile(tmp_path / "p", "hvac")
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        with pytest.raises(ConfigError) as exc:
            load("nope")
        assert "not found" in str(exc.value) and "hvac" in str(exc.value)


class TestLoadedContent:
    def test_config_values_are_exposed(self, tmp_path, monkeypatch):
        make_profile(tmp_path / "p", "hvac")
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        p = load("hvac")
        assert p.name == "hvac"
        assert p.tags == ["outreach", "hvac", "prospector"]
        assert p.product_url == "https://example.com/thing"
        assert p.keywords[0] == "hvac repair"
        assert "running ads" in p.banned_claims
        assert p.signature.startswith("Sam")

    def test_fallback_template_and_invariants_parsed(self, tmp_path, monkeypatch):
        make_profile(tmp_path / "p", "hvac")
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        p = load("hvac")
        assert "{greeting_name}" in p.fallback_template
        assert p.fallback_invariants == ["A locked sentence that must survive."]

    def test_instructions_are_assembled_from_the_profile(self, tmp_path, monkeypatch):
        make_profile(tmp_path / "p", "hvac")
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        text = load("hvac").instructions.text
        assert "You are Sam." in text and "Be brief." in text


class TestValidationFailsEarly:
    """Every failure below must raise before any company is processed (FR-019)."""

    @pytest.mark.parametrize(
        "missing",
        ["IDENTITY.md", "OFFER.md", "CONSTRAINTS.md", "skills/write-cold-email.md",
         "fallback.md", "profile.toml"],
    )
    def test_missing_required_file(self, tmp_path, monkeypatch, missing):
        make_profile(tmp_path / "p", "hvac", omit=(missing,))
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        assert "hvac" in str(exc.value)

    def test_fallback_without_sections_is_rejected(self, tmp_path, monkeypatch):
        make_profile(tmp_path / "p", "hvac", fallback="just some prose\n")
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        assert "Template" in str(exc.value)

    def test_missing_toml_key_is_rejected(self, tmp_path, monkeypatch):
        make_profile(tmp_path / "p", "hvac", toml='tags = ["a"]\nsignature = "s"\n')
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        assert "product_url" in str(exc.value)

    def test_unparseable_toml_is_rejected(self, tmp_path, monkeypatch):
        make_profile(tmp_path / "p", "hvac", toml="not = = toml\n")
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        with pytest.raises(ConfigError):
            load("hvac")

    def test_empty_required_file_is_rejected(self, tmp_path, monkeypatch):
        d = make_profile(tmp_path / "p", "hvac")
        (d / "OFFER.md").write_text("", encoding="utf-8")
        monkeypatch.setenv("PROSPECTOR_PROFILES", str(tmp_path / "p"))
        with pytest.raises(ConfigError):
            load("hvac")
