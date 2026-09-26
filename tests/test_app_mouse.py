"""The pointer on a list: a click selects, a double click plays, the right
button opens the menu `m` opens. Everywhere a track can be pointed at."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime, settle

from tidalamp import config
from tidalamp.app import RowList, TidalAmp
from tidalamp.library import Row
from tidalamp.queue import Entry
from tidalamp.screens import (
    BrowserScreen,
    FullscreenScreen,
    PlaylistPickerScreen,
    TrackActionsScreen,
)
from tidalamp.screens import browser as browser_module
from tidalamp.screens.grid import GridList


def at(widget, x: int, y: int) -> tuple[int, int]:
    """`x`, `y` in the widget's content, as an offset from its outer edge:
    some lists carry padding, and a row is counted from inside it."""
    return (
        widget.content_region.x - widget.region.x + x,
        widget.content_region.y - widget.region.y + y,
    )


async def point(
    pilot, widget, x: int, y: int, *, times: int = 1, button: int = 1
) -> None:
    """Click `widget` at `x`, `y` of its content, `times` times in a row."""
    click = pilot.double_click if times == 2 else pilot.click
    await click(widget, offset=at(widget, x, y), button=button)


def a_queue(application, count: int = 4) -> None:
    application.queue.replace(
        [Entry(id=i, title=f"t{i}", artist="a") for i in range(count)], start=-1
    )
    application._sync_queue()


def spy_on_plays(monkeypatch) -> list[int]:
    played: list[int] = []
    monkeypatch.setattr(TidalAmp, "_play_index", lambda self, index: played.append(index))
    return played


def test_a_click_on_a_queue_row_selects_it_and_plays_nothing(monkeypatch):
    isolate_runtime(monkeypatch)
    played = spy_on_plays(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            a_queue(application)
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            await point(pilot, playlist, 8, 2)
            await pilot.pause()
            assert playlist.cursor == 2
            assert played == []

    asyncio.run(scenario())


def test_a_double_click_on_a_queue_row_plays_it(monkeypatch):
    isolate_runtime(monkeypatch)
    played = spy_on_plays(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            a_queue(application)
            await pilot.pause()
            await point(pilot, application.query_one("#playlist"), 8, 3, times=2)
            await settle(pilot, lambda: played)
            assert played == [3]

    asyncio.run(scenario())


def test_a_click_under_the_last_row_does_nothing(monkeypatch):
    isolate_runtime(monkeypatch)
    played = spy_on_plays(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            a_queue(application, 2)
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            playlist.cursor = 1
            await point(pilot, playlist, 8, 6, times=2)
            await pilot.pause()
            assert playlist.cursor == 1
            assert played == []
            assert not isinstance(application.screen, TrackActionsScreen)

    asyncio.run(scenario())


def test_a_right_click_on_a_queue_row_opens_its_menu_there(monkeypatch):
    """The menu `m` opens, on the row under the pointer and not on the one the
    cursor was on; and a click on an option takes it."""
    isolate_runtime(monkeypatch)
    played = spy_on_plays(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            a_queue(application)
            await pilot.pause()
            await point(pilot, application.query_one("#playlist"), 8, 1, button=3)
            await settle(
                pilot, lambda: isinstance(application.screen, TrackActionsScreen)
            )
            assert application.query_one("#playlist", RowList).cursor == 1
            # Opening the menu plays nothing: it did, while `RowMenu` was a
            # kind of `RowChosen` and both handlers answered it.
            await pilot.pause()
            assert played == []
            # The first option is «play».
            await point(pilot, application.screen.query_one("#actions-list"), 4, 0)
            await settle(pilot, lambda: played)
            assert played == [1]
            assert not isinstance(application.screen, TrackActionsScreen)

    asyncio.run(scenario())


def test_the_full_screen_queue_answers_the_pointer_on_the_players_cursor(monkeypatch):
    """The panel is the player's queue: a click moves the player's cursor,
    which every queue key acts on, and the right button opens its menu."""
    isolate_runtime(monkeypatch)
    played = spy_on_plays(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            a_queue(application)
            await pilot.press("w")
            await settle(pilot, lambda: isinstance(application.screen, FullscreenScreen))
            screen = application.screen
            screen.open_queue()
            await pilot.pause()
            await point(pilot, application.screen.query_one("#fs-queue-list"), 8, 2)
            await pilot.pause()
            assert application.query_one("#playlist", RowList).cursor == 2
            await point(
                pilot, application.screen.query_one("#fs-queue-list"), 8, 3, times=2
            )
            await settle(pilot, lambda: played)
            assert played == [3]
            await point(
                pilot, application.screen.query_one("#fs-queue-list"), 8, 1, button=3
            )
            await settle(
                pilot, lambda: isinstance(application.screen, TrackActionsScreen)
            )
            assert application.query_one("#playlist", RowList).cursor == 1

    asyncio.run(scenario())


def tracks(*ids: int) -> list[Row]:
    return [
        Row(label=f"t{i}", detail="1:00", entry=Entry(id=i, title=f"t{i}", artist="a"))
        for i in ids
    ]


def quiet(monkeypatch, view: str = "list") -> None:
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(config, "LIBRARY_VIEW", view)
    monkeypatch.setattr(browser_module, "cover_cells", lambda url: None)
    monkeypatch.setattr(browser_module, "ensure_fresh", lambda session: None)


def test_the_browser_opens_a_tracks_menu_on_a_right_click(monkeypatch):
    quiet(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            application.push_screen(
                BrowserScreen("MI BIBLIOTECA", lambda: tracks(1, 2, 3))
            )
            await settle(pilot, lambda: application.screen.query_one(RowList).rows)
            listing = application.screen.query_one(RowList)
            await point(pilot, listing, 8, 2, button=3)
            await settle(
                pilot, lambda: isinstance(application.screen, TrackActionsScreen)
            )
            assert listing.cursor == 2

    asyncio.run(scenario())


def test_a_double_click_in_the_browser_does_what_enter_does(monkeypatch):
    quiet(monkeypatch)
    chosen: list[int] = []
    monkeypatch.setattr(
        BrowserScreen,
        "action_choose",
        lambda self: chosen.append(self.query_one(RowList).cursor),
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            application.push_screen(
                BrowserScreen("MI BIBLIOTECA", lambda: tracks(1, 2, 3))
            )
            await settle(pilot, lambda: application.screen.query_one(RowList).rows)
            await point(pilot, application.screen.query_one(RowList), 8, 1, times=2)
            await settle(pilot, lambda: chosen)
            assert chosen == [1]

    asyncio.run(scenario())


def albums(count: int) -> list[Row]:
    return [
        Row(label=f"album {i}", detail="10 pistas", loader=list, art=f"u{i}")
        for i in range(count)
    ]


def test_a_click_on_a_tile_selects_that_tile(monkeypatch):
    quiet(monkeypatch, "grid")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 50)) as pilot:
            application.push_screen(BrowserScreen("MI BIBLIOTECA", lambda: albums(12)))
            await settle(pilot, lambda: application.screen.query_one(GridList).rows)
            grid = application.screen.query_one(GridList)
            columns = grid.columns
            assert columns > 1
            # The first tile of the second line of tiles, on its cover.
            await point(pilot, grid, 3, GridList.TILE_H + 2)
            await pilot.pause()
            assert grid.cursor == columns
            # The line of air under a tile belongs to no tile.
            await point(pilot, grid, 3, GridList.TILE_H - 1)
            await pilot.pause()
            assert grid.cursor == columns

    asyncio.run(scenario())


def test_a_double_click_picks_a_playlist_to_add_to(monkeypatch):
    isolate_runtime(monkeypatch)
    picked: list[str | None] = []
    rows = [Row(label=f"mine {i}", detail="", key=f"playlist:{i}") for i in range(3)]
    monkeypatch.setattr("tidalamp.library.playlist_rows", lambda session: rows)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            application.push_screen(PlaylistPickerScreen(object()), picked.append)
            await settle(pilot, lambda: application.screen.query_one(RowList).rows)
            await point(pilot, application.screen.query_one(RowList), 8, 2, times=2)
            await settle(pilot, lambda: picked)
            assert picked == ["playlist:2"]

    asyncio.run(scenario())
