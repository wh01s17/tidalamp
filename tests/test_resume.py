"""The second a track was at, kept across a quit: saved once on the way
out, and picked up when that track is played again."""

from __future__ import annotations

import asyncio
import json

from app_helpers import FakeMpv
from test_app_gapless import Playable, isolate, three

from tidalamp.app import TidalAmp
from tidalamp.queue import Queue

# ------------------------------------------------------------------- queue


def test_the_second_goes_to_disk_with_the_queue(entries, queue_file):
    queue = Queue()
    queue.replace(entries, start=1)
    queue.position = 83.44
    queue.save()

    restored = Queue()
    assert restored.load()
    assert restored.resume_at == 1
    assert restored.resume_position == 83.4
    assert restored.playing == -1, "restaurada, pero no sonando"


def test_a_queue_saved_before_the_second_existed_starts_at_the_top(queue_file):
    queue_file.write_text(
        json.dumps({"entries": [{"id": 1, "title": "a", "artist": "b"}], "playing": 0}),
        encoding="utf-8",
    )
    queue = Queue()
    assert queue.load()
    assert queue.resume_position == 0.0


def test_junk_in_the_second_starts_at_the_top(queue_file):
    queue_file.write_text(
        json.dumps(
            {
                "entries": [{"id": 1, "title": "a", "artist": "b"}],
                "playing": 0,
                "position": "mitad",
            }
        ),
        encoding="utf-8",
    )
    queue = Queue()
    assert queue.load()
    assert queue.resume_position == 0.0


# --------------------------------------------------------------------- app


def test_a_restored_track_plays_from_where_the_last_session_quit(monkeypatch):
    isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            application.queue.append(entries)
            application._sync_queue()
            application.queue.resume_at = 1
            application.queue.resume_position = 83.4

            application._restore_position()
            assert application.status == (
                "cola restaurada (3 pistas); «Parabol» sigue en 1:23"
            )
            assert mpv.loaded is None, "no se pone a sonar sola"

            application._play_index(1)
            application._start(entries[1], Playable("https://cdn/2"))
            assert mpv.started_at == 83.4

            # Once: playing it again starts at the top.
            application._play_index(1)
            application._start(entries[1], Playable("https://cdn/2b"))
            assert mpv.started_at == 0.0

    asyncio.run(scenario())


def test_another_track_played_first_starts_at_the_top_and_drops_it(monkeypatch):
    isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            application.queue.append(entries)
            application._sync_queue()
            application.queue.resume_at = 1
            application.queue.resume_position = 83.4
            application._restore_position()

            application._play_index(0)
            application._start(entries[0], Playable("https://cdn/1"))
            assert mpv.started_at == 0.0
            assert application._resume is None

    asyncio.run(scenario())


def test_quitting_writes_the_second_of_the_track_playing(monkeypatch):
    isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            application.queue.append(entries)
            application._sync_queue()
            application._play_index(2)
            application._start(entries[2], Playable("https://cdn/3"))
            mpv.idle, mpv.duration, mpv.position = False, 200.0, 61.0
            await pilot.pause(0.3)

            application._remember_position()
            assert application.queue.position == 61.0
            assert application.queue.playing == 2

    asyncio.run(scenario())


def test_quitting_before_playing_the_restored_track_keeps_its_second(monkeypatch):
    """Open, look, quit: the second the session before left must not be
    lost to a session that never played anything."""
    isolate(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            application.queue.append(entries)
            application._sync_queue()
            application.queue.resume_at = 1
            application.queue.resume_position = 83.4
            application._restore_position()

            application._remember_position()
            assert application.queue.playing == 1
            assert application.queue.position == 83.4

    asyncio.run(scenario())


def test_quitting_stopped_writes_no_second(monkeypatch):
    isolate(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.queue.append(three())
            application._sync_queue()

            application._remember_position()
            assert application.queue.position == 0.0

    asyncio.run(scenario())
