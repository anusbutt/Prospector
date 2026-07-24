"""OAuth token load/refresh + identity guard (T022/T023; re-pointed at the
feature-004 sender seam). No real consent/network: credentials are injected via
fake objects and monkeypatched module functions."""

import json
from types import SimpleNamespace

import pytest

from prospector import gmail
from prospector.config import Settings
from prospector.send import IdentityError, verified_sender


def _settings(tmp_path):
    return Settings(
        openrouter_key=None, openrouter_model="m", places_key=None, hunter_key=None,
        vault_dir=tmp_path / "vault", send_from="outreach@omniveer.com",
        gmail_client_secret_path=tmp_path / "client.json",
        gmail_token_path=tmp_path / "token.json",
    )


def test_load_uses_existing_valid_token(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text('{"token": "x"}', encoding="utf-8")
    fake = SimpleNamespace(valid=True)

    class FakeCreds:
        @staticmethod
        def from_authorized_user_info(info, scopes):
            return fake

    # Patch the symbol imported lazily inside load_or_authorize.
    monkeypatch.setattr("google.oauth2.credentials.Credentials", FakeCreds)
    creds = gmail.load_or_authorize(tmp_path / "client.json", token)
    assert creds is fake  # reused stored token; no consent flow


def test_missing_client_secret_raises_auth_error(tmp_path):
    # No token, no client secret → cannot run consent.
    with pytest.raises(gmail.AuthError):
        gmail.load_or_authorize(tmp_path / "nope.json", tmp_path / "notoken.json")


def _gmail_sender(tmp_path, monkeypatch, account):
    """GmailSender with OAuth + userinfo stubbed out (no consent, no network)."""
    monkeypatch.setattr(gmail, "load_or_authorize", lambda c, t: object())
    monkeypatch.setattr(gmail, "account_email", lambda creds: account)
    return gmail.GmailSender(_settings(tmp_path))


def test_verified_sender_accepts_matching_gmail_account(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    sender = _gmail_sender(tmp_path, monkeypatch, "outreach@omniveer.com")
    assert verified_sender(settings, sender=sender) is sender


def test_verified_sender_rejects_wrong_gmail_account(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    sender = _gmail_sender(tmp_path, monkeypatch, "someoneelse@gmail.com")
    with pytest.raises(IdentityError):
        verified_sender(settings, sender=sender)


def test_verified_sender_gmail_account_is_case_insensitive(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    sender = _gmail_sender(tmp_path, monkeypatch, "Outreach@Omniveer.com")
    assert verified_sender(settings, sender=sender) is sender
