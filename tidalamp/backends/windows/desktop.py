"""The Start menu shortcut on Windows, for now: never offered.

The `.lnk` and its icon are phase F4 in windows.md. Until then this has the
Linux backend's shape and declines everything, which is the policy's own
answer for a system with nowhere to put a launcher: the player opens and
nothing is asked. Without it the Linux backend would offer to write a
`.desktop` file into a Windows home.
"""

from __future__ import annotations

from pathlib import Path

from ...config import STATE_DIR

MARKER = STATE_DIR / "desktop-entry"


def data_dirs() -> list[Path]:
    return []


def existing(dirs: list[Path]) -> Path | None:
    return None


def user_launchers(data_home: Path | None = None) -> list[Path]:
    """No launcher of ours to delete with the user's data."""
    return []


def offer(
    dirs: list[Path] | None = None,
    marker: Path = MARKER,
    executable: str | None = None,
) -> bool:
    return False


def create(
    dirs: list[Path] | None = None,
    marker: Path = MARKER,
    executable: str | None = None,
    on_omarchy: bool | None = None,
) -> Path | None:
    return None


def decline(marker: Path = MARKER) -> None:
    return None
