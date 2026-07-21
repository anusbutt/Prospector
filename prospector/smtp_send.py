"""Authenticated SMTP transport (contracts/smtp-sender.md). Stdlib only.

Implements the EmailSender Protocol over smtplib/ssl for custom-domain
mailboxes (e.g. Zoho Mail). One authenticated connection per message — sends
are paced 30–90s apart, so a held connection would idle out, and reconnecting
isolates a broken connection to exactly one send. The SMTP password exists
only in the login() call; it is never logged, echoed, or embedded in
exceptions (FR-111).
"""

import smtplib
import ssl
from email.utils import make_msgid

from prospector.config import Settings
from prospector.transport import AuthError, SendError, build_email

SMTP_TIMEOUT = 30.0  # seconds; bounded connect/dialogue wait


class SmtpSender:
    """EmailSender over authenticated SMTP (implicit SSL or STARTTLS).

    `smtp_factory` maps security mode -> SMTP class and is injectable so tests
    run offline (the smtplib analogue of the repo's respx convention)."""

    def __init__(self, settings: Settings, smtp_factory: dict | None = None):
        self._host = settings.smtp_host
        self._port = settings.resolved_smtp_port()
        self._security = settings.smtp_security
        self._username = settings.smtp_username
        self._password = settings.smtp_password
        self._from_name = settings.send_name
        self._reply_to = settings.reply_to
        self._factory = smtp_factory or {
            "ssl": smtplib.SMTP_SSL,
            "starttls": smtplib.SMTP,
        }

    def _open(self):
        """Connect, negotiate TLS per the security mode, and authenticate.

        Auth failure -> AuthError; connect/TLS trouble -> SendError (the
        caller decides fatality). Exception text carries only the server's
        own response — never the password."""
        context = ssl.create_default_context()
        try:
            if self._security == "ssl":
                conn = self._factory["ssl"](
                    self._host, self._port, timeout=SMTP_TIMEOUT, context=context
                )
            else:  # starttls (require_send() already validated the mode)
                conn = self._factory["starttls"](
                    self._host, self._port, timeout=SMTP_TIMEOUT
                )
                conn.starttls(context=context)
        except (smtplib.SMTPException, OSError) as exc:
            raise SendError(
                f"SMTP connection to {self._host}:{self._port} failed: {exc}"
            ) from exc
        try:
            conn.login(self._username, self._password)
        except smtplib.SMTPAuthenticationError as exc:
            self._quit_quietly(conn)
            raise AuthError(
                f"SMTP authentication failed for {self._username} "
                f"(server said: {exc.smtp_code} {_decode(exc.smtp_error)}). "
                "Check PROSPECTOR_SMTP_PASSWORD (never shown)."
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            self._quit_quietly(conn)
            raise SendError(f"SMTP login dialogue failed: {exc}") from exc
        return conn

    @staticmethod
    def _quit_quietly(conn) -> None:
        try:
            conn.quit()
        except Exception:
            pass

    def verify_identity(self) -> str:
        """Prove the credentials work; return the authenticated username.

        Any failure here is fatal to the run (exit 3), so connection trouble
        is promoted to AuthError."""
        try:
            conn = self._open()
        except SendError as exc:
            raise AuthError(str(exc)) from exc
        self._quit_quietly(conn)
        return self._username

    def send_message(
        self, from_address: str, to_address: str, subject: str, body: str
    ) -> str:
        """Send one message; return its generated Message-ID for the ledger.

        Recipient refusal and any SMTP/transport exception -> SendError
        (failed ledger row; note stays approved; batch continues)."""
        message_id = make_msgid(domain=from_address.rsplit("@", 1)[-1])
        msg = build_email(
            from_address,
            self._from_name,
            self._reply_to,
            to_address,
            subject,
            body,
            message_id=message_id,
        )
        try:
            conn = self._open()
        except AuthError as exc:
            # Mid-batch credential trouble fails this send; it must not crash the run.
            raise SendError(str(exc)) from exc
        try:
            refused = conn.send_message(
                msg, from_addr=from_address, to_addrs=[to_address]
            )
        except smtplib.SMTPRecipientsRefused as exc:
            raise SendError(f"SMTP recipient refused: {_refusals(exc.recipients)}") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise SendError(f"SMTP send to {to_address} failed: {exc}") from exc
        finally:
            self._quit_quietly(conn)
        if refused:
            raise SendError(f"SMTP recipient refused: {_refusals(refused)}")
        return message_id


def _decode(value) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def _refusals(recipients: dict) -> str:
    return "; ".join(
        f"{addr}: {code} {_decode(reason)}"
        for addr, (code, reason) in recipients.items()
    )
