"""SmtpSender (contracts/smtp-sender.md): SSL/STARTTLS selection, mandatory
auth, Message-ID return, failure mapping, and password hygiene. All offline —
smtplib is replaced by an injected fake factory."""

import smtplib
import ssl

import pytest

from prospector.config import Settings
from prospector.smtp_send import SmtpSender
from prospector.transport import AuthError, SendError

PASSWORD = "sentinel-secret-123"


def make_settings(tmp_path, **kw):
    defaults = dict(
        openrouter_key=None, openrouter_model="m", places_key=None,
        hunter_key=None, vault_dir=tmp_path / "vault",
        send_provider="smtp", send_from="anas@omniveer.com",
        send_name="Anas from Omniveer", reply_to="anas@omniveer.com",
        smtp_host="smtp.zoho.com", smtp_username="anas@omniveer.com",
        smtp_password=PASSWORD,
    )
    defaults.update(kw)
    return Settings(**defaults)


class FakeConnection:
    def __init__(self, log, name, *, fail_login=False, refuse=None, boom=False):
        self.log = log
        self.name = name
        self.fail_login = fail_login
        self.refuse = refuse or {}
        self.boom = boom

    def starttls(self, context=None):
        self.log.append(("starttls", self.name, isinstance(context, ssl.SSLContext)))

    def login(self, username, password):
        self.log.append(("login", username))
        if self.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"authentication failed")

    def send_message(self, msg, from_addr=None, to_addrs=None):
        self.log.append(("send", from_addr, tuple(to_addrs or ()), msg))
        if self.boom:
            raise smtplib.SMTPServerDisconnected("connection lost")
        if self.refuse:
            raise smtplib.SMTPRecipientsRefused(self.refuse)
        return {}

    def quit(self):
        self.log.append(("quit", self.name))


class FakeFactory:
    """Stands in for {'ssl': SMTP_SSL, 'starttls': SMTP}. Records construction."""

    def __init__(self, **conn_kwargs):
        self.log = []
        self.constructed = []
        self.conn_kwargs = conn_kwargs

    def as_dict(self):
        def ssl_cls(host, port, timeout=None, context=None):
            self.constructed.append(("ssl", host, port, timeout, isinstance(context, ssl.SSLContext)))
            return FakeConnection(self.log, "ssl", **self.conn_kwargs)

        def plain_cls(host, port, timeout=None):
            self.constructed.append(("starttls", host, port, timeout, None))
            return FakeConnection(self.log, "starttls", **self.conn_kwargs)

        return {"ssl": ssl_cls, "starttls": plain_cls}


def make_sender(tmp_path, factory=None, **settings_kw):
    factory = factory or FakeFactory()
    sender = SmtpSender(make_settings(tmp_path, **settings_kw), smtp_factory=factory.as_dict())
    return sender, factory


# --- connection modes ---

def test_ssl_uses_implicit_tls_on_465_with_default_context(tmp_path):
    sender, factory = make_sender(tmp_path)
    sender.verify_identity()
    kind, host, port, timeout, has_context = factory.constructed[0]
    assert (kind, host, port) == ("ssl", "smtp.zoho.com", 465)
    assert timeout == 30.0
    assert has_context  # ssl.create_default_context()
    assert ("starttls", "ssl", True) not in factory.log  # no upgrade call on SSL


def test_starttls_upgrades_on_587(tmp_path):
    sender, factory = make_sender(tmp_path, smtp_security="starttls")
    sender.verify_identity()
    kind, host, port, timeout, _ = factory.constructed[0]
    assert (kind, port) == ("starttls", 587)
    assert ("starttls", "starttls", True) in factory.log  # upgraded with a real context


def test_explicit_port_wins(tmp_path):
    sender, factory = make_sender(tmp_path, smtp_port="2465")
    sender.verify_identity()
    assert factory.constructed[0][2] == 2465


# --- identity & auth ---

def test_verify_identity_logs_in_and_returns_username(tmp_path):
    sender, factory = make_sender(tmp_path)
    assert sender.verify_identity() == "anas@omniveer.com"
    assert ("login", "anas@omniveer.com") in factory.log


def test_bad_credentials_raise_autherror(tmp_path):
    sender, _ = make_sender(tmp_path, factory=FakeFactory(fail_login=True))
    with pytest.raises(AuthError):
        sender.verify_identity()


def test_login_always_precedes_send(tmp_path):
    sender, factory = make_sender(tmp_path)
    sender.send_message("anas@omniveer.com", "owner@acme.com", "Hi", "Body.")
    ops = [entry[0] for entry in factory.log]
    assert ops.index("login") < ops.index("send")


# --- message + Message-ID ---

def test_send_returns_generated_message_id_matching_header(tmp_path):
    sender, factory = make_sender(tmp_path)
    mid = sender.send_message("anas@omniveer.com", "owner@acme.com", "Hi", "Body.")
    sent = [e for e in factory.log if e[0] == "send"][0]
    msg = sent[3]
    assert mid == msg["Message-ID"]
    assert mid.startswith("<") and "omniveer.com" in mid and mid.endswith(">")


def test_message_headers_from_name_reply_to_date(tmp_path):
    sender, factory = make_sender(tmp_path)
    sender.send_message("anas@omniveer.com", "owner@acme.com", "Hi", "Body.")
    msg = [e for e in factory.log if e[0] == "send"][0][3]
    assert msg["From"] == "Anas from Omniveer <anas@omniveer.com>"
    assert msg["To"] == "owner@acme.com"
    assert msg["Reply-To"] == "anas@omniveer.com"
    assert msg["Date"] is not None


def test_envelope_uses_from_and_single_recipient(tmp_path):
    sender, factory = make_sender(tmp_path)
    sender.send_message("anas@omniveer.com", "owner@acme.com", "Hi", "Body.")
    _, from_addr, to_addrs, _ = [e for e in factory.log if e[0] == "send"][0]
    assert from_addr == "anas@omniveer.com"
    assert to_addrs == ("owner@acme.com",)


# --- failure mapping ---

def test_recipient_refusal_is_a_send_error(tmp_path):
    refuse = {"owner@acme.com": (550, b"mailbox unavailable")}
    sender, _ = make_sender(tmp_path, factory=FakeFactory(refuse=refuse))
    with pytest.raises(SendError, match="refused"):
        sender.send_message("anas@omniveer.com", "owner@acme.com", "Hi", "Body.")


def test_transport_exception_is_a_send_error(tmp_path):
    sender, _ = make_sender(tmp_path, factory=FakeFactory(boom=True))
    with pytest.raises(SendError):
        sender.send_message("anas@omniveer.com", "owner@acme.com", "Hi", "Body.")


def test_mid_batch_auth_failure_is_a_send_error_not_fatal(tmp_path):
    sender, _ = make_sender(tmp_path, factory=FakeFactory(fail_login=True))
    with pytest.raises(SendError):
        sender.send_message("anas@omniveer.com", "owner@acme.com", "Hi", "Body.")


# --- password hygiene (FR-111) ---

def test_password_never_in_auth_error_text(tmp_path):
    sender, _ = make_sender(tmp_path, factory=FakeFactory(fail_login=True))
    with pytest.raises(AuthError) as excinfo:
        sender.verify_identity()
    assert PASSWORD not in str(excinfo.value)
    assert PASSWORD not in repr(excinfo.value)


def test_password_never_in_send_error_text(tmp_path):
    refuse = {"owner@acme.com": (550, b"no")}
    sender, _ = make_sender(tmp_path, factory=FakeFactory(refuse=refuse))
    with pytest.raises(SendError) as excinfo:
        sender.send_message("anas@omniveer.com", "owner@acme.com", "Hi", "Body.")
    assert PASSWORD not in str(excinfo.value)
