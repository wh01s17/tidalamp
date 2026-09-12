"""``Mpv`` driven against the fake mpv in ``fake_mpv.py``."""

from __future__ import annotations

import contextlib
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from tidalamp import player
from tidalamp.player import Mpv

FAKE = Path(__file__).parent / "fake_mpv.py"


@pytest.fixture
def mpv(tmp_path, monkeypatch):
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "mpv").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    (shim / "mpv").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}:{os.environ['PATH']}")
    monkeypatch.setattr(player, "IPC_SOCKET", tmp_path / "mpv.sock")
    monkeypatch.setattr(player, "ensure_dirs", lambda: None)

    instance = Mpv()
    yield instance
    with contextlib.suppress(Exception):
        instance.close()


def test_properties_survive_the_async_event_noise(mpv):
    # The fake sends an event before every reply; getting the right answer
    # proves we correlate on request_id instead of taking the first line.
    assert mpv.volume == 100
    assert mpv.idle is True
    assert mpv.paused is False


def test_volume_roundtrip(mpv):
    mpv.volume = 40
    assert mpv.volume == 40


def test_volume_is_clamped(mpv):
    """Not to mpv's own 130: above 100 it is digital gain, and it clips."""
    mpv.volume = 500
    assert mpv.volume == Mpv.VOLUME_MAX == 100
    mpv.volume = 101
    assert mpv.volume == 100
    mpv.volume = -10
    assert mpv.volume == 0


def test_load_leaves_idle_and_unpauses(mpv):
    mpv.toggle_pause()
    assert mpv.paused is True
    mpv.load("https://cdn/a")
    assert mpv.idle is False
    assert mpv.paused is False
    assert mpv.duration == 300.0


def test_stop_goes_back_to_idle(mpv):
    mpv.load("https://cdn/a")
    mpv.stop()
    assert mpv.idle is True
    assert mpv.position == 0.0


def test_seek(mpv):
    mpv.load("https://cdn/a")
    mpv.seek(42, "absolute")
    assert mpv.position == 42.0


def test_rms_reads_the_astats_filter(mpv):
    assert mpv.rms() == -21.0


def test_alive_turns_false_when_mpv_dies(mpv):
    assert mpv.alive is True
    mpv._proc.send_signal(signal.SIGKILL)
    deadline = time.monotonic() + 3
    while mpv.alive and time.monotonic() < deadline:
        time.sleep(0.05)
    assert mpv.alive is False


def test_restart_brings_it_back_with_the_same_volume(mpv):
    mpv.volume = 33
    mpv._proc.send_signal(signal.SIGKILL)
    mpv._proc.wait(timeout=3)
    mpv.restart()
    assert mpv.alive is True
    assert mpv.volume == 33


# ------------------------------------------------------------------ filters


def filters(mpv):
    return mpv._command("get_filters")


def test_set_filter_uses_the_label_first_syntax(mpv):
    mpv.set_filter("eq", "equalizer=f=60:t=q:w=1.0:g=6")
    # Label in front: "@eq:lavfi=[…]". The other order makes real mpv abort at
    # startup, so the fake rejects it too.
    assert filters(mpv) == {"eq": "lavfi=[equalizer=f=60:t=q:w=1.0:g=6]"}


def test_set_filter_replaces_rather_than_stacking(mpv):
    mpv.set_filter("eq", "equalizer=f=60:t=q:w=1.0:g=6")
    mpv.set_filter("eq", "equalizer=f=60:t=q:w=1.0:g=-6")
    assert filters(mpv) == {"eq": "lavfi=[equalizer=f=60:t=q:w=1.0:g=-6]"}


def test_a_none_graph_removes_the_filter(mpv):
    mpv.set_filter("balance", "pan=stereo|c0=1.00*c0|c1=0.50*c1")
    mpv.set_filter("balance", None)
    assert filters(mpv) == {}


def test_filters_are_independent(mpv):
    mpv.set_filter("balance", "pan=stereo|c0=0.50*c0|c1=1.00*c1")
    mpv.set_filter("eq", "equalizer=f=1000:t=q:w=1.0:g=3")
    mpv.set_filter("balance", None)
    assert list(filters(mpv)) == ["eq"]


def test_mpv_is_allowed_to_follow_https_from_a_local_playlist(mpv):
    """A hi-res track is a local .m3u8 of https segments; ffmpeg blocks that
    by default, and mpv needs its %length% escape or the commas split the
    option into pieces that never reach ffmpeg."""
    args = mpv._proc.args
    option = next(a for a in args if a.startswith("--demuxer-lavf-o="))
    value = option.split("=", 1)[1]

    assert value == "protocol_whitelist=%30%file,http,https,tcp,tls,crypto"
    assert "https" in value and "file" in value


def test_the_cache_is_asked_for_rather_than_left_to_auto(mpv):
    """`--cache=auto` reads the *playlist* to decide, and a hi-res track's
    playlist is a local file: mpv called it local, switched the cache off and
    streamed 6 Mbit/s of FLAC behind a one-second readahead. Measured on a
    176.4 kHz track: 1.02 s buffered, and asking explicitly gave 29.8 s.

    Headroom against a slow network. It was *not* what caused the dropouts we
    were chasing when this was written; those were a USB cable that had
    negotiated full speed, capping the DAC at 16 bit / 96 kHz."""
    args = mpv._proc.args

    assert "--cache=yes" in args
    readahead = next(a for a in args if a.startswith("--demuxer-readahead-secs="))
    assert float(readahead.split("=", 1)[1]) >= 10


# ------------------------------------------------- a socket that misbehaves


@pytest.fixture
def unruly(tmp_path, monkeypatch):
    """The same fake mpv, started with the environment a test gave it."""
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "mpv").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    (shim / "mpv").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}:{os.environ['PATH']}")
    monkeypatch.setattr(player, "IPC_SOCKET", tmp_path / "mpv.sock")
    monkeypatch.setattr(player, "ensure_dirs", lambda: None)
    monkeypatch.setattr(Mpv, "TIMEOUT", 0.3)
    started: list[Mpv] = []

    def start(**env: str) -> Mpv:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        started.append(Mpv())
        return started[-1]

    yield start
    for instance in started:
        with contextlib.suppress(Exception):
            instance._proc.kill()
        with contextlib.suppress(Exception):
            instance.close()


def test_an_mpv_that_stops_answering_freezes_one_command_not_every_tick(unruly):
    """A live mpv that holds the socket and never replies used to cost the
    full wait on every property the tick read, several a tick, forever. Now
    the first command waits once, and the rest give up at once."""
    mpv = unruly(FAKE_MPV_HANG_ON="get_property")

    started = time.monotonic()
    assert mpv.paused is False
    assert time.monotonic() - started >= Mpv.TIMEOUT
    assert mpv.stalled and mpv.alive, "atascado, que no muerto"
    assert mpv.failure == "mpv no contesta"

    started = time.monotonic()
    for _ in range(20):
        mpv.position, mpv.idle, mpv.rms()
    assert time.monotonic() - started < Mpv.TIMEOUT, "los siguientes no esperan"
    assert mpv.probe() is False
    assert mpv.stalled_for() > 0


def test_a_stall_clears_when_mpv_answers_again(unruly):
    mpv = unruly(FAKE_MPV_HANG_ON="nonexistent")
    mpv._stalled_since = time.monotonic() - 1

    assert mpv.probe() is True
    assert not mpv.stalled and mpv.failure == ""
    assert mpv.volume == 100, "y los comandos vuelven a pasar"


def test_an_mpv_that_closes_the_socket_reads_as_dead(unruly):
    """EOF used to come back as a silent None: the UI read a volume of 0 and
    a position of 0 off a corpse, and nobody restarted it."""
    mpv = unruly(FAKE_MPV_EOF_ON="cycle")

    mpv.toggle_pause()

    assert mpv.alive is False
    assert not mpv.stalled
    assert mpv.failure == "mpv cerró la conexión"
    assert mpv.get("volume") is None


def test_replies_cut_into_pieces_are_put_back_together(unruly):
    mpv = unruly(FAKE_MPV_SPLIT="1")

    mpv.volume = 42
    assert mpv.volume == 42
    assert mpv.rms() == -21.0
    assert not mpv.stalled


def test_restart_after_a_stall_starts_clean(unruly):
    mpv = unruly()
    mpv._stalled_since = time.monotonic() - 10
    mpv.failure = "mpv no contesta"

    mpv.restart()

    assert not mpv.stalled and mpv.failure == ""
    assert mpv.volume == 100


# ------------------------------------------------------------------ gapless


def playlist(mpv):
    return mpv._command("get_playlist")


def test_the_next_track_waits_in_mpvs_playlist_behind_the_current_one(mpv):
    mpv.load("https://cdn/a")
    mpv.append("https://cdn/b", gain=-3.5)

    assert [item["url"] for item in playlist(mpv)] == ["https://cdn/a", "https://cdn/b"]
    assert mpv.playlist_pos == 0
    assert "--prefetch-playlist=yes" in mpv._proc.args

    mpv._command("finish")
    assert mpv.playlist_pos == 1, "mpv pasó a la siguiente sin quedarse en idle"
    assert mpv.idle is False
    assert mpv.gain == -3.5, "con su propia ganancia desde el primer momento"

    mpv.drop_queued()
    assert [item["url"] for item in playlist(mpv)] == ["https://cdn/b"]
    assert mpv.playlist_pos == 0


def test_dropping_the_queued_track_keeps_the_one_playing(mpv):
    mpv.load("https://cdn/a")
    mpv.append("https://cdn/b")
    mpv.drop_queued()

    mpv._command("finish")
    assert mpv.idle is True, "la que se quitó no suena"


def test_loading_replaces_whatever_was_queued(mpv):
    mpv.load("https://cdn/a")
    mpv.append("https://cdn/b")
    mpv.load("https://cdn/c")

    assert [item["url"] for item in playlist(mpv)] == ["https://cdn/c"]


def test_a_load_carries_its_gain_as_a_per_file_option(mpv):
    mpv.load("https://cdn/a", gain=-6.2)
    assert playlist(mpv)[0]["options"] == "volume-gain=-6.2"
    assert mpv.gain == -6.2

    mpv.load("https://cdn/b")
    assert playlist(mpv)[0]["options"] == "", "sin normalizar, sin opción"
    assert mpv.gain == 0.0


def test_an_mpv_that_refuses_the_gain_still_plays(mpv, monkeypatch):
    sent: list[object] = []
    original = Mpv._request

    def refuse_options(self, command, probe=False):
        sent.append(command)
        if isinstance(command, dict) and "options" in command:
            return False, None
        return original(self, command, probe)

    monkeypatch.setattr(Mpv, "_request", refuse_options)
    mpv.load("https://cdn/a", gain=-2.0)

    assert mpv.idle is False
    assert [item["url"] for item in playlist(mpv)] == ["https://cdn/a"]


def test_a_load_can_start_part_way_in(mpv):
    """How a track goes back where it was after mpv restarts: an option of
    the load, not a seek that would have to wait for the stream."""
    mpv.load("https://cdn/a", gain=-2.0, start=95.5)

    assert playlist(mpv)[0]["options"] == "start=95.5,volume-gain=-2"
    assert mpv.position == 95.5


def test_the_retry_without_the_gain_keeps_the_start(mpv, monkeypatch):
    original = Mpv._request

    def refuse_the_gain(self, command, probe=False):
        if isinstance(command, dict) and "volume-gain" in command.get("options", ""):
            return False, None
        return original(self, command, probe)

    monkeypatch.setattr(Mpv, "_request", refuse_the_gain)
    mpv.load("https://cdn/a", gain=-2.0, start=40.0)

    assert playlist(mpv)[0]["options"] == "start=40"
    assert mpv.position == 40.0
