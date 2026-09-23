"""The desktop's media integration: what lets media keys and panels reach us.

A facade (see `tidalamp.backends`): MPRIS2 over D-Bus on Linux, in
`tidalamp.backends.linux.mpris`; on Windows, for now, a service that does
nothing. The contract is in `tidalamp.media`. The `mpris_*` names in the app
are the adapter's and keep that name whatever the backend.
"""

from __future__ import annotations

import sys

from .media import MediaService, PlayerBackend

if sys.platform == "win32":
    from .backends.windows.media import MprisService
else:
    from .backends.linux.mpris import MprisService

__all__ = ["MediaService", "MprisService", "PlayerBackend"]
