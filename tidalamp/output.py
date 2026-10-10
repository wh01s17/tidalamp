"""Where the sound goes, and what the output line says about it.

The sink mpv plays to and the rate it runs at, followed for a few seconds
after each track starts because PipeWire switches rate quietly, and forced
when it does not. And the device chosen in the settings: played to when it is
there, left for the system's default when it goes, and taken back when it is
plugged in again.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from textual.worker import get_current_worker

from . import audio, config
from .i18n import _
from .workers import thread_worker

if TYPE_CHECKING:
    from .app import TidalAmp

log = logging.getLogger("tidalamp.app")

# How long to keep watching the output device after a track starts, and how
# often. PipeWire's rate switch lands somewhere in the first couple of
# seconds, and is silent: there is nothing to subscribe to.
SINK_SETTLE = 4.0
SINK_POLL = 0.4


class Output:
    """Where the sound goes: the sink, its rate, and the device chosen."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        self.sink = audio.Sink()
        # The rate mpv sends to the sink, read with it: when the two differ,
        # PipeWire is resampling and the OUT badge says so.
        self.stream_rate = 0

    @property
    def node(self) -> TidalAmp:
        return self.app

    def gone(self) -> bool:
        """mpv stopped because the device it played to was unplugged.

        mpv ends the track with «audio output initialization failed» and so
        does every one after it, since none can open the output. From here
        that looked like a track that ended and then a queue of tracks that
        would not open: unplugging the DAC skipped the queue, a retry at a
        time, while playing nothing (seen with a FiiO BTR15, 2026-09-24).
        Only while mpv is on the chosen device: on `auto` it follows the
        system's default by itself.
        """
        device = self.app.mpv.device
        return device not in ("", "auto") and not audio.connected(device)

    def watch(self) -> None:
        """Go back to the chosen device once it is plugged in again.

        While mpv plays to the default in its place, because it was unplugged
        or was not there at the start. Choosing it again in the settings did
        nothing, since the setting already said it: the sound stayed on the
        speaker it had fallen back to (seen with a FiiO BTR15, 2026-09-24).
        Asked off the UI thread, and only while mpv is not on it. A USB DAC
        on Linux comes and goes the same way: its sink leaves PipeWire's list
        when it is unplugged and comes back when it is plugged in.
        """
        if self.sink.muted:
            # Unmuting happens in Windows and nothing tells us: look again.
            self.follow()
        wanted = config.AUDIO_DEVICE
        if wanted in ("", "auto") or self.app.mpv.device == wanted:
            return
        self.back_worker(wanted)

    @thread_worker(group="output-back")
    def back_worker(self, wanted: str) -> None:
        if audio.connected(wanted):
            self.app.call_from_thread(self.back, wanted)

    def back(self, wanted: str) -> None:
        # The setting may have changed while Windows was being asked.
        if wanted != config.AUDIO_DEVICE or self.app.mpv.device == wanted:
            return
        self.app.mpv.set_device(wanted)
        self.app.status = _("volvió el dispositivo de salida; suena por él")
        self.follow()
        self.app.spectrum.pick()

    @thread_worker(group="audio-output")
    def follow(self) -> None:
        """Follow the sink until it settles on the rate this track will use.

        PipeWire only switches the graph rate once mpv opens the device, and
        mpv only opens it after fetching and decoding enough of the stream —
        a good deal later than the quarter second this used to wait. Reading
        `pactl` once, that early, reports the rate of the *previous* track:
        the badge said 44.1 kHz while the DAC's own screen read 96K. So poll
        instead of guessing a delay, and publish each change as it lands.

        Nor does PipeWire switch at all while the device is running, and
        between tracks it always is: mpv reopens its output in milliseconds.
        The first track after a restart set the rate and every later one was
        resampled to it. When mpv and the sink disagree, the rate is forced
        until the sink follows, then handed back.
        """
        worker = get_current_worker()
        deadline = time.monotonic() + SINK_SETTLE
        last: tuple[audio.Sink, int] | None = None
        forced = 0
        try:
            while not worker.is_cancelled:
                sink = audio.sink()
                stream = self.app.mpv.samplerate
                if (sink, stream) != last:
                    last = (sink, stream)
                    self.app.call_from_thread(self.set_sink, sink, stream)
                if forced and sink.rate == forced:
                    audio.force_rate(0)
                    forced = 0
                elif not forced and stream and sink.rate and stream != sink.rate:
                    target = audio.rate_to_force(
                        sink,
                        stream,
                        audio.allowed_rates(),
                        audio.hardware_rates(sink.name),
                        audio.streams_on(sink),
                    )
                    if target and audio.force_rate(target):
                        log.info("forzando %s Hz: el sink iba a %s Hz", target, sink.rate)
                        forced = target
                if time.monotonic() >= deadline:
                    return
                time.sleep(SINK_POLL)
        finally:
            if forced:
                audio.force_rate(0)

    def set_sink(self, sink: audio.Sink, stream_rate: int = 0) -> None:
        self.sink = sink
        self.stream_rate = stream_rate
        self.app.readout.refresh_output_line()
