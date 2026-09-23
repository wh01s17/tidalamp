"""How to install a system package, for the message that says one is missing.

A facade (see `tidalamp.backends`): `/etc/os-release` on Linux, in
`tidalamp.backends.linux.distro`; winget, scoop or choco on Windows, in
`tidalamp.backends.windows.distro`.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .backends.windows.distro import install_command, missing
else:
    from .backends.linux.distro import install_command, missing

__all__ = ["install_command", "missing"]
