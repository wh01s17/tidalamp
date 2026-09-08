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
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path

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


class Cava:
    """A cava process whose latest frame can be read at any time.

    The reader thread keeps only the most recent frame: the UI samples at its
    own rate and older frames are of no use to it.
    """

    def __init__(
        self,
        bars: int = 19,
        framerate: int = 30,
        method: str = "pulse",
        source: str = "auto",
    ) -> None:
        if shutil.which("cava") is None:
            raise SpectrumUnavailable("cava no está instalado (pacman -S cava)")
        self.bars = bars
        self._frame = [0.0] * bars
        self._lock = threading.Lock()
        self._config = self._write_config(bars, framerate, method, source)
        self._proc = subprocess.Popen(
            ["cava", "-p", str(self._config)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
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
