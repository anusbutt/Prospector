"""Feature 004 send configuration: provider selection, SMTP parsing (SSL /
STARTTLS), require_send() pre-flight failures, and secret hygiene."""

import pytest

from prospector.config import ConfigError, load_settings

SEND_ENV = [
    "PROSPECTOR_SEND_PROVIDER", "PROSPECTOR_SEND_FROM", "PROSPECTOR_SEND_NAME",
    "PROSPECTOR_REPLY_TO", "PROSPECTOR_SMTP_HOST", "PROSPECTOR_SMTP_PORT",
    "PROSPECTOR_SMTP_SECURITY", "PROSPECTOR_SMTP_USERNAME", "PROSPECTOR_SMTP_PASSWORD",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in SEND_ENV:
        monkeypatch.delenv(var, raising=False)


def _smtp_env(monkeypatch, **overrides):
    values = {
        "PROSPECTOR_SEND_PROVIDER": "smtp",
        "PROSPECTOR_SEND_FROM": "anas@omniveer.com",
        "PROSPECTOR_SMTP_HOST": "smtp.zoho.com",
        "PROSPECTOR_SMTP_USERNAME": "anas@omniveer.com",
        "PROSPECTOR_SMTP_PASSWORD": "sentinel-secret-123",
    }
    values.update(overrides)
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def _load(tmp_path):
    return load_settings(tmp_path / "nonexistent.env")


# --- provider selection & defaults ---

def test_provider_defaults_to_gmail(tmp_path):
    s = _load(tmp_path)
    assert s.send_provider == "gmail"


def test_send_from_has_no_hardcoded_default(tmp_path):
    s = _load(tmp_path)
    assert s.send_from is None


def test_provider_and_security_are_lowercased(tmp_path, monkeypatch):
    _smtp_env(monkeypatch)
    monkeypatch.setenv("PROSPECTOR_SEND_PROVIDER", "SMTP")
    monkeypatch.setenv("PROSPECTOR_SMTP_SECURITY", "StartTLS")
    s = _load(tmp_path)
    assert s.send_provider == "smtp"
    assert s.smtp_security == "starttls"


# --- SMTP SSL / STARTTLS parsing ---

def test_smtp_ssl_config_parses_with_default_port_465(tmp_path, monkeypatch):
    _smtp_env(monkeypatch)  # security defaults to ssl
    s = _load(tmp_path)
    s.require_send()  # no raise
    assert s.smtp_security == "ssl"
    assert s.resolved_smtp_port() == 465
    assert s.smtp_host == "smtp.zoho.com"
    assert s.smtp_username == "anas@omniveer.com"


def test_smtp_starttls_config_parses_with_default_port_587(tmp_path, monkeypatch):
    _smtp_env(monkeypatch, PROSPECTOR_SMTP_SECURITY="starttls")
    s = _load(tmp_path)
    s.require_send()  # no raise
    assert s.smtp_security == "starttls"
    assert s.resolved_smtp_port() == 587


def test_explicit_port_overrides_security_default(tmp_path, monkeypatch):
    _smtp_env(monkeypatch, PROSPECTOR_SMTP_PORT="2465")
    s = _load(tmp_path)
    assert s.resolved_smtp_port() == 2465


# --- pre-flight failures (all before any network) ---

def test_invalid_provider_fails_preflight(tmp_path, monkeypatch):
    monkeypatch.setenv("PROSPECTOR_SEND_PROVIDER", "carrier-pigeon")
    monkeypatch.setenv("PROSPECTOR_SEND_FROM", "anas@omniveer.com")
    with pytest.raises(ConfigError, match="PROSPECTOR_SEND_PROVIDER"):
        _load(tmp_path).require_send()


def test_missing_send_from_fails_preflight(tmp_path):
    with pytest.raises(ConfigError, match="PROSPECTOR_SEND_FROM"):
        _load(tmp_path).require_send()


def test_missing_smtp_password_fails_safely(tmp_path, monkeypatch):
    _smtp_env(monkeypatch, PROSPECTOR_SMTP_PASSWORD=None)
    with pytest.raises(ConfigError, match="PROSPECTOR_SMTP_PASSWORD"):
        _load(tmp_path).require_send()


def test_missing_smtp_host_fails_preflight(tmp_path, monkeypatch):
    _smtp_env(monkeypatch, PROSPECTOR_SMTP_HOST=None)
    with pytest.raises(ConfigError, match="PROSPECTOR_SMTP_HOST"):
        _load(tmp_path).require_send()


def test_invalid_security_mode_fails_preflight(tmp_path, monkeypatch):
    _smtp_env(monkeypatch, PROSPECTOR_SMTP_SECURITY="tlsv9")
    with pytest.raises(ConfigError, match="ssl.*starttls|starttls.*ssl"):
        _load(tmp_path).require_send()


def test_bad_port_fails_preflight(tmp_path, monkeypatch):
    _smtp_env(monkeypatch, PROSPECTOR_SMTP_PORT="not-a-port")
    with pytest.raises(ConfigError, match="PROSPECTOR_SMTP_PORT"):
        _load(tmp_path).require_send()


def test_from_username_mismatch_is_rejected_before_sending(tmp_path, monkeypatch):
    _smtp_env(monkeypatch, PROSPECTOR_SEND_FROM="someoneelse@omniveer.com")
    with pytest.raises(ConfigError, match="spoof"):
        _load(tmp_path).require_send()


def test_from_username_comparison_is_case_insensitive(tmp_path, monkeypatch):
    _smtp_env(monkeypatch, PROSPECTOR_SEND_FROM="Anas@Omniveer.com")
    _load(tmp_path).require_send()  # no raise: same mailbox, different case


def test_gmail_provider_needs_no_smtp_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PROSPECTOR_SEND_FROM", "outreach@example.com")
    _load(tmp_path).require_send()  # provider defaults to gmail; no raise


# --- secret hygiene ---

def test_password_never_appears_in_settings_repr(tmp_path, monkeypatch):
    _smtp_env(monkeypatch)
    s = _load(tmp_path)
    assert "sentinel-secret-123" not in repr(s)


def test_preflight_errors_never_echo_secret_values(tmp_path, monkeypatch):
    _smtp_env(monkeypatch, PROSPECTOR_SEND_FROM="wrong@omniveer.com")
    with pytest.raises(ConfigError) as excinfo:
        _load(tmp_path).require_send()
    assert "sentinel-secret-123" not in str(excinfo.value)
