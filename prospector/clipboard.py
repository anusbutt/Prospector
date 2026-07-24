"""Best-effort OS clipboard write for assisted-manual Messenger delivery (007).

Constitution VI (smallest viable build) settles the stack: no third-party
clipboard dependency. We shell out to whatever native copier the platform
provides. This is deliberately best-effort — `copy_to_clipboard` NEVER raises and
returns False when no copier works, so the delivery loop degrades to showing the
draft in the terminal for manual copy rather than aborting (research.md R1,
spec Edge Cases).
"""

import shutil
import subprocess

# (executable, argv-after-exe) — first one present on PATH wins.
_COPIERS: tuple[tuple[str, list[str]], ...] = (
    ("clip.exe", []),  # WSL / Windows
    ("pbcopy", []),  # macOS
    ("wl-copy", []),  # Wayland
    ("xclip", ["-selection", "clipboard"]),  # X11
    ("xsel", ["--clipboard", "--input"]),  # X11 alt
)


def copy_to_clipboard(text: str) -> bool:
    """Copy `text` to the OS clipboard. Return True on success, False if no
    copier is available or the copy failed. Never raises."""
    for exe, args in _COPIERS:
        if shutil.which(exe) is None:
            continue
        try:
            proc = subprocess.run(
                [exe, *args],
                input=text.encode("utf-8"),
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            return True
    return False
