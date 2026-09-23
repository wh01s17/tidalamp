"""mpv's JSON IPC over a Windows named pipe, with real timeouts.

mpv takes ``--input-ipc-server=\\\\.\\pipe\\<name>`` on Windows and speaks the
same protocol there. This is the `player.Transport` for it.

**Overlapped I/O, not `open()` and a thread.** A pipe opened with `open()` is
a synchronous handle, and Windows serialises every operation on one: while a
read waits for mpv to say something, a write from another thread waits for
that read. That is exactly when mpv has gone quiet, which is when a command
most needs to get through. With ``FILE_FLAG_OVERLAPPED`` the read and the
write are independent, and a read can be waited on with a timeout.

**A read that times out is kept, not cancelled.** It stays pending and the
next `recv` waits on the same one. Cancelling it could lose whatever arrived
between the cancel and the next read, and half a JSON line lost puts the
request ids out of step, which is the failure `Mpv` is built to avoid.

`_winapi` is private, but it is what `multiprocessing.connection` and
asyncio's Windows event loop are built on, so it is kept working; and if a
Python version breaks it, the damage stays in this file.
"""

from __future__ import annotations

import contextlib
import sys
import time
from typing import Any

from ...i18n import _

# `_winapi` exists only on Windows, and saying so is what makes mypy skip this
# module when it checks the Linux side (and check it on the Windows one).
assert sys.platform == "win32"

import _winapi  # noqa: E402

# What `connect` waits between tries while mpv has not made the pipe yet.
_RETRY = 0.05


class NamedPipe:
    """The transport on Windows: mpv's named pipe at ``address``."""

    def __init__(self, address: str) -> None:
        self._address = address
        self._handle: int | None = None
        self._pending: Any = None  # the overlapped read still in flight
        self._waiting = False  # whether it has yet to complete

    @property
    def address(self) -> str:
        return self._address

    @property
    def connected(self) -> bool:
        return self._handle is not None

    def prepare(self) -> None:
        """Nothing to clear: a pipe goes away with its last handle, and the
        name carries our pid, so no other run's pipe can be in the way."""

    def connect(self, timeout: float) -> None:
        from ...player import MpvNotFound

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self._handle = _winapi.CreateFile(
                    self._address,
                    _winapi.GENERIC_READ | _winapi.GENERIC_WRITE,
                    0,
                    _winapi.NULL,
                    _winapi.OPEN_EXISTING,
                    _winapi.FILE_FLAG_OVERLAPPED,
                    _winapi.NULL,
                )
                return
            except FileNotFoundError:
                pass  # mpv has not created the pipe yet
            except OSError as exc:
                if getattr(exc, "winerror", None) != _winapi.ERROR_PIPE_BUSY:
                    raise
                with contextlib.suppress(OSError):
                    _winapi.WaitNamedPipe(self._address, int(_RETRY * 1000))
            time.sleep(_RETRY)
        raise MpvNotFound(_("mpv no abrió el socket IPC a tiempo"))

    def recv(self, timeout: float) -> bytes:
        if self._handle is None:
            raise OSError("not connected")
        if self._pending is None:
            try:
                self._pending, error = _winapi.ReadFile(
                    self._handle, 65536, overlapped=True
                )
            except BrokenPipeError:
                return b""  # mpv closed its end: EOF, as socket.recv says it
            self._waiting = error == _winapi.ERROR_IO_PENDING
        if self._waiting:
            waited = _winapi.WaitForMultipleObjects(
                [self._pending.event], False, max(0, int(timeout * 1000))
            )
            if waited == _winapi.WAIT_TIMEOUT:
                raise TimeoutError  # the read stays pending for the next call
        read, self._pending = self._pending, None
        # For a read, a broken pipe and a message longer than the buffer come
        # back as codes rather than exceptions. The first is mpv gone; the
        # second still delivered good bytes, and `Mpv` joins lines itself.
        _read, error = read.GetOverlappedResult(True)
        if error == _winapi.ERROR_BROKEN_PIPE:
            return b""
        return bytes(read.getbuffer())

    def sendall(self, data: bytes) -> None:
        if self._handle is None:
            raise OSError("not connected")
        written, _error = _winapi.WriteFile(self._handle, data, overlapped=True)
        sent, _error = written.GetOverlappedResult(True)
        if sent != len(data):
            raise OSError(f"short write to mpv's pipe: {sent} of {len(data)} bytes")

    def disconnect(self) -> None:
        if self._pending is not None:
            with contextlib.suppress(OSError):
                self._pending.cancel()
                self._pending.GetOverlappedResult(True)
            self._pending = None
        if self._handle is not None:
            with contextlib.suppress(OSError):
                _winapi.CloseHandle(self._handle)
            self._handle = None

    def close(self) -> None:
        self.disconnect()
