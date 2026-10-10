"""The library browser: what it says while a level loads, its filter, going
back, reloading, sorting and removing a row."""

from __future__ import annotations

import asyncio
import threading

from app_helpers import (
    FakeMpv,
    isolate_runtime,
    open_browser,
    opened,
    settle,
    type_into_filter,
    visible_labels,
)
from textual.widgets import Static

from tidalamp import levels, library
from tidalamp.app import BrowserScreen, RowList, TidalAmp
from tidalamp.levels import Row
from tidalamp.queue import Entry
from tidalamp.widgets import Spinner


def test_the_browser_says_what_it_is_loading_and_stops_when_it_lands(monkeypatch):
    """The complaint this fixes: pressing `l` sat silent while the API answered."""
    isolate_runtime(monkeypatch)
    release = threading.Event()

    def slow_root():
        release.wait(5)
        return [Row(label="Mi playlist", loader=list)]

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            application.push_screen(BrowserScreen("MI BIBLIOTECA", slow_root))
            await pilot.pause()

            spinner = application.screen.query_one(Spinner)
            assert spinner.busy
            assert "biblioteca" in spinner.label

            release.set()
            await settle(pilot, lambda: not spinner.busy)
            assert not spinner.busy

    asyncio.run(scenario())


def test_a_title_with_brackets_survives_the_browser_header(monkeypatch):
    """TIDAL names square-bracket things all the time: «[Deluxe Edition]».

    `Static.update` reads a str as Rich markup, so the header used to swallow
    everything from the first bracket on, and a name carrying a closing tag
    («[/]») raised MarkupError instead of drawing.
    """
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            for name in ("Lateralus [Deluxe Edition]", "Song [/] end", "[red]hot[/red]"):
                application.push_screen(BrowserScreen(name, lambda: [Row(label="x")]))
                await pilot.pause()
                drawn = application.screen.query_one("#browser-title").render_line(0)
                assert name[:20] in drawn.text
                application.pop_screen()
                await pilot.pause()

    asyncio.run(scenario())


def test_slash_opens_a_filter_bar_and_leaves_the_level_on_screen(monkeypatch):
    """Like the bar at the foot of a browser: it narrows the list underneath
    instead of covering it with a window of its own. In a search, where the
    filter leaves the pages still to come where they are."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            # The filter on its own: a level this short would page on at
            # once, which test_paging covers.
            monkeypatch.setattr(BrowserScreen, "_page_on", lambda self: None)
            open_browser(application, search=True)
            await opened(pilot)
            screen = application.screen
            assert screen.query_one("#browser-filter-bar").display is False

            await pilot.press("slash")
            await pilot.pause()

            assert screen.query_one("#browser-filter-bar").display is True
            assert isinstance(application.screen, BrowserScreen)
            assert len(visible_labels(screen)) == 4
            assert "3 en este nivel" in (
                screen.query_one("#browser-filter-count").render_line(0).text
            )

    asyncio.run(scenario())


def test_typing_narrows_the_level_and_says_how_much_is_left(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            # The filter on its own: a level this short would page on at
            # once, which test_paging covers.
            monkeypatch.setattr(BrowserScreen, "_page_on", lambda self: None)
            open_browser(application, search=True)
            await opened(pilot)
            screen = application.screen
            await pilot.press("slash")
            await type_into_filter(pilot, "sober")

            assert visible_labels(screen) == ["TOOL - Sober", "más…"]
            assert "1 de 3" in (
                screen.query_one("#browser-filter-count").render_line(0).text
            )

    asyncio.run(scenario())


def test_the_filter_reaches_what_the_line_does_not_show(monkeypatch):
    """The album is not on the line unless that column is on, and it is what
    people remember. Accents are not required either."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            # The filter on its own: a level this short would page on at
            # once, which test_paging covers.
            monkeypatch.setattr(BrowserScreen, "_page_on", lambda self: None)
            open_browser(application, search=True)
            await opened(pilot)
            screen = application.screen
            await pilot.press("slash")
            await type_into_filter(pilot, "lateralus")
            assert visible_labels(screen) == ["TOOL - Schism", "más…"]

            await pilot.press(*["backspace"] * len("lateralus"))
            await type_into_filter(pilot, "sinfonia")
            assert visible_labels(screen) == ["Sinfonía nº 9", "más…"]

    asyncio.run(scenario())


def test_the_more_row_survives_the_filter(monkeypatch):
    """In a search, a level is one page deep until somebody asks for the
    rest. Hiding the only way to ask would claim that what matched is all
    there is. (In the library the filter brings the rest in: test_paging.)"""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            # The filter on its own: a level this short would page on at
            # once, which test_paging covers.
            monkeypatch.setattr(BrowserScreen, "_page_on", lambda self: None)
            open_browser(application, search=True)
            await opened(pilot)
            screen = application.screen
            await pilot.press("slash")
            await type_into_filter(pilot, "nada de esto existe")

            assert visible_labels(screen) == ["más…"]
            assert "0 de 3" in (
                screen.query_one("#browser-filter-count").render_line(0).text
            )

    asyncio.run(scenario())


def test_a_page_pulled_under_a_filter_lands_where_it_belongs(monkeypatch):
    """The «más…» row is spliced by itself, not by the number on screen: under
    a filter that number is not its place in the level."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_browser(application)
            await opened(pilot)
            screen = application.screen
            await pilot.press("slash")
            await type_into_filter(pilot, "sober")
            # ↵ commits the filter and hands the keys back to the list; the
            # cursor then walks to «más…», the second and last visible row.
            await pilot.press("enter")
            await pilot.press("down")
            await pilot.press("enter")
            await settle(pilot, lambda: all(r.more is None for r in screen._level()))

            # The page replaced the «más…» row at the end of the level, and
            # the three rows above it are still there in order.
            assert [row.label for row in screen._level()] == [
                "TOOL - Schism",
                "TOOL - Sober",
                "Sinfonía nº 9",
                "Ænema",
            ]
            # And what is on screen is still only what matched.
            assert visible_labels(screen) == ["TOOL - Sober"]

    asyncio.run(scenario())


def test_escape_drops_the_filter_before_it_closes_the_window(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_browser(application)
            await opened(pilot)
            screen = application.screen
            await pilot.press("slash")
            await type_into_filter(pilot, "sober")
            await pilot.press("escape")
            await pilot.pause()

            assert isinstance(application.screen, BrowserScreen)
            assert screen.query_one("#browser-filter-bar").display is False
            assert len(visible_labels(screen)) == 4
            # The cursor stays on the row the filter was opened to reach.
            assert screen.query_one(RowList).current.label == "TOOL - Sober"

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(application.screen, BrowserScreen)

    asyncio.run(scenario())


def test_the_filter_belongs_to_the_level_it_was_typed_in(monkeypatch):
    """Opening another level with the last one's word still applied would hide
    most of it, with nothing on screen saying why."""
    isolate_runtime(monkeypatch)
    inner = [Row(label="Himno a la alegría", detail="9:00")]
    rows = [Row(label="Sinfonía nº 9", detail="1 pista", loader=lambda: inner)]

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_browser(application, rows)
            await opened(pilot)
            screen = application.screen
            await pilot.press("slash")
            await type_into_filter(pilot, "sinfonia")
            await pilot.press("enter")  # commits the filter, keeps it applied
            await pilot.press("enter")  # opens the level under the cursor
            await settle(pilot, lambda: len(screen._level()) == 1)

            assert screen._filter == ""
            assert screen.query_one("#browser-filter-bar").display is False
            assert visible_labels(screen) == ["Himno a la alegría"]

    asyncio.run(scenario())


def test_opening_a_playlist_names_the_playlist_while_it_loads(monkeypatch):
    isolate_runtime(monkeypatch)
    release = threading.Event()

    def slow_level():
        release.wait(5)
        return []

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            screen = BrowserScreen(
                "MI BIBLIOTECA",
                lambda: [Row(label="Mi playlist", loader=slow_level)],
            )
            application.push_screen(screen)
            await pilot.pause()
            spinner = application.screen.query_one(Spinner)
            await settle(pilot, lambda: not spinner.busy)

            await pilot.press("enter")
            await pilot.pause()
            assert spinner.busy
            assert spinner.label == "abriendo Mi playlist…"
            # The title is what tells the user where they are; it stays put.
            title = application.screen.query_one("#browser-title", Static).content
            assert str(title) == "MI BIBLIOTECA"

            release.set()
            await settle(pilot, lambda: not spinner.busy)

    asyncio.run(scenario())


def test_going_back_stops_a_spinner_for_a_level_nobody_is_waiting_for(monkeypatch):
    isolate_runtime(monkeypatch)
    release = threading.Event()

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:

            def blocked():
                release.wait(5)
                return []

            screen = BrowserScreen(
                "MI BIBLIOTECA",
                lambda: [Row(label="A", loader=lambda: [Row(label="B", loader=blocked)])],
            )
            application.push_screen(screen)
            await pilot.pause()
            spinner = application.screen.query_one(Spinner)
            await settle(pilot, lambda: not spinner.busy)

            await pilot.press("enter")
            await settle(pilot, lambda: not spinner.busy)
            await pilot.press("enter")
            await pilot.pause()
            assert spinner.busy

            await pilot.press("backspace")
            await pilot.pause()
            assert not spinner.busy
            release.set()

            # ⌫ took the user from A back to the root while B was loading. B
            # arrives now, and it used to be pushed anyway, over the root the
            # user had gone back to; and when the app was closing, it landed
            # on a screen with no widgets and raised, which is what failed on
            # CI (Python 3.14, 2026-09-14). Waited for here so the answer
            # lands while the window is still up.
            await settle(pilot, lambda: all(w.is_finished for w in application.workers))
            await pilot.pause()
            assert [level[0] for level in screen._stack] == ["MI BIBLIOTECA"]
            assert not spinner.busy

    asyncio.run(scenario())


def test_a_level_asked_for_before_going_back_is_dropped_however_late_it_starts(
    monkeypatch,
):
    """The test above, without the luck. The worker used to read the count
    of ⌫ when its thread got going; on a slow runner (CI, Windows, Python
    3.11) the ⌫ was in it already and the stale level was pushed anyway.
    Here the thread starts after the ⌫ every time."""
    isolate_runtime(monkeypatch)

    async def scenario() -> list[str]:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            screen = BrowserScreen("MI BIBLIOTECA", lambda: [Row(label="A", loader=list)])
            application.push_screen(screen)
            await pilot.pause()
            spinner = application.screen.query_one(Spinner)
            await settle(pilot, lambda: not spinner.busy)
            await pilot.press("enter")
            await settle(pilot, lambda: len(screen._stack) == 2)

            # B is asked for on A; then ⌫, before its thread has started.
            asked = screen._left
            screen.action_back()
            screen._load(asked, "B", list)
            await settle(pilot, lambda: all(w.is_finished for w in application.workers))
            await pilot.pause()
            return [level[0] for level in screen._stack]

    assert asyncio.run(scenario()) == ["MI BIBLIOTECA"]


def test_reload_drops_the_cached_level_and_asks_again(monkeypatch):
    """The cache lasts the session; `R` is the way to see a new playlist."""
    isolate_runtime(monkeypatch)
    calls: list[int] = []

    def loader():
        calls.append(1)
        return [Row(label="Mi playlist", loader=list)]

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            screen = BrowserScreen(
                "MI BIBLIOTECA", levels.cached("playlists", loader), "playlists"
            )
            application.push_screen(screen)
            await pilot.pause()
            spinner = application.screen.query_one(Spinner)
            await settle(pilot, lambda: not spinner.busy)
            assert calls == [1]

            await pilot.press("R")
            await settle(pilot, lambda: not spinner.busy and len(calls) == 2)

            assert calls == [1, 1]
            # One level on the stack, not two: reloading replaces, it does not
            # drill in.
            assert len(screen._stack) == 1
            title = application.screen.query_one("#browser-title", Static).content
            assert str(title) == "MI BIBLIOTECA"

    asyncio.run(scenario())


def test_browser_modal_stays_inside_the_compact_terminal(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(60, 18)) as pilot:
            screen = BrowserScreen("PRUEBA", list)
            application.push_screen(screen)
            await settle(pilot, lambda: not screen.query_one(Spinner).busy)
            box = screen.query_one("#browser-box")

            assert box.region.x >= 0 and box.region.y >= 0
            assert box.region.right <= 60
            assert box.region.bottom <= 18

    asyncio.run(scenario())


def test_s_sorts_the_level_says_so_and_keeps_it(monkeypatch):
    """`s` offers the orders the level has; the level comes back sorted, the
    title names the order, and walking out and back in keeps it."""
    from app_helpers import settle, visible_labels

    from tidalamp.levels import Row
    from tidalamp.screens import BrowserScreen, ChoiceScreen

    isolate_runtime(monkeypatch)
    monkeypatch.setattr(levels, "_CHOSEN", {})
    levels.forget()
    tracks = [
        Row(label=f"TOOL - {title}", entry=Entry(id=i, title=title, artist="TOOL"))
        for i, title in enumerate(["Sober", "Aenema", "Schism"])
    ]
    album = Row(
        label="Álbum",
        **levels._sortable(
            "album:9",
            levels.ALBUM_TRACK_BY,
            lambda order: lambda: list(tracks),
            local=True,
        ),
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            browser = BrowserScreen("MI BIBLIOTECA", lambda: [album])
            application.push_screen(browser)
            await settle(pilot, lambda: visible_labels(browser) == ["Álbum"])

            await pilot.press("s")
            await pilot.pause()
            assert "no se puede ordenar" in application.status

            await pilot.press("enter")
            await settle(pilot, lambda: len(visible_labels(browser)) == 3)
            await pilot.press("s")
            await pilot.pause()
            assert isinstance(application.screen, ChoiceScreen)
            await pilot.press("down", "enter")  # from «orden original» to name A-Z
            wanted = ["TOOL - Aenema", "TOOL - Schism", "TOOL - Sober"]
            await settle(pilot, lambda: visible_labels(browser) == wanted)
            title = browser.query_one("#browser-title").render_line(0).text
            assert "nombre: A-Z" in title

            await pilot.press("backspace")
            await settle(pilot, lambda: visible_labels(browser) == ["Álbum"])
            await pilot.press("enter")
            await settle(pilot, lambda: visible_labels(browser) == wanted)
            levels.forget()

    asyncio.run(scenario())


def test_d_removes_a_favourite_after_asking_and_the_row_goes(monkeypatch):
    """`d` asks first, on «cancel»; confirmed, the row leaves the level. At
    the top there is nothing to remove from, and it says so."""
    from app_helpers import settle, visible_labels

    from tidalamp.levels import Row
    from tidalamp.queue import Entry
    from tidalamp.screens import BrowserScreen, ChoiceScreen

    isolate_runtime(monkeypatch)
    removed: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        library,
        "favourite",
        lambda session, row, add=True: removed.append((row.label, add)) or row.label,
    )
    monkeypatch.setattr(
        "tidalamp.screens.playlist_edits.ensure_fresh", lambda session: None
    )
    tracks = [
        Row(label=f"TOOL - {title}", entry=Entry(id=i, title=title, artist="TOOL"))
        for i, title in enumerate(["Sober", "Schism"])
    ]
    favourites = Row(label="Pistas favoritas", key="fav:tracks", loader=lambda: tracks)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            browser = BrowserScreen("MI BIBLIOTECA", lambda: [favourites])
            application.push_screen(browser)
            await settle(pilot, lambda: visible_labels(browser) == ["Pistas favoritas"])

            await pilot.press("d")
            await pilot.pause()
            assert "no hay de dónde quitar" in application.status

            await pilot.press("enter")
            await settle(pilot, lambda: len(visible_labels(browser)) == 2)
            await pilot.press("d")
            await pilot.pause()
            assert isinstance(application.screen, ChoiceScreen)
            await pilot.press("enter")  # it opens on «cancel»
            await pilot.pause()
            assert removed == []
            assert len(visible_labels(browser)) == 2

            await pilot.press("d", "up", "enter")
            await settle(pilot, lambda: visible_labels(browser) == ["TOOL - Schism"])
            assert removed == [("TOOL - Sober", False)]
            assert "quitado de favoritos" in application.status

    asyncio.run(scenario())
