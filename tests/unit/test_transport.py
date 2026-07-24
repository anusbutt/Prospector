"""Provider-neutral transport seam: build_email headers and create_sender
factory selection (contracts/email-sender.md)."""

import pytest

from prospector import transport
from prospector.config import ConfigError, Settings


def make_settings(tmp_path, **kw):
    defaults = dict(
        openrouter_key=None, openrouter_model="m", places_key=None,
        hunter_key=None, vault_dir=tmp_path / "vault",
    )
    defaults.update(kw)
    return Settings(**defaults)


# --- build_email ---

def test_from_display_name_is_formatted_correctly():
    msg = transport.build_email(
        "anas@omniveer.com", "Anas from Omniveer", None,
        "owner@acme.com", "Hello", "Body.",
    )
    assert msg["From"] == "Anas from Omniveer <anas@omniveer.com>"


def test_from_degrades_to_bare_address_without_name():
    msg = transport.build_email(
        "anas@omniveer.com", None, None, "owner@acme.com", "Hello", "Body.",
    )
    assert msg["From"] == "anas@omniveer.com"


def test_reply_to_included_when_configured():
    msg = transport.build_email(
        "anas@omniveer.com", "Anas from Omniveer", "anas@omniveer.com",
        "owner@acme.com", "Hello", "Body.",
    )
    assert msg["Reply-To"] == "anas@omniveer.com"


def test_reply_to_omitted_when_not_configured():
    msg = transport.build_email(
        "anas@omniveer.com", None, None, "owner@acme.com", "Hello", "Body.",
    )
    assert msg["Reply-To"] is None


def test_standard_headers_and_plain_text_body():
    msg = transport.build_email(
        "anas@omniveer.com", None, None, "owner@acme.com", "Hello", "Body line.",
        message_id="<abc123@omniveer.com>",
    )
    assert msg["To"] == "owner@acme.com"
    assert msg["Subject"] == "Hello"
    assert msg["Date"] is not None
    assert msg["Message-ID"] == "<abc123@omniveer.com>"
    assert msg.get_content_type() == "text/plain"
    assert "Body line." in msg.get_content()


def test_message_id_omitted_by_default_for_gmail_path():
    msg = transport.build_email(
        "anas@omniveer.com", None, None, "owner@acme.com", "Hello", "Body.",
    )
    assert msg["Message-ID"] is None  # Gmail assigns its own id


# --- create_sender factory ---

def test_factory_returns_gmail_sender_for_gmail(tmp_path):
    from prospector.gmail import GmailSender

    s = make_settings(tmp_path, send_provider="gmail", send_from="x@example.com")
    assert isinstance(transport.create_sender(s), GmailSender)


def test_factory_returns_smtp_sender_for_smtp(tmp_path):
    from prospector.smtp_send import SmtpSender

    s = make_settings(
        tmp_path, send_provider="smtp", send_from="anas@omniveer.com",
        smtp_host="smtp.zoho.com", smtp_username="anas@omniveer.com",
        smtp_password="pw",
    )
    assert isinstance(transport.create_sender(s), SmtpSender)


def test_factory_rejects_unknown_provider(tmp_path):
    s = make_settings(tmp_path, send_provider="pigeon")
    with pytest.raises(ConfigError):
        transport.create_sender(s)
