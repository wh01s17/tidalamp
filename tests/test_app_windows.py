"""The windows over the player: help, the equaliser, how wide a window is,
the notice of a terminal too small, and the player behind a modal."""

from __future__ import annotations

import asyncio

from app_helpers import (
    FakeMpv,
    isolate_runtime,
    open_browser,
    settle,
    transport,
    visible_labels,
    wait_for,
)
from rich.cells import cell_len
from textual.screen import Screen
from textual.widgets import Static

from tidalamp import about, keys
from tidalamp import app as app_module
from tidalamp.app import HelpScreen, TidalAmp
from tidalamp.transport import SEPARATOR
from tidalamp.widgets import Analyzer, TimeDisplay


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
            assert application.playback.was_idle is False

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
                application.transport.refresh()
                drawn = transport(application, "menu")

                assert cell_len(drawn) <= width, "el menú no puede desbordar"
                entries = [part.strip() for part in drawn.split(SEPARATOR)]
                assert entries[0].strip() == "? ayuda", "la ayuda va primero"
                # Every entry that survived is one of the whole ones.
                for entry in entries:
                    assert entry in whole.split(SEPARATOR)

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
            application.push_screen(HelpScreen(keys.keys_for))
            await pilot.pause()

            box = application.screen.query_one("#help-box")
            assert box.size.width <= 96
            # And still the whole width when there is none to spare.
            await pilot.resize_terminal(76, 20)
            await wait_for(
                pilot,
                lambda: application.screen.query_one("#help-box").size.width >= 50,
                what="la ayuda a lo ancho",
            )
            assert application.screen.query_one("#help-box").size.width >= 50

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
            application.push_screen(HelpScreen(keys.keys_for))
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
            screen = HelpScreen(keys.keys_for)
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
            screen = HelpScreen(keys.keys_for)
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
            screen = HelpScreen(keys.keys_for)
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


def test_the_notice_appears_and_clears_as_the_window_is_resized(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            notice = application.query_one("#too-small", Static)
            assert notice.display is False

            await pilot.resize_terminal(59, 40)
            await wait_for(pilot, lambda: notice.display, what="el aviso")
            assert notice.display is True

            await pilot.resize_terminal(100, 40)
            await wait_for(pilot, lambda: not notice.display, what="sin aviso")
            assert notice.display is False

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
            screen = HelpScreen(keys.keys_for)
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
            # Once the layout has given the page the box's row, however long
            # that takes: a page left a line short never gets there.
            await wait_for(
                pilot,
                lambda: body() == everything,
                what="vuelve la página entera, a su alto",
            )

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(application.screen, HelpScreen)

    asyncio.run(scenario())


def test_question_mark_in_the_browser_shows_only_its_keys(monkeypatch):
    """The footer says `? ayuda` and no more; `?` opens the help with the
    browser's section alone, and esc comes back to the browser."""

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
