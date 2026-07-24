"""Per-vertical profiles: the offer as selectable content, not code (008).

Constitution v7.0.0, Principle VI: the offer, sender identity, writing guidance,
locked fallback copy, note tags, promotional link, and default sourcing keywords
are supplied by a named profile. Adding a vertical MUST NOT require changing
application code, which is why profiles are resolved from a search path that
puts the operator's own directory ahead of anything shipped in the package.

Everything is validated up front. A profile missing its locked fallback would
let a batch run with no safe answer available when generated copy fails
validation — so that is a startup ConfigError (exit 1, nothing written), the
same way every other missing-configuration case in this codebase behaves.
"""

import os
import tomllib
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from prospector.config import ConfigError
from prospector.instructions import InstructionSet, load_instructions

REQUIRED_FILES = (
    "IDENTITY.md",
    "OFFER.md",
    "CONSTRAINTS.md",
    "skills/write-cold-email.md",
    "fallback.md",
    "profile.toml",
)

REQUIRED_KEYS = ("tags", "signature", "product_url", "keywords", "banned_claims")

TEMPLATE_HEADING = "## Template"
INVARIANTS_HEADING = "## Invariants"


@dataclass
class Profile:
    """One vertical's offer content, loaded and validated once per run."""

    name: str
    root: Path
    instructions: InstructionSet
    fallback_template: str
    fallback_invariants: list[str]
    tags: list[str]
    signature: str
    product_url: str
    keywords: list[str] = field(default_factory=list)
    banned_claims: list[str] = field(default_factory=list)

    @property
    def tags_line(self) -> str:
        """Frontmatter rendering of `tags`, e.g. "[outreach, hvac]"."""
        return "[" + ", ".join(self.tags) + "]"


def search_paths() -> list[Path]:
    """Directories searched for profiles, most specific first (research.md R3).

    The operator's own directory wins so that adding a vertical never means
    editing an installed package."""
    paths: list[Path] = []
    env = os.environ.get("PROSPECTOR_PROFILES")
    if env:
        paths.append(Path(env))
    paths.append(Path.cwd() / "profiles")
    try:
        paths.append(Path(str(files("prospector").joinpath("profiles"))))
    except (ModuleNotFoundError, TypeError):  # pragma: no cover - packaging edge
        pass
    return paths


def discover() -> list[str]:
    """Available profile names, de-duplicated, in search-path precedence."""
    names: list[str] = []
    for base in search_paths():
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and child.name not in names:
                names.append(child.name)
    return names


def _locate(name: str) -> Path:
    for base in search_paths():
        candidate = base / name
        if candidate.is_dir():
            return candidate
    available = ", ".join(discover()) or "(none)"
    raise ConfigError(
        f"profile {name!r} not found. Available: {available}. "
        f"Profiles are directories under ./profiles/ or $PROSPECTOR_PROFILES."
    )


def _read(root: Path, name: str, relative: str) -> str:
    path = root / relative
    try:
        content = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ConfigError(
            f"profile {name!r} is missing required file: {relative}"
        ) from exc
    except OSError as exc:
        raise ConfigError(f"profile {name!r}: {relative} could not be read ({exc})") from exc
    if not content.strip():
        raise ConfigError(f"profile {name!r} has an empty required file: {relative}")
    return content


def _parse_fallback(name: str, text: str) -> tuple[str, list[str]]:
    """Split fallback.md into its locked template and its invariants.

    Both sections are mandatory: the template is what answers when generated
    copy fails validation, and the invariants are what prove it was not
    paraphrased on the way out."""
    if TEMPLATE_HEADING not in text or INVARIANTS_HEADING not in text:
        raise ConfigError(
            f"profile {name!r}: fallback.md must contain "
            f"'{TEMPLATE_HEADING}' and '{INVARIANTS_HEADING}'"
        )
    _, rest = text.split(TEMPLATE_HEADING, 1)
    template, invariant_block = rest.split(INVARIANTS_HEADING, 1)
    template = template.strip("\n")
    invariants = [
        line.lstrip("-").strip()
        for line in invariant_block.splitlines()
        if line.strip().startswith("-")
    ]
    if not template.strip():
        raise ConfigError(f"profile {name!r}: fallback.md has an empty {TEMPLATE_HEADING} section")
    if not invariants:
        raise ConfigError(f"profile {name!r}: fallback.md lists no invariants")
    return template, invariants


def _parse_config(name: str, text: str) -> dict:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"profile {name!r}: profile.toml is not valid TOML ({exc})") from exc
    for key in REQUIRED_KEYS:
        if key not in data:
            raise ConfigError(f"profile {name!r}: profile.toml is missing required key: {key}")
    return data


def load(name: str) -> Profile:
    """Locate, read and validate a profile. Raises ConfigError on any problem.

    Callers run this as a pre-flight, before any company is processed, so a
    malformed profile costs nothing and writes nothing (FR-018/FR-019)."""
    root = _locate(name)
    for relative in REQUIRED_FILES:
        _read(root, name, relative)  # presence + non-empty

    template, invariants = _parse_fallback(name, _read(root, name, "fallback.md"))
    config = _parse_config(name, _read(root, name, "profile.toml"))

    try:
        instructions = load_instructions(root)
    except ConfigError as exc:
        raise ConfigError(f"profile {name!r}: {exc}") from exc

    return Profile(
        name=name,
        root=root,
        instructions=instructions,
        fallback_template=template,
        fallback_invariants=invariants,
        tags=list(config["tags"]),
        signature=str(config["signature"]),
        product_url=str(config["product_url"]),
        keywords=list(config["keywords"]),
        banned_claims=list(config["banned_claims"]),
    )
