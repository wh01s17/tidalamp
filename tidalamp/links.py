"""Handing a link to the rest of the desktop: the browser, or the clipboard.

A TUI owns the mouse, so the terminal's own selection and its click on a URL
never reach the text: a link drawn in a window is a link nobody can follow.
These do it for the user, and say whether they could.

Every helper runs with its output thrown away and in a session of its own:
`xdg-open` and the browsers it starts print to the terminal they inherit,
and that terminal is the one the player is drawing on.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence


def _opener(platform: str = sys.platform) -> list[str] | None:
    if platform == "darwin":
        return ["open"]
    for name in ("xdg-open", "gio"):
        if shutil.which(name):
            return [name, "open"] if name == "gio" else [name]
    return None


def open_url(url: str, platform: str = sys.platform) -> bool:
    """Open ``url`` in the default browser. False when there is nothing to
    open it with, or it would not start."""
    try:
        if platform == "win32":
            # Only Windows has it, and only its stubs say so: looked up so
            # the same line type-checks for both systems.
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                return False
            startfile(url)
            return True
        command = _opener(platform)
        if command is None:
            return False
        subprocess.Popen(
            [*command, url],
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError:
        return False


def _copiers(platform: str = sys.platform) -> list[Sequence[str]]:
    """The clipboard tools worth trying here, most specific first."""
    if platform == "win32":
        return [["clip"]]
    if platform == "darwin":
        return [["pbcopy"]]
    tools: list[Sequence[str]] = []
    if os.environ.get("WAYLAND_DISPLAY"):
        tools.append(["wl-copy"])
    if os.environ.get("DISPLAY"):
        tools += [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]
    return [tool for tool in tools if shutil.which(tool[0])]


def copy_text(text: str, platform: str = sys.platform) -> bool:
    """Put ``text`` on the system clipboard with the system's own tool.

    False when there is none: the caller then falls back to OSC 52, which
    asks the terminal instead and which not every terminal allows.
    """
    for tool in _copiers(platform):
        try:
            subprocess.run(
                list(tool),
                input=text.encode(),
                check=True,
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        return True
    return False
