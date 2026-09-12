"""Balance and equaliser, persisted between runs.

Both are pure mpv filter state: nothing here talks to TIDAL, and the graphs are
built as strings so ``player.set_filter`` stays generic. Losing the file is not
an error — you get a flat EQ and centred balance, which is where everyone
starts anyway.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from .config import STATE_DIR, ensure_dirs, write_atomically

SETTINGS_FILE = STATE_DIR / "settings.json"

# Winamp's own ten bands, in Hz.
BANDS = [60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000]
BAND_LABELS = ["60", "170", "310", "600", "1k", "3k", "6k", "12k", "14k", "16k"]
GAIN_LIMIT = 12.0  # dB, like the original

# The presets, as data, the way the release notes are: nothing here imports
# Textual, so they are read and applied without standing an app up. Eight
# rather than the original's thirty — eight fit on the window and cover what
# anyone reaches for. Each is one gain per band of `BANDS`, in its order, and
# `apply_preset` is what clamps them, so a curve written past the limit reads
# here as what it meant rather than as what survived.
PRESETS: tuple[tuple[str, tuple[float, ...]], ...] = (
    ("flat", (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)),
    ("rock", (5, 4, 2, -1, -2, 1, 3, 5, 5, 4)),
    ("pop", (-1, 2, 4, 5, 3, 0, -1, -1, -1, -2)),
    ("jazz", (4, 3, 1, 2, -1, -1, 0, 2, 3, 4)),
    ("classical", (5, 4, 3, 2, -1, -1, 0, 2, 3, 4)),
    ("vocal", (-3, -2, 0, 3, 5, 5, 3, 1, 0, -1)),
    ("bass", (8, 7, 5, 2, 0, -1, -2, -2, -2, -2)),
    ("treble", (-3, -3, -2, -1, 0, 2, 4, 6, 7, 7)),
)

# What the window shows when the gains match no preset, which is the state
# anyone who has moved a band is in.
MANUAL = "manual"

# The `replaygain` setting: off, the track's own gain, or its album's, which
# keeps the loud and quiet songs of one record as the record has them.
REPLAYGAIN_MODES = ("off", "track", "album")


def replaygain(
    mode: str,
    track: tuple[float | None, float | None],
    album: tuple[float | None, float | None],
) -> float:
    """The gain in dB to play a track at, for ``mode``.

    ``track`` and ``album`` are (gain, peak) as TIDAL gives them, peak on a
    scale where 1.0 is full scale. An album mode with no album gain falls
    back to the track's; no gain at all is 0 dB, the track as it came.

    **The peak is the ceiling.** A quiet track is raised, and raising one
    whose loudest sample already sits near full scale would clip it: the
    gain is cut to what takes that peak to exactly 1.0 and no further. A
    gain that lowers the level is never cut.
    """
    if mode not in ("track", "album"):
        return 0.0
    gain, peak = album if mode == "album" else track
    if gain is None:
        gain, peak = track
    if gain is None:
        return 0.0
    if peak is not None and peak > 0:
        gain = min(gain, -20 * math.log10(peak))
    return round(gain, 2)


@dataclass
class Settings:
    """What survives a restart, besides the queue."""

    # -1.0 hard left … 0.0 centre … 1.0 hard right
    balance: float = 0.0
    gains: list[float] = field(default_factory=lambda: [0.0] * len(BANDS))

    # ------------------------------------------------------------- balance

    def set_balance(self, value: float) -> float:
        self.balance = max(-1.0, min(1.0, round(value, 2)))
        return self.balance

    def balance_graph(self) -> str | None:
        """A ``pan`` graph, or None when centred (no filter, no glitch)."""
        if abs(self.balance) < 0.01:
            return None
        left = min(1.0, 1.0 - self.balance)
        right = min(1.0, 1.0 + self.balance)
        return f"pan=stereo|c0={left:.2f}*c0|c1={right:.2f}*c1"

    # ------------------------------------------------------------------ eq

    def set_gain(self, band: int, value: float) -> float:
        if not 0 <= band < len(self.gains):
            return 0.0
        self.gains[band] = max(-GAIN_LIMIT, min(GAIN_LIMIT, round(value, 1)))
        return self.gains[band]

    def reset_eq(self) -> None:
        self.gains = [0.0] * len(BANDS)

    def apply_preset(self, name: str) -> None:
        """Put a preset's curve on the bands, clamped to the limit."""
        for band, gain in enumerate(dict(PRESETS)[name]):
            self.set_gain(band, gain)

    @property
    def preset(self) -> str:
        """Which preset the bands are currently sitting on, or `MANUAL`.

        Worked out from the gains rather than remembered, so moving one band
        after choosing a curve is enough to stop calling it that curve. A
        stored name would have gone on lying until something reset it.
        """
        for name, gains in PRESETS:
            wanted = [max(-GAIN_LIMIT, min(GAIN_LIMIT, float(g))) for g in gains]
            if self.gains == wanted:
                return name
        return MANUAL

    def eq_graph(self) -> str | None:
        """One ffmpeg ``equalizer`` (peaking) filter per non-flat band.

        Flat bands are left out rather than added at 0 dB: a shorter chain is
        cheaper, and an all-flat EQ becomes no filter at all.
        """
        parts = [
            f"equalizer=f={freq}:t=q:w=1.0:g={gain:g}"
            for freq, gain in zip(BANDS, self.gains, strict=True)
            if abs(gain) >= 0.05
        ]
        return ",".join(parts) if parts else None

    @property
    def eq_active(self) -> bool:
        return self.eq_graph() is not None

    # ---------------------------------------------------------- persistence

    def save(self) -> None:
        """Failures are non-fatal, as with the queue."""
        try:
            ensure_dirs()
            write_atomically(
                SETTINGS_FILE, json.dumps({"balance": self.balance, "gains": self.gains})
            )
        except OSError:
            pass

    @classmethod
    def load(cls) -> Settings:
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        settings = cls()
        try:
            settings.set_balance(float(raw.get("balance", 0.0)))
            for band, gain in enumerate(raw.get("gains", [])):
                settings.set_gain(band, float(gain))
        except (TypeError, ValueError):
            # A hand-edited file with junk in it should not stop playback.
            return cls()
        return settings
