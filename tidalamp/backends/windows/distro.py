"""How to install a system package on Windows: winget, scoop or choco.

The same job as the Linux backend's, with package managers in the place of
distributions: whichever of the three is installed, in that order (winget
ships with Windows 10 and 11). None of them gives the empty string, and the
message drops the parenthetical rather than guessing.

The identifiers were read off each manager's own index on 2026-09-23, not
written from memory: `mpv.net` is another program, and a wrong id sends the
user to it or to nothing.

- winget: `shinchiro.mpv` (0.41.0). Its installer puts mpv in
  `%ProgramFiles%\\MPV Player` **and leaves the PATH alone**, which is why the
  player looks there too (`backends.windows.mpv`).
- scoop: `mpv` lives in the `extras` bucket, not in `main`.
- choco: `mpv`, last updated 2024-09. Last of the three for that reason.

- cava: winget's `karlstav.cava` (1.0.0), an installer into
  `%LOCALAPPDATA%\\cava` that adds it to the user's PATH (`backends.windows.cava`
  looks there too). Not in scoop's main or extras.
"""

from __future__ import annotations

import shutil

from ...i18n import _

# Package manager to the command that installs each package through it.
_COMMANDS: dict[str, dict[str, str]] = {
    "winget": {
        "mpv": "winget install shinchiro.mpv",
        "cava": "winget install karlstav.cava",
    },
    "scoop": {"mpv": "scoop bucket add extras; scoop install extras/mpv"},
    "choco": {"mpv": "choco install mpv"},
}


def install_command(package: str) -> str:
    """``winget install shinchiro.mpv`` and the like, or "" with none known."""
    for manager, packages in _COMMANDS.items():
        if package in packages and shutil.which(manager) is not None:
            return packages[package]
    return ""


def missing(package: str) -> str:
    """Why playback (or the spectrum) cannot start, and what to do about it."""
    command = install_command(package)
    if command:
        return _("{package} no está instalado ({command})").format(
            package=package, command=command
        )
    return _("{package} no está instalado").format(package=package)
