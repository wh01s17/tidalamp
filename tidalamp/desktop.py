"""The launcher entry that puts tidalamp in the desktop's application menu.

A facade (see `tidalamp.backends`): a freedesktop `.desktop` file on Linux, in
`tidalamp.backends.linux.desktop`; on Windows, until the Start menu shortcut
exists, a backend that never offers one.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .backends.windows.desktop import (
        create,
        data_dirs,
        decline,
        existing,
        offer,
        user_launchers,
    )
else:
    from .backends.linux.desktop import (
        create,
        data_dirs,
        decline,
        existing,
        offer,
        user_launchers,
    )

__all__ = ["create", "data_dirs", "decline", "existing", "offer", "user_launchers"]
