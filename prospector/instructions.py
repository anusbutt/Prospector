"""Instruction files that steer the drafting call (006, FR-321..FR-325).

These files are CONTENT, not code (Constitution v5.0.0, Additional Constraints):
version-controlled markdown, reviewed like prose, editable without touching
Python. They cannot grant the model capabilities the code withholds — the model
still gets no tools, no network, and no filesystem regardless of what any file
says.

Loaded once per run, not once per company. A missing file or an oversized
assembly is a pre-flight ConfigError (exit 1, nothing written), matching how
every other missing-configuration case in this codebase behaves.
"""

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from prospector.config import ConfigError

# Fixed load order: who you are, what you're offering, the hard rules, then how
# to write. Constraints deliberately precede the writing guidance so the rules
# frame the craft advice rather than trailing it.
REQUIRED_FILES = (
    "agent/IDENTITY.md",
    "agent/OFFER.md",
    "agent/CONSTRAINTS.md",
    "agent/skills/write-cold-email.md",
)

# ~5k tokens, leaving ample room for per-company evidence and the response
# inside a standard context window. A working bound, tunable without a schema
# change — NOT a silent truncation point (FR-325).
MAX_INSTRUCTION_CHARS = 20_000

SEPARATOR = "\n\n---\n\n"


@dataclass
class InstructionSet:
    """The loaded, bounded instruction context for one run."""

    text: str
    sources: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)


def _read(root: Path | None, relative: str) -> str:
    """Read one instruction file from the package, or from `root` in tests."""
    try:
        if root is None:
            return files("prospector").joinpath(relative).read_text(encoding="utf-8")
        return (Path(root) / relative).read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError, ModuleNotFoundError) as exc:
        raise ConfigError(
            f"instruction file not found: {relative}. It ships with the package "
            f"and is required for drafting; restore it or reinstall."
        ) from exc
    except OSError as exc:
        raise ConfigError(f"instruction file could not be read: {relative} ({exc})") from exc


def load_instructions(root: Path | None = None) -> InstructionSet:
    """Load and bound every required instruction file.

    `root` overrides the package location so tests can supply fixtures.
    Raises ConfigError on a missing/unreadable file or an oversized assembly —
    never truncates, because a truncated CONSTRAINTS.md would silently drop
    hard rules, which is the worst available failure."""
    parts: list[str] = []
    sources: list[str] = []
    for relative in REQUIRED_FILES:
        content = _read(root, relative).strip()
        if not content:
            raise ConfigError(f"instruction file is empty: {relative}")
        parts.append(content)
        sources.append(relative)

    text = SEPARATOR.join(parts)
    if len(text) > MAX_INSTRUCTION_CHARS:
        raise ConfigError(
            f"instruction context is {len(text):,} chars (max {MAX_INSTRUCTION_CHARS:,}). "
            f"Trim the files in prospector/agent/ — they are never truncated "
            f"automatically, because dropping part of CONSTRAINTS.md would "
            f"silently weaken the honesty rules."
        )
    return InstructionSet(text=text, sources=sources)
