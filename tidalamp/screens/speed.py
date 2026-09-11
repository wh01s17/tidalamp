"""The playback speed window."""

from __future__ import annotations

from ..i18n import _
from ..player import Mpv
from .choice import ChoiceScreen


def speed_text(speed: float) -> str:
    """A speed as the transport and this window write it: `1×`, `0.75×`."""
    return f"{speed:g}×"


class SpeedScreen(ChoiceScreen):
    """Pick how fast the track plays, from a quarter to double.

    Applied on ↵ rather than while the cursor moves: walking past 0.25 on the
    way to 1.5 would drag the song through every speed in between.
    """

    def __init__(self, current: float) -> None:
        speeds = Mpv.SPEEDS
        options = [
            (
                speed,
                f"{speed_text(speed):<6}{_('normal') if speed == 1.0 else ''}".rstrip(),
            )
            for speed in speeds
        ]
        cursor = speeds.index(current) if current in speeds else speeds.index(1.0)
        super().__init__(_("▓ VELOCIDAD ▓"), options, current, cursor=cursor)
