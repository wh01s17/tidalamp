"""The queue: rows, cursor, filter, clearing, moving and restoring."""

from __future__ import annotations

import asyncio

from app_helpers import (
    FakeMpv,
    a_queue,
    isolate_runtime,
    lit,
    open_menu_on_b,
    settle,
    track_rows,
    transport,
)
from textual.widgets import Input

from tidalamp import app as app_module
from tidalamp import library
from tidalamp.app import RowList, TidalAmp
from tidalamp.queue import Entry
from tidalamp.screens import (
    PlaylistNameScreen,
)
from tidalamp.widgets import (
    Artwork,
    Spinner,
)


def test_shuffle_and_repeat_are_lit_buttons_on_the_transport_row(monkeypatch):
    """They used to be «SHUF OFF» / «REP ALL» words on a row of their own.

    Colour still reinforces the state, but the glyphs also say it explicitly.
    """
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            assert lit(application) == {"⇄": False, "↻": False}
            assert "⇄○" in transport(application)
            assert "↻–" in transport(application)

            await pilot.press("s")
            await pilot.pause()
            assert lit(application)["⇄"] is True
            assert "⇄●" in transport(application)

            await pilot.press("r")
            await pilot.pause()
            assert lit(application)["↻"] is True
            assert "↻A" in transport(application)

            application.mpris_set_loop_status("Track")
            application.mpris_set_shuffle(False)
            await pilot.pause()
            assert lit(application)["⇄"] is False
            assert "↻1" in transport(application)

    asyncio.run(scenario())


def test_toggling_repeat_does_not_shift_the_rest_of_the_row(monkeypatch):
    """«↻ » and «↻1» are the same width on purpose."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 24)) as pilot:
            await pilot.pause()
            widths = set()
            for _attempt in range(3):
                widths.add(len(transport(application)))
                await pilot.press("r")
                await pilot.pause()
            assert len(widths) == 1

    asyncio.run(scenario())


def test_a_narrow_but_tall_terminal_keeps_the_small_box(monkeypatch):
    """Height alone must not grow it: the readout shares the row and would go."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(76, 200)) as pilot:
            await pilot.pause()
            assert application.query_one(Artwork).rows == Artwork.MIN_ROWS

    asyncio.run(scenario())


# -------------------------------------------------------------- MPRIS TrackList


def test_the_track_list_is_the_queue_with_one_id_per_row(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            # The same song twice: the ids still have to differ, or a client
            # could not tell the two rows apart.
            application.queue.append(
                [
                    Entry(id=7, title="Schism", artist="TOOL"),
                    Entry(id=7, title="Schism", artist="TOOL"),
                ]
            )

            tracks = application.mpris_tracks()
            ids = [t["trackid"] for t in tracks]
            assert len(set(ids)) == 2
            assert all(t["title"] == "Schism" for t in tracks)

    asyncio.run(scenario())


def test_go_to_plays_the_row_with_that_id(monkeypatch):
    isolate_runtime(monkeypatch)
    played: list[int] = []
    monkeypatch.setattr(TidalAmp, "_play_index", lambda self, index: played.append(index))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            application.queue.append(
                [Entry(id=i, title=f"t{i}", artist="a") for i in range(3)]
            )

            application.mpris_go_to(application.mpris_tracks()[2]["trackid"])
            # An id we never handed out is ignored, not an index error.
            application.mpris_go_to("/org/mpris/MediaPlayer2/tidalamp/track/999999")

            assert played == [2]

    asyncio.run(scenario())


def test_g_returns_the_cursor_to_the_playing_track(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            application.queue.playing = 1
            application._sync_queue()
            playlist = application.query_one("#playlist", RowList)
            playlist.cursor = 2

            await pilot.press("g")
            await pilot.pause()

            assert playlist.cursor == 1
            assert playlist.current.entry.title == "Lateralus"

    asyncio.run(scenario())


def test_g_without_a_playing_track_leaves_the_cursor_and_explains_why(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            playlist = application.query_one("#playlist", RowList)
            playlist.cursor = 2

            await pilot.press("g")
            await pilot.pause()

            assert playlist.cursor == 2
            assert application.status == "no hay una pista reproduciéndose"

    asyncio.run(scenario())


def test_ctrl_f_narrows_the_queue_and_esc_gives_it_back(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            await pilot.pause()
            bar = application.query_one("#queue-filter-bar")
            assert bar.display is False

            await pilot.press("ctrl+f")
            await pilot.pause()
            assert bar.display is True
            assert application.query_one("#queue-filter").has_focus

            application.query_one("#queue-filter").value = "later"
            await pilot.pause()
            assert [
                row.label for row in application.query_one("#playlist", RowList).rows
            ] == ["TOOL - Lateralus"]
            assert "1 de 3" in application.query_one("#queue-filter-count").render().plain

            # The queue itself never changed: only what is being shown did.
            assert len(application.queue) == 3

            await pilot.press("escape")
            await pilot.pause()
            assert bar.display is False
            assert len(application.query_one("#playlist", RowList).rows) == 3

    asyncio.run(scenario())


def test_saving_the_queue_uses_the_written_name_and_a_queue_snapshot(monkeypatch):
    isolate_runtime(monkeypatch)
    calls: list[tuple[str, list[int]]] = []
    steps: list[str] = []
    busy_during_save: list[tuple[bool, str]] = []

    def fresh(session):
        steps.append("fresh")
        return False

    def save(session, title, entries):
        steps.append("save")
        calls.append((title, [entry.id for entry in entries]))
        return len(entries)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(app_module, "ensure_fresh", fresh)
            monkeypatch.setattr(library, "save_queue_playlist", save)
            monkeypatch.setattr(
                application,
                "call_from_thread",
                lambda callback, *args: callback(*args),
            )

            def run_now(title, entries):
                spinner = application.query_one("#busy", Spinner)
                busy_during_save.append((spinner.busy, spinner.label))
                TidalAmp._save_playlist_worker.__wrapped__(application, title, entries)

            monkeypatch.setattr(application, "_save_playlist_worker", run_now)
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            application.queue.shuffle = True

            await pilot.press("p")
            await pilot.pause()
            assert isinstance(application.screen, PlaylistNameScreen)
            application.screen.query_one("#playlist-name-input", Input).value = "Viaje"
            await pilot.press("enter")
            await pilot.pause()
            # Mutating the live queue cannot rewrite the snapshot handed to save.
            application.queue.clear()

            assert steps == ["fresh", "save"]
            assert calls == [("Viaje", [0, 1, 2])]
            assert busy_during_save == [(True, "guardando la cola como «Viaje»…")]
            assert application.status == "playlist «Viaje» creada con 3 pistas"
            assert not application.query_one("#busy", Spinner).busy

    asyncio.run(scenario())


def test_saving_an_empty_queue_opens_nothing_and_calls_nothing(monkeypatch):
    isolate_runtime(monkeypatch)
    calls = []
    monkeypatch.setattr(library, "save_queue_playlist", lambda *args: calls.append(args))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

            assert len(application.screen_stack) == 1
            assert calls == []
            assert application.status == "la cola está vacía; no hay nada que guardar"

    asyncio.run(scenario())


def test_the_queue_fills_its_missing_years_in_the_background(monkeypatch):
    """The rows go up without the year and it arrives a moment later, rather
    than every level load waiting a request per record it holds."""
    isolate_runtime(monkeypatch)
    asked: list[int] = []

    def year_of(session, album_id: int) -> int:
        asked.append(album_id)
        return {7: 1997, 8: 2000}.get(album_id, 0)

    monkeypatch.setattr(library, "album_year", year_of)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [
                    Entry(id=1, title="a", artist="Deftones", album="AtF", album_id=7),
                    Entry(id=2, title="b", artist="Deftones", album="AtF", album_id=7),
                    Entry(id=3, title="c", artist="Deftones", album="WP", album_id=8),
                ],
                start=-1,
            )
            application._sync_queue()
            await settle(pilot, lambda: len(asked) >= 2)

            assert sorted(asked) == [7, 8], "una petición por álbum, no por pista"
            assert [entry.year for entry in application.queue] == [1997, 1997, 2000]

    asyncio.run(scenario())


def test_a_queue_saved_before_the_album_id_existed_asks_nothing(monkeypatch):
    """There is no id to ask about. Those entries fill on the next reload,
    and until then the cell is honestly empty."""
    isolate_runtime(monkeypatch)
    asked: list[int] = []
    monkeypatch.setattr(library, "album_year", lambda s, a: asked.append(a) or 0)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=1, title="a", artist="x", album="y")], start=-1
            )
            application._sync_queue()
            await pilot.pause()

            assert asked == []

    asyncio.run(scenario())


def test_undo_puts_back_the_queue_that_c_threw_away(monkeypatch):
    """`c` stops and `C` clears. A slipped shift used to be the end of it."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            application.query_one("#playlist", RowList).cursor = 2
            await pilot.pause()

            await pilot.press("C")
            await pilot.pause()
            assert len(application.queue) == 0

            await pilot.press("u")
            await pilot.pause()
            assert [e.title for e in application.queue] == [
                "Schism",
                "Lateralus",
                "The Grudge",
            ]
            assert application.query_one("#playlist", RowList).cursor == 2

    asyncio.run(scenario())


def test_a_second_clear_replaces_what_undo_is_holding(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus")
            await pilot.press("C")
            await pilot.pause()
            a_queue(application, "Rosemary")
            await pilot.press("C")
            await pilot.press("u")
            await pilot.pause()

            assert [e.title for e in application.queue] == ["Rosemary"]

    asyncio.run(scenario())


def test_radio_replaces_the_queue_with_the_station_behind_its_seed(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)
    asked: list[str] = []

    def station(session, entry, limit=100):
        # library.track_radio has already dropped the seed; see the tests
        # there for the reason it has to.
        asked.append(entry.title)
        return [Entry(id=90 + i, title=f"R{i}", artist="TOOL") for i in range(3)]

    monkeypatch.setattr(library, "track_radio", station)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await pilot.pause()
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("d")
            await settle(pilot, lambda: len(application.queue) > 0)

            assert asked == ["B"]
            # The seed leads, or the station looks like the wrong thing started.
            assert [e.title for e in application.queue] == ["B", "R0", "R1", "R2"]
            assert application.queue.playing == 0
            # And it leads exactly once.
            titles = [e.title for e in application.queue]
            assert titles.count("B") == 1

    asyncio.run(scenario())


def test_a_track_with_no_radio_says_so_and_leaves_the_queue_alone(monkeypatch):
    isolate_runtime(monkeypatch)

    def no_station(session, entry, limit=100):
        raise library.NoRadio("TIDAL no tiene radio para «B»")

    monkeypatch.setattr(library, "track_radio", no_station)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await pilot.pause()
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("d")
            await settle(pilot, lambda: "radio" in application.status)

            assert len(application.queue) == 0
            assert not application.query_one("#busy", Spinner).busy

    asyncio.run(scenario())


def _two_tracks_playing_the_last(application) -> None:
    application.queue.replace(
        [Entry(id=1, title="A", artist="x"), Entry(id=2, title="B", artist="x")],
        start=1,
    )
    application._sync_queue()


def test_autoplay_carries_on_with_the_last_track_s_radio(monkeypatch):
    """At the end of the queue, with autoplay on: the last track's radio goes
    on the end, without the seed or what the queue already has, and plays."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)
    monkeypatch.setattr(app_module.config, "AUTOPLAY", True)
    asked: list[str] = []

    def station(session, entry, limit=100):
        asked.append(entry.title)
        return [
            Entry(id=1, title="A", artist="x"),
            Entry(id=90, title="R0", artist="x"),
            Entry(id=91, title="R1", artist="x"),
        ]

    monkeypatch.setattr(library, "track_radio", station)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            _two_tracks_playing_the_last(application)
            application.action_next()
            # A second «next» while the radio is on its way asks nothing more.
            application.action_next()
            await settle(pilot, lambda: len(application.queue) == 4)

            assert asked == ["B"]
            assert [e.title for e in application.queue] == ["A", "B", "R0", "R1"]
            assert application.queue.playing == 2

    asyncio.run(scenario())


def test_without_autoplay_the_end_of_the_queue_stops(monkeypatch):
    isolate_runtime(monkeypatch)
    asked: list[str] = []
    monkeypatch.setattr(
        library, "track_radio", lambda session, entry, limit=100: asked.append("x") or []
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            _two_tracks_playing_the_last(application)
            application.action_next()
            await pilot.pause()
            assert asked == []
            assert application.queue.playing == -1
            assert len(application.queue) == 2

    asyncio.run(scenario())


def test_a_radio_with_nothing_new_stops_and_says_so(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(app_module.config, "AUTOPLAY", True)
    monkeypatch.setattr(
        library,
        "track_radio",
        lambda session, entry, limit=100: [Entry(id=1, title="A", artist="x")],
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            _two_tracks_playing_the_last(application)
            application.action_next()
            await settle(pilot, lambda: "no hay más" in application.status)
            assert application.queue.playing == -1
            assert len(application.queue) == 2

    asyncio.run(scenario())


def test_stopping_while_the_radio_is_on_its_way_keeps_it_stopped(monkeypatch):
    """A station arriving after the user pressed stop, or played something
    else, must not start by itself."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)
    monkeypatch.setattr(app_module.config, "AUTOPLAY", True)
    asked: list[Entry] = []
    monkeypatch.setattr(
        TidalAmp, "_autoplay_worker", lambda self, seed: asked.append(seed)
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            _two_tracks_playing_the_last(application)
            application.action_next()
            assert len(asked) == 1
            application.action_stop()
            station = [Entry(id=90, title="R0", artist="x")]
            application._autoplay_ready(asked[0], station)
            await pilot.pause()
            assert len(application.queue) == 2
            assert application.queue.playing == -1

            # Back to the last track, so «next» runs past the end again.
            _two_tracks_playing_the_last(application)
            application.action_next()
            assert len(asked) == 2
            application._play_index(0)
            application._autoplay_ready(asked[1], station)
            assert len(application.queue) == 2
            assert application.queue.playing == 0

    asyncio.run(scenario())
