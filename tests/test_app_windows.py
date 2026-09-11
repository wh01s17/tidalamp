"""The windows over the player: help, browser, search, menus, lyrics, EQ."""

from __future__ import annotations

import asyncio
import threading

from app_helpers import (
    FakeMpv,
    a_deftones_track,
    a_queue,
    isolate_runtime,
    open_browser,
    open_menu_on_b,
    queue_lines,
    settle,
    track_rows,
    transport,
    type_into_filter,
    visible_labels,
)
from rich.cells import cell_len
from textual.screen import Screen
from textual.widgets import Static

from tidalamp import about, library
from tidalamp import app as app_module
from tidalamp.app import BrowserScreen, HelpScreen, RowList, TidalAmp
from tidalamp.library import Row
from tidalamp.queue import Entry
from tidalamp.screens import (
    TRACK_ACTIONS,
    PlaylistNameScreen,
    TrackActionsScreen,
)
from tidalamp.widgets import (
    Analyzer,
    Spinner,
    TimeDisplay,
)


def test_slow_tick_does_not_reapply_audio_filters(monkeypatch):
    """Changing filters may create an audible gap; polling must stay read-only."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test() as pilot:
            await pilot.pause()
            initial = list(mpv.filter_calls)
            application._tick_slow()
            assert initial == [("balance", None), ("eq", None)]
            assert mpv.filter_calls == initial

    asyncio.run(scenario())


# ------------------------------------------------ el fondo detrás de un modal


def test_the_player_stops_animating_behind_a_modal(monkeypatch):
    """The scrim leaves the player visible, and a translucent screen means
    every analyzer frame repaints it and blends the whole terminal again.
    Measured at 240x62 with the library open: 8.8% of a core against 37.7%."""
    isolate_runtime(monkeypatch)
    ticks = []
    monkeypatch.setattr(Analyzer, "tick", lambda self: ticks.append(1))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            # The app's own timer fires this too, so each phase counts from
            # zero rather than against a total nobody controls.
            ticks.clear()
            application._tick_fast()
            assert ticks

            application.push_screen(Screen())
            await pilot.pause()
            ticks.clear()
            application._tick_fast()
            assert not ticks, "el fondo no debería animarse tras un modal"

            application.pop_screen()
            await pilot.pause()
            ticks.clear()
            application._tick_fast()
            assert ticks, "y debería seguir donde estaba al volver"

    asyncio.run(scenario())


def test_the_clock_stops_behind_a_modal_but_the_music_does_not(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            clock = application.query_one(TimeDisplay)
            mpv.position, mpv.duration = 30.0, 200.0
            application._tick_slow()
            assert clock.seconds == 30.0

            application.push_screen(Screen())
            await pilot.pause()
            mpv.position = 90.0
            application._tick_slow()
            assert clock.seconds == 30.0, "el reloj de detrás no vale un repintado"

            # What is not cosmetic keeps running: mpv going idle after having
            # played still means the track ended.
            mpv.idle = False
            application._tick_slow()
            assert application._was_idle is False

            application.pop_screen()
            await pilot.pause()
            application._tick_slow()
            assert clock.seconds == 90.0

    asyncio.run(scenario())


def test_the_status_line_is_written_behind_a_modal_but_only_when_it_changed(
    monkeypatch,
):
    """A favourite added from the browser reports on the status line, and
    through the scrim it is legible — so that one keeps being written. Four
    times a second, though, it almost always says the same thing."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            status = application.query_one("#status", Static)
            writes = []
            # On the instance, not on `Static`: patching the class caught the
            # repaint of every other Static in the app and made the count
            # depend on which tick happened to land during the test.
            monkeypatch.setattr(
                status, "update", lambda text="": writes.append(text), raising=False
            )

            application.push_screen(Screen())
            await pilot.pause()
            # Flush whatever the startup left on the line before watching it:
            # the app's own timer runs this four times a second, so which
            # side of the first write the spy lands on is not ours to pick.
            application._tick_slow()
            writes.clear()

            application.status = "«Schism» añadido a favoritos"
            application._tick_slow()
            assert writes == [" «Schism» añadido a favoritos"]

            application._tick_slow()
            application._tick_slow()
            assert len(writes) == 1, "repetir lo mismo no debería repintar"

    asyncio.run(scenario())


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


# ------------------------------------------------------------------ transport


def test_the_transport_keys_and_the_menu_sit_at_opposite_ends(monkeypatch):
    """They used to be one string, so the menu ran straight into «b ▶▶»."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 24)) as pilot:
            await pilot.pause()
            play = application.query_one("#transport-play")
            menu = application.query_one("#transport-menu")

            # One row, transport on the left, menu against the right edge.
            assert play.region.y == menu.region.y
            assert play.region.right <= menu.region.x
            assert menu.region.right == application.query_one("#transport").region.right

            drawn = transport(application, "menu")
            assert drawn.rstrip().endswith(("quit", "salir"))
            assert drawn.startswith(" "), "el menú tiene que quedar pegado a la derecha"

            # And there is real air between the two halves.
            gap = menu.region.width - len(drawn.strip())
            assert gap > 10

    asyncio.run(scenario())


def test_a_narrow_menu_drops_whole_entries_instead_of_cutting_a_word(monkeypatch):
    """Half a word behind a «·» reads as a rendering fault."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            widget = application.query_one("#transport-menu")
            whole = transport(application, "menu").strip()
            assert whole.endswith(("salir", "quit"))

            for width in range(20, 110, 7):
                widget.styles.width = width
                await pilot.pause()
                application._refresh_modes()
                drawn = transport(application, "menu")

                assert cell_len(drawn) <= width, "el menú no puede desbordar"
                entries = [part.strip() for part in drawn.split(TidalAmp.SEPARATOR)]
                assert entries[0].strip() == "? ayuda", "la ayuda va primero"
                # Every entry that survived is one of the whole ones.
                for entry in entries:
                    assert entry in whole.split(TidalAmp.SEPARATOR)

    asyncio.run(scenario())


def test_the_help_key_survives_on_a_narrow_terminal(monkeypatch):
    """The menu is cropped from the right when it does not fit, so the one
    entry that explains all the others has to come first."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(76, 20)) as pilot:
            await pilot.pause()
            assert transport(application, "menu").strip().startswith("?")

    asyncio.run(scenario())


def test_slash_opens_a_filter_bar_and_leaves_the_level_on_screen(monkeypatch):
    """Like the bar at the foot of a browser: it narrows the list underneath
    instead of covering it with a window of its own."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_browser(application)
            await pilot.pause()
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
            open_browser(application)
            await pilot.pause()
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
            open_browser(application)
            await pilot.pause()
            screen = application.screen
            await pilot.press("slash")
            await type_into_filter(pilot, "lateralus")
            assert visible_labels(screen) == ["TOOL - Schism", "más…"]

            await pilot.press(*["backspace"] * len("lateralus"))
            await type_into_filter(pilot, "sinfonia")
            assert visible_labels(screen) == ["Sinfonía nº 9", "más…"]

    asyncio.run(scenario())


def test_the_more_row_survives_the_filter(monkeypatch):
    """A level is one page deep until somebody asks for the rest. Hiding the
    only way to ask would claim that what matched is all there is."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_browser(application)
            await pilot.pause()
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
            await pilot.pause()
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
            await pilot.pause()
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
            await pilot.pause()
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


def test_escaping_the_menu_leaves_the_browser_open_and_the_queue_alone(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert isinstance(application.screen, BrowserScreen)
            assert len(application.queue) == 0

    asyncio.run(scenario())


def test_play_now_still_queues_the_whole_level_from_the_chosen_track(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await pilot.pause()
            await pilot.press("down")  # cursor on B
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()

            assert [e.title for e in application.queue] == ["A", "B", "C"]
            assert application.queue.playing == 1

    asyncio.run(scenario())


def test_g_clears_a_filter_that_hides_the_playing_track(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            application.queue.playing = 0
            application._sync_queue()
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
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

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
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            application._play_index(1)
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
    monkeypatch.setattr(library, "save_queue_playlist", lambda *args: calls.append(args))

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


def test_a_shape_reaches_the_right_edge_of_the_window(monkeypatch):
    """The bars used to stop at nineteen, and then at a cap on the band count,
    both of which left most of the column empty."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(app_module.config, "VISUALIZER", "bars")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(200, 34)) as pilot:
            await pilot.pause()
            analyzer = application.query_one("#analyzer", Analyzer)
            analyzer.active = True
            analyzer.spectrum = [0.9] * Analyzer.BANDS
            for _ in range(20):
                analyzer.tick()
            await pilot.pause()

            width = analyzer.size.width
            bottom = analyzer.render_line(analyzer.size.height - 1).text
            assert bottom.rstrip() != ""
            # The last band is drawn within a band's width of the edge.
            assert len(bottom.rstrip()) >= width - 2, len(bottom.rstrip())

    asyncio.run(scenario())


def test_a_document_window_is_no_wider_than_what_it_holds(monkeypatch):
    """The browser is a table and spends every cell. Help and lyrics are
    documents, and an 85% box on a wide terminal left two thirds of itself
    empty beside text hugging the left edge."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            application.push_screen(HelpScreen(app_module.keys_for))
            await pilot.pause()

            box = application.screen.query_one("#help-box")
            assert box.size.width <= 96
            # And still the whole width when there is none to spare.
            await pilot.resize_terminal(76, 20)
            await pilot.pause()
            assert application.screen.query_one("#help-box").size.width >= 50

    asyncio.run(scenario())


def test_m_opens_the_track_menu_on_the_queue_row(monkeypatch):
    """The same menu the browser opens with ↵. There it has to be asked for
    because ↵ queues the whole level; here ↵ plays the row."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [a_deftones_track(), Entry(id=2, title="b", artist="x")], start=-1
            )
            application._sync_queue()
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


def test_the_equalizer_cycles_presets_and_names_the_one_it_is_on(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()

            await pilot.press("p")
            await pilot.pause()
            assert application.settings.preset == "rock"
            drawn = application.screen.query_one("#eq-preset").render().plain
            assert "rock" in drawn

            await pilot.press("P")
            await pilot.pause()
            assert application.settings.preset == "flat"

            # Wraps rather than stopping at the end.
            await pilot.press("P")
            await pilot.pause()
            assert application.settings.preset == "treble"

    asyncio.run(scenario())


def test_the_track_menu_can_add_the_track_to_an_existing_playlist(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr("tidalamp.app.ensure_fresh", lambda session: False)
    sent: list[tuple[str, int]] = []

    def add(session, playlist_id, tracks, batch_size=100):
        sent.append((playlist_id, len(list(tracks))))
        return 1

    monkeypatch.setattr(library, "add_to_playlist", add)
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
    monkeypatch.setattr(library, "add_to_playlist", lambda *a, **k: sent.append("x") or 0)
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
    monkeypatch.setattr("tidalamp.screens.browser.ensure_fresh", lambda session: False)
    added: list[tuple[str, bool]] = []

    def favourite(session, row, add=True):
        added.append((row.entry.title, add))
        return row.entry.label

    monkeypatch.setattr("tidalamp.library.favourite", favourite)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await pilot.pause()
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
            await pilot.pause()
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
            await pilot.pause()
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
            await pilot.pause()
            await pilot.press("enter")
            await settle(
                pilot, lambda: len(application.screen.query_one(RowList).rows) == 3
            )
            assert isinstance(application.screen, BrowserScreen)

    asyncio.run(scenario())


# ------------------------------------------------------------------------- help


def test_the_help_key_opens_the_help_and_closes_it_again(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            assert len(application.screen_stack) == 1

            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(application.screen, HelpScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert len(application.screen_stack) == 1

            # `h` is the second binding on the same action.
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(application.screen, HelpScreen)

    asyncio.run(scenario())


def test_the_help_lists_the_rebound_key_not_the_shipped_one(monkeypatch):
    """A help screen that showed DEFAULT_KEYS would be wrong for anyone who
    edited config.toml — which is the only reason the file exists."""
    isolate_runtime(monkeypatch)
    monkeypatch.setitem(app_module.config.KEYS, "play", "ctrl+j")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            application.push_screen(HelpScreen(app_module.keys_for))
            await pilot.pause()
            drawn = "\n".join(
                application.screen.query_one("#help-body").render_line(y).text
                for y in range(application.screen.query_one("#help-body").size.height)
            )
            assert "ctrl+j" in drawn
            assert "\n  x " not in drawn

    asyncio.run(scenario())


def test_the_help_credits_the_author_the_repo_the_licence_and_the_changes(monkeypatch):
    """The credits live on the «Acerca de» tab, one → away from the keys."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            screen = HelpScreen(app_module.keys_for)
            application.push_screen(screen)
            await pilot.pause()

            await pilot.press("right")
            await pilot.pause()
            document = "\n".join(text for _kind, text in screen._lines)

            assert about.AUTHOR in document
            assert about.REPO_URL in document
            assert about.LICENSE in document
            assert about.LICENSE_URL in document
            assert about.version() in document
            for release in about.releases():
                assert release.version in document
                for change in release.changes:
                    assert change in document

    asyncio.run(scenario())


def test_the_help_moves_between_the_keys_and_the_about_tab(monkeypatch):
    """→ opens «Acerca de», ← comes back, and neither runs off the ends."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            screen = HelpScreen(app_module.keys_for)
            application.push_screen(screen)
            await pilot.pause()
            assert screen._tab == HelpScreen.SHORTCUTS

            # ← on the first tab has nowhere to go and must not wrap round.
            await pilot.press("left")
            await pilot.pause()
            assert screen._tab == HelpScreen.SHORTCUTS

            # Leave the keys scrolled, so coming back can be checked.
            await pilot.press("down", "down")
            await pilot.pause()
            assert screen._offset == 2

            await pilot.press("right")
            await pilot.pause()
            assert screen._tab == HelpScreen.ABOUT
            assert screen._offset == 0
            drawn = "\n".join(
                screen.query_one("#help-body").render_line(y).text
                for y in range(screen.query_one("#help-body").size.height)
            )
            assert about.REPO_URL in drawn

            await pilot.press("right")
            await pilot.pause()
            assert screen._tab == HelpScreen.ABOUT, "no hay una tercera pestaña"

            await pilot.press("left")
            await pilot.pause()
            assert screen._tab == HelpScreen.SHORTCUTS
            assert screen._offset == 2, "cada pestaña recuerda dónde se quedó"

    asyncio.run(scenario())


def test_the_help_scrolls_and_stops_at_both_ends(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            screen = HelpScreen(app_module.keys_for)
            application.push_screen(screen)
            await pilot.pause()
            assert screen._offset == 0

            await pilot.press("up")
            await pilot.pause()
            assert screen._offset == 0, "no debe pasar del principio"

            await pilot.press("end")
            await pilot.pause()
            bottom = screen._offset
            assert bottom > 0
            assert bottom == len(screen._lines) - screen._height()

            await pilot.press("down")
            await pilot.pause()
            assert screen._offset == bottom, "no debe pasar del final"

            await pilot.press("home")
            await pilot.pause()
            assert screen._offset == 0

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

    asyncio.run(scenario())


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
                "MI BIBLIOTECA", library.cached("playlists", loader), "playlists"
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


def test_the_notice_appears_and_clears_as_the_window_is_resized(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            notice = application.query_one("#too-small", Static)
            assert notice.display is False

            await pilot.resize_terminal(59, 40)
            await pilot.pause()
            assert notice.display is True

            await pilot.resize_terminal(100, 40)
            await pilot.pause()
            assert notice.display is False

    asyncio.run(scenario())


# ---------------------------------------------------------------- favoritos


def test_f_favourites_the_selected_track_and_says_so(monkeypatch):
    isolate_runtime(monkeypatch)
    calls: list[tuple[int, bool]] = []

    def fake_favourite(session, row, add=True):
        calls.append((row.entry.id, add))
        return row.entry.label

    monkeypatch.setattr("tidalamp.library.favourite", fake_favourite)
    monkeypatch.setattr("tidalamp.screens.browser.ensure_fresh", lambda session: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.queue.append([Entry(id=42, title="Schism", artist="TOOL")])
            application._sync_queue()
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
    monkeypatch.setattr("tidalamp.screens.browser.ensure_fresh", lambda session: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.queue.append([Entry(id=1, title="t", artist="a")])
            application._sync_queue()
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
    monkeypatch.setattr("tidalamp.screens.browser.ensure_fresh", lambda session: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            library.cached("fav:tracks", lambda: [Row(label="vieja")])()
            assert "fav:tracks" in library._LEVELS

            application.queue.append([Entry(id=1, title="t", artist="a")])
            application._sync_queue()
            await pilot.pause()
            await pilot.press("f")
            await settle(pilot, lambda: "favoritos" in application.status)

            assert "fav:tracks" not in library._LEVELS

    asyncio.run(scenario())


def test_the_help_can_be_searched_and_says_how_at_the_bottom(monkeypatch):
    """`/` opens a box under the keys; what is typed narrows them, each match
    under its section's heading, and esc takes the search away before it
    closes the window. The footer names the key."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            screen = HelpScreen(app_module.keys_for)
            application.push_screen(screen)
            await pilot.pause()

            def body() -> str:
                widget = screen.query_one("#help-body")
                return "\n".join(
                    widget.render_line(y).text for y in range(widget.size.height)
                )

            hint = screen.query_one("#help-hint", Static).render_line(0).text
            assert "/ buscar" in hint
            everything = body()

            await pilot.press("slash")
            await pilot.pause()
            assert screen.query_one("#help-filter-bar").display
            # Letters go to the box, not to the bindings: `h` would close.
            for key in ("h", "question_mark", "backspace", "backspace"):
                await pilot.press(key)
            await pilot.pause()
            assert isinstance(application.screen, HelpScreen)
            for key in "balance":
                await pilot.press(key)
            await pilot.pause()

            narrowed = body()
            assert "balance" in narrowed
            assert "Volumen y sonido" in narrowed, "cada fila bajo su sección"
            assert "cola" not in narrowed.lower().split("volumen")[0]
            assert len(narrowed.strip()) < len(everything.strip())
            count = screen.query_one("#help-filter-count", Static).render_line(0).text
            assert " de " in count

            # Accents and case do not matter.
            screen.query_one("#help-filter").value = "ECUALIZADOR"
            await pilot.pause()
            assert "ecualizador" in body()

            screen.query_one("#help-filter").value = "zzzz"
            await pilot.pause()
            assert "nada coincide" in body()

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(application.screen, HelpScreen)
            assert not screen.query_one("#help-filter-bar").display
            assert body() == everything, "vuelve la página entera, a su alto"

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(application.screen, HelpScreen)

    asyncio.run(scenario())


def test_s_sorts_the_level_says_so_and_keeps_it(monkeypatch):
    """`s` offers the orders the level has; the level comes back sorted, the
    title names the order, and walking out and back in keeps it."""
    from app_helpers import settle, visible_labels

    from tidalamp import library
    from tidalamp.library import Row
    from tidalamp.queue import Entry
    from tidalamp.screens import BrowserScreen, ChoiceScreen

    isolate_runtime(monkeypatch)
    monkeypatch.setattr(library, "_CHOSEN", {})
    library.forget()
    tracks = [
        Row(label=f"TOOL - {title}", entry=Entry(id=i, title=title, artist="TOOL"))
        for i, title in enumerate(["Sober", "Aenema", "Schism"])
    ]
    album = Row(
        label="Álbum",
        **library._sortable(
            "album:9",
            library.ALBUM_TRACK_BY,
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
            library.forget()

    asyncio.run(scenario())


def test_d_removes_a_favourite_after_asking_and_the_row_goes(monkeypatch):
    """`d` asks first, on «cancel»; confirmed, the row leaves the level. At
    the top there is nothing to remove from, and it says so."""
    from app_helpers import settle, visible_labels

    from tidalamp import library
    from tidalamp.library import Row
    from tidalamp.queue import Entry
    from tidalamp.screens import BrowserScreen, ChoiceScreen

    isolate_runtime(monkeypatch)
    removed: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        library,
        "favourite",
        lambda session, row, add=True: removed.append((row.label, add)) or row.label,
    )
    monkeypatch.setattr("tidalamp.screens.browser.ensure_fresh", lambda session: None)
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


def test_question_mark_in_the_browser_shows_only_its_keys(monkeypatch):
    """The footer says `? ayuda` and no more; `?` opens the help with the
    browser's section alone, and esc comes back to the browser."""
    from app_helpers import settle, visible_labels

    from tidalamp.screens import BrowserScreen, HelpScreen

    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            open_browser(application)
            browser = application.screen
            assert isinstance(browser, BrowserScreen)
            await settle(pilot, lambda: len(visible_labels(browser)) > 0)

            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(application.screen, HelpScreen)
            body = application.screen.query_one("#help-body")
            text = "\n".join(body.render_line(y).text for y in range(body.size.height))
            assert "ordenar el nivel" in text
            assert "quitar de favoritos o de la playlist abierta" in text
            assert "subir volumen" not in text
            title = application.screen.query_one("#help-title").render_line(0).text
            assert "ACERCA DE" not in title

            await pilot.press("escape")
            await pilot.pause()
            assert application.screen is browser

    asyncio.run(scenario())
