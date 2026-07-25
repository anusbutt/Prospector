"""008 US4: a broken profile aborts pre-flight, having written nothing.

`test_profiles.py` proves each malformed profile raises. This file pins the two
things that make the guarantee *operationally* true (FR-018/FR-019):

1. The error text matches contracts/profile.md, so an operator can act on it
   without reading the source.
2. Validation happens before ANY company is processed — `run_batch` is never
   entered, no vault appears, and no HTTP client is ever constructed. A profile
   is the honesty floor the fallback path depends on (Constitution v7.0.0,
   Principle IV), so discovering it is broken halfway through a batch would mean
   notes already written against a profile that cannot answer.
"""

import httpx
import pytest
from typer.testing import CliRunner

from prospector.cli import app
from prospector.config import ConfigError
from prospector.instructions import MAX_INSTRUCTION_CHARS
from prospector.profiles import load
from test_profiles import TOML, make_profile

runner = CliRunner()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any outbound HTTP during a pre-flight failure is itself the bug.

    The transport methods are patched rather than `httpx.Client` itself: the
    class object is still needed as a type annotation when `prospector.fetch` is
    lazily imported."""

    def forbidden(*args, **kwargs):
        raise AssertionError("pre-flight failure must not touch the network")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    monkeypatch.setattr(httpx, "post", forbidden)
    monkeypatch.setattr(httpx, "get", forbidden)


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    """An isolated profiles root; the bundled one must not mask a broken fixture."""
    root = tmp_path / "profiles"
    root.mkdir()
    monkeypatch.setenv("PROSPECTOR_PROFILES", str(root))
    monkeypatch.delenv("PROSPECTOR_PROFILE", raising=False)
    return root


class TestContractErrorMessages:
    """Each row of the contracts/profile.md validation table."""

    def test_profile_not_found_names_the_available_ones(self, profiles_dir):
        make_profile(profiles_dir, "hvac")
        with pytest.raises(ConfigError) as exc:
            load("nope")
        assert "profile 'nope' not found" in str(exc.value)
        assert "Available: hvac" in str(exc.value)

    def test_missing_required_file_names_profile_and_file(self, profiles_dir):
        make_profile(profiles_dir, "hvac", omit=("fallback.md",))
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        assert str(exc.value) == "profile 'hvac' is missing required file: fallback.md"

    def test_empty_required_file_is_distinguished_from_missing(self, profiles_dir):
        d = make_profile(profiles_dir, "hvac")
        (d / "profile.toml").write_text("   \n", encoding="utf-8")
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        assert str(exc.value) == "profile 'hvac' has an empty required file: profile.toml"

    def test_fallback_missing_a_section_lists_all_three(self, profiles_dir):
        make_profile(profiles_dir, "hvac", fallback="## Template\nHi {greeting_name},\n")
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        message = str(exc.value)
        assert message.startswith("profile 'hvac': fallback.md must contain")
        for heading in ("'## Subject'", "'## Template'", "'## Invariants'"):
            assert heading in message

    def test_fallback_with_no_invariants_is_rejected(self, profiles_dir):
        make_profile(
            profiles_dir,
            "hvac",
            fallback="## Subject\nS for {subject_company}\n\n## Template\nHi {greeting_name},\n\n## Invariants\n",
        )
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        assert str(exc.value) == "profile 'hvac': fallback.md lists no invariants"

    def test_missing_toml_key_names_the_key(self, profiles_dir):
        make_profile(
            profiles_dir,
            "hvac",
            toml=TOML.replace('product_url = "https://example.com/thing"\n', ""),
        )
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        assert str(exc.value) == (
            "profile 'hvac': profile.toml is missing required key: product_url"
        )

    def test_unparseable_toml_names_the_profile_and_file(self, profiles_dir):
        make_profile(profiles_dir, "hvac", toml="not = = toml\n")
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        assert "profile 'hvac': profile.toml is not valid TOML" in str(exc.value)

    def test_oversized_instructions_report_both_sizes(self, profiles_dir):
        d = make_profile(profiles_dir, "hvac")
        (d / "OFFER.md").write_text("x" * (MAX_INSTRUCTION_CHARS + 1), encoding="utf-8")
        with pytest.raises(ConfigError) as exc:
            load("hvac")
        message = str(exc.value)
        assert message.startswith("profile 'hvac': instruction context is")
        assert f"max {MAX_INSTRUCTION_CHARS:,}" in message


class TestNothingIsWrittenOrFetched:
    """FR-019: exit 1 with nothing fetched and nothing written."""

    def _csv(self, tmp_path):
        path = tmp_path / "list.csv"
        path.write_text("company,email\nAcme,info@acme.com\n", encoding="utf-8")
        return path

    @pytest.fixture(autouse=True)
    def never_runs_a_batch(self, monkeypatch):
        """Reaching the pipeline at all means validation ran too late."""
        import prospector.pipeline as pipeline
        import prospector.source as source

        def forbidden(*args, **kwargs):
            raise AssertionError("a broken profile must abort before any work")

        monkeypatch.setattr(pipeline, "run_batch", forbidden)
        monkeypatch.setattr(source, "run_sourcing", forbidden)

    def test_run_exits_1_and_writes_no_vault(self, tmp_path, monkeypatch, profiles_dir):
        make_profile(profiles_dir, "hvac", omit=("fallback.md",))
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
        vault = tmp_path / "vault"
        result = runner.invoke(
            app,
            ["run", str(self._csv(tmp_path)), "--profile", "hvac", "--vault", str(vault)],
        )
        assert result.exit_code == 1
        assert "missing required file: fallback.md" in result.output
        assert not vault.exists()

    def test_run_reports_the_profile_before_the_missing_input(self, monkeypatch, profiles_dir):
        """Ordering proof: the profile is validated first (FR-018)."""
        make_profile(profiles_dir, "hvac", omit=("fallback.md",))
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
        result = runner.invoke(app, ["run", "no-such-file.csv", "--profile", "hvac"])
        assert result.exit_code == 1
        assert "fallback.md" in result.output
        assert "input file not found" not in result.output

    def test_run_validates_the_profile_before_the_llm_key(self, monkeypatch, tmp_path, profiles_dir):
        make_profile(profiles_dir, "hvac", omit=("fallback.md",))
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        result = runner.invoke(
            app, ["run", str(self._csv(tmp_path)), "--profile", "hvac"]
        )
        assert result.exit_code == 1
        assert "fallback.md" in result.output
        assert "OPENROUTER_API_KEY" not in result.output

    def test_source_exits_1_and_writes_no_csv(self, tmp_path, monkeypatch, profiles_dir):
        make_profile(profiles_dir, "hvac", toml="not = = toml\n")
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "pk-x")
        out = tmp_path / "candidates.csv"
        result = runner.invoke(app, ["source", "--profile", "hvac", "--out", str(out)])
        assert result.exit_code == 1
        assert "not valid TOML" in result.output
        assert not out.exists()

    def test_unknown_profile_name_exits_1(self, tmp_path, monkeypatch, profiles_dir):
        make_profile(profiles_dir, "hvac")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
        result = runner.invoke(
            app, ["run", str(self._csv(tmp_path)), "--profile", "landscaping"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output and "hvac" in result.output

    def test_no_profiles_anywhere_explains_how_to_create_one(
        self, tmp_path, monkeypatch, profiles_dir
    ):
        """An empty search path is a setup error, not an empty prompt.

        A normal install cannot reach this: the reference profile ships inside
        the package, so the search path's last tier always yields one. The tier
        is emptied here deliberately, to prove the branch reports how to fix
        itself rather than dropping into a prompt with no options."""
        import prospector.profiles as profiles_mod

        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(profiles_mod, "search_paths", lambda: [empty])
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
        result = runner.invoke(app, ["run", str(self._csv(tmp_path))])
        assert result.exit_code == 1
        assert "no profiles found" in result.output
        assert "profile.toml" in result.output  # names what a profile needs

    def test_non_interactive_run_without_a_profile_fails_instead_of_hanging(
        self, tmp_path, monkeypatch, profiles_dir
    ):
        """contracts/cli.md: a pipe or cron job must not block on a prompt."""
        make_profile(profiles_dir, "hvac")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
        result = runner.invoke(app, ["run", str(self._csv(tmp_path))], input="")
        assert result.exit_code == 1
        assert "no profile selected" in result.output
        assert "hvac" in result.output
