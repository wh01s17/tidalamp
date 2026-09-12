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

# What `_readline` hands back when the wait ran out, as opposed to None for a
# socket that is gone: the first means mpv is slow, the second that it is dead.
_TIMED_OUT = b""


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
    # How long one command waits for its reply. The ticks call from the UI
    # thread, so this is how long a hung mpv can freeze the screen, once:
    # after a timeout the player is stalled and every command fails at once
    # until a probe from a worker gets an answer again.
    TIMEOUT = 1.0
    # How long a stalled mpv is given before the app restarts it.
    STALL_LIMIT = 5.0

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
        # When mpv first failed to answer in time; None while it answers.
        self._stalled_since: float | None = None
        # What went wrong last, for the status line. Empty while all is well.
        self.failure = ""
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
                # The next track is appended while this one plays (see
                # `append`); this has mpv open it before the end, so the
                # network is not what the gap between them waits on.
                "--prefetch-playlist=yes",
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
                    sock.settimeout(self.TIMEOUT)
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

    @property
    def stalled(self) -> bool:
        """True while mpv is alive but has stopped answering in time."""
        return self._stalled_since is not None

    def stalled_for(self) -> float:
        """Seconds since mpv last failed to answer, 0 while it answers."""
        if self._stalled_since is None:
            return 0.0
        return time.monotonic() - self._stalled_since

    def probe(self) -> bool:
        """Ask a stalled mpv whether it is back, waiting the full timeout.

        For a worker thread: it is the one command a stall lets through, and
        its wait is exactly the freeze the stall exists to keep off the UI.
        """
        self._request(("get_property", "idle-active"), probe=True)
        return self.alive and not self.stalled

    def restart(self) -> None:
        """Bring mpv back after a crash. Playback does not resume by itself:
        the caller decides whether to reload the current track.

        The lock is held only to take the old socket away: killing and
        spawning take seconds, and a command from the UI thread meanwhile has
        to find no socket and give up, not queue behind them.
        """
        with self._lock:
            if self._sock is not None:
                self._sock.close()
                self._sock = None
            self._buf = b""
            self._stalled_since = None
            self.failure = ""
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
        """Send a command and return its data, or None when it failed."""
        return self._request(args)[1]

    def _request(self, command: tuple | dict, probe: bool = False) -> tuple[bool, Any]:
        """Send a command and wait for the reply carrying our request_id.

        Answers whether mpv said "success", and the data. ``command`` is a
        list of positional arguments or a dict of named ones.

        Three ways for it to go wrong, and they are told apart on purpose:
        a socket that is gone (EOF, a failed send) means mpv is dead, and the
        socket is dropped so `alive` says so; a reply that does not come in
        time means mpv is stuck, and the player stalls; a reply with an error
        is just a command mpv refused.
        """
        if self._sock is None:
            return False, None
        if self._stalled_since is not None and not probe:
            return False, None
        with self._lock:
            if self._sock is None:
                return False, None
            self._request_id += 1
            rid = self._request_id
            body = dict(command) if isinstance(command, dict) else list(command)
            payload = json.dumps({"command": body, "request_id": rid}) + "\n"
            try:
                self._sock.sendall(payload.encode())
            except OSError as exc:
                self._lose(f"send: {exc}")
                return False, None

            deadline = time.monotonic() + self.TIMEOUT
            while True:
                line = self._readline(deadline - time.monotonic())
                if line is None:
                    self._lose("EOF")
                    return False, None
                if line == _TIMED_OUT:
                    self._stall(body)
                    return False, None
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Async events share the stream; skip anything that is not ours.
                # A reply that missed its own deadline lands here later and is
                # skipped the same way: its request_id is an older one.
                if message.get("request_id") == rid:
                    if self._stalled_since is not None:
                        log.warning("mpv vuelve a contestar")
                    self._stalled_since = None
                    self.failure = ""
                    ok = message.get("error") == "success"
                    return ok, message.get("data") if ok else None

    def _readline(self, timeout: float) -> bytes | None:
        """One line off the socket: None when the socket is gone, `_TIMED_OUT`
        when nothing complete arrived in ``timeout``. A line split across
        several reads is put back together in `_buf`."""
        sock = self._sock
        while b"\n" not in self._buf:
            if sock is None or timeout <= 0:
                return None if sock is None else _TIMED_OUT
            try:
                sock.settimeout(timeout)
                chunk = sock.recv(65536)
            except TimeoutError:
                return _TIMED_OUT
            except OSError:
                return None
            if not chunk:
                return None
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        # An empty line would read as `_TIMED_OUT`; mpv never sends one, but
        # a blank is not a timeout either.
        return line or b" "

    def _lose(self, reason: str) -> None:
        """The socket is gone: drop it, so `alive` turns False and the app
        restarts mpv instead of polling a corpse. Called with the lock held."""
        log.warning("mpv perdió el socket (%s)", reason)
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        self._buf = b""
        self.failure = _("mpv cerró la conexión")

    def _stall(self, command: Any) -> None:
        if self._stalled_since is None:
            log.warning("mpv no contestó a %s en %.1f s", command, self.TIMEOUT)
            self._stalled_since = time.monotonic()
        self.failure = _("mpv no contesta")

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

    def load(self, url: str, gain: float = 0.0, start: float = 0.0) -> None:
        """Play ``url`` now, dropping whatever was playing or queued, from
        ``start`` seconds in."""
        self._loadfile(url, "replace", gain, start)
        self.set("pause", False)

    def append(self, url: str, gain: float = 0.0) -> None:
        """Queue ``url`` after the current track, so mpv goes on to it with
        no gap. `playlist_pos` turning 1 is how the caller learns it did."""
        self._loadfile(url, "append", gain)

    def drop_queued(self) -> None:
        """Forget what `append` queued, keeping the track that plays. The one
        playing is left alone at position 0."""
        self._command("playlist-clear")

    @property
    def playlist_pos(self) -> int:
        """Where in mpv's own playlist we are: 0 is the track `load` started,
        1 the one `append` queued after it, -1 nothing."""
        pos = self.get("playlist-pos")
        return pos if isinstance(pos, int) else -1

    def _loadfile(self, url: str, flags: str, gain: float, start: float = 0.0) -> None:
        """``loadfile`` with the track's ReplayGain as a per-file option, and
        the second to start at as another.

        ``start`` is how a track goes back where it was after mpv restarts.
        As an option of the load itself rather than a seek afterwards: a seek
        has to wait for the stream to open, and nothing says when it has.

        Per file and not a property set after the fact, so a track appended
        for a gapless start comes in at its own level from its first sample,
        and the one before keeps its own to its last. ``volume-gain`` is a
        volume and not a filter, which also matters: a filter change
        reinitialises the chain, and that is the gap this is here to avoid.

        Named arguments rather than positional, because mpv 0.38 put an index
        between the flags and the options. And an mpv too old to know
        ``volume-gain`` refuses the whole command, so it is tried once more
        without it: playing at the wrong level beats not playing.
        """
        base = [f"start={start:g}"] if start > 0 else []
        options = base + ([f"volume-gain={gain:g}"] if gain else [])

        def loadfile(options: list[str]) -> bool:
            command: dict[str, Any] = {"name": "loadfile", "url": url, "flags": flags}
            if options:
                command["options"] = ",".join(options)
            return self._request(command)[0]

        if not loadfile(options) and gain and not self.stalled and self.alive:
            log.warning("mpv no aceptó volume-gain; se carga sin normalizar")
            loadfile(base)

    @property
    def gain(self) -> float:
        """The ReplayGain on the track that plays, in dB."""
        value = self.get("volume-gain")
        return float(value) if isinstance(value, int | float) else 0.0

    @gain.setter
    def gain(self, value: float) -> None:
        """Change it for the rest of this track, as a mode change does."""
        self.set("volume-gain", value)

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
