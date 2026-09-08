#!/usr/bin/env python3
"""A stand-in for mpv that speaks just enough of its JSON IPC.

Real mpv needs an audio device and a network stream; this answers the handful
of commands ``player.Mpv`` sends, and — importantly — it also emits async
events on the same socket, which is the part of the protocol that has bitten
us before (the reply we want is not necessarily the first line back).
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading

# Labelled filters currently in the chain, so the tests can assert on what
# set_filter() actually sent.
filters: dict[str, str] = {}

props = {
    "pause": False,
    "idle-active": True,
    "time-pos": None,
    "duration": None,
    "volume": 100,
    "af-metadata/astats": {"lavfi.astats.Overall.RMS_level": "-21.0"},
}


def handle(command, conn):
    name = command[0]
    if name == "get_property":
        return props.get(command[1]), "success"
    if name == "set_property":
        props[command[1]] = command[2]
        return None, "success"
    if name == "loadfile":
        props.update({"idle-active": False, "time-pos": 0.0, "duration": 300.0})
        return None, "success"
    if name == "cycle" and command[1] == "pause":
        props["pause"] = not props["pause"]
        return None, "success"
    if name == "stop":
        props.update({"idle-active": True, "time-pos": None, "duration": None})
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
    if name == "quit":
        return None, "success"
    return None, "unsupported"


def serve(path):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    conn, _ = server.accept()
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
            # An unsolicited event first, exactly like mpv does.
            conn.sendall(json.dumps({"event": "property-change"}).encode() + b"\n")
            data, error = handle(message["command"], conn)
            conn.sendall(
                json.dumps(
                    {"data": data, "error": error, "request_id": message.get("request_id")}
                ).encode()
                + b"\n"
            )
            if message["command"][0] == "quit":
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
        try:
            os.unlink(path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
