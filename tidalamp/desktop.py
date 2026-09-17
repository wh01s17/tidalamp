"""The launcher entry that puts tidalamp in the desktop's application menu.

pipx and pip install a command and nothing else, so the menu never learns
tidalamp exists; only the AUR package ships a `.desktop` file. The first launch
that opens the player asks whether to write one to
`~/.local/share/applications`, where every freedesktop menu looks, Omarchy's
included.

It is asked once. A marker in the state directory keeps the answer, so a no
is not asked again and a launcher deleted by hand is not written back. An
entry already found that launches tidalamp settles it without asking: the
AUR's, or one made with `omarchy-tui-install`. Nothing here may stop the
player from opening, so every failure is logged and swallowed.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from importlib import resources
from pathlib import Path

from .config import STATE_DIR, _xdg, write_atomically

log = logging.getLogger("tidalamp.desktop")

# MPRIS announces `DesktopEntry=tidalamp`: with this file name the desktop
# matches the media controls to the launcher and its icon.
FILE_NAME = "tidalamp.desktop"
MARKER = STATE_DIR / "desktop-entry"
ICON_NAME = "tidalamp"

_EXEC = re.compile(r"^Exec=.*\btidalamp\b", re.MULTILINE)


def data_dirs() -> list[Path]:
    """Where menus read `applications/` from, the user's own first."""
    home = _xdg("XDG_DATA_HOME", ".local/share")
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [home, *(Path(part) for part in system.split(":") if part)]


def existing(dirs: list[Path]) -> Path | None:
    """An entry that already launches tidalamp, under any file name."""
    for base in dirs:
        folder = base / "applications"
        if (folder / FILE_NAME).exists():
            # Even one without Exec: a `Hidden=true` override is a choice.
            return folder / FILE_NAME
        try:
            candidates = sorted(folder.glob("*.desktop"))
        except OSError:
            continue
        for candidate in candidates:
            try:
                if _EXEC.search(candidate.read_text(errors="replace")):
                    return candidate
            except OSError:
                continue
    return None


def user_launchers(data_home: Path | None = None) -> list[Path]:
    """Every launcher of tidalamp in the user's own menu folder, and its icon.

    What a logout that takes the app's data deletes: ours, `tidalamp.desktop`,
    and one written for it under another name, such as `omarchy-tui-install`'s
    `TidalAmp.desktop`, which would otherwise keep the first start from asking.
    Only the user's folder: the system's belong to a package.
    """
    home = data_dirs()[0] if data_home is None else data_home
    folder = home / "applications"
    found: list[Path] = []
    try:
        candidates = sorted(folder.glob("*.desktop"))
    except OSError:
        candidates = []
    for candidate in candidates:
        try:
            if candidate.name == FILE_NAME or _EXEC.search(
                candidate.read_text(errors="replace")
            ):
                found.append(candidate)
        except OSError:
            continue
    icon = home / "icons/hicolor/scalable/apps" / f"{ICON_NAME}.svg"
    if icon.exists():
        found.append(icon)
    return found


def command() -> str:
    """The absolute command a menu can run, or "" when it cannot be told."""
    found = shutil.which("tidalamp")
    if found:
        return str(Path(found).absolute())
    argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if argv0 is not None and argv0.name == "tidalamp" and argv0.is_file():
        return str(argv0.absolute())
    return ""


def omarchy() -> bool:
    """Omarchy opens terminal apps its own way, with a window rule per style."""
    return bool(shutil.which("omarchy-launch-tui")) or Path("/usr/share/omarchy").is_dir()


def _quoted(path: str) -> str:
    """An Exec argument, quoted the way the Desktop Entry spec asks."""
    if not re.search(r'[\s"`$\\]', path):
        return path
    escaped = re.sub(r'(["`$\\])', r"\\\1", path)
    return f'"{escaped}"'


def entry(executable: str, on_omarchy: bool) -> str:
    """The text of the launcher."""
    run = f"{_quoted(executable)} tui"
    if on_omarchy:
        # What `omarchy-tui-install` writes: Omarchy's terminal, tiled.
        exec_line = f"Exec=xdg-terminal-exec --app-id=TUI.tile -e {run}"
        terminal = "Terminal=false"
    else:
        exec_line = f"Exec={run}"
        terminal = "Terminal=true"
    return (
        "[Desktop Entry]\n"
        "# Written by tidalamp when asked on its first start. Delete it to take\n"
        "# tidalamp out of the menu; it will not be written again.\n"
        "Type=Application\n"
        "Version=1.5\n"
        "Name=TidalAmp\n"
        "GenericName=Music Player\n"
        "GenericName[es]=Reproductor de música\n"
        "Comment=TIDAL client for the terminal with a retro interface\n"
        "Comment[es]=Cliente de TIDAL para terminal con interfaz retro\n"
        f"{exec_line}\n"
        f"Icon={ICON_NAME}\n"
        f"{terminal}\n"
        "Categories=AudioVideo;Audio;Player;ConsoleOnly;\n"
        "Keywords=tidal;music;player;flac;mpris;\n"
        "Keywords[es]=tidal;música;reproductor;flac;mpris;\n"
        "StartupNotify=false\n"
    )


def _install_icon(data_home: Path) -> None:
    target = data_home / "icons/hicolor/scalable/apps" / f"{ICON_NAME}.svg"
    if target.exists():
        return
    icon = resources.files("tidalamp").joinpath("tidalamp.svg").read_text()
    write_atomically(target, icon)


def _enabled() -> bool:
    return not os.environ.get("TIDALAMP_NO_DESKTOP_ENTRY") and sys.platform.startswith(
        "linux"
    )


def offer(
    dirs: list[Path] | None = None,
    marker: Path = MARKER,
    executable: str | None = None,
) -> bool:
    """Whether to ask about the launcher on this start.

    Not when it was answered before, not when a launcher for tidalamp is
    already there (which settles it for good), and not when there is no path
    a menu could run.
    """
    if not _enabled():
        return False
    try:
        if marker.exists():
            return False
        found = existing(data_dirs() if dirs is None else dirs)
        if found is not None:
            log.info("ya hay un lanzador de tidalamp en %s", found)
            _mark(marker, str(found))
            return False
    except OSError as exc:
        log.warning("no se pudo comprobar el lanzador: %s", exc)
        return False
    return bool(command() if executable is None else executable)


def create(
    dirs: list[Path] | None = None,
    marker: Path = MARKER,
    executable: str | None = None,
    on_omarchy: bool | None = None,
) -> Path | None:
    """Write the launcher and its icon. The path written, or None."""
    dirs = data_dirs() if dirs is None else dirs
    run = command() if executable is None else executable
    if not run:
        return None
    try:
        target = dirs[0] / "applications" / FILE_NAME
        if target.exists():
            # Never over someone's own file, a `Hidden=true` included.
            _mark(marker, str(target))
            return None
        write_atomically(
            target, entry(run, omarchy() if on_omarchy is None else on_omarchy)
        )
        _install_icon(dirs[0])
        _mark(marker, str(target))
        return target
    except OSError as exc:
        log.warning("no se pudo crear el lanzador: %s", exc)
        return None


def decline(marker: Path = MARKER) -> None:
    """Remember a no, so the question is not asked again."""
    try:
        _mark(marker, "declined")
    except OSError as exc:
        log.warning("no se pudo guardar la respuesta: %s", exc)


def _mark(marker: Path, answer: str) -> None:
    write_atomically(marker, f"{answer}\n")
