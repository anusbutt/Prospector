"""Provider-neutral email transport seam (contracts/email-sender.md).

The send pipeline depends only on this module: the `EmailSender` Protocol, the
shared exceptions, the shared message builder, and the provider factory.
Concrete providers (`gmail`, `smtp_send`) are imported lazily so `--help`
stays fast and neither provider is touched unless selected.
"""

from email.message import EmailMessage
from email.utils import formataddr, formatdate
from typing import Protocol

from prospector.config import ConfigError, Settings


class SendError(Exception):
    """One message failed to send (recipient refused, transport error).

    Non-fatal: the pipeline records a `failed` ledger row, leaves the note
    `approved`, and continues. Must never carry credential material."""


class AuthError(Exception):
    """The provider cannot authenticate (OAuth consent / SMTP login failure).

    Fatal to the run (CLI exit 3). Must never carry credential material."""


class EmailSender(Protocol):
    """What the send pipeline needs from any mail provider."""

    def verify_identity(self) -> str:
        """Authenticate and return the address the provider will send as
        (Gmail: the OAuth account; SMTP: the login username). Raises AuthError."""
        ...

    def send_message(
        self, from_address: str, to_address: str, subject: str, body: str
    ) -> str:
        """Deliver one plain-text message; return the provider message id
        (Gmail API id / SMTP Message-ID). Raises SendError on failure."""
        ...


def build_email(
    from_address: str,
    from_name: str | None,
    reply_to: str | None,
    to_address: str,
    subject: str,
    body: str,
    message_id: str | None = None,
) -> EmailMessage:
    """The single message-construction path for every provider.

    From uses the RFC-formatted display-name pair when a name is configured
    (e.g. `Anas from Omniveer <anas@omniveer.com>`), else the bare address.
    Plain text only — no HTML, no tracking headers."""
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_address)) if from_name else from_address
    msg["To"] = to_address
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Date"] = formatdate(localtime=True)
    if message_id:
        msg["Message-ID"] = message_id
    msg.set_content(body)
    return msg


def create_sender(settings: Settings) -> EmailSender:
    """Build the configured provider's sender. Callers run
    `settings.require_send()` first; the unknown-provider raise is a backstop.
    Never called on the dry-run path (dry-run constructs no sender)."""
    if settings.send_provider == "gmail":
        from prospector.gmail import GmailSender

        return GmailSender(settings)
    if settings.send_provider == "smtp":
        from prospector.smtp_send import SmtpSender

        return SmtpSender(settings)
    raise ConfigError(
        f"unknown send provider {settings.send_provider!r} (expected 'gmail' or 'smtp')"
    )
