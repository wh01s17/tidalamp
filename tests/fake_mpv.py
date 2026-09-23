#!/usr/bin/env python3
"""A stand-in for mpv that speaks just enough of its JSON IPC.

Real mpv needs an audio device and a network stream; this answers the handful
of commands ``player.Mpv`` sends, and — importantly — it also emits async
events on the same socket, which is the part of the protocol that has bitten
us before (the reply we want is not necessarily the first line back).

It serves whatever ``--input-ipc-server`` names: a Unix socket, or on Windows
a named pipe made with the same `_winapi` calls the player's client uses, so
the transport that ships is the one under test on both systems.

Three environment variables make it misbehave the ways a real one can:
``FAKE_MPV_HANG_ON`` names a command it receives and then never answers,
``FAKE_MPV_EOF_ON`` one on which it closes the socket, and ``FAKE_MPV_SPLIT``
sends every reply a few bytes at a time.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
import time

# Labelled filters currently in the chain, so the tests can assert on what
# set_filter() actually sent.
filters: dict[str, str] = {}

# mpv's own playlist: each item is the url and its per-file options.
playlist: list[dict] = []

props = {
    "pause": False,
    "idle-active": True,
    "time-pos": None,
    "duration": None,
    "volume": 100,
    "volume-gain": 0.0,
    "playlist-pos": -1,
    "af-metadata/astats": {"lavfi.astats.Overall.RMS_level": "-21.0"},
}


def _positional(command):
    """Named arguments, as `Mpv._loadfile` sends them, to positional ones."""
    if isinstance(command, dict):
        return [
            command["name"],
            command.get("url"),
            command.get("flags", "replace"),
            -1,
            command.get("options", ""),
        ]
    return list(command)


def _start(item):
    props.update({"idle-active": False, "time-pos": 0.0, "duration": 300.0})
    gain = 0.0
    for option in filter(None, (item.get("options") or "").split(",")):
        name, value = option.split("=", 1)
        if name == "start":
            props["time-pos"] = float(value)
        elif name == "volume-gain":
            gain = float(value)
        else:
            return "error"
    props["volume-gain"] = gain
    return "success"


def handle(command, conn):
    command = _positional(command)
    name = command[0]
    if name == "get_property":
        return props.get(command[1]), "success"
    if name == "set_property":
        props[command[1]] = command[2]
        return None, "success"
    if name == "loadfile":
        url, flags = command[1], command[2] if len(command) > 2 else "replace"
        options = command[4] if len(command) > 4 else ""
        item = {"url": url, "options": options}
        if flags == "append":
            playlist.append(item)
            return None, "success"
        playlist[:] = [item]
        props["playlist-pos"] = 0
        return None, _start(item)
    if name == "playlist-clear":
        pos = props["playlist-pos"]
        playlist[:] = [playlist[pos]] if 0 <= pos < len(playlist) else []
        props["playlist-pos"] = 0 if playlist else -1
        return None, "success"
    if name == "finish":  # not mpv: the tests use it to end the current track
        pos = props["playlist-pos"] + 1
        if pos < len(playlist):
            props["playlist-pos"] = pos
            _start(playlist[pos])
        else:
            playlist.clear()
            props.update({"idle-active": True, "playlist-pos": -1})
        return None, "success"
    if name == "cycle" and command[1] == "pause":
        props["pause"] = not props["pause"]
        return None, "success"
    if name == "stop":
        playlist.clear()
        props.update(
            {"idle-active": True, "time-pos": None, "duration": None, "playlist-pos": -1}
        )
        return None, "success"
    if name == "seek":
        props["time-pos"] = float(command[1])
        return None, "success"
    if name == "af":
        action, spec = command[1], command[2]
        if action == "remove":
            filters.pop(spec.lstrip("@"), None)
        elif action == "add":
            # The real mpv wants "@label:filter"; anything else is a bug.
            if not spec.startswith("@") or ":" not in spec:
                return None, "error"
            label, graph = spec[1:].split(":", 1)
            filters[label] = graph
        else:
            return None, "error"
        return None, "success"
    if name == "get_filters":  # not mpv; the tests use it to inspect state
        return dict(filters), "success"
    if name == "get_playlist":  # not mpv either
        return list(playlist), "success"
    if name == "quit":
        return None, "success"
    return None, "unsupported"


def send(conn, payload: bytes) -> None:
    if not os.environ.get("FAKE_MPV_SPLIT"):
        conn.sendall(payload)
        return
    for start in range(0, len(payload), 3):
        conn.sendall(payload[start : start + 3])
        time.sleep(0.001)


class _PipeConnection:
    """The server end of a Windows named pipe, with a socket's three calls.

    A plain blocking handle: this side does one thing at a time, which is
    what the fake has always done over the socket too.
    """

    # Byte-type pipe, read in bytes, blocking: all three are zero, and
    # `_winapi` does not name them.
    _BYTE_PIPE = 0

    def __init__(self, name: str) -> None:
        import _winapi

        self._winapi = _winapi
        self._handle = _winapi.CreateNamedPipe(
            name,
            _winapi.PIPE_ACCESS_DUPLEX | _winapi.FILE_FLAG_FIRST_PIPE_INSTANCE,
            self._BYTE_PIPE | _winapi.PIPE_WAIT,
            1,
            65536,
            65536,
            _winapi.NMPWAIT_WAIT_FOREVER,
            _winapi.NULL,
        )
        try:
            _winapi.ConnectNamedPipe(self._handle, overlapped=False)
        except OSError as exc:
            # The client got in between creating the pipe and waiting on it.
            if getattr(exc, "winerror", None) != _winapi.ERROR_PIPE_CONNECTED:
                raise

    def recv(self, size: int) -> bytes:
        try:
            data, _error = self._winapi.ReadFile(self._handle, size)
        except BrokenPipeError:
            return b""
        return bytes(data)

    def sendall(self, payload: bytes) -> None:
        self._winapi.WriteFile(self._handle, payload)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._winapi.CloseHandle(self._handle)


def _accept(address: str):
    """Wait for the player and hand back the connection, pipe or socket."""
    if address.startswith("\\\\.\\pipe\\"):
        return _PipeConnection(address)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(address)
    server.listen(1)
    conn, _ = server.accept()
    return conn


def serve(path):
    hang_on = os.environ.get("FAKE_MPV_HANG_ON", "")
    eof_on = os.environ.get("FAKE_MPV_EOF_ON", "")
    conn = _accept(path)
    buf = b""
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            message = json.loads(line)
            command = _positional(message["command"])
            if command[0] == eof_on:
                conn.close()
                return
            if command[0] == hang_on:
                # Alive and holding the socket, but never answering.
                time.sleep(3600)
            # An unsolicited event first, exactly like mpv does.
            send(conn, json.dumps({"event": "property-change"}).encode() + b"\n")
            data, error = handle(message["command"], conn)
            send(
                conn,
                json.dumps(
                    {
                        "data": data,
                        "error": error,
                        "request_id": message.get("request_id"),
                    }
                ).encode()
                + b"\n",
            )
            if command[0] == "quit":
                conn.close()
                return


def main():
    path = None
    for arg in sys.argv[1:]:
        if arg.startswith("--input-ipc-server="):
            path = arg.split("=", 1)[1]
    if path is None:
        sys.exit("sin --input-ipc-server")
    try:
        serve(path)
    finally:
        if not path.startswith("\\\\.\\pipe\\"):
            with contextlib.suppress(OSError):
                os.unlink(path)


if __name__ == "__main__":
    main()
