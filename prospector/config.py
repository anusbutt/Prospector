"""Settings loaded from .env / process environment. Secrets never live in code."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_VAULT = "Vault/Outreach"

# --- Approved-send (features 003/004) defaults ---
# PROSPECTOR_SEND_FROM has NO built-in default (constitution v4.0.0): the
# dedicated outreach mailbox must be configured explicitly, never assumed.
DEFAULT_SEND_PROVIDER = "gmail"  # backward compatible; "smtp" for e.g. Zoho
DEFAULT_SMTP_SECURITY = "ssl"  # implicit TLS (port 465); or "starttls" (587)
DEFAULT_SEND_CAPS = "15,30,60,100"  # weekly ramp; last value applies to week 4+
DEFAULT_SEND_DELAY = "30,90"  # randomized seconds between real sends: min,max
DEFAULT_LEDGER = "send_ledger.jsonl"
DEFAULT_DM_LEDGER = "dm_ledger.jsonl"  # assisted-manual Messenger deliveries (007)
DEFAULT_GMAIL_CLIENT = "secrets/gmail_client_secret.json"
DEFAULT_GMAIL_TOKEN = "secrets/gmail_token.json"

VALID_SEND_PROVIDERS = ("gmail", "smtp")
VALID_SMTP_SECURITY = ("ssl", "starttls")


class ConfigError(Exception):
    pass


@dataclass
class Settings:
    openrouter_key: str | None
    openrouter_model: str
    places_key: str | None
    hunter_key: str | None
    vault_dir: Path
    send_from: str | None = None  # required for `send`; no hardcoded account
    send_provider: str = DEFAULT_SEND_PROVIDER
    send_name: str | None = None  # From display name, e.g. "Anas from Omniveer"
    reply_to: str | None = None
    smtp_host: str | None = None
    smtp_port: str | None = None  # raw env value; validated/resolved lazily
    smtp_security: str = DEFAULT_SMTP_SECURITY
    smtp_username: str | None = None
    smtp_password: str | None = field(default=None, repr=False)  # never logged
    send_caps: list[int] = field(default_factory=lambda: [15, 30, 60, 100])
    send_delay: tuple[int, int] = (30, 90)
    ledger_path: Path = field(default_factory=lambda: Path(DEFAULT_LEDGER))
    dm_ledger_path: Path = field(default_factory=lambda: Path(DEFAULT_DM_LEDGER))
    gmail_client_secret_path: Path = field(
        default_factory=lambda: Path(DEFAULT_GMAIL_CLIENT)
    )
    gmail_token_path: Path = field(default_factory=lambda: Path(DEFAULT_GMAIL_TOKEN))

    def require_llm(self) -> None:
        if not self.openrouter_key:
            raise ConfigError(
                "OPENROUTER_API_KEY is not set. Add it to .env (see .env.example) "
                "or run with --no-llm to skip drafting."
            )

    def require_instructions(self):
        """Pre-flight the drafting instruction files (006, FR-323/FR-325).

        Loads once per run and returns the InstructionSet, so `run` fails
        before touching the network or writing a note when a file is missing
        or the assembled context is oversized. Imported lazily: `--help` and
        `--no-llm` should not pay for it."""
        from prospector.instructions import load_instructions

        return load_instructions()

    def require_places(self) -> None:
        if not self.places_key:
            raise ConfigError(
                "GOOGLE_PLACES_API_KEY is not set. Add it to .env (see .env.example); "
                "sourcing has no fallback discovery mechanism."
            )

    def resolved_smtp_port(self) -> int:
        """SMTP port: explicit value, else the security mode's standard port."""
        if not self.smtp_port:
            return 465 if self.smtp_security == "ssl" else 587
        try:
            port = int(self.smtp_port)
        except ValueError:
            port = 0
        if port <= 0:
            raise ConfigError(
                f"PROSPECTOR_SMTP_PORT must be a positive integer (got {self.smtp_port!r})."
            )
        return port

    def require_send(self) -> None:
        """Pre-flight for `prospector send` (features 003/004). No network.

        Validates provider selection, the sender identity, and — for smtp —
        the full transport config, including the From==username anti-spoofing
        rule. Error messages name env variables; secret VALUES are never
        echoed (FR-111)."""
        if self.send_provider not in VALID_SEND_PROVIDERS:
            raise ConfigError(
                f"PROSPECTOR_SEND_PROVIDER must be one of {'/'.join(VALID_SEND_PROVIDERS)} "
                f"(got {self.send_provider!r})."
            )
        if not self.send_from:
            raise ConfigError(
                "PROSPECTOR_SEND_FROM is not set. Set it to the dedicated outreach "
                "mailbox (never a personal account); see .env.example."
            )
        if self.send_provider != "smtp":
            return
        if not self.smtp_host:
            raise ConfigError(
                "PROSPECTOR_SMTP_HOST is not set (required for PROSPECTOR_SEND_PROVIDER=smtp)."
            )
        if not self.smtp_username:
            raise ConfigError(
                "PROSPECTOR_SMTP_USERNAME is not set (required for PROSPECTOR_SEND_PROVIDER=smtp)."
            )
        if not self.smtp_password:
            raise ConfigError(
                "PROSPECTOR_SMTP_PASSWORD is not set (required for "
                "PROSPECTOR_SEND_PROVIDER=smtp). Put it in .env only — never commit it."
            )
        if self.smtp_security not in VALID_SMTP_SECURITY:
            raise ConfigError(
                f"PROSPECTOR_SMTP_SECURITY must be one of {'/'.join(VALID_SMTP_SECURITY)} "
                f"(got {self.smtp_security!r})."
            )
        self.resolved_smtp_port()
        if _normalize_addr(self.send_from) != _normalize_addr(self.smtp_username):
            raise ConfigError(
                "PROSPECTOR_SEND_FROM must equal PROSPECTOR_SMTP_USERNAME: sending with "
                "a From address different from the authenticated mailbox is refused "
                "(no From spoofing)."
            )


def _normalize_addr(addr: str) -> str:
    """Case-insensitive email comparison key (headers keep their casing)."""
    return addr.strip().lower()


def _parse_caps(raw: str) -> list[int]:
    try:
        caps = [int(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise ConfigError(
            f"PROSPECTOR_SEND_CAPS must be comma-separated integers (got {raw!r})."
        )
    if not caps or any(c < 0 for c in caps):
        raise ConfigError(
            f"PROSPECTOR_SEND_CAPS must list one or more non-negative integers (got {raw!r})."
        )
    return caps


def _parse_delay(raw: str) -> tuple[int, int]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        raise ConfigError(
            f"PROSPECTOR_SEND_DELAY must be 'min,max' seconds (got {raw!r})."
        )
    if len(nums) != 2 or nums[0] < 0 or nums[1] < nums[0]:
        raise ConfigError(
            f"PROSPECTOR_SEND_DELAY must be 'min,max' with 0 <= min <= max (got {raw!r})."
        )
    return (nums[0], nums[1])


def load_settings(env_file: str | Path = ".env") -> Settings:
    # override=False: real environment variables win over .env values
    load_dotenv(env_file, override=False)
    return Settings(
        openrouter_key=os.environ.get("OPENROUTER_API_KEY") or None,
        openrouter_model=os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL,
        places_key=os.environ.get("GOOGLE_PLACES_API_KEY") or None,
        hunter_key=os.environ.get("HUNTER_API_KEY") or None,
        vault_dir=Path(os.environ.get("PROSPECTOR_VAULT") or DEFAULT_VAULT),
        send_from=os.environ.get("PROSPECTOR_SEND_FROM") or None,
        send_provider=(os.environ.get("PROSPECTOR_SEND_PROVIDER") or DEFAULT_SEND_PROVIDER)
        .strip()
        .lower(),
        send_name=os.environ.get("PROSPECTOR_SEND_NAME") or None,
        reply_to=os.environ.get("PROSPECTOR_REPLY_TO") or None,
        smtp_host=os.environ.get("PROSPECTOR_SMTP_HOST") or None,
        smtp_port=os.environ.get("PROSPECTOR_SMTP_PORT") or None,
        smtp_security=(os.environ.get("PROSPECTOR_SMTP_SECURITY") or DEFAULT_SMTP_SECURITY)
        .strip()
        .lower(),
        smtp_username=os.environ.get("PROSPECTOR_SMTP_USERNAME") or None,
        smtp_password=os.environ.get("PROSPECTOR_SMTP_PASSWORD") or None,
        send_caps=_parse_caps(os.environ.get("PROSPECTOR_SEND_CAPS") or DEFAULT_SEND_CAPS),
        send_delay=_parse_delay(os.environ.get("PROSPECTOR_SEND_DELAY") or DEFAULT_SEND_DELAY),
        ledger_path=Path(os.environ.get("PROSPECTOR_LEDGER") or DEFAULT_LEDGER),
        dm_ledger_path=Path(os.environ.get("PROSPECTOR_DM_LEDGER") or DEFAULT_DM_LEDGER),
        gmail_client_secret_path=Path(
            os.environ.get("PROSPECTOR_GMAIL_CLIENT") or DEFAULT_GMAIL_CLIENT
        ),
        gmail_token_path=Path(os.environ.get("PROSPECTOR_GMAIL_TOKEN") or DEFAULT_GMAIL_TOKEN),
    )
