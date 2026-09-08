"""``Mpv`` driven against the fake mpv in ``fake_mpv.py``."""

from __future__ import annotations

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
    try:
        instance.close()
    except Exception:
        pass


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
    mpv.volume = 500
    assert mpv.volume == 130
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
