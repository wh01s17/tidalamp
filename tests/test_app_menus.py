"""The track menu and the menu over an album, an artist or a playlist, and
favourites from either."""

from __future__ import annotations

import asyncio

from app_helpers import (
    FakeMpv,
    a_deftones_track,
    a_queue,
    isolate_runtime,
    open_menu_on_b,
    opened,
    settle,
    track_rows,
)

from tidalamp import levels, library, playlists
from tidalamp.app import BrowserScreen, RowList, TidalAmp
from tidalamp.levels import Row
from tidalamp.playback import Playback
from tidalamp.queue import Entry
from tidalamp.screens import CONTAINER_ACTIONS, TRACK_ACTIONS, TrackActionsScreen
from tidalamp.widgets import Spinner


def test_escaping_the_menu_leaves_the_browser_open_and_the_queue_alone(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await opened(pilot)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert isinstance(application.screen, BrowserScreen)
            assert len(application.queue) == 0

    asyncio.run(scenario())


def test_play_now_still_queues_the_whole_level_from_the_chosen_track(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(Playback, "resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await opened(pilot)
            await pilot.press("down")  # cursor on B
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()

            assert [e.title for e in application.queue] == ["A", "B", "C"]
            assert application.queue.playing == 1

    asyncio.run(scenario())


def test_m_opens_the_track_menu_on_the_queue_row(monkeypatch):
    """The same menu the browser opens with ↵. There it has to be asked for
    because ↵ queues the whole level; here ↵ plays the row."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(Playback, "resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [a_deftones_track(), Entry(id=2, title="b", artist="x")], start=-1
            )
            application.queue_view.sync()
            application.query_one("#playlist", RowList).cursor = 1
            await pilot.press("m")
            await pilot.pause()

            assert isinstance(application.screen, TrackActionsScreen)
            await pilot.press("a")
            await settle(pilot, lambda: application.queue.playing >= 0)

            assert application.queue.playing == 1, "toca la fila del cursor"

    asyncio.run(scenario())


def test_the_track_menu_says_so_when_the_queue_is_empty(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()

            assert len(application.screen_stack) == 1
            assert "pista" in application.status

    asyncio.run(scenario())


def test_the_track_menu_can_add_the_track_to_an_existing_playlist(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr("tidalamp.auth.ensure_fresh", lambda session: False)
    sent: list[tuple[str, int]] = []

    def add(session, playlist_id, tracks, batch_size=100):
        sent.append((playlist_id, len(list(tracks))))
        return 1

    monkeypatch.setattr(playlists, "add_to_playlist", add)
    monkeypatch.setattr(
        library,
        "playlist_rows",
        lambda session: [Row(label="Mis rolas", detail="12 pistas", key="playlist:42")],
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism")
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("l")
            await settle(pilot, lambda: application.screen.query("#picker-list"))

            await pilot.press("enter")
            await settle(pilot, lambda: bool(sent))

            assert sent == [("42", 1)], "el id sale de la clave de caché"

    asyncio.run(scenario())


def test_cancelling_the_playlist_picker_sends_nothing(monkeypatch):
    isolate_runtime(monkeypatch)
    sent: list[str] = []
    monkeypatch.setattr(
        playlists, "add_to_playlist", lambda *a, **k: sent.append("x") or 0
    )
    monkeypatch.setattr(library, "playlist_rows", lambda session: [])

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism")
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("l")
            await settle(pilot, lambda: application.screen.query("#picker-list"))

            await pilot.press("escape")
            await pilot.pause()

            assert sent == []

    asyncio.run(scenario())


def test_favourite_from_the_menu_touches_tidal_and_not_the_queue(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(
        "tidalamp.screens.playlist_edits.ensure_fresh", lambda session: False
    )
    added: list[tuple[str, bool]] = []

    def favourite(session, row, add=True):
        added.append((row.entry.title, add))
        return row.entry.label

    monkeypatch.setattr("tidalamp.library.favourite", favourite)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await opened(pilot)
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("v")
            await settle(pilot, lambda: bool(added))

            assert added == [("B", True)]
            assert len(application.queue) == 0

    asyncio.run(scenario())


def test_the_menu_arrow_keys_pick_the_same_actions_as_the_letters(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            application.queue.replace([Entry(id=8, title="sonando", artist="x")], start=0)
            open_menu_on_b(application, track_rows())
            await opened(pilot)
            await pilot.press("enter")
            await pilot.pause()

            # Down once lands on "play next", the second entry.
            await pilot.press("down")
            await pilot.pause()
            assert application.screen.cursor == 1
            await pilot.press("enter")
            await pilot.pause()

            assert [e.title for e in application.queue] == ["sonando", "A"]

    asyncio.run(scenario())


def test_the_menu_cursor_wraps_at_both_ends(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await opened(pilot)
            await pilot.press("enter")
            await pilot.pause()
            screen = application.screen

            await pilot.press("up")
            await pilot.pause()
            assert screen.cursor == len(TRACK_ACTIONS) - 1

            await pilot.press("down")
            await pilot.pause()
            assert screen.cursor == 0

    asyncio.run(scenario())


def test_enter_on_a_level_still_opens_it_instead_of_the_menu(monkeypatch):
    """The menu is for tracks. A level has one obvious thing to do."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            rows = [Row(label="Un álbum", loader=lambda: track_rows(), key="album:1")]
            open_menu_on_b(application, rows)
            await opened(pilot)
            await pilot.press("enter")
            await settle(
                pilot, lambda: len(application.screen.query_one(RowList).rows) == 3
            )
            assert isinstance(application.screen, BrowserScreen)

    asyncio.run(scenario())


# ---------------------------------------------------------------- favoritos


def test_f_favourites_the_selected_track_and_says_so(monkeypatch):
    isolate_runtime(monkeypatch)
    calls: list[tuple[int, bool]] = []

    def fake_favourite(session, row, add=True):
        calls.append((row.entry.id, add))
        return row.entry.label

    monkeypatch.setattr("tidalamp.library.favourite", fake_favourite)
    monkeypatch.setattr(
        "tidalamp.screens.playlist_edits.ensure_fresh", lambda session: False
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.queue.append([Entry(id=42, title="Schism", artist="TOOL")])
            application.queue_view.sync()
            await pilot.pause()

            await pilot.press("f")
            await settle(pilot, lambda: "favoritos" in application.status)
            assert calls == [(42, True)]
            assert application.status == "«TOOL - Schism» añadido a favoritos"

            await pilot.press("F")
            await settle(pilot, lambda: "quitado" in application.status)
            assert calls == [(42, True), (42, False)]

    asyncio.run(scenario())


def test_a_favourite_that_fails_reaches_the_status_line(monkeypatch):
    isolate_runtime(monkeypatch)

    def boom(session, row, add=True):
        raise RuntimeError("sin red")

    monkeypatch.setattr("tidalamp.library.favourite", boom)
    monkeypatch.setattr(
        "tidalamp.screens.playlist_edits.ensure_fresh", lambda session: False
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.queue.append([Entry(id=1, title="t", artist="a")])
            application.queue_view.sync()
            await pilot.pause()

            await pilot.press("f")
            await settle(pilot, lambda: "favoritos" in application.status)
            assert application.status == "favoritos: sin red"
            assert not application.query_one("#busy", Spinner).busy

    asyncio.run(scenario())


def test_favouriting_drops_the_cached_favourites_levels(monkeypatch):
    """The level on disk is now a lie; the next visit must ask again."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(
        "tidalamp.library.favourite", lambda s, r, add=True: r.entry.label
    )
    monkeypatch.setattr(
        "tidalamp.screens.playlist_edits.ensure_fresh", lambda session: False
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            levels.cached("fav:tracks", lambda: [Row(label="vieja")])()
            assert "fav:tracks" in levels._LEVELS

            application.queue.append([Entry(id=1, title="t", artist="a")])
            application.queue_view.sync()
            await pilot.pause()
            await pilot.press("f")
            await settle(pilot, lambda: "favoritos" in application.status)

            assert "fav:tracks" not in levels._LEVELS

    asyncio.run(scenario())


# ------------------------------------------------------------- container menu


def two_page_album() -> list[Row]:
    """An album whose tracks come in two pages, the second behind a «más…»."""
    first, second, third = track_rows()
    more = Row(label="más…", more=lambda: [third])
    return [Row(label="Lateralus", key="album:9", loader=lambda: [first, second, more])]


def test_m_on_an_album_plays_every_page_of_it(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, two_page_album())
            await opened(pilot)
            await pilot.press("m")
            await pilot.pause()
            assert isinstance(application.screen, TrackActionsScreen)
            await pilot.press("a")
            await settle(pilot, lambda: len(application.queue) == 3)

            assert [e.title for e in application.queue] == ["A", "B", "C"]
            assert application.queue.playing == 0

    asyncio.run(scenario())


def test_m_on_an_album_queues_it_next(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            application.queue.replace([Entry(id=8, title="sonando", artist="x")], start=0)
            application.queue.append([Entry(id=9, title="después", artist="x")])
            open_menu_on_b(application, two_page_album())
            await opened(pilot)
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("c")
            await settle(pilot, lambda: len(application.queue) == 5)

            titles = [e.title for e in application.queue]
            assert titles == ["sonando", "A", "B", "C", "después"]
            assert "3" in application.status

    asyncio.run(scenario())


def test_m_on_an_album_adds_all_of_it_to_a_playlist(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr("tidalamp.auth.ensure_fresh", lambda session: False)
    sent: list[tuple[str, list[str]]] = []

    def add(session, playlist_id, tracks, batch_size=100):
        titles = [t.title for t in tracks]
        sent.append((playlist_id, titles))
        return len(titles)

    monkeypatch.setattr(playlists, "add_to_playlist", add)
    monkeypatch.setattr(
        library,
        "playlist_rows",
        lambda session: [Row(label="Mis rolas", detail="12 pistas", key="playlist:42")],
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, two_page_album())
            await opened(pilot)
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("l")
            await settle(pilot, lambda: application.screen.query("#picker-list"))
            await pilot.press("enter")
            await settle(pilot, lambda: bool(sent))

            assert sent == [("42", ["A", "B", "C"])]
            assert len(application.queue) == 0

    asyncio.run(scenario())


def test_m_on_an_album_can_favourite_the_album_itself(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(
        "tidalamp.screens.playlist_edits.ensure_fresh", lambda session: False
    )
    added: list[tuple[str, bool]] = []

    def favourite(session, row, add=True):
        added.append((row.key, add))
        return row.label

    monkeypatch.setattr("tidalamp.library.favourite", favourite)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, two_page_album())
            await opened(pilot)
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("v")
            await settle(pilot, lambda: bool(added))

            assert added == [("album:9", True)]
            assert isinstance(application.screen, BrowserScreen), "sigue en el nivel"

    asyncio.run(scenario())


def test_the_container_menu_offers_no_radio(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, two_page_album())
            await opened(pilot)
            await pilot.press("m")
            await pilot.pause()
            menu = application.screen
            drawn = menu.query_one("#actions-list").render_line
            lines = [drawn(y).text for y in range(len(CONTAINER_ACTIONS) + 1)]
            assert not any("radio" in line for line in lines)

            await pilot.press("d")
            await pilot.pause()
            assert application.screen is menu, "la d de la radio no hace nada aquí"

            await pilot.press("up")
            await pilot.pause()
            assert menu.cursor == len(CONTAINER_ACTIONS) - 1

    asyncio.run(scenario())


def test_m_on_a_track_opens_the_track_menu(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await opened(pilot)
            await pilot.press("m")
            await pilot.pause()

            menu = application.screen
            assert isinstance(menu, TrackActionsScreen)
            drawn = menu.query_one("#actions-list").render_line
            lines = [drawn(y).text for y in range(len(TRACK_ACTIONS))]
            assert any("radio" in line for line in lines), "la pista sí tiene radio"

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(application.screen, BrowserScreen)

    asyncio.run(scenario())


def test_a_on_an_album_appends_every_page_of_it(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, two_page_album())
            await opened(pilot)
            await pilot.press("a")
            await settle(pilot, lambda: len(application.queue) == 3)

            assert [e.title for e in application.queue] == ["A", "B", "C"]

    asyncio.run(scenario())
