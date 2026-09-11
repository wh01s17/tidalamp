"""The cover: its box, its protocols, and windows opening over it."""

from __future__ import annotations

import asyncio

import pytest
from app_helpers import (
    FakeMpv,
    a_cover,
    a_deftones_track,
    a_queue,
    config_row,
    isolate_config,
    isolate_runtime,
    settle,
    use_theme,
)
from textual.screen import Screen
from textual.widgets import Input, Static

from tidalamp import app as app_module
from tidalamp import artwork, library
from tidalamp import audio as audio_module
from tidalamp.app import ConfigScreen, RowList, TidalAmp
from tidalamp.artwork import Protocol
from tidalamp.queue import Entry
from tidalamp.widgets import (
    Analyzer,
    Artwork,
    Glide,
    Spinner,
)


def test_the_cover_takes_no_room_until_there_is_one(monkeypatch):
    # Custom render_line implementations must give every Segment a Style;
    # Textual's monochrome filter otherwise receives None under NO_COLOR.
    monkeypatch.setenv("NO_COLOR", "1")
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            art = application.query_one(Artwork)
            assert art.cover is None
            assert art.styles.display == "none"

            art.show(a_cover())
            await pilot.pause()
            assert art.styles.display == "block"

    asyncio.run(scenario())


def test_the_cover_box_grows_with_the_terminal_but_leaves_the_row_alone(monkeypatch):
    """18x9 was fixed, which made the cover a stamp on a big terminal.

    Two ceilings have to hold: the display band must not eat the playlist,
    and the box shares its row with the clock and the readout.
    """
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        for size, expected in ((80, 30), 9), ((120, 50), 12), ((180, 100), 20):
            application = TidalAmp(object(), FakeMpv())
            async with application.run_test(size=size) as pilot:
                await pilot.pause()
                art = application.query_one(Artwork)
                assert (art.rows, art.cols) == (expected, expected * 2), size

                # A square box on screen, and room left for the rest of the row.
                art.show(a_cover())
                await pilot.pause()
                clock = application.query_one("#clock")
                readout = application.query_one("#readout")
                assert art.region.right <= clock.region.x
                assert readout.region.right <= size[0]
                assert application.query_one("#playlist").size.height > 0

    asyncio.run(scenario())


def test_resizing_asks_for_the_cover_again_at_the_new_size(monkeypatch):
    """resize() drops the old cover, so something has to redraw it."""
    isolate_runtime(monkeypatch)
    asked: list[str] = []
    monkeypatch.setattr(TidalAmp, "_art_worker", lambda self, url: asked.append(url))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            application._art_url = "http://example/cover.jpg"
            asked.clear()
            application.query_one(Artwork).show(a_cover())

            await pilot.resize_terminal(180, 100)
            await pilot.pause()
            assert application.query_one(Artwork).rows == 20
            assert asked == ["http://example/cover.jpg"]

    asyncio.run(scenario())


def test_blocks_paint_four_pixels_per_cell(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            art = application.query_one(Artwork)
            art.show(a_cover())
            await pilot.pause()

            segments = list(art.render_line(0))
            # Red and green over blue and yellow: the two bright ones are the
            # upper pair, so the cell is a quadrant glyph and not a half block.
            assert segments[0].text in artwork.QUADRANTS
            assert segments[0].style.color is not None
            assert segments[0].style.bgcolor is not None
            # The second cell is the black pair, which is flat and so a space.
            assert segments[1].text == " "

    asyncio.run(scenario())


def test_a_modal_takes_a_pixel_cover_down_and_the_tick_puts_it_back(monkeypatch):
    """kitty images float above the text, so a modal would open under them."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        # Roomy on purpose: the compact layout drops the cover by design.
        async with application.run_test(size=(100, 30)) as pilot:
            art = application.query_one(Artwork)
            cover = a_cover(Protocol.KITTY, escape="\x1b_Ga=T\x1b\\")
            art.show(cover)
            await pilot.pause()

            application.push_screen(Screen())
            await pilot.pause()
            assert art.cover is None
            assert application._art_hidden

            application.pop_screen()
            await pilot.pause()
            application._tick_slow()
            assert art.cover is cover
            assert not application._art_hidden

    asyncio.run(scenario())


def test_switching_the_cover_protocol_redraws_it_without_a_restart(monkeypatch):
    """It used to say «al reiniciar», which was tolerable while this was a
    detail of the display. Transparency now moves this setting on the user's
    behalf, and a hole where the cover was until the next launch is not."""
    isolate_runtime(monkeypatch)
    asked: list[str] = []
    monkeypatch.setattr(TidalAmp, "_art_worker", lambda self, url: asked.append(url))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        application.art_protocol = Protocol.KITTY
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            entry = Entry(id=1, title="t", artist="a", art_url="https://c/1.jpg")
            application.queue.replace([entry], start=0)
            application._load_art(entry)
            application.query_one(Artwork).show(a_cover(Protocol.KITTY))
            asked.clear()

            # Through monkeypatch: it is a module global, and leaving it set
            # would follow the next test into its own run.
            monkeypatch.setattr(app_module.config, "ARTWORK", "blocks")
            application._setting_changed("artwork")
            await pilot.pause()

            assert application.art_protocol is Protocol.BLOCKS
            # The old picture came down — a kitty image outlives its cells
            # until something deletes it — and the new one was asked for.
            assert asked == ["https://c/1.jpg"]

    asyncio.run(scenario())


def test_a_cover_that_lands_while_a_modal_is_open_does_not_cover_it(monkeypatch):
    """A pixel cover is painted above the text whenever it arrives, so a track
    started from the browser used to drop the album art onto the browser."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            application.push_screen(Screen())
            await pilot.pause()

            application._art_ready(a_cover(Protocol.KITTY))
            assert application.query_one(Artwork).cover is None
            assert application._art_hidden

            # Text covers have no such problem and stay where they land.
            application._art_hidden = False
            blocks = a_cover(Protocol.BLOCKS)
            application._art_ready(blocks)
            assert application.query_one(Artwork).cover is blocks

    asyncio.run(scenario())


def test_a_second_cover_behind_a_window_stays_down_too(monkeypatch):
    """The first cover was taken down when the window opened, so a second one
    arriving behind it (a track changed from the browser, a theme changed in
    the settings) found `_hide_art` saying it had already hidden a cover, and
    stayed up, painted over the window. It waits for the window instead, and
    is the one that comes back when the window closes."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            art = application.query_one(Artwork)
            first = a_cover(Protocol.KITTY)
            application._art_ready(first)
            assert art.cover is first

            application.push_screen(Screen())
            await pilot.pause()
            assert art.cover is None and application._art_hidden

            second = a_cover(Protocol.KITTY)
            application._art_ready(second)
            assert art.cover is None, "no se pinta encima de la ventana"
            assert application._pending_art is second

            application.pop_screen()
            await pilot.pause(0.4)
            assert art.cover is second

    asyncio.run(scenario())


def test_a_cover_drawn_as_text_stays_up_behind_a_modal(monkeypatch):
    """Half blocks are characters like any other, so a modal draws over them.
    Taking them down anyway left a hole in the player behind the scrim."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            art = application.query_one(Artwork)
            cover = a_cover(Protocol.BLOCKS)
            art.show(cover)
            await pilot.pause()

            application.push_screen(Screen())
            await pilot.pause()

            assert art.cover is cover
            assert not application._art_hidden

    asyncio.run(scenario())


def test_the_same_cover_is_not_fetched_twice(monkeypatch):
    isolate_runtime(monkeypatch)
    asked: list[str] = []
    monkeypatch.setattr(TidalAmp, "_art_worker", lambda self, url: asked.append(url))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            entry = Entry(id=1, title="t", artist="a", art_url="https://c/1.jpg")
            application._load_art(entry)
            application._load_art(entry)
            assert asked == ["https://c/1.jpg"]

            # A track with no cover hides whatever was on screen.
            application.query_one(Artwork).show(a_cover())
            application._load_art(Entry(id=2, title="t2", artist="a"))
            assert application.query_one(Artwork).cover is None

    asyncio.run(scenario())


def test_artwork_off_never_asks_for_a_cover(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(
        "tidalamp.artwork.detect_protocol",
        lambda env=None, configured="": Protocol.NONE,
    )
    asked: list[str] = []
    monkeypatch.setattr(TidalAmp, "_art_worker", lambda self, url: asked.append(url))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            application._load_art(
                Entry(id=1, title="t", artist="a", art_url="https://c/1.jpg")
            )
            assert asked == []

    asyncio.run(scenario())


def test_x_pauses_what_is_playing_instead_of_restarting_it(monkeypatch):
    """This is what stops it being a second Enter: Enter always starts the
    cursor track, «x» acts on what is already going."""
    isolate_runtime(monkeypatch)
    started: list[int] = []
    monkeypatch.setattr(TidalAmp, "_play_index", lambda self, i: started.append(i))

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 24)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=1, title="t", artist="a", duration=9)], start=0
            )
            mpv.idle = False

            await pilot.press("x")
            await pilot.pause()
            assert mpv.paused is True
            assert started == [], "no debe reiniciar la pista"

            await pilot.press("x")
            await pilot.pause()
            assert mpv.paused is False

    asyncio.run(scenario())


def test_stop_stays_stopped_instead_of_restarting_the_queue(monkeypatch):
    """«v» stopped mpv, the tick saw it go idle, read that as «the track
    ended» and played the next one — which from a stopped queue is the first.
    Pressing stop restarted the whole list."""
    isolate_runtime(monkeypatch)
    started: list[int] = []
    monkeypatch.setattr(TidalAmp, "_play_index", lambda self, i: started.append(i))

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 26)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=i, title=f"t{i}", artist="a", duration=9) for i in range(3)],
                start=1,
            )
            application._sync_queue()
            mpv.idle = False
            # Long enough for the slow tick to have seen it playing: without
            # that the guard is never reached and the test passes for the
            # wrong reason.
            await pilot.pause(0.4)
            assert application._was_idle is False
            started.clear()

            await pilot.press("c")
            await pilot.pause(0.8)

            assert application.queue.playing == -1
            assert started == [], "nada debe volver a arrancar"
            assert mpv.idle is True

    asyncio.run(scenario())


def test_x_starts_the_cursor_track_when_nothing_is_loaded(monkeypatch):
    isolate_runtime(monkeypatch)
    started: list[int] = []
    monkeypatch.setattr(TidalAmp, "_play_index", lambda self, i: started.append(i))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 24)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=i, title=f"t{i}", artist="a", duration=9) for i in range(3)]
            )
            application._sync_queue()
            application.query_one("#playlist", RowList).cursor = 2

            await pilot.press("x")
            await pilot.pause()
            assert started == [2]

    asyncio.run(scenario())


def test_a_partial_playlist_reaches_status_without_changing_the_queue(monkeypatch):
    isolate_runtime(monkeypatch)

    def partial(session, title, entries):
        raise library.PlaylistSaveFailed(title, 2, len(entries), RuntimeError("sin red"))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(app_module, "ensure_fresh", lambda session: False)
            monkeypatch.setattr(library, "save_queue_playlist", partial)
            monkeypatch.setattr(
                application,
                "call_from_thread",
                lambda callback, *args: callback(*args),
            )
            monkeypatch.setattr(
                application,
                "_save_playlist_worker",
                lambda title, entries: TidalAmp._save_playlist_worker.__wrapped__(
                    application, title, entries
                ),
            )
            a_queue(application, "Schism", "Lateralus", "The Grudge")
            before = [entry.id for entry in application.queue]

            await pilot.press("p")
            await pilot.pause()
            application.screen.query_one("#playlist-name-input", Input).value = "Viaje"
            await pilot.press("enter")
            await pilot.pause()

            assert [entry.id for entry in application.queue] == before
            assert application.status == (
                "playlist «Viaje» creada con 2 de 3 pistas: sin red"
            )
            assert not application.query_one("#busy", Spinner).busy

    asyncio.run(scenario())


def test_the_analyser_starts_where_the_track_details_do(monkeypatch):
    """Beside the cover and the clock, not under them: the wide shapes share
    the readout column with the SRC and OUT lines above them."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(app_module.config, "VISUALIZER", "mirror")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            analyzer = application.query_one("#analyzer", Analyzer)
            badges = application.query_one("#badges", Glide)
            art = application.query_one(Artwork)

            assert analyzer.region.x == badges.region.x
            assert analyzer.region.x > art.region.right
            # As far right as anything else inside the panel: the frame and
            # the one cell of air the whole display band keeps.
            assert analyzer.region.right == application.size.width - 3

    asyncio.run(scenario())


def test_the_block_under_the_clock_names_the_artist_album_and_year(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            meta = application.query_one("#trackmeta", Glide)
            assert meta.render().plain == "", "vacío mientras no suena nada"

            application.queue.replace([a_deftones_track()], start=-1)
            application._sync_queue()
            application._play_index(0)
            await pilot.pause()

            lines = [line.rstrip() for line in meta.render().plain.split("\n")]
            assert lines[:3] == ["Deftones", "Around the Fur", "1997 · 4:59"]
            # Written when the track starts, not when the stream resolves: the
            # readout waits for the network and this does not have to.
            assert (
                not application.query("#badges")[0].render().plain.startswith("SRC  AAC")
            )

    asyncio.run(scenario())


def test_the_centred_wordmark_gets_a_row_between_it_and_the_band(monkeypatch):
    """Tried once while it was left-aligned and taken back, because there the
    row isolated a bar that already sat on the cover. Centred it separates."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "quattro")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            title = application.query_one("#titlebar", Static)
            display = application.query_one("#display")
            assert display.region.y - title.region.bottom == 1
            # Outside the bar, so the band keeps its rows and `_fit_artwork`
            # keeps its arithmetic.
            assert display.size.height == 10

            await pilot.resize_terminal(82, 24)
            await pilot.pause()
            title = application.query_one("#titlebar", Static)
            assert application.query_one("#display").region.y == title.region.bottom

    asyncio.run(scenario())


@pytest.mark.parametrize("theme", app_module.LAYOUTS)
def test_the_cover_has_air_inside_its_band(theme, monkeypatch):
    """Two cells off the frame and a row off the top of the dark band. It
    used to sit flush against both, on the idea that a gap reads as the
    picture having come loose; in use it read as glued to the border."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, theme)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            application.query_one(Artwork).show(a_cover())
            await pilot.pause()

            display = application.query_one("#display")
            art = application.query_one(Artwork)
            assert art.region.x - display.region.x >= 2, theme
            assert art.region.y - display.region.y >= 1, theme
            assert art.region.bottom <= display.region.bottom, theme
            seek = application.query_one("#seek")
            assert display.region.bottom <= seek.region.y, theme

    asyncio.run(scenario())


def test_the_band_follows_the_padding_even_when_nothing_resized(monkeypatch):
    """The padding is the other half of the sum and settles on its own
    schedule: at startup the layout class lands before Textual has recomputed
    the styles, so the first pass reads none and the second resizes nothing.
    Tying the correction to the cover having changed size skipped it."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 44)) as pilot:
            await pilot.pause()
            application.query_one(Artwork).show(a_cover())
            await pilot.pause()

            display = application.query_one("#display")
            before = int(display.styles.height.value)
            top, bottom = display.styles.padding.top, display.styles.padding.bottom
            # A layout that pads more than the last one, with a cover that is
            # already the right size, so `resize()` reports nothing.
            display.styles.padding = (top + 2, 1, bottom, 2)
            application._fit_artwork()

            # The declared height, not the laid-out one: this is what the band
            # is responsible for, and the geometry follows a frame later.
            assert int(display.styles.height.value) == before + 2

    asyncio.run(scenario())


def test_undoing_a_clear_does_not_start_the_music_again(monkeypatch):
    """Clearing stopped it. A song starting on its own because someone undid a
    mistake is a worse surprise than the mistake."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            a_queue(application, "Schism", "Lateralus")
            await pilot.press("C")
            await pilot.press("u")
            await pilot.pause()

            assert application.queue.playing == -1

    asyncio.run(scenario())


def test_cycling_from_a_hand_made_curve_starts_at_the_first_preset(monkeypatch):
    """There is nowhere in the list to step from: the bands are somewhere the
    catalogue does not describe, and the nearest curve is nobody's idea of the
    next one."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.settings.set_gain(3, 7.0)
            assert application.settings.preset == "manual"

            await pilot.press("e")
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

            assert application.settings.preset == "flat"

    asyncio.run(scenario())


def test_turning_transparency_on_moves_a_pixel_cover_to_blocks(monkeypatch, tmp_path):
    """The player behind the window is the whole point, and a kitty cover has
    to come down for the window to be visible at all. Blocks stay up."""
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        application.art_protocol = Protocol.KITTY
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = config_row(screen, "Transparencia")
            await pilot.press("enter")
            await pilot.pause()

            assert app_module.config.ARTWORK == "blocks"
            assert app_module.config.read_file(path)["artwork"] == "blocks"
            # And it says so, rather than moving a setting behind the user's
            # back: it costs the cover its resolution.
            assert "blocks" in screen._notice
            assert screen.KITTY_DOCS in screen._notice
            drawn = application.screen.query_one("#config-list").render_line
            lines = [drawn(y).text for y in range(34)]
            assert any(screen.KITTY_DOCS in line for line in lines)

    asyncio.run(scenario())


def test_a_cover_that_is_already_text_changes_without_a_word(monkeypatch, tmp_path):
    """`auto` on a terminal where auto already meant blocks: the row has to
    say a word the shortened list contains, but nothing was taken away, so
    there is nothing to warn about."""
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        application.art_protocol = Protocol.BLOCKS
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = config_row(screen, "Transparencia")
            await pilot.press("enter")
            await pilot.pause()

            assert app_module.config.TRANSPARENCY is True
            assert app_module.config.read_file(path)["artwork"] == "blocks"
            assert screen._notice == ""

    asyncio.run(scenario())


def test_transparency_leaves_the_cover_only_what_a_window_can_cover(
    monkeypatch, tmp_path
):
    """With the player showing through, `kitty` is not a choice any more: it
    would put the album art on top of the window. The list says so by not
    offering it, and gives it back when transparency goes off."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        application.art_protocol = Protocol.KITTY
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()

            def cover_row():
                return screen._rows[config_row(screen, "Carátula")]

            assert cover_row().choices == ConfigScreen.ARTWORKS

            screen.cursor = config_row(screen, "Transparencia")
            await pilot.press("enter")
            await pilot.pause()
            assert cover_row().choices == ConfigScreen.ARTWORKS_OVER_PLAYER

            # And cycling it now only ever lands on one of those two.
            screen.cursor = config_row(screen, "Carátula")
            seen = set()
            for _ in range(4):
                await pilot.press("enter")
                await pilot.pause()
                seen.add(app_module.config.ARTWORK)
            assert seen == set(ConfigScreen.ARTWORKS_OVER_PLAYER)

            screen.cursor = config_row(screen, "Transparencia")
            await pilot.press("enter")
            await pilot.pause()
            assert app_module.config.TRANSPARENCY is False
            assert cover_row().choices == ConfigScreen.ARTWORKS

    asyncio.run(scenario())


def test_restarting_pipewire_stops_playback_first(monkeypatch, tmp_path):
    """mpv is holding the sink; the daemon must not be pulled from under it."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(audio_module, "restart", lambda: "hecho")

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=1, title="t", artist="a", duration=9)], start=0
            )
            mpv.idle = False
            screen = ConfigScreen()
            application.push_screen(screen)
            await pilot.pause()

            screen.cursor = config_row(screen, "Reiniciar PipeWire")
            await pilot.pause()
            await pilot.press("enter")
            await settle(pilot, lambda: application.status == "hecho")

            assert mpv.idle is True
            assert application.queue.playing == -1

    asyncio.run(scenario())


def test_the_help_hides_a_kitty_cover_like_the_other_modals(monkeypatch):
    """An image drawn by the terminal floats over the text: a modal opened
    under it would be unreadable. push_screen already handles it."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            application.query_one(Artwork).show(a_cover(Protocol.KITTY, escape="\x1b_G"))
            await pilot.pause()

            await pilot.press("question_mark")
            await pilot.pause()
            assert application._art_hidden
            assert application.query_one(Artwork).cover is None

    asyncio.run(scenario())
