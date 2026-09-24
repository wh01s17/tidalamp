"""The Start menu shortcut that puts tidalamp among the user's programs.

pip and pipx install `tidalamp.exe` and nothing else, so the Start menu never
learns tidalamp exists. The first start that opens the player asks whether to
add a shortcut, with the Linux backend's policy, which is the valuable part:
asked once, a no is not asked again (the same marker), a shortcut deleted by
hand is not written back, one already there settles it, and nothing here may
stop the player from opening.

The shortcut opens Windows Terminal when there is one, which is where the
TUI looks as it should; otherwise tidalamp.exe runs in the console it opens.

A yes also puts a copy on the desktop, which is where Windows users look for
a program they just installed. The Start menu's is the one that counts: the
desktop's is written after it, a failure there only reaches the log, and one
already on the desktop is left as it is.

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
import uuid
from importlib import resources
from pathlib import Path

from ...config import STATE_DIR, write_atomically
from ...i18n import _

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

# FOLDERID_Desktop, from KnownFolders.h.
_DESKTOP = uuid.UUID("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}")


def question() -> str:
    """What the first start asks."""
    return _("¿AÑADIR TIDALAMP AL MENÚ INICIO Y AL ESCRITORIO?")


def created() -> str:
    """What the status line says once the shortcut is made."""
    return _("tidalamp ya está en el menú Inicio y en el escritorio")


def setting() -> tuple[str, str]:
    """The settings window's row: its name, and what it does."""
    return _("Accesos directos"), _("añade tidalamp al menú Inicio y al escritorio")


def data_note() -> str:
    """What the logout window says the data is. Both shortcuts go with it,
    the Start menu's and the desktop's (`user_launchers`)."""
    return _(
        "Los datos son la configuración, la cola, el ecualizador,\n"
        "la caché y los accesos directos del menú Inicio y del escritorio."
    )


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
    """Our shortcuts in the user's own menu and on the desktop, for a logout
    that takes the data. Only the user's folder: a shared one belongs to
    whoever installed it. With ``data_home``, only that folder is looked in."""
    folders = [data_dirs()[0]] if data_home is None else [data_home]
    if data_home is None:
        desktop = _desktop_folder()
        if desktop is not None:
            folders.append(desktop)
    found = (existing([folder]) for folder in folders)
    return [path for path in found if path is not None]


def _desktop_folder() -> Path | None:
    """The user's desktop, wherever it is. OneDrive moves it out of the
    profile's own folder when it backs the desktop up, so the path is asked
    of the shell rather than guessed. None when it cannot be told."""
    if sys.platform != "win32":
        return None
    import ctypes

    found = ctypes.c_wchar_p()
    folder_id = ctypes.create_string_buffer(_DESKTOP.bytes_le, 16)
    result = ctypes.windll.shell32.SHGetKnownFolderPath(
        folder_id, 0, None, ctypes.byref(found)
    )
    try:
        if result != 0 or not found.value:
            log.warning("no se encontró la carpeta del escritorio (%#x)", result)
            return None
        return Path(found.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(found)


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
        _write(target, program, arguments)
        _mark(marker, str(target))
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("no se pudo crear el acceso directo: %s", exc)
        return None
    _put_on_desktop(program, arguments)
    return target


def _put_on_desktop(program: str, arguments: str) -> None:
    """The desktop's copy; never a reason to report the shortcut failed."""
    try:
        folder = _desktop_folder()
        if folder is None or existing([folder]) is not None:
            return
        _write(folder / FILE_NAME, program, arguments)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("no se pudo crear el acceso directo del escritorio: %s", exc)


def _write(target: Path, program: str, arguments: str) -> None:
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


def decline(marker: Path = MARKER) -> None:
    """Remember a no, so the question is not asked again."""
    try:
        _mark(marker, "declined")
    except OSError as exc:
        log.warning("no se pudo guardar la respuesta: %s", exc)


def _mark(marker: Path, answer: str) -> None:
    write_atomically(marker, f"{answer}\n")
