"""The launcher entry that puts tidalamp in the desktop's application menu.

A facade (see `tidalamp.backends`): the implementation is a freedesktop
`.desktop` file on Linux, in `tidalamp.backends.linux.desktop`.
"""

from __future__ import annotations

from .backends.linux.desktop import (
    create,
    data_dirs,
    decline,
    existing,
    offer,
    user_launchers,
)

__all__ = ["create", "data_dirs", "decline", "existing", "offer", "user_launchers"]
