import pytest

from prospector.config import DEFAULT_MODEL, DEFAULT_VAULT, ConfigError, load_settings

ENV_VARS = ["OPENROUTER_API_KEY", "OPENROUTER_MODEL", "GOOGLE_PLACES_API_KEY", "HUNTER_API_KEY", "PROSPECTOR_VAULT"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults_when_nothing_set(tmp_path):
    s = load_settings(tmp_path / "nonexistent.env")
    assert s.openrouter_key is None
    assert s.openrouter_model == DEFAULT_MODEL
    assert s.places_key is None
    assert s.hunter_key is None
    assert str(s.vault_dir) == DEFAULT_VAULT


def test_values_read_from_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-test\nOPENROUTER_MODEL=some/model\n")
    s = load_settings(env)
    assert s.openrouter_key == "sk-test"
    assert s.openrouter_model == "some/model"


def test_process_env_wins_over_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=from-file\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-process")
    s = load_settings(env)
    assert s.openrouter_key == "from-process"


def test_require_llm_error_message(tmp_path):
    s = load_settings(tmp_path / "nonexistent.env")
    with pytest.raises(ConfigError, match="OPENROUTER_API_KEY.*--no-llm"):
        s.require_llm()


def test_require_llm_passes_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    s = load_settings(tmp_path / "nonexistent.env")
    s.require_llm()  # no raise


def test_require_places_error_message(tmp_path):
    s = load_settings(tmp_path / "nonexistent.env")
    with pytest.raises(ConfigError, match="GOOGLE_PLACES_API_KEY"):
        s.require_places()


def test_require_places_passes_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "places-x")
    s = load_settings(tmp_path / "nonexistent.env")
    s.require_places()  # no raise
