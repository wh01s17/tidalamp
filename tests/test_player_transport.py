"""``Mpv`` over a transport double: what it asks of a `Transport`, whatever
carries the bytes. The socket and the pipe are tested against a real process
elsewhere; these hold the protocol to the contract, on every system."""

from __future__ import annotations

import contextlib
import json
import sys

import pytest

from tidalamp import player
from tidalamp.player import Mpv

# Something to be mpv's process: alive until killed, and never touching IPC.
IDLE = [sys.executable, "-c", "import time; time.sleep(60)"]


class Scripted:
    """A transport that answers from a script instead of from mpv.

    ``replies`` maps a command name to what `recv` hands back after it is
    sent: a reply dict, raw bytes, an exception to raise, or a list of those
    for one per read. Unlisted commands get a success.
    """

    def __init__(self, replies: dict | None = None) -> None:
        self.replies = replies or {}
        self.sent: list[dict] = []
        self.calls: list[str] = []
        self._inbox: list[bytes | BaseException] = []
        self._connected = False

    @property
    def address(self) -> str:
        return "scripted-address"

    @property
    def connected(self) -> bool:
        return self._connected

    def prepare(self) -> None:
        self.calls.append("prepare")

    def connect(self, timeout: float) -> None:
        self.calls.append("connect")
        self._connected = True

    def sendall(self, data: bytes) -> None:
        message = json.loads(data)
        self.sent.append(message)
        body = message["command"]
        name = body["name"] if isinstance(body, dict) else body[0]
        reply = self.replies.get(name)
        if reply is None:
            reply = {"error": "success", "data": None}
        if isinstance(reply, dict):
            # An event first, as mpv does: the reply is not the first line.
            self._inbox.append(b'{"event":"property-change"}\n')
            reply = json.dumps({**reply, "request_id": message["request_id"]}).encode()
            self._inbox.append(reply + b"\n")
        elif isinstance(reply, list):
            self._inbox.extend(reply)
        else:
            self._inbox.append(reply)

    def recv(self, timeout: float) -> bytes:
        if not self._inbox:
            raise TimeoutError
        item = self._inbox.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def disconnect(self) -> None:
        self.calls.append("disconnect")
        self._connected = False

    def close(self) -> None:
        self.calls.append("close")
        self._connected = False


@pytest.fixture
def started(monkeypatch):
    monkeypatch.setattr(player, "ensure_dirs", lambda: None)
    instances: list[Mpv] = []

    def start(transport: Scripted) -> Mpv:
        instances.append(Mpv(command=IDLE, transport=transport))
        return instances[-1]

    yield start
    for instance in instances:
        with contextlib.suppress(Exception):
            instance._proc.kill()
            instance._proc.wait(timeout=2)


def test_mpv_is_told_the_transports_address(started):
    mpv = started(Scripted())
    assert "--input-ipc-server=scripted-address" in mpv._proc.args
    assert mpv._proc.args[: len(IDLE)] == IDLE


def test_the_transport_is_prepared_before_mpv_and_connected_after(started):
    transport = Scripted()
    started(transport)
    assert transport.calls == ["prepare", "connect"]


def test_a_reply_is_matched_by_request_id_past_the_events(started):
    transport = Scripted({"get_property": {"error": "success", "data": 42}})
    mpv = started(transport)
    assert mpv.get("volume") == 42


def test_a_reply_split_across_reads_is_put_back_together(started):
    halves = [b'{"error":"success","da', b'ta":7,"request_id":1}\n']
    mpv = started(Scripted({"get_property": halves}))
    assert mpv.get("volume") == 7


def test_nothing_in_time_stalls_the_player_and_keeps_it_alive(started, monkeypatch):
    monkeypatch.setattr(Mpv, "TIMEOUT", 0.05)
    transport = Scripted({"get_property": TimeoutError()})
    mpv = started(transport)
    assert mpv.get("volume") is None
    assert mpv.stalled
    assert mpv.alive


def test_end_of_file_is_a_dead_mpv_not_a_slow_one(started):
    transport = Scripted({"get_property": b""})
    mpv = started(transport)
    assert mpv.get("volume") is None
    assert not mpv.stalled
    assert not mpv.alive
    assert "disconnect" in transport.calls


def test_a_broken_connection_is_a_dead_mpv(started):
    transport = Scripted({"get_property": BrokenPipeError()})
    mpv = started(transport)
    assert mpv.get("volume") is None
    assert not mpv.alive


def test_closing_disconnects_and_then_cleans_up(started):
    transport = Scripted()
    mpv = started(transport)
    mpv._proc.kill()
    mpv.close()
    assert transport.calls[-2:] == ["disconnect", "close"]
