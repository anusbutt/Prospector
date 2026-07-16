"""Settings loaded from .env / process environment. Secrets never live in code."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_VAULT = "Vault/Outreach"

# --- Approved-send (feature 003) defaults ---
DEFAULT_SEND_FROM = "nestaroassistant@gmail.com"
DEFAULT_SEND_CAPS = "15,30,60,100"  # weekly ramp; last value applies to week 4+
DEFAULT_SEND_DELAY = "30,90"  # randomized seconds between real sends: min,max
DEFAULT_LEDGER = "send_ledger.jsonl"
DEFAULT_GMAIL_CLIENT = "secrets/gmail_client_secret.json"
DEFAULT_GMAIL_TOKEN = "secrets/gmail_token.json"


class ConfigError(Exception):
    pass


@dataclass
class Settings:
    openrouter_key: str | None
    openrouter_model: str
    places_key: str | None
    hunter_key: str | None
    vault_dir: Path
    send_from: str = DEFAULT_SEND_FROM
    send_caps: list[int] = field(default_factory=lambda: [15, 30, 60, 100])
    send_delay: tuple[int, int] = (30, 90)
    ledger_path: Path = field(default_factory=lambda: Path(DEFAULT_LEDGER))
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

    def require_places(self) -> None:
        if not self.places_key:
            raise ConfigError(
                "GOOGLE_PLACES_API_KEY is not set. Add it to .env (see .env.example); "
                "sourcing has no fallback discovery mechanism."
            )


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
        send_from=os.environ.get("PROSPECTOR_SEND_FROM") or DEFAULT_SEND_FROM,
        send_caps=_parse_caps(os.environ.get("PROSPECTOR_SEND_CAPS") or DEFAULT_SEND_CAPS),
        send_delay=_parse_delay(os.environ.get("PROSPECTOR_SEND_DELAY") or DEFAULT_SEND_DELAY),
        ledger_path=Path(os.environ.get("PROSPECTOR_LEDGER") or DEFAULT_LEDGER),
        gmail_client_secret_path=Path(
            os.environ.get("PROSPECTOR_GMAIL_CLIENT") or DEFAULT_GMAIL_CLIENT
        ),
        gmail_token_path=Path(os.environ.get("PROSPECTOR_GMAIL_TOKEN") or DEFAULT_GMAIL_TOKEN),
    )
