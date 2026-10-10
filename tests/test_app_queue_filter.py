"""The queue's search bar, the playlist name window and undoing a clear."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, a_queue, isolate_runtime, queue_lines

from tidalamp import playlists
from tidalamp.app import RowList, TidalAmp
from tidalamp.playback import Playback
from tidalamp.screens import PlaylistNameScreen


def test_g_clears_a_filter_that_hides_the_playing_track(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            application.queue.playing = 0
            application.queue_view.sync()
            await pilot.press("ctrl+f")
            application.query_one("#queue-filter").value = "grudge"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.press("g")
            await pilot.pause()

            playlist = application.query_one("#playlist", RowList)
            assert application.query_one("#queue-filter-bar").display is False
            assert [row.entry.title for row in playlist.rows] == [
                "Schism",
                "Lateralus",
                "The Grudge",
            ]
            assert playlist.cursor == 0
            assert playlist.current.entry.title == "Schism"

    asyncio.run(scenario())


def test_a_filtered_queue_keeps_the_numbers_the_tracks_really_have(monkeypatch):
    """Renumbering the matches 1, 2, 3 would claim a playing order that is
    not the one the player follows."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            await pilot.press("ctrl+f")
            application.query_one("#queue-filter").value = "grudge"
            await pilot.pause()

            drawn = [line for line in queue_lines(application) if line.strip()]
            assert len(drawn) == 1
            assert drawn[0].strip().startswith("3. The Grudge")

    asyncio.run(scenario())


def test_enter_on_a_filtered_row_plays_that_track_and_not_its_place_on_screen(
    monkeypatch,
):
    """The row is the first one shown but the third one queued: acting on the
    cursor's number instead of the track's would start the wrong song."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(Playback, "resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            await pilot.press("ctrl+f")
            application.query_one("#queue-filter").value = "grudge"
            await pilot.pause()
            # ↵ inside the box only hands the keys back to the list.
            await pilot.press("enter")
            await pilot.pause()
            assert not application.query_one("#queue-filter").has_focus

            await pilot.press("enter")
            await pilot.pause()

            assert application.queue.playing == 2
            assert application.queue.current.title == "The Grudge"

    asyncio.run(scenario())


def test_removing_under_a_filter_takes_out_the_track_that_was_selected(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            await pilot.press("ctrl+f")
            application.query_one("#queue-filter").value = "grudge"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            await pilot.press("d")
            await pilot.pause()

            assert [e.title for e in application.queue] == ["Schism", "Lateralus"]

    asyncio.run(scenario())


def test_clearing_the_filter_leaves_the_cursor_on_the_track_it_was_on(monkeypatch):
    """Narrowing the queue is how you reach a track in it; landing back at the
    top afterwards would undo the whole point."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            await pilot.press("ctrl+f")
            application.query_one("#queue-filter").value = "grudge"
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            playlist = application.query_one("#playlist", RowList)
            assert playlist.cursor == 2
            assert playlist.current.entry.title == "The Grudge"

    asyncio.run(scenario())


def test_the_playing_row_stays_marked_only_while_the_filter_shows_it(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(Playback, "resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            application.playback.play_index(1)
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            assert playlist.marked == 1

            await pilot.press("ctrl+f")
            application.query_one("#queue-filter").value = "grudge"
            await pilot.pause()
            # Hidden by the filter, so there is no row to mark — and the app
            # has not stopped playing it.
            assert playlist.marked == -1
            assert application.queue.playing == 1

            application.query_one("#queue-filter").value = "later"
            await pilot.pause()
            assert playlist.marked == 0

    asyncio.run(scenario())


def test_typing_in_the_queue_search_does_not_reach_the_transport(monkeypatch):
    """`x` is play/pause, and a search box that let it through could not spell
    «Lateralus»."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            mpv.idle = False
            await pilot.press("ctrl+f")
            await pilot.pause()

            await pilot.press("x")
            await pilot.pause()

            assert mpv.paused is False
            assert application.query_one("#queue-filter").value == "x"

    asyncio.run(scenario())


def test_cancelling_the_playlist_name_does_not_write(monkeypatch):
    isolate_runtime(monkeypatch)
    calls = []
    monkeypatch.setattr(
        playlists, "save_queue_playlist", lambda *args: calls.append(args)
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism")

            await pilot.press("p")
            await pilot.pause()
            assert isinstance(application.screen, PlaylistNameScreen)
            await pilot.press("escape")
            await pilot.pause()

            assert len(application.screen_stack) == 1
            assert calls == []

    asyncio.run(scenario())


def test_undo_holds_one_level_and_says_when_it_holds_none(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            await pilot.press("u")
            await pilot.pause()
            assert "deshacer" in application.status

            a_queue(application, "Schism")
            await pilot.press("C")
            await pilot.press("u")
            await pilot.pause()
            assert len(application.queue) == 1

            # And it is spent: one level, not a stack.
            await pilot.press("u")
            await pilot.pause()
            assert "deshacer" in application.status
            assert len(application.queue) == 1

    asyncio.run(scenario())
