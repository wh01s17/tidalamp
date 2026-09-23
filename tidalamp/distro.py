"""How to install a system package, for the message that says one is missing.

A facade (see `tidalamp.backends`): the implementation reads `/etc/os-release`
on Linux, in `tidalamp.backends.linux.distro`.
"""

from __future__ import annotations

from .backends.linux.distro import install_command, missing

__all__ = ["install_command", "missing"]
