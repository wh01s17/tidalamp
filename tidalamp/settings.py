"""Balance and equaliser, persisted between runs.

Both are pure mpv filter state: nothing here talks to TIDAL, and the graphs are
built as strings so ``player.set_filter`` stays generic. Losing the file is not
an error — you get a flat EQ and centred balance, which is where everyone
starts anyway.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .config import STATE_DIR, ensure_dirs

SETTINGS_FILE = STATE_DIR / "settings.json"

# Winamp's own ten bands, in Hz.
BANDS = [60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000]
BAND_LABELS = ["60", "170", "310", "600", "1k", "3k", "6k", "12k", "14k", "16k"]
GAIN_LIMIT = 12.0  # dB, like the original


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
            SETTINGS_FILE.write_text(
                json.dumps({"balance": self.balance, "gains": self.gains}),
                encoding="utf-8",
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
