"""Install what tidalamp runs, with winget, when the user says yes.

The zip carries tidalamp and nothing else: mpv is GPL, weighs some 30 MB and
updates on its own, and winget already knows how to install it and keep it
current. So instead of shipping it, the first start without it offers to run
the same command the error message would have told the user to type.

It runs in this console, not hidden: winget shows its progress there, and the
mpv installer asks for elevation (UAC), which the user has to see to accept.

Imports on any system, so it is tested on Linux too.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from ...config import STATE_DIR, write_atomically

# The winget ids, the same ones `distro` names (read off winget's index, not
# from memory: see backends/windows/distro.py).
IDS = {"mpv": "shinchiro.mpv", "cava": "karlstav.cava"}

# A no to an optional package is not asked again; mpv is always asked, since
# nothing plays without it.
DECLINED = STATE_DIR / "declined"


def available() -> bool:
    """Whether winget is here. It ships with Windows 10 and 11, but not with
    every edition (LTSC, Server), and can be removed."""
    return shutil.which("winget") is not None


def command(package: str) -> list[str]:
    """The winget call that installs ``package``, agreeing to its terms up
    front so it does not stop to ask in the middle."""
    return [
        "winget",
        "install",
        "--id",
        IDS[package],
        "--exact",
        "--source",
        "winget",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ]


def install(
    package: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> bool:
    """Run winget for ``package`` in this console. True when it says it did.

    The answer is only a hint: an install that was already there also ends
    in an error code. What counts is whether the program is found afterwards.
    """
    try:
        return run(command(package)).returncode == 0
    except OSError:
        return False


def linked(executable: str, environ: Mapping[str, str] | None = None) -> str | None:
    """Where winget links a portable package's ``executable``, when it is there.

    A portable install (cava's) adds that folder to the PATH, but only for
    processes started after it: this one, which just ran winget, does not
    see it."""
    values = os.environ if environ is None else environ
    base = values.get("LOCALAPPDATA")
    if not base:
        return None
    path = Path(base) / "Microsoft/WinGet/Links" / executable
    return str(path) if path.is_file() else None


def declined(package: str, marker: Path | None = None) -> bool:
    """Whether the user already said no to ``package``."""
    path = DECLINED if marker is None else marker
    try:
        return package in path.read_text(encoding="utf-8").split()
    except OSError:
        return False


def decline(package: str, marker: Path | None = None) -> None:
    """Remember a no, so the question is not asked on every start."""
    path = DECLINED if marker is None else marker
    if declined(package, path):
        return
    try:
        before = path.read_text(encoding="utf-8")
    except OSError:
        before = ""
    # A write that fails asks again next time, which is no worse than before.
    with contextlib.suppress(OSError):
        write_atomically(path, before + f"{package}\n")
