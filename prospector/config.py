"""Settings loaded from .env / process environment. Secrets never live in code."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_VAULT = "Vault/Outreach"


class ConfigError(Exception):
    pass


@dataclass
class Settings:
    openrouter_key: str | None
    openrouter_model: str
    places_key: str | None
    hunter_key: str | None
    vault_dir: Path

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


def load_settings(env_file: str | Path = ".env") -> Settings:
    # override=False: real environment variables win over .env values
    load_dotenv(env_file, override=False)
    return Settings(
        openrouter_key=os.environ.get("OPENROUTER_API_KEY") or None,
        openrouter_model=os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL,
        places_key=os.environ.get("GOOGLE_PLACES_API_KEY") or None,
        hunter_key=os.environ.get("HUNTER_API_KEY") or None,
        vault_dir=Path(os.environ.get("PROSPECTOR_VAULT") or DEFAULT_VAULT),
    )
