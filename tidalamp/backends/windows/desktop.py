"""The Start menu shortcut that puts tidalamp among the user's programs.

pip and pipx install `tidalamp.exe` and nothing else, so the Start menu never
learns tidalamp exists. The first start that opens the player asks whether to
add a shortcut, with the Linux backend's policy, which is the valuable part:
asked once, a no is not asked again (the same marker), a shortcut deleted by
hand is not written back, one already there settles it, and nothing here may
stop the player from opening.

The shortcut opens Windows Terminal when there is one, which is where the
TUI looks as it should; otherwise tidalamp.exe runs in the console it opens.

A `.lnk` is written through the shell's COM object, from PowerShell, so no
dependency comes in for it. The script is fixed text and every value reaches
it through the environment: a path with a quote in it cannot become code, and
a value starting with a dash cannot be read as one of PowerShell's options.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from ...config import STATE_DIR, write_atomically

log = logging.getLogger("tidalamp.desktop")

FILE_NAME = "TidalAmp.lnk"
MARKER = STATE_DIR / "desktop-entry"

# The shortcut, from values PowerShell reads off its own environment.
_SCRIPT = (
    "$ErrorActionPreference = 'Stop'; "
    "$link = (New-Object -ComObject WScript.Shell).CreateShortcut($env:TIDALAMP_LNK); "
    "$link.TargetPath = $env:TIDALAMP_LNK_TARGET; "
    "$link.Arguments = $env:TIDALAMP_LNK_ARGUMENTS; "
    "$link.IconLocation = $env:TIDALAMP_LNK_ICON; "
    "$link.Description = $env:TIDALAMP_LNK_DESCRIPTION; "
    "$link.Save()"
)

_NO_WINDOW = 0
if sys.platform == "win32":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW


def data_dirs() -> list[Path]:
    """The Start menu's program folders, the user's own first."""
    home = Path.home()
    roaming = Path(os.environ.get("APPDATA") or home / "AppData/Roaming")
    shared = Path(os.environ.get("PROGRAMDATA") or "C:/ProgramData")
    tail = Path("Microsoft/Windows/Start Menu/Programs")
    return [roaming / tail, shared / tail]


def existing(dirs: list[Path]) -> Path | None:
    """A shortcut to tidalamp already in the menu. A `.lnk` is binary, so it
    goes by its name: ours, whatever case the file system kept."""
    for folder in dirs:
        try:
            for candidate in folder.iterdir():
                if candidate.name.lower() == FILE_NAME.lower():
                    return candidate
        except OSError:
            continue
    return None


def user_launchers(data_home: Path | None = None) -> list[Path]:
    """Our shortcut in the user's own menu, for a logout that takes the data.
    Only the user's folder: a shared one belongs to whoever installed it."""
    folder = data_dirs()[0] if data_home is None else data_home
    found = existing([folder])
    return [found] if found is not None else []


def command() -> str:
    """The absolute path of what runs tidalamp, or "" when it cannot be told."""
    if getattr(sys, "frozen", False):
        return sys.executable  # the .exe from the release zip
    found = shutil.which("tidalamp")
    return str(Path(found).absolute()) if found else ""


def shortcut(executable: str) -> tuple[str, str]:
    """What the shortcut runs, and with which arguments."""
    terminal = shutil.which("wt.exe")
    if terminal:
        return terminal, f'"{executable}" tui'
    return executable, "tui"


def _icon() -> str:
    return str(resources.files("tidalamp").joinpath("tidalamp.ico"))


def _enabled() -> bool:
    return not os.environ.get("TIDALAMP_NO_DESKTOP_ENTRY") and sys.platform == "win32"


def offer(
    dirs: list[Path] | None = None,
    marker: Path = MARKER,
    executable: str | None = None,
) -> bool:
    """Whether to ask about the shortcut on this start."""
    if not _enabled():
        return False
    try:
        if marker.exists():
            return False
        found = existing(data_dirs() if dirs is None else dirs)
        if found is not None:
            log.info("ya hay un acceso directo de tidalamp en %s", found)
            _mark(marker, str(found))
            return False
    except OSError as exc:
        log.warning("no se pudo comprobar el acceso directo: %s", exc)
        return False
    return bool(command() if executable is None else executable)


def create(
    dirs: list[Path] | None = None,
    marker: Path = MARKER,
    executable: str | None = None,
    on_omarchy: bool | None = None,
) -> Path | None:
    """Write the shortcut. The path written, or None. ``on_omarchy`` is the
    Linux backend's and means nothing here."""
    dirs = data_dirs() if dirs is None else dirs
    run = command() if executable is None else executable
    if not run:
        return None
    target = dirs[0] / FILE_NAME
    try:
        if existing([dirs[0]]) is not None:
            _mark(marker, str(target))
            return None
        dirs[0].mkdir(parents=True, exist_ok=True)
        program, arguments = shortcut(run)
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
            env={
                **os.environ,
                "TIDALAMP_LNK": str(target),
                "TIDALAMP_LNK_TARGET": program,
                "TIDALAMP_LNK_ARGUMENTS": arguments,
                "TIDALAMP_LNK_ICON": _icon(),
                "TIDALAMP_LNK_DESCRIPTION": "TIDAL client for the terminal",
            },
            capture_output=True,
            timeout=30,
            check=True,
            creationflags=_NO_WINDOW,
        )
        _mark(marker, str(target))
        return target
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("no se pudo crear el acceso directo: %s", exc)
        return None


def decline(marker: Path = MARKER) -> None:
    """Remember a no, so the question is not asked again."""
    try:
        _mark(marker, "declined")
    except OSError as exc:
        log.warning("no se pudo guardar la respuesta: %s", exc)


def _mark(marker: Path, answer: str) -> None:
    write_atomically(marker, f"{answer}\n")
