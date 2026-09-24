"""The launcher entry that puts tidalamp in the desktop's application menu.

A facade (see `tidalamp.backends`): a freedesktop `.desktop` file on Linux, in
`tidalamp.backends.linux.desktop`; on Windows, a `.lnk` in the Start menu and
another on the desktop, in `tidalamp.backends.windows.desktop`. What the
question and the status line say comes from the backend too, since only
Windows writes the second one.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .backends.windows.desktop import (
        create,
        created,
        data_dirs,
        data_note,
        decline,
        existing,
        offer,
        question,
        user_launchers,
    )
else:
    from .backends.linux.desktop import (
        create,
        created,
        data_dirs,
        data_note,
        decline,
        existing,
        offer,
        question,
        user_launchers,
    )

__all__ = [
    "create",
    "created",
    "data_dirs",
    "data_note",
    "decline",
    "existing",
    "offer",
    "question",
    "user_launchers",
]
