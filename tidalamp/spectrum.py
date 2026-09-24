"""A real spectrum, borrowed from cava.

mpv's ``astats`` filter reports a level, not a frequency breakdown, so the
built-in analyser is a VU meter spread across bands. cava does the FFT
properly, so when it is installed we run it against the audio sink and read its
raw output: one byte per band, per frame.

The catch, stated plainly: cava listens to the *sink*, not to our mpv process.
It shows whatever the machine is playing. That is right almost always (mpv is
the only thing making noise) and wrong if something else plays at the same
time. Routing mpv to a private sink would fix it and costs a PipeWire node per
run; not worth it yet.

Nothing here is required: if cava is missing, dies, or the sink cannot be
opened, the caller keeps the RMS meter.

On Windows cava listens through ``winscap``, WASAPI's loopback capture, which
is the same thing seen from there: whatever the output device plays. Its raw
output to ``/dev/stdout`` works as it does on Linux; cava's Windows build
maps that name to the standard output handle (checked in its source,
2026-09-23: cava.c, OUTPUT_RAW).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from . import distro
from .config import CACHE_DIR, ensure_dirs

log = logging.getLogger("tidalamp.spectrum")

CONFIG_TEMPLATE = """\
# Generado por tidalamp. Se reescribe en cada arranque.
[general]
bars = {bars}
framerate = {framerate}
autosens = 1

[input]
method = {method}
source = {source}

[output]
method = raw
raw_target = /dev/stdout
data_format = binary
bit_format = 8bit
channels = mono
"""


class SpectrumUnavailable(RuntimeError):
    pass


def input_method(platform: str = sys.platform) -> str:
    """How cava hears the machine: PulseAudio's API (PipeWire speaks it too),
    or WASAPI's loopback on Windows."""
    return "winscap" if platform == "win32" else "pulse"


METHOD = input_method()

# A console program opens a console window on Windows; not this one.
_NO_WINDOW = 0
if sys.platform == "win32":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW


def _command() -> list[str] | None:
    """What runs cava, or None when it is not installed.

    On Windows also where winget links it, which this process does not have on
    its PATH when winget installed it a moment ago (`cli._offer_installs`)."""
    if shutil.which("cava") is not None:
        return ["cava"]
    if sys.platform == "win32":
        from .backends.windows.winget import linked

        found = linked("cava.exe")
        if found is not None:
            return [found]
    return None


def available() -> bool:
    """Whether cava is installed where we can find it."""
    return _command() is not None


class Cava:
    """A cava process whose latest frame can be read at any time.

    The reader thread keeps only the most recent frame: the UI samples at its
    own rate and older frames are of no use to it.
    """

    def __init__(
        self,
        bars: int = 19,
        framerate: int = 30,
        method: str = METHOD,
        source: str = "auto",
    ) -> None:
        command = _command()
        if command is None:
            raise SpectrumUnavailable(distro.missing("cava"))
        self.bars = bars
        self._frame = [0.0] * bars
        self._lock = threading.Lock()
        self._config = self._write_config(bars, framerate, method, source)
        self._proc = subprocess.Popen(
            [*command, "-p", str(self._config)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
        if sys.platform == "win32":
            # Like mpv: it would outlive a closed terminal (backends/windows/job.py).
            from .backends.windows.job import tie

            tie(self._proc)
        self._thread = threading.Thread(target=self._read_frames, daemon=True)
        self._thread.start()

    @staticmethod
    def _write_config(bars: int, framerate: int, method: str, source: str) -> Path:
        ensure_dirs()
        path = CACHE_DIR / "cava.conf"
        path.write_text(
            CONFIG_TEMPLATE.format(
                bars=bars, framerate=framerate, method=method, source=source
            ),
            encoding="utf-8",
        )
        return path

    def _read_frames(self) -> None:
        stream = self._proc.stdout
        assert stream is not None
        while True:
            chunk = stream.read(self.bars)
            if not chunk or len(chunk) < self.bars:
                break
            frame = [byte / 255.0 for byte in chunk]
            with self._lock:
                self._frame = frame
        log.warning("cava terminó; volvemos al medidor RMS")

    @property
    def alive(self) -> bool:
        return self._proc.poll() is None

    def frame(self) -> list[float]:
        """The most recent frame, one 0..1 value per band."""
        with self._lock:
            return list(self._frame)

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._proc.stdout is not None:
            self._proc.stdout.close()
