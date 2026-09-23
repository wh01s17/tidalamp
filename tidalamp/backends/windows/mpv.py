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

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

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
