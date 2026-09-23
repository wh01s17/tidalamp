"""The media integration on Windows, for now: none, and no complaint.

SMTC (the panel and the media keys) is its own phase in windows.md, the one
with the most uncertainty. Until then this has the service's shape and does
nothing, so the app starts, `_start_mpris` finds it ready, and nobody is told
about an MPRIS that was never going to exist on this system.
"""

from __future__ import annotations

from ...media import PlayerBackend


class MprisService:
    """No integration. `start` names nothing, which is not a second instance."""

    def __init__(self, backend: PlayerBackend) -> None:
        self._backend = backend

    @property
    def shared(self) -> bool:
        return False

    async def start(self) -> str:
        return ""

    async def stop(self) -> None:
        return None

    def publish(self) -> None:
        return None

    def publish_tracks(self) -> None:
        return None

    def seeked(self, position: float) -> None:
        return None
