"""The desktop's media integration: what lets media keys and panels reach us.

A facade (see `tidalamp.backends`): the implementation is MPRIS2 over D-Bus on
Linux, in `tidalamp.backends.linux.mpris`. The `mpris_*` names in the app are
the adapter's contract and keep that name whatever the backend.
"""

from __future__ import annotations

from .backends.linux.mpris import MprisService, PlayerBackend

__all__ = ["MprisService", "PlayerBackend"]
