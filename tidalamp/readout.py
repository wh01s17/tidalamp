"""The readout: what the display band says about the track and the sound.

The artist, album and year under the clock, the source line (codec, rate,
quality or licence, the analyser's source and the playback state, and the
gain while the volume is normalised) and the output line (the sink, its
format and rate, and whether PipeWire is resampling).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import columns, config
from .i18n import _
from .stream import Playable, gain_for
from .widgets import Glide

if TYPE_CHECKING:
    from .app import TidalAmp


class Readout:
    """The lines of the display band that say what is playing and how."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app

    def gain_badge(self, playable: Playable) -> str:
        """The gain on the badge line while the volume is normalised.

        The gain applied, peak cap included, since that is what is heard. A
        track TIDAL sent no gain for says so instead of «0 dB», which would
        read as measured and found neutral. Nothing at all when off.
        """
        if config.REPLAYGAIN not in ("track", "album"):
            return ""
        sent = any(
            getattr(playable, name, None) is not None
            for name in ("track_gain", "album_gain")
        )
        if not sent:
            return " · RG —"
        return f" · RG {gain_for(playable):+.1f} dB"

    @staticmethod
    def codec_label(playable: Playable) -> str:
        codec = (playable.codec or "").lower()
        if codec.startswith("mp4a") or codec == "aac":
            return "AAC"
        return codec.upper() or ("AAC" if playable.quality in {"LOW", "HIGH"} else "FLAC")

    def playback_label(self) -> str:
        if self.app.mpv.paused and not self.app.mpv.idle:
            return _("pausa").upper()
        if self.app.playback.playable is not None and self.app.queue.current is not None:
            return _("reproduciendo").upper()
        return _("detenido").upper()

    def track_meta(self) -> str:
        """Artist, album and year of what is playing, one per line.

        Never wrapped: the column is 24 cells wide and a wrapped album title
        would push the year out of the band. A line that does not fit glides
        to show the rest (`Glide`) instead of being cut off for good.
        """
        entry = self.app.queue.current
        if entry is None:
            return ""
        tail = " · ".join(
            part for part in (str(entry.year) if entry.year else "", entry.length) if part
        )
        lines = [entry.artist, entry.album, tail]
        return "\n".join(line for line in lines if line)

    def refresh_track_meta(self) -> None:
        """Write the block under the clock. Separate from the readout because
        it is known the moment a track starts, while the codec line waits for
        the stream to resolve."""
        if self.app.query("#trackmeta"):
            self.app.query_one("#trackmeta", Glide).update(self.track_meta())

    def refresh(self) -> None:
        """Redraw source, analyser and playback state from cached values."""
        if not self.app.query("#badges"):
            return
        self.refresh_track_meta()
        analyzer = self.app.spectrum.analyzer()
        playable = self.app.playback.playable
        if playable is None:
            source = f"SRC  — · {analyzer.source} · {self.playback_label()}"
        else:
            # Only what is known. A TIDAL track knows all of it; a free one
            # knows its codec and its licence and nothing else, and a line
            # reading «— · — kHz» spends eleven cells saying so.
            parts = [self.codec_label(playable)]
            if playable.kbps != "—":
                parts.append(playable.kbps)
            if playable.khz != "—":
                parts.append(f"{playable.khz} kHz")
            tier = playable.licence or columns.QUALITY_LABELS.get(
                playable.quality, playable.quality
            )
            if tier:
                parts.append(tier)
            parts += [analyzer.source, self.playback_label()]
            source = "SRC  " + " · ".join(parts)
            source += self.gain_badge(playable)
        self.app.query_one("#badges", Glide).update(source)
        self.refresh_output_line()

    def refresh_output_line(self) -> None:
        sink = self.app.output.sink
        if not sink.known:
            line = "OUT  —"
        else:
            parts = [sink.description or sink.name]
            if sink.sample_format:
                parts.append(f"PCM {sink.sample_format.upper()}")
            if sink.rate:
                parts.append(f"{sink.rate / 1000:g} kHz")
            if (
                sink.rate
                and self.app.output.stream_rate
                and self.app.output.stream_rate != sink.rate
            ):
                parts.append(
                    _("resampling desde {rate} kHz").format(
                        rate=f"{self.app.output.stream_rate / 1000:g}"
                    )
                )
            if sink.muted:
                # The clock runs and nothing is heard: this is the only clue.
                parts.append(_("silenciado en Windows"))
            line = "OUT  " + " · ".join(parts)
        self.app.query_one("#output", Glide).update(line)
