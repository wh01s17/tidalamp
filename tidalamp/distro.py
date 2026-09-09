"""How to install a system package on the distribution we are running on.

mpv and cava are not Python dependencies. pip cannot install them, so when one
is missing the message has to say how to get it — and the command differs per
distribution. Hardcoding one of them sends everyone else to a package manager
they do not have, which is worse than saying nothing.

`/etc/os-release` is the standard file that names the distribution, and its
``ID_LIKE`` gives derivatives (Linux Mint, Pop!_OS, Nobara…) for free. When it
names something we have no command for, the caller gets an empty string and
drops the parenthetical rather than guessing.
"""

from __future__ import annotations

from pathlib import Path

from .i18n import _

OS_RELEASE = Path("/etc/os-release")

# Distribution family to the command that installs a system package there.
_COMMANDS = {
    "arch": "sudo pacman -S {package}",
    "debian": "sudo apt install {package}",
    "ubuntu": "sudo apt install {package}",
    "fedora": "sudo dnf install {package}",
    "rhel": "sudo dnf install {package}",
    "opensuse": "sudo zypper install {package}",
    "suse": "sudo zypper install {package}",
    "alpine": "sudo apk add {package}",
    "void": "sudo xbps-install -S {package}",
    "gentoo": "sudo emerge {package}",
}


def _fields(text: str) -> dict[str, str]:
    """The KEY=value pairs of an os-release file, unquoted."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def _families(text: str) -> list[str]:
    """``ID`` first, then every ``ID_LIKE``: os-release orders them by closeness."""
    fields = _fields(text)
    names = [fields.get("ID", ""), *fields.get("ID_LIKE", "").split()]
    # opensuse-tumbleweed, opensuse-leap: the family is the part before the
    # dash, and it is only consulted after the exact ids have missed.
    prefixes = [name.split("-", 1)[0] for name in names if "-" in name]
    return [name for name in [*names, *prefixes] if name]


def install_command(package: str) -> str:
    """``sudo dnf install mpv`` and the like, or "" on an unrecognised system."""
    try:
        text = OS_RELEASE.read_text(encoding="utf-8")
    except OSError:
        return ""
    for family in _families(text):
        template = _COMMANDS.get(family)
        if template is not None:
            return template.format(package=package)
    return ""


def missing(package: str) -> str:
    """Why playback (or the spectrum) cannot start, and what to do about it."""
    command = install_command(package)
    if command:
        return _("{package} no está instalado ({command})").format(
            package=package, command=command
        )
    return _("{package} no está instalado").format(package=package)
