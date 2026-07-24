"""Gmail send + identity via respx-mocked httpx (T010). No real network/OAuth."""

import base64
from types import SimpleNamespace

import httpx
import pytest
import respx

from prospector import gmail


def _creds(token="fake-token"):
    # Minimal stand-in for google.oauth2.credentials.Credentials: send_message and
    # account_email only need a bearer token and validity.
    return SimpleNamespace(token=token, valid=True, expired=False, refresh_token="r")


def test_build_raw_contains_headers_and_body():
    raw = gmail.build_raw("anas@omniveer.com", "you@acme.com", "Hello there", "Body line.")
    decoded = base64.urlsafe_b64decode(raw).decode()
    assert "From: anas@omniveer.com" in decoded
    assert "To: you@acme.com" in decoded
    assert "Subject: Hello there" in decoded
    assert "Body line." in decoded


@respx.mock
def test_send_message_posts_and_returns_id():
    route = respx.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "msg-123"})
    )
    mid = gmail.send_message(_creds(), "anas@omniveer.com", "you@acme.com", "Hi", "Body")
    assert mid == "msg-123"
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer fake-token"
    payload = sent.read().decode()
    assert '"raw"' in payload


@respx.mock
def test_send_message_raises_on_error():
    respx.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send").mock(
        return_value=httpx.Response(403, json={"error": "denied"})
    )
    with pytest.raises(gmail.SendError):
        gmail.send_message(_creds(), "anas@omniveer.com", "you@acme.com", "Hi", "Body")


@respx.mock
def test_account_email_reads_userinfo():
    respx.get("https://www.googleapis.com/oauth2/v3/userinfo").mock(
        return_value=httpx.Response(200, json={"email": "outreach@omniveer.com"})
    )
    assert gmail.account_email(_creds()) == "outreach@omniveer.com"
