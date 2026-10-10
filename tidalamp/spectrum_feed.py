"""What the analyser draws: cava's spectrum, or the level mpv reports.

cava is used when it is installed and can hear what mpv plays; its absence is
not an error, and the analyser falls back to the RMS meter and says so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import audio, config
from .spectrum import Cava, SpectrumUnavailable
from .widgets import Analyzer

if TYPE_CHECKING:
    from .app import TidalAmp


class SpectrumFeed:
    """Feeds the analyser from cava, or leaves it on mpv's level meter."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        # cava, when it is installed. None means the RMS fallback.
        self.cava: Cava | None = None

    def apply_shape(self) -> None:
        """Put the shape the setting names on the analyser.

        The shape only changes how the readout's analyser draws itself, not
        where it is: all of them live beside the cover, under the track
        details, and the wide ones simply use the rest of that column instead
        of stopping at nineteen bars. A name that is not one of them — the
        setting comes from a file the user edits by hand — is the classic one.
        """
        wanted = config.VISUALIZER if config.VISUALIZER in Analyzer.MODES else "bars"
        self.analyzer().mode = wanted

    def analyzer(self) -> Analyzer:
        return self.app.query_one("#analyzer", Analyzer)

    def start(self) -> None:
        """Use cava for a real FFT when it is available. Its absence is not an
        error: the analyser falls back to the RMS meter and says so.

        One process feeds every shape, at a band count none of them draws
        directly: each resamples it. Asking cava for exactly what is on screen
        would mean restarting it on every resize and on every change of shape,
        and a restart is a gap in the picture.

        Not in WASAPI's exclusive mode. cava hears the machine through the
        loopback capture, which only gets what goes through Windows's mixer,
        and an exclusive stream goes around it: cava drew a flat line while
        the music played, under an «FFT» badge (measured with a tone on a real
        machine, 2026-09-24). mpv's own level meter hears the stream itself.
        """
        if not self.hears_mpv():
            self.feed(None)
            return
        try:
            self.cava = Cava(
                bars=Analyzer.BANDS, source=audio.monitor(self.app.mpv.device)
            )
        except SpectrumUnavailable:
            self.feed(None)
            return
        self.feed(self.cava.frame())

    def hears_mpv(self) -> bool:
        """Whether what mpv plays reaches cava. Always on Linux
        (`MANAGES_RATES` is what tells the systems apart), where cava listens
        to the monitor of whichever sink mpv plays to (`audio.monitor`),
        chosen or default. On Windows cava
        hears the default output's mix and nothing else, and cannot be told
        another: not in exclusive mode, and not while mpv plays to another
        device, where the analyser read «FFT» over a line that hardly moved
        (a FiiO, with a JBL as the default, 2026-09-24)."""
        if audio.MANAGES_RATES:
            return True
        if config.EXCLUSIVE:
            return False
        device = self.app.mpv.device
        return device in ("", "auto") or device == audio.system_default()

    def pick(self) -> None:
        """Start the spectrum again from the source that can hear mpv now."""
        self.stop()
        self.start()

    def stop(self) -> None:
        """Drop back to the RMS meter, for good."""
        if self.cava is not None:
            self.cava.close()
            self.cava = None
        self.feed(None)

    def feed(self, frame: list[float] | None) -> None:
        self.analyzer().spectrum = frame
