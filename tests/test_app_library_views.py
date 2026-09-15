"""The browser as a grid of covers, and the changes a playlist of yours takes
from inside it: the menu's verbs and moving a track with alt+↑↓."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime, settle

from tidalamp import config, library
from tidalamp.app import BrowserScreen, RowList, TidalAmp
from tidalamp.library import Row
from tidalamp.queue import Entry
from tidalamp.screens import browser as browser_module
from tidalamp.screens import grid as grid_module
from tidalamp.screens.grid import GridList
from tidalamp.screens.tracks import CONTAINER_ACTIONS, PLAYLIST_ACTIONS


def albums(count: int = 7) -> list[Row]:
    return [
        Row(
            label=f"Disco {i}",
            detail="1997",
            key=f"album:{i}",
            loader=list,
            art=f"https://x/{i}/160x160.jpg",
        )
        for i in range(count)
    ]


def tracks(*ids: int) -> list[Row]:
    return [
        Row(label=f"t{i}", detail="1:00", entry=Entry(id=i, title=f"t{i}", artist="a"))
        for i in ids
    ]


def quiet(monkeypatch, view: str) -> None:
    """No network for covers, nor for the session, and the view asked for."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(config, "LIBRARY_VIEW", view)
    monkeypatch.setattr(browser_module, "cover_cells", lambda url: None)
    monkeypatch.setattr(browser_module, "ensure_fresh", lambda session: None)


def open_level(application, rows) -> None:
    application.push_screen(BrowserScreen("MI BIBLIOTECA", lambda: rows))


def test_a_level_of_albums_is_a_grid_when_the_grid_is_asked_for(monkeypatch):
    quiet(monkeypatch, "grid")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 50)) as pilot:
            open_level(application, albums())
            await settle(pilot, lambda: application.screen.query_one(GridList).rows)
            screen = application.screen
            assert screen.query_one(GridList).display
            assert not screen.query_one(RowList).display

    asyncio.run(scenario())


def test_a_level_of_tracks_stays_a_list_under_the_grid(monkeypatch):
    quiet(monkeypatch, "grid")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 50)) as pilot:
            open_level(application, tracks(1, 2, 3))
            await settle(pilot, lambda: application.screen.query_one(RowList).rows)
            assert not application.screen.query_one(GridList).display

    asyncio.run(scenario())


def test_the_arrows_walk_the_grid_both_ways(monkeypatch):
    quiet(monkeypatch, "grid")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 50)) as pilot:
            open_level(application, albums(12))
            await settle(pilot, lambda: application.screen.query_one(GridList).rows)
            grid = application.screen.query_one(GridList)
            columns = grid.columns
            assert columns > 1

            await pilot.press("right")
            assert grid.cursor == 1
            await pilot.press("down")
            assert grid.cursor == 1 + columns
            await pilot.press("left")
            assert grid.cursor == columns
            # ← on the first tile of a line walks, it does not close the level.
            assert isinstance(application.screen, BrowserScreen)

    asyncio.run(scenario())


def test_v_switches_the_view_and_writes_it_down(monkeypatch):
    quiet(monkeypatch, "list")
    written: list[tuple[str, object]] = []

    def set_option(name, value, path=None):
        written.append((name, value))
        monkeypatch.setattr(config, "LIBRARY_VIEW", value)

    monkeypatch.setattr(config, "set_option", set_option)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 50)) as pilot:
            open_level(application, albums())
            await settle(pilot, lambda: application.screen.query_one(RowList).rows)
            screen = application.screen
            await pilot.press("down", "down")

            await pilot.press("v")
            assert written == [("library_view", "grid")]
            grid = screen.query_one(GridList)
            assert grid.display and grid.cursor == 2  # The same row, now a tile.

            await pilot.press("v")
            assert written[-1] == ("library_view", "list")
            assert screen.query_one(RowList).display

    asyncio.run(scenario())


def test_a_cover_that_arrives_is_drawn_in_its_tile(monkeypatch):
    quiet(monkeypatch, "grid")
    red = ((("█", (255, 0, 0), (0, 0, 0)),) * GridList.COVER_W,) * GridList.COVER_H

    def cells(url):
        grid_module._CELLS[url] = red
        return red

    monkeypatch.setattr(browser_module, "cover_cells", cells)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 50)) as pilot:
            open_level(application, albums(2))
            await pilot.pause()
            grid = application.screen.query_one(GridList)
            await settle(pilot, lambda: grid.rows and "█" in grid.render_line(0).text)
            assert "█" * GridList.COVER_W in grid.render_line(0).text

    try:
        asyncio.run(scenario())
    finally:
        grid_module._CELLS.clear()


def test_the_menu_of_your_playlist_offers_to_rename_describe_and_delete(monkeypatch):
    quiet(monkeypatch, "list")
    offered: list[tuple] = []
    real = browser_module.TrackActionsScreen

    def spy(label, actions=CONTAINER_ACTIONS):
        offered.append(actions)
        return real(label, actions)

    monkeypatch.setattr(browser_module, "TrackActionsScreen", spy)
    mine = Row(label="Viaje", key="playlist:p1", loader=list, editable=True)
    theirs = Row(label="Ajena", key="playlist:p2", loader=list)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 50)) as pilot:
            open_level(application, [mine, theirs])
            await settle(pilot, lambda: application.screen.query_one(RowList).rows)
            await pilot.press("m")
            await pilot.press("escape")
            await pilot.press("down", "m")

    asyncio.run(scenario())
    assert offered == [PLAYLIST_ACTIONS, CONTAINER_ACTIONS]


def _inside_my_playlist(application, rows):
    mine = Row(label="Viaje", key="playlist:p1", loader=lambda: rows, editable=True)
    application.push_screen(BrowserScreen("MI BIBLIOTECA", lambda: [mine]))


def test_alt_down_moves_the_track_in_tidal_and_on_screen(monkeypatch):
    quiet(monkeypatch, "list")
    moves: list[tuple] = []

    def move(session, playlist_id, entry, index, delta):
        moves.append((playlist_id, entry.id, index, delta))
        return "Viaje"

    monkeypatch.setattr(library, "move_in_playlist", move)
    rows = tracks(10, 11, 12)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 50)) as pilot:
            _inside_my_playlist(application, rows)
            await pilot.pause()
            listed = application.screen.query_one(RowList)
            await settle(pilot, lambda: listed.rows)
            await pilot.press("enter")
            await settle(pilot, lambda: len(listed.rows) == 3)

            await pilot.press("alt+down")
            await settle(
                pilot,
                lambda: (
                    listed.current
                    and listed.current.entry.id == 10
                    and listed.cursor == 1
                ),
            )
            assert moves == [("p1", 10, 0, 1)]
            assert [row.entry.id for row in listed.rows] == [11, 10, 12]

    asyncio.run(scenario())


def test_a_sorted_playlist_is_not_reordered(monkeypatch):
    quiet(monkeypatch, "list")
    monkeypatch.setattr(
        library, "move_in_playlist", lambda *a: (_ for _ in ()).throw(AssertionError)
    )
    monkeypatch.setattr(library, "chosen", lambda row: library.Order("name"))
    rows = tracks(10, 11)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 50)) as pilot:
            mine = Row(
                label="Viaje", key="playlist:p1", loader=lambda: rows, editable=True
            )
            mine.sort = lambda order: ("playlist:p1|name-asc", lambda: rows)
            application.push_screen(BrowserScreen("MI BIBLIOTECA", lambda: [mine]))
            await pilot.pause()
            listed = application.screen.query_one(RowList)
            await settle(pilot, lambda: listed.rows)
            await pilot.press("enter")
            await settle(pilot, lambda: len(listed.rows) == 2 and listed.rows[0].entry)

            await pilot.press("alt+down")
            await pilot.pause()
            assert "orden" in application.status

    asyncio.run(scenario())
