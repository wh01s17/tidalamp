"""A thin mpv front-end driven over its JSON IPC socket.

We spawn one long-lived ``mpv --idle`` process and talk to it through a unix
socket, which keeps playback alive across track changes and gives us the
position/volume properties the Winamp display needs.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from typing import Any

from .config import IPC_SOCKET, ensure_dirs

# astats gives us per-channel RMS every 100ms, which is enough to drive the
# analyser. It is a level meter, not a real FFT — see visualizer.py.
_AUDIO_FILTER = "@astats:lavfi=[astats=metadata=1:reset=1]"


class MpvNotFound(RuntimeError):
    pass


class Mpv:
    def __init__(self) -> None:
        if shutil.which("mpv") is None:
            raise MpvNotFound("mpv no está instalado (pacman -S mpv)")
        ensure_dirs()
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._buf = b""
        self._request_id = 0
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
        raise MpvNotFound("mpv no abrió el socket IPC a tiempo")

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
                    return message.get("data") if message.get("error") == "success" else None
            return None

    def _readline(self) -> bytes | None:
        while b"\n" not in self._buf:
            try:
                chunk = self._sock.recv(65536)  # type: ignore[union-attr]
            except (socket.timeout, OSError):
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
        return int(self.get("volume") or 0)

    @volume.setter
    def volume(self, value: int) -> None:
        self.set("volume", max(0, min(130, value)))

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
