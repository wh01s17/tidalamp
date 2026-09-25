"""Where mpv is on Windows, where it is seldom on the PATH.

Looked for in order: ``mpv.exe`` on the PATH, then where each package manager
puts it. The folders are not a formality: winget's `shinchiro.mpv` installs
to ``%ProgramFiles%\\MPV Player`` and does not touch the PATH at all, and a
terminal opened before an install does not see a PATH that did change.

``mpv.exe`` and never plain ``mpv``: `shutil.which("mpv")` walks PATHEXT,
where ``.COM`` comes before ``.EXE``, and the official builds ship an
``mpv.com`` console wrapper beside the ``mpv.exe``. The result is a full
path, because `CreateProcess` does not consult PATHEXT the way `which` did.

Imports on any system, so it is tested on Linux too.
"""

from __future__ import annotations

import functools
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

log = logging.getLogger("tidalamp.player")

_NO_WINDOW = 0
if sys.platform == "win32":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW

# Environment variable to the mpv.exe under it, in the order they are tried.
PLACES = (
    ("ProgramFiles", "MPV Player/mpv.exe"),  # winget: shinchiro.mpv
    ("ProgramFiles", "mpv/mpv.exe"),
    ("USERPROFILE", "scoop/shims/mpv.exe"),  # scoop: extras/mpv
    ("ProgramData", "chocolatey/bin/mpv.exe"),  # choco: mpv
    ("LOCALAPPDATA", "Microsoft/WinGet/Links/mpv.exe"),  # winget, portable
)


def find(environ: Mapping[str, str] | None = None) -> str | None:
    """The full path of mpv.exe, or None when it is nowhere we know of."""
    found = shutil.which("mpv.exe")
    if found:
        return found
    values = os.environ if environ is None else environ
    for variable, rest in PLACES:
        base = values.get(variable)
        if base and (Path(base) / rest).is_file():
            return str(Path(base) / rest)
    return None


def media_controls_off(executable: tuple[str, ...]) -> list[str]:
    """``--media-controls=no``, when this mpv has the option.

    Recent mpv registers media controls of its own on Windows, a session of
    its own in the volume flyout. The media keys went to it and
    not to tidalamp's: play/pause paused mpv behind the app's back, and next
    and previous asked mpv's playlist, which only ever holds the one track,
    so they did nothing (seen on mpv 0.41, 2026-09-24). Off, tidalamp's
    session is the only one.

    Asked of mpv rather than assumed: an option it does not know is a fatal
    error, and an older mpv would not start at all.
    """
    return ["--media-controls=no"] if _knows(executable, "--media-controls") else []


@functools.cache
def _knows(executable: tuple[str, ...], option: str) -> bool:
    """Whether ``--list-options`` names ``option``. Once per mpv."""
    try:
        listed = subprocess.run(
            [*executable, "--no-config", "--list-options"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=_NO_WINDOW,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("no se pudo preguntar a mpv por sus opciones: %s", exc)
        return False
    return any(line.split()[:1] == [option] for line in listed.splitlines())
