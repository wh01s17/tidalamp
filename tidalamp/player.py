"""A thin mpv front-end driven over its JSON IPC socket.

We spawn one long-lived ``mpv --idle`` process and talk to it through a unix
socket, which keeps playback alive across track changes and gives us the
position/volume properties the Winamp display needs.
"""

from __future__ import annotations

import json
import logging
import shutil
import socket
import subprocess
import threading
import time
from typing import Any

from . import distro
from .config import IPC_SOCKET, ensure_dirs
from .i18n import _

log = logging.getLogger("tidalamp.player")

# astats gives us per-channel RMS every 100ms, which is enough to drive the
# analyser. It is a level meter, not a real FFT — see visualizer.py.
_AUDIO_FILTER = "@astats:lavfi=[astats=metadata=1:reset=1]"

# A hi-res track reaches mpv as a local .m3u8 whose segments are https URLs
# (see stream.py). ffmpeg derives the allowed protocols from the parent one, so
# a playlist opened from `file:` may only follow `file,crypto,data` and every
# segment fails with "Protocol 'https' not on whitelist". The list has to be
# widened explicitly — and because mpv splits key-value options on commas, the
# value needs mpv's own `%<length>%` escape or it never reaches ffmpeg.
_PROTOCOLS = "file,http,https,tcp,tls,crypto"
_PROTOCOL_OPTION = f"protocol_whitelist=%{len(_PROTOCOLS)}%{_PROTOCOLS}"

# `--cache=auto` turns the cache on for network streams and off for local
# files, and a hi-res track reaches mpv as a *local* .m3u8 whose segments are
# https (see stream.py): mpv looks at the playlist, calls it local, and plays
# 6 Mbit/s of FLAC off the network with nothing but the one-second demuxer
# readahead in front of it. Measured on a 176.4 kHz track: 1.02 s buffered and
# an input rate exactly equal to the bitrate, which is no headroom at all.
# Asking for the cache explicitly took the same track to 29.8 s buffered.
_CACHE_SECONDS = 20


class MpvNotFound(RuntimeError):
    pass


class Mpv:
    # mpv would happily amplify past 100 (its own `volume-max` is 130), but
    # that is digital gain on an already-normalised stream: it clips. The
    # slider is a 0-100 Winamp slider, and this is the number it means.
    VOLUME_MAX = 100
    # A quarter to double, in quarters. mpv takes any speed above zero; these
    # are the ones the speed window offers, and 1 is the track as recorded.
    SPEEDS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)

    def __init__(self) -> None:
        if shutil.which("mpv") is None:
            raise MpvNotFound(distro.missing("mpv"))
        ensure_dirs()
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._buf = b""
        self._request_id = 0
        # Kept so a respawned mpv comes back with the user's volume rather
        # than mpv's default. The speed likewise.
        self._volume = 100
        self._speed = 1.0
        self._proc = self._spawn()
        self._connect()

    # ------------------------------------------------------------------ setup

    def _spawn(self) -> subprocess.Popen:
        IPC_SOCKET.unlink(missing_ok=True)
        return subprocess.Popen(
            [
                "mpv",
                "--idle=yes",
                "--no-video",
                "--no-terminal",
                "--audio-display=no",
                # A system-wide mpv-mpris would otherwise publish a second,
                # duplicate player on the bus. We expose MPRIS ourselves.
                "--load-scripts=no",
                f"--input-ipc-server={IPC_SOCKET}",
                f"--af={_AUDIO_FILTER}",
                f"--demuxer-lavf-o={_PROTOCOL_OPTION}",
                "--cache=yes",
                f"--demuxer-readahead-secs={_CACHE_SECONDS}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _connect(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if IPC_SOCKET.exists():
                try:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.connect(str(IPC_SOCKET))
                    sock.settimeout(2.0)
                    self._sock = sock
                    return
                except OSError:
                    pass
            time.sleep(0.05)
        raise MpvNotFound(_("mpv no abrió el socket IPC a tiempo"))

    @property
    def alive(self) -> bool:
        """False once the mpv process is gone. Without this the UI would keep
        polling a dead socket and simply freeze at the last known position."""
        return self._proc.poll() is None and self._sock is not None

    def restart(self) -> None:
        """Bring mpv back after a crash. Playback does not resume by itself:
        the caller decides whether to reload the current track."""
        with self._lock:
            if self._sock is not None:
                self._sock.close()
                self._sock = None
            self._buf = b""
            if self._proc.poll() is None:
                self._proc.kill()
                self._proc.wait(timeout=2)
            self._proc = self._spawn()
        self._connect()
        log.warning("mpv reiniciado (pid %s)", self._proc.pid)
        self.set("volume", self._volume)
        if self._speed != 1.0:
            self.set("speed", self._speed)

    # ------------------------------------------------------------------- IPC

    def _command(self, *args: Any) -> Any:
        """Send a command and wait for the reply carrying our request_id."""
        if self._sock is None:
            return None
        with self._lock:
            self._request_id += 1
            rid = self._request_id
            payload = json.dumps({"command": list(args), "request_id": rid}) + "\n"
            try:
                self._sock.sendall(payload.encode())
            except OSError:
                return None

            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                line = self._readline()
                if line is None:
                    return None
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Async events share the stream; skip anything that is not ours.
                if message.get("request_id") == rid:
                    return (
                        message.get("data") if message.get("error") == "success" else None
                    )
            return None

    def _readline(self) -> bytes | None:
        while b"\n" not in self._buf:
            try:
                chunk = self._sock.recv(65536)  # type: ignore[union-attr]
            except (TimeoutError, OSError):
                return None
            if not chunk:
                return None
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line

    def get(self, prop: str) -> Any:
        return self._command("get_property", prop)

    def set(self, prop: str, value: Any) -> None:
        self._command("set_property", prop, value)

    def set_filter(self, label: str, graph: str | None) -> None:
        """Install (or drop) a labelled lavfi filter.

        ``af set`` would replace the whole chain and take our astats meter with
        it, so we remove the old instance by label and add the new one. Note
        the label goes *before* the filter (``@eq:lavfi=[…]``): the other way
        round mpv aborts at startup and the IPC socket never appears.

        Adding a filter reinitialises the chain, which costs a barely audible
        gap — so the callers skip the call entirely when the setting is neutral.
        """
        self._command("af", "remove", f"@{label}")
        if graph:
            self._command("af", "add", f"@{label}:lavfi=[{graph}]")

    # -------------------------------------------------------------- transport

    def load(self, url: str) -> None:
        self._command("loadfile", url, "replace")
        self.set("pause", False)

    def toggle_pause(self) -> None:
        self._command("cycle", "pause")

    def stop(self) -> None:
        self._command("stop")

    def seek(self, seconds: float, mode: str = "absolute") -> None:
        self._command("seek", seconds, mode)

    @property
    def paused(self) -> bool:
        return bool(self.get("pause"))

    @property
    def idle(self) -> bool:
        """True when mpv has nothing loaded — our end-of-track signal."""
        return bool(self.get("idle-active"))

    @property
    def position(self) -> float:
        return float(self.get("time-pos") or 0.0)

    @property
    def duration(self) -> float:
        return float(self.get("duration") or 0.0)

    @property
    def volume(self) -> int:
        current = self.get("volume")
        if current is not None:
            self._volume = int(current)
        return self._volume

    @volume.setter
    def volume(self, value: int) -> None:
        self._volume = max(0, min(self.VOLUME_MAX, value))
        self.set("volume", self._volume)

    @property
    def speed(self) -> float:
        """How fast the track plays: 1 as recorded. mpv keeps the pitch."""
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = value
        self.set("speed", value)

    def rms(self) -> float:
        """Overall RMS level in dBFS, or -91.0 when silent/unavailable."""
        data = self.get("af-metadata/astats")
        if not isinstance(data, dict):
            return -91.0
        for key in ("lavfi.astats.Overall.RMS_level", "lavfi.astats.1.RMS_level"):
            if key in data:
                try:
                    return float(data[key])
                except (TypeError, ValueError):
                    return -91.0
        return -91.0

    # ---------------------------------------------------------------- cleanup

    def close(self) -> None:
        try:
            self._command("quit")
        finally:
            if self._sock is not None:
                self._sock.close()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            IPC_SOCKET.unlink(missing_ok=True)
