"""Where cava is on Windows, when the PATH does not say.

winget's `karlstav.cava` is an installer, not a portable package: it puts
``cava.exe`` in ``%LOCALAPPDATA%\\cava`` and adds that folder to the user's
PATH, which only processes started afterwards see. A terminal open during the
install, or tidalamp itself right after running winget, would not find it
there, and the offer to install it came back on every start.

Imports on any system, so it is tested on Linux too.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

# Environment variable to the cava.exe under it, in the order they are tried.
PLACES = (
    ("LOCALAPPDATA", "cava/cava.exe"),  # winget: karlstav.cava
    ("LOCALAPPDATA", "Microsoft/WinGet/Links/cava.exe"),  # winget, portable
)


def find(environ: Mapping[str, str] | None = None) -> str | None:
    """The full path of cava.exe where an installer left it, or None."""
    values = os.environ if environ is None else environ
    for variable, rest in PLACES:
        base = values.get(variable)
        if base and (Path(base) / rest).is_file():
            return str(Path(base) / rest)
    return None
