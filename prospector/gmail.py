"""Gmail auth + send (contracts/gmail-send.md).

OAuth (one-time consent + token refresh) uses google-auth(-oauthlib); the actual
send and the identity lookup are plain httpx calls so they are mockable with the
repo's existing respx test infra. Token material is never logged (FR-018).
"""

import base64
import json
from pathlib import Path

import httpx

# Shared transport exceptions: gmail.SendError / gmail.AuthError remain valid
# names for existing callers and tests, but are the provider-neutral classes.
from prospector.transport import AuthError, SendError, build_email

# Least-privilege scopes: send only, plus email address for the identity check.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_raw(
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    from_name: str | None = None,
    reply_to: str | None = None,
) -> str:
    """Base64url-encode a plain-text RFC 2822 message for the Gmail API.

    Built via the shared transport builder so From display-name and Reply-To
    behavior cannot drift between providers. No Message-ID is set — Gmail
    assigns its own id, which is what the ledger stores (003 behavior)."""
    msg = build_email(from_addr, from_name, reply_to, to_addr, subject, body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def _access_token(creds) -> str:
    """Return a valid bearer token, refreshing if needed."""
    if not getattr(creds, "valid", True) and getattr(creds, "refresh_token", None):
        from google.auth.transport.requests import Request

        creds.refresh(Request())
    return creds.token


def send_message(
    creds,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    from_name: str | None = None,
    reply_to: str | None = None,
) -> str:
    """Send one message; return the Gmail message id. Raise SendError on failure."""
    raw = build_raw(from_addr, to_addr, subject, body, from_name=from_name, reply_to=reply_to)
    try:
        response = httpx.post(
            GMAIL_SEND_URL,
            headers={"Authorization": f"Bearer {_access_token(creds)}"},
            json={"raw": raw},
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise SendError(f"gmail send transport error: {exc}") from exc
    if response.status_code // 100 != 2:
        raise SendError(f"gmail send failed: HTTP {response.status_code} {response.text}")
    return response.json().get("id", "")


def account_email(creds) -> str:
    """Resolve the email address the credentials belong to (for the identity guard)."""
    try:
        response = httpx.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {_access_token(creds)}"},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise SendError(f"userinfo transport error: {exc}") from exc
    if response.status_code // 100 != 2:
        raise SendError(f"userinfo failed: HTTP {response.status_code}")
    return (response.json().get("email") or "").strip()


def load_or_authorize(client_secret_path: str | Path, token_path: str | Path, scopes=None):
    """Load a stored token (refreshing if needed) or run one-time desktop consent.

    Persists the refreshable credentials to token_path (gitignored). Returns a
    google.oauth2.credentials.Credentials. Never logs token material."""
    scopes = scopes or SCOPES
    client_secret_path = Path(client_secret_path)
    token_path = Path(token_path)

    from google.oauth2.credentials import Credentials

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_info(
            json.loads(token_path.read_text(encoding="utf-8")), scopes
        )

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
        _persist(creds, token_path)
        return creds

    # No usable token → run one-time consent.
    if not client_secret_path.exists():
        raise AuthError(
            f"OAuth client secret not found at {client_secret_path}. "
            "Download it from Google Cloud (Desktop OAuth client) into secrets/."
        )
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes)
    creds = flow.run_local_server(port=0)
    _persist(creds, token_path)
    return creds


def _persist(creds, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")


class GmailSender:
    """EmailSender adapter over this module's OAuth + httpx mechanics
    (contracts/email-sender.md). Feature 003 behavior, unchanged: the ledger
    stores the Gmail-assigned message id."""

    def __init__(self, settings):
        self._settings = settings
        self._creds = None

    def _credentials(self):
        if self._creds is None:
            self._creds = load_or_authorize(
                self._settings.gmail_client_secret_path,
                self._settings.gmail_token_path,
            )
        return self._creds

    def verify_identity(self) -> str:
        """One-time consent if needed, then the OAuth account's address."""
        try:
            return account_email(self._credentials())
        except SendError as exc:
            # Identity resolution failing is an auth problem, fatal to the run.
            raise AuthError(str(exc)) from exc

    def send_message(
        self, from_address: str, to_address: str, subject: str, body: str
    ) -> str:
        return send_message(
            self._credentials(),
            from_address,
            to_address,
            subject,
            body,
            from_name=self._settings.send_name,
            reply_to=self._settings.reply_to,
        )
