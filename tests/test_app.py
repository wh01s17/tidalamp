"""Focused Textual workflow regressions."""

from __future__ import annotations

import asyncio
import threading

import pytest
from rich.cells import cell_len
from textual.screen import Screen
from textual.widgets import Input, Static

from tidalamp import about, artwork, library
from tidalamp import app as app_module
from tidalamp import audio as audio_module
from tidalamp import columns as columns_module
from tidalamp.app import BrowserScreen, ConfigScreen, HelpScreen, RowList, TidalAmp
from tidalamp.artwork import Cover, Protocol
from tidalamp.library import Row
from tidalamp.player import Mpv
from tidalamp.queue import Entry, Queue
from tidalamp.screens import (
    BROWSER_HINTS,
    TRACK_ACTIONS,
    ColumnsScreen,
    PlaylistNameScreen,
    TrackActionsScreen,
)
from tidalamp.settings import Settings
from tidalamp.theme import DEFAULT_COLORS, ThemePalette
from tidalamp.widgets import (
    Analyzer,
    Artwork,
    Marquee,
    SeekBar,
    Slider,
    Spinner,
    TimeDisplay,
)


async def settle(pilot, done, tries: int = 100) -> None:
    """Pump the event loop until a worker's result has landed."""
    for _ in range(tries):
        await pilot.pause()
        if done():
            # The callback can make `done` true just before the thread worker
            # itself returns. Waiting for the Worker prevents asyncio.run()
            # from closing its executor while call_from_thread() is in flight.
            await pilot.app.workers.wait_for_complete()
            return
        await asyncio.sleep(0.01)
    raise AssertionError("el worker no terminó")


class FakeMpv:
    alive = True
    position = 0.0
    duration = 0.0
    paused = False
    idle = True

    def __init__(self) -> None:
        self.filter_calls: list[tuple[str, str | None]] = []
        self.seek_calls: list[tuple[float, str]] = []
        self.loaded: str | None = None
        self._volume = 100

    @property
    def volume(self) -> int:
        return self._volume

    @volume.setter
    def volume(self, value: int) -> None:
        # Same ceiling as the real player: the app relies on it to clamp.
        self._volume = max(0, min(Mpv.VOLUME_MAX, value))

    def load(self, url: str) -> None:
        self.loaded = url

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def stop(self) -> None:
        self.paused = False
        self.idle = True
        self.loaded = None

    def seek(self, seconds: float, mode: str = "absolute") -> None:
        self.seek_calls.append((seconds, mode))

    def set_filter(self, label: str, graph: str | None) -> None:
        self.filter_calls.append((label, graph))

    def rms(self) -> float:
        return -91.0

    def close(self) -> None:
        pass


def isolate_runtime(monkeypatch) -> None:
    async def no_mpris(self) -> None:
        return None

    def probe_audio(screen) -> None:
        """Resolve the fake audio stack inline, without a closing-loop race."""
        sink = audio_module.sink()
        allowed = audio_module.allowed_rates()
        screen._probed(sink, allowed, audio_module.hardware_rates(sink.name))

    monkeypatch.setattr(Queue, "load", lambda self: False)
    monkeypatch.setattr(Queue, "save", lambda self: None)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings()))
    monkeypatch.setattr(TidalAmp, "_start_spectrum", lambda self: None)
    monkeypatch.setattr(TidalAmp, "_start_mpris", no_mpris)
    # The app-level audio worker is unrelated to these UI tests. Letting it
    # race the end of run_test() can leave call_from_thread() waiting on an
    # event loop that is already closing, which makes asyncio.run() wait for
    # its default executor indefinitely on Python 3.14.
    monkeypatch.setattr(TidalAmp, "_refresh_sink_worker", lambda self: None)
    monkeypatch.setattr(ConfigScreen, "_probe", probe_audio)
    monkeypatch.setattr(audio_module, "sink", lambda: audio_module.Sink())
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: ())
    monkeypatch.setattr(audio_module, "hardware_rates", lambda name: ())


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


# The transport is drawn as boxes three rows tall; row 1 carries the labels.
LABEL_ROW = 1


def transport(application, half: str = "play") -> str:
    return application.query_one(f"#transport-{half}").render_line(LABEL_ROW).text


def use_theme(monkeypatch, name: str) -> None:
    """Both layouts come out of the same widgets; pick one for a test.

    `config.THEME` is a module global, so it is set through monkeypatch and
    not by hand: conftest restores it either way, but this keeps the reason
    next to the test that needs it.
    """
    monkeypatch.setattr(app_module.config, "THEME", name)


def lit(application) -> dict[str, bool]:
    """Whether each state button is drawn on the accent, by its glyph."""
    accent = application.tidalamp_palette["accent"].lower()
    found = {}
    for segment in application.query_one("#transport-play").render_line(LABEL_ROW):
        for glyph in ("⇄", "↻"):
            if glyph in segment.text:
                colour = segment.style.bgcolor
                found[glyph] = colour is not None and colour.name.lower() == accent
    return found


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


def test_the_transport_buttons_are_clickable_without_changing_keyboard_controls(
    monkeypatch,
):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            start, end, _action = next(
                hit for hit in application._transport_hits if hit[2] == "shuffle"
            )
            clicked = await pilot.click(
                "#transport-play", offset=((start + end) // 2, LABEL_ROW)
            )
            await pilot.pause()

            assert clicked is True
            assert application.queue.shuffle is True
            assert "⇄●" in transport(application)

    asyncio.run(scenario())


def test_running_app_follows_an_omarchy_theme_change(monkeypatch):
    isolate_runtime(monkeypatch)
    initial = ThemePalette(dict(DEFAULT_COLORS), source="omarchy")
    changed_colors = dict(DEFAULT_COLORS)
    changed_colors["accent"] = "#7aa2f7"
    changed_colors["panel"] = "#1a1b26"
    changed = ThemePalette(changed_colors, source="omarchy")
    palettes = iter((initial, changed))
    monkeypatch.setattr(
        "tidalamp.app.load_palette", lambda *args, **kwargs: next(palettes)
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.press("s")
            application._refresh_theme()

            modes = application.query_one("#transport-play", Static)
            assert application.tidalamp_palette is changed
            assert application.get_theme_variable_defaults()["tidalamp-accent"] == (
                "#7aa2f7"
            )
            assert application.query_one("#main").styles.background.hex == "#1A1B26"
            assert any("#7aa2f7" in str(span.style) for span in modes.content.spans)

    asyncio.run(scenario())


# ---------------------------------------------------------------------- artwork


def a_cover(protocol=Protocol.BLOCKS, escape=""):
    pixels = (((255, 0, 0), (0, 255, 0)), ((0, 0, 255), (255, 255, 0)))
    return Cover(
        cols=2,
        rows=1,
        protocol=protocol,
        pixels=pixels if protocol is Protocol.BLOCKS else None,
        escape=escape,
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


def test_a_narrow_but_tall_terminal_keeps_the_small_box(monkeypatch):
    """Height alone must not grow it: the readout shares the row and would go."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(76, 200)) as pilot:
            await pilot.pause()
            assert application.query_one(Artwork).rows == Artwork.MIN_ROWS

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


def test_half_blocks_paint_two_pixels_per_cell(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            art = application.query_one(Artwork)
            art.show(a_cover())
            await pilot.pause()

            segments = list(art.render_line(0))
            assert segments[0].text == "▀"
            # Upper half is the first pixel row, lower half the second.
            assert segments[0].style.color.triplet == (255, 0, 0)
            assert segments[0].style.bgcolor.triplet == (0, 0, 255)
            assert segments[1].style.color.triplet == (0, 255, 0)
            assert segments[1].style.bgcolor.triplet == (255, 255, 0)

    asyncio.run(scenario())


def test_a_pixel_protocol_goes_out_as_a_zero_width_control_segment(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            art = application.query_one(Artwork)
            art.show(a_cover(Protocol.KITTY, escape="\033_Ga=T;AAAA\033\\"))
            await pilot.pause()

            strip = art.render_line(0)
            control = [segment for segment in strip if segment.is_control]
            assert control and control[0].text.startswith("\033_G")
            # The escape must not eat cells, or the compositor would shift the
            # rest of the row to the left.
            assert strip.cell_length == art.size.width
            # One anchor draws the whole image; the other rows stay empty.
            assert not any(segment.is_control for segment in art.render_line(1))

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


def test_pushing_a_screen_before_the_ui_exists_is_harmless(monkeypatch):
    """Textual pushes the default screen while compose has not run yet."""
    isolate_runtime(monkeypatch)
    application = TidalAmp(object(), FakeMpv())
    application._hide_art()
    application._restore_art()
    assert application._artwork() is None


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


# ---------------------------------------------------------------- loading state


def test_the_spinner_is_silent_until_there_is_something_to_wait_for():
    spinner = Spinner()
    assert spinner.busy is False
    assert spinner.render().plain == ""

    # Idle must not animate: a frame change would repaint the screen forever.
    spinner._advance()
    assert spinner._frame == 0

    spinner.start("cargando playlists…")
    spinner._advance()
    assert spinner.busy is True
    assert spinner._frame == 1
    assert spinner.render().plain == f"{Spinner.FRAMES[1]} cargando playlists…"

    spinner.stop()
    assert spinner.render().plain == ""


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


def test_the_retro_theme_squares_each_button_and_spells_the_toggles(monkeypatch):
    """The original's buttons are separate square keys, not one frame, and
    its two toggles carry the words SHUFFLE and REPEAT."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "retro")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            widget = application.query_one("#transport-play")
            top, face, bottom = (widget.render_line(y).text for y in range(3))

            # Six buttons, six frames, square corners — not one shared frame.
            assert top.count("┌") == 6 and top.count("┐") == 6
            assert bottom.count("└") == 6 and bottom.count("┘") == 6
            assert face.count("│") == 12
            assert "┐┌" in top, "los botones van pegados, no fundidos"
            # No half blocks: they fill their cell, so a row of them came out
            # as a solid slab instead of an edge.
            assert not any(glyph in top + face + bottom for glyph in "▛▜▙▟▌▐")
            assert "SHUFFLE" in face and "REPEAT" in face
            # The mark, not the colour, is what says the state.
            assert "SHUFFLE ○" in face and "REPEAT ○" in face

            await pilot.press("s")
            await pilot.pause()
            assert "SHUFFLE ●" in transport(application)

    asyncio.run(scenario())


def test_the_ascii_theme_types_its_chrome_and_keeps_the_brackets(monkeypatch):
    """Bracket keys, ASCII rules, and no glyph the chrome cannot type.

    The brackets are also the regression: `Static.update` reads a `str` as
    Rich markup, so «[ TIDAL AMP ]» came out as two rules with a hole where
    the title had been.
    """
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "ascii")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            title = application.query_one("#titlebar", Static).render_line(0).text
            heading = application.query_one("#pl-title", Static).render_line(0).text
            face = application.query_one("#transport-play").render_line(1).text

            assert "[ TIDAL AMP ]" in title
            assert "[ COLA ]" in heading
            assert "[ z << ]" in face and "[ x >  ]" in face
            assert "[ s SHUFFLE - ]" in face and "[ r REPEAT - ]" in face
            # Nothing outside ASCII in any of the three, which is the point.
            for drawn in (title, heading.split("  ")[0], face):
                assert drawn.isascii(), drawn

            await pilot.press("s")
            await pilot.press("r")
            await pilot.pause()
            face = application.query_one("#transport-play").render_line(1).text
            assert "[ s SHUFFLE * ]" in face and "[ r REPEAT * ]" in face

    asyncio.run(scenario())


def test_no_look_lets_the_cover_spill_onto_the_seek_bar(monkeypatch):
    """A graphical protocol paints over what is below it, it does not clip.

    `height` is border-box, so a layout that pads the display band takes
    those rows out of the content. Nova pads the top by one, and that one row
    put the bottom of the cover on the seek bar.
    """
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        for name in app_module.LAYOUTS:
            app_module.config.THEME = name
            application = TidalAmp(object(), FakeMpv())
            async with application.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                art = application.query_one(Artwork)
                display = application.query_one("#display")
                seek = application.query_one("#seek")
                padding = display.styles.padding

                room = display.region.height - padding.top - padding.bottom
                assert art.rows <= room, f"{name}: la carátula no cabe en su banda"
                assert display.region.bottom <= seek.region.y, name
                # And the band is not padded out further than it needs.
                assert room == max(app_module.DISPLAY_HEIGHT, art.rows), name

    asyncio.run(scenario())


def test_every_look_fits_the_smallest_supported_terminal(monkeypatch):
    """A layout that does not fit wraps into the row above and ruins both."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        for name in app_module.LAYOUTS:
            app_module.config.THEME = name
            application = TidalAmp(object(), FakeMpv())
            async with application.run_test(size=(60, 18)) as pilot:
                await pilot.pause()
                transport_row = application.query_one("#transport")
                play = application.query_one("#transport-play")
                menu = application.query_one("#transport-menu")

                assert play.size.height == 3, name
                assert play.region.right <= menu.region.x, name
                assert menu.region.right <= transport_row.region.right, name
                for y in range(3):
                    drawn = play.render_line(y).text
                    assert cell_len(drawn) <= play.size.width, f"{name} fila {y}"

    asyncio.run(scenario())


def test_switching_look_remeasures_the_transport_instead_of_cropping_it(monkeypatch):
    """The three looks are different widths, and the buttons were being cut
    to whichever one was on screen when the widget was last measured."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            widget = application.query_one("#transport-play")

            for name in ("retro", "nova", "quattro"):
                app_module.config.THEME = name
                application._apply_appearance()
                await pilot.pause()
                drawn = widget.render_line(1).text

                assert cell_len(drawn) <= widget.size.width, name
                # The last button is drawn whole, not cut off after its key.
                last = (
                    "r ↻–"
                    if name == "quattro"
                    else f"r {'repeat' if name == 'nova' else 'REPEAT'} ○"
                )
                assert last in drawn, name

    asyncio.run(scenario())


def test_the_retro_theme_rules_its_two_title_bars(monkeypatch):
    """The original tells its windows apart by the texture behind the name."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "retro")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            for selector, name in (("#titlebar", "A M P"), ("#pl-title", "LISTA")):
                widget = application.query_one(selector, Static)
                drawn = widget.render_line(0).text

                assert cell_len(drawn) == widget.size.width, "la regla llena la fila"
                assert name in drawn
                assert drawn.startswith("═") and drawn.endswith("═")
                # Centred: the two halves of the rule are within a cell.
                left, right = drawn.split(" ", 1)[0], drawn.rsplit(" ", 1)[-1]
                assert abs(len(left) - len(right)) <= 1

    asyncio.run(scenario())


def test_the_nova_theme_carries_state_without_drawing_a_single_box(monkeypatch):
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "nova")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            widget = application.query_one("#transport-play")
            top, face, under = (widget.render_line(y).text for y in range(3))

            assert not any(glyph in face for glyph in "╭│▛▌"), "nova no dibuja cajas"
            assert not top.strip(), "la fila de arriba queda vacía"
            assert not under.strip(), "sin nada encendido, no hay subrayado"
            assert "s shuffle ○" in face

            await pilot.press("s")
            await pilot.pause()
            face = widget.render_line(1).text
            under = widget.render_line(2).text
            assert "s shuffle ●" in face
            # The rule sits exactly under the label it belongs to.
            start = face.index("s shuffle ●")
            assert under[start : start + len("s shuffle ●")] == "─" * 11
            assert under.strip() == "─" * 11, "sólo el que está encendido"

    asyncio.run(scenario())


def test_the_quattro_theme_separates_the_groups_without_a_frame(monkeypatch):
    """The default layout keeps the two groups legible with one divider."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            play_widget = application.query_one("#transport-play")
            play = transport(application)

            assert "╭" not in play_widget.render_line(0).text
            assert play.count("│") == 1, "un separador entre los dos grupos"
            for key, glyph in (("z", "◀◀"), ("x", "▶"), ("c", "■"), ("v", "▶▶")):
                assert f"{key} {glyph}" in play
            # The rows above and below the labels stay empty, not framed.
            assert not play_widget.render_line(0).text.strip()
            assert not play_widget.render_line(2).text.strip()

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


def test_the_transport_runs_z_x_c_v_across_the_keyboard(monkeypatch):
    """Four adjacent keys in the order the buttons sit on screen. Winamp's
    fifth (`b`) went with the separate pause button."""
    isolate_runtime(monkeypatch)
    keys = app_module.DEFAULT_KEYS

    faces = [keys[action].split(",")[0] for action in ("prev", "play", "stop", "next")]
    assert faces == list("zxcv")
    assert "b" not in {
        key for binding in TidalAmp.BINDINGS for key in binding.key.split(",")
    }

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 26)) as pilot:
            await pilot.pause()
            drawn = transport(application)
            for key, glyph in (("z", "◀◀"), ("x", "▶"), ("c", "■"), ("v", "▶▶")):
                assert f"{key} {glyph}" in drawn

    asyncio.run(scenario())


def test_the_buttons_show_the_rebound_key_not_the_shipped_one(monkeypatch):
    """A button with the wrong letter on it is worse than one with none."""
    isolate_runtime(monkeypatch)
    monkeypatch.setitem(app_module.config.KEYS, "stop", "k")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 26)) as pilot:
            await pilot.pause()
            drawn = transport(application)
            assert "k ■" in drawn
            assert "c ■" not in drawn

    asyncio.run(scenario())


def test_play_and_pause_are_one_button_showing_what_it_will_do(monkeypatch):
    """There used to be «x ▶» and «c ‖» side by side, and only one of them
    ever made sense at a given moment."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 30)) as pilot:
            await pilot.pause()
            # Stopped: the button offers to play, and there is no second one.
            drawn = transport(application)
            assert "x ▶" in drawn
            assert drawn.count("‖") == 0

            application.queue.replace(
                [Entry(id=1, title="t", artist="a", duration=9)], start=0
            )
            mpv.idle = False
            await pilot.pause(0.3)
            drawn = transport(application)
            assert "x ‖" in drawn
            assert drawn.count("▶") == 2, "los dos del ▶▶ de «siguiente», y ninguno más"

            mpv.paused = True
            await pilot.pause(0.3)
            assert "x ▶" in transport(application)

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


def test_a_track_ending_on_its_own_still_advances(monkeypatch):
    """The guard must not cost the auto-advance it sits next to."""
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
                start=0,
            )
            application._sync_queue()
            mpv.idle = False
            await pilot.pause(0.3)
            started.clear()

            # mpv falls idle by itself: the song finished.
            mpv.idle = True
            await settle(pilot, lambda: bool(started))
            assert started == [1]

    asyncio.run(scenario())


def test_there_is_no_second_key_that_pauses(monkeypatch):
    """«c» used to pause as well as «x», which after merging the two buttons
    was just a second shortcut for the same thing. It is the stop key now."""
    isolate_runtime(monkeypatch)

    assert "pause" not in app_module.DEFAULT_KEYS
    assert app_module.DEFAULT_KEYS["stop"] == "c"

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 24)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=1, title="t", artist="a", duration=9)], start=0
            )
            mpv.idle = False

            await pilot.press("c")
            await pilot.pause()
            assert mpv.paused is False, "«c» para, no pausa"
            assert mpv.idle is True

    asyncio.run(scenario())


def test_mpris_play_pause_still_toggles(monkeypatch):
    """The key went; the D-Bus verb did not, and it has to keep working."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 24)) as pilot:
            await pilot.pause()
            mpv.idle = False

            application.mpris_play_pause()
            assert mpv.paused is True
            application.mpris_play_pause()
            assert mpv.paused is False

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


def test_the_menu_announces_the_settings_window(monkeypatch):
    """It was reachable only from the help screen, which you have to know to
    open in the first place."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 26)) as pilot:
            await pilot.pause()
            assert "o config" in transport(application, "menu")

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


# -------------------------------------------------------- el filtro del nivel


def library_rows() -> list[Row]:
    """A level with two tracks, a container and a page that is not loaded."""
    schism = Entry(id=1, title="Schism", artist="TOOL", album="Lateralus")
    sober = Entry(id=2, title="Sober", artist="TOOL", album="Undertow")
    return [
        Row(label=schism.label, detail="6:47", entry=schism),
        Row(label=sober.label, detail="5:06", entry=sober),
        Row(label="Sinfonía nº 9", detail="4 pistas", key="playlist:9"),
        Row(label="más…", detail="siguientes 100", more=lambda: [Row(label="Ænema")]),
    ]


def open_browser(application, rows=None):
    level = rows if rows is not None else library_rows()
    application.push_screen(BrowserScreen("MI BIBLIOTECA", lambda: level))


async def type_into_filter(pilot, text: str) -> None:
    for character in text:
        await pilot.press(character)
    await pilot.pause()


def visible_labels(screen) -> list[str]:
    return [row.label for row in screen.query_one(RowList).rows]


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


def test_the_footer_drops_whole_hints_instead_of_cropping_one(monkeypatch):
    """It was one literal, and at the browser's own width the terminal ate
    «R recargar   esc cerrar», leaving a stray «R» against the border."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_browser(application)
            await pilot.pause()
            hint = application.screen.query_one("#browser-hint")
            line = hint.render_line(0).text

            assert cell_len(line) <= hint.size.width
            assert line.rstrip().endswith("esc cerrar")
            assert "/ filtrar" in line
            # Whatever survived, survived whole.
            for key, label, _drop in BROWSER_HINTS:
                assert (f"{key} {label}" in line) or (label not in line)

    asyncio.run(scenario())


# ---------------------------------------------------------------- track menu


def track_rows() -> list[Row]:
    return [
        Row(label=name, detail="1:40", entry=Entry(id=i, title=name, artist="TOOL"))
        for i, name in enumerate(("A", "B", "C"))
    ]


def open_menu_on_b(application, rows):
    """Push the browser wired to the app, exactly as `/` and `l` do."""
    application.push_screen(
        BrowserScreen("BUSCAR: x", lambda: rows), application._browser_result
    )


def test_enter_on_a_track_offers_the_four_things_worth_doing(monkeypatch):
    """It used to queue the whole level and start playing, with no way to say
    «just this one next» or «play the radio»."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(application.screen, TrackActionsScreen)
            drawn = application.screen.query_one("#actions-list").render_line
            lines = [drawn(y).text for y in range(len(TRACK_ACTIONS))]
            for (_action, icon, letter, label), line in zip(
                TRACK_ACTIONS, lines, strict=True
            ):
                assert icon in line
                assert label in line
                assert f"[{letter}]" in line

            # And it names the track it is about.
            title = application.screen.query_one("#actions-title")
            assert "A" in title.render_line(0).text

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


def test_play_next_adds_only_that_track_after_the_current_one(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [
                    Entry(id=8, title="sonando", artist="x"),
                    Entry(id=9, title="luego", artist="x"),
                ],
                start=0,
            )
            open_menu_on_b(application, track_rows())
            await pilot.pause()
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert [e.title for e in application.queue] == ["sonando", "B", "luego"]
            assert application.queue.playing == 0
            assert "B" in application.status

    asyncio.run(scenario())


def a_queue(application, *titles: str) -> None:
    """Fill the queue with one entry per title and put it on screen."""
    application.queue.replace(
        [Entry(id=i, title=t, artist="TOOL", duration=60) for i, t in enumerate(titles)],
        start=-1,
    )
    application._sync_queue()


def queue_lines(application) -> list[str]:
    """What the playlist widget is actually drawing, line by line."""
    playlist = application.query_one("#playlist", RowList)
    return [playlist.render_line(y).text.rstrip() for y in range(playlist.size.height)]


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


def test_the_setting_changes_the_shape_without_moving_the_analyser(monkeypatch):
    """Every shape is drawn in the same place — beside the cover, under the
    track details — and all of them use the whole column."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            analyzer = application.query_one("#analyzer", Analyzer)
            assert analyzer.mode == "bars"
            where = analyzer.region

            monkeypatch.setattr(app_module.config, "VISUALIZER", "curve")
            application._setting_changed("visualizer")
            await pilot.pause()

            assert analyzer.mode == "curve"
            assert analyzer.region == where, "no se mueve de sitio"

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
            badges = application.query_one("#badges", Static)
            art = application.query_one(Artwork)

            assert analyzer.region.x == badges.region.x
            assert analyzer.region.x > art.region.right
            # As far right as anything else inside the panel: the frame and
            # the one cell of air the whole display band keeps.
            assert analyzer.region.right == application.size.width - 3

    asyncio.run(scenario())


def test_a_shape_that_is_not_one_of_the_three_falls_back_to_bars(monkeypatch):
    """The setting comes from a file the user edits by hand."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(app_module.config, "VISUALIZER", "espiral")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            assert application.query_one("#analyzer", Analyzer).mode == "bars"

    asyncio.run(scenario())


def test_the_config_screen_offers_every_shape_and_writes_the_one_chosen(
    monkeypatch, tmp_path
):
    isolate_runtime(monkeypatch)
    path = tmp_path / "config.toml"
    monkeypatch.setattr(app_module.config, "CONFIG_FILE", path)
    changed: list[str] = []

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()

            def applied(name: str) -> None:
                changed.append(name)
                application._setting_changed(name)

            screen = ConfigScreen(applied)
            application.push_screen(screen)
            await pilot.pause()
            row = next(o for o in screen._rows if o.key == "visualizer")
            assert row.choices == Analyzer.MODES

            # One step along the row, the way ↵ moves it.
            screen._cycle(row, 1)
            await pilot.pause()

            assert app_module.config.VISUALIZER == "mirror"
            assert 'visualizer = "mirror"' in path.read_text(encoding="utf-8")
            assert changed == ["visualizer"]
            assert application.query_one("#analyzer", Analyzer).mode == "mirror"

    asyncio.run(scenario())


def test_the_marquee_carries_the_number_and_the_title_and_nothing_else(monkeypatch):
    """The artist, the album and the length moved under the clock. One line is
    all the marquee has, and it spends it on the title."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace([a_deftones_track()], start=-1)
            application._sync_queue()
            application._play_index(0)
            await pilot.pause()

            text = application.query_one(Marquee).text
            assert text == "1. Entombed"
            assert "Deftones" not in text and "4:59" not in text

    asyncio.run(scenario())


def a_deftones_track() -> Entry:
    return Entry(
        id=1,
        title="Entombed",
        artist="Deftones",
        album="Around the Fur",
        year=1997,
        duration=299,
    )


def test_the_block_under_the_clock_names_the_artist_album_and_year(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            meta = application.query_one("#trackmeta", Static)
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


def test_a_track_with_no_year_does_not_leave_a_stray_separator(monkeypatch):
    """A restored queue from before the year column carries `year = 0`."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [
                    Entry(
                        id=1,
                        title="Entombed",
                        artist="Deftones",
                        album="Around the Fur",
                        duration=299,
                    )
                ],
                start=-1,
            )
            application._sync_queue()
            application._play_index(0)
            await pilot.pause()

            lines = [
                line.rstrip()
                for line in application.query_one("#trackmeta", Static)
                .render()
                .plain.split("\n")
            ]
            assert lines[:3] == ["Deftones", "Around the Fur", "4:59"]

    asyncio.run(scenario())


def test_the_compact_layout_drops_the_block_and_keeps_the_clock(monkeypatch):
    """Five rows of display band is the clock and nothing else."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(70, 20)) as pilot:
            await pilot.pause()
            assert not application.query_one("#trackmeta", Static).display
            assert application.query_one("#clock").display

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


def test_nobody_pays_for_the_year_column_they_turned_off(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(app_module.config, "COLUMNS", ("artist", "duration"))
    asked: list[int] = []
    monkeypatch.setattr(library, "album_year", lambda s, a: asked.append(a) or 0)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=1, title="a", artist="x", album="y", album_id=7)], start=-1
            )
            application._sync_queue()
            await pilot.pause()

            assert asked == []

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


@pytest.mark.parametrize("theme", ["quattro", "retro", "nova", "ascii"])
def test_every_layout_fills_its_queue_heading_to_the_right_edge(theme, monkeypatch):
    """Each look measured that row with a number written by hand, and each
    stopped short of the edge by a different amount. Quattro did not measure
    at all and left two thirds of the row empty."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, theme)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            title = application.query_one("#pl-title", Static)
            drawn = title.render_line(0).text.rstrip()

            assert cell_len(drawn) == title.size.width, theme

    asyncio.run(scenario())


def test_the_frameless_layout_does_not_start_on_row_zero(monkeypatch):
    """The other three get that separation from their border. Nova has none,
    so it buys the row: without it the wordmark sat against the terminal."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "nova")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            assert application.query_one("#titlebar", Static).region.y == 1

            # And gives it back where there is nothing to spare.
            await pilot.resize_terminal(82, 24)
            await pilot.pause()
            assert application.query_one("#titlebar", Static).region.y == 0

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


def test_space_plays_and_pauses_like_x(monkeypatch):
    """What every other player uses, and nothing in the main window wanted."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace([a_deftones_track()], start=0)
            mpv.idle = False

            await pilot.press("space")
            await pilot.pause()
            assert mpv.paused is True

            await pilot.press("space")
            await pilot.pause()
            assert mpv.paused is False

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


def test_favourite_from_the_menu_touches_tidal_and_not_the_queue(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr("tidalamp.screens.ensure_fresh", lambda session: False)
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


# ------------------------------------------------------------------------ volume


def test_clicking_the_middle_of_seek_jumps_to_the_middle(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        mpv.duration = 200.0
        mpv.idle = False
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            seek = application.query_one("#seek", SeekBar)
            seek.total = mpv.duration
            middle = seek.content_offset.x + (seek.size.width - 1) // 2

            assert await pilot.click("#seek", offset=(middle, 0))
            await pilot.pause()

            assert len(mpv.seek_calls) == 1
            seconds, mode = mpv.seek_calls[0]
            assert mode == "absolute"
            assert seconds == pytest.approx(100.0, abs=200 / (seek.size.width - 1))

    asyncio.run(scenario())


def test_clicking_seek_without_a_loaded_track_does_nothing(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            seek = application.query_one("#seek", SeekBar)
            middle = seek.content_offset.x + (seek.size.width - 1) // 2

            assert await pilot.click("#seek", offset=(middle, 0))
            await pilot.pause()

            assert mpv.seek_calls == []

    asyncio.run(scenario())


def test_clicking_volume_sets_the_players_volume(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        mpv.volume = 0
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            slider = application.query_one("#volume", Slider)
            start, track = slider._track()
            right = slider.content_offset.x + start + track - 1

            assert await pilot.click("#volume", offset=(right, 0))
            await pilot.pause()

            assert mpv.volume == Mpv.VOLUME_MAX
            assert slider.value == Mpv.VOLUME_MAX

    asyncio.run(scenario())


def test_clicking_the_balance_centre_sets_exactly_zero(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(Settings, "save", lambda self: None)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            application.settings.set_balance(0.7)
            slider = application.query_one("#balance", Slider)
            slider.value = 70
            start, track = slider._track()
            centre = slider.content_offset.x + start + track // 2

            assert await pilot.click("#balance", offset=(centre, 0))
            await pilot.pause()

            assert application.settings.balance == 0.0
            assert slider.value == 0
            assert mpv.filter_calls[-1] == ("eq", None)
            assert application.status == "balance: centro"

    asyncio.run(scenario())


def test_the_volume_slider_scales_to_the_players_ceiling(monkeypatch):
    """A full bar has to mean the loudest the player will actually go."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            slider = application.query_one("#volume", Slider)
            assert slider.maximum == Mpv.VOLUME_MAX

            slider.value = Mpv.VOLUME_MAX
            await pilot.pause()
            assert "░" not in slider.render_line(0).text

    asyncio.run(scenario())


def test_turning_the_volume_up_stops_at_the_ceiling(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            for _ in range(30):
                await pilot.press("plus")
            await pilot.pause()
            assert mpv.volume == Mpv.VOLUME_MAX

            for _ in range(40):
                await pilot.press("minus")
            await pilot.pause()
            assert mpv.volume == 0

    asyncio.run(scenario())


def test_mpris_cannot_push_the_volume_past_the_ceiling(monkeypatch):
    """The bus used to accept 1.3 and hand the player 130, which is the same
    boost the keyboard could no longer ask for."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            application.mpris_set_volume(1.3)
            assert mpv.volume == Mpv.VOLUME_MAX
            assert application.mpris_volume() == 1.0

            application.mpris_set_volume(-2.0)
            assert mpv.volume == 0

            application.mpris_set_volume(0.45)
            assert mpv.volume == 45

    asyncio.run(scenario())


# ----------------------------------------------------------------- settings


def isolate_config(monkeypatch, tmp_path):
    """Point the config file at a temp one and drop every override."""
    path = tmp_path / "config.toml"
    monkeypatch.setattr(app_module.config, "CONFIG_FILE", path)
    for variable in app_module.config.ENV_VARS.values():
        monkeypatch.delenv(variable, raising=False)
    app_module.config.reload()
    return path


def config_row(screen, label: str) -> int:
    """Find a settings row by its label.

    By index, every test that touched the settings screen broke the day a row
    was inserted above the one it meant. The label is what the user is
    looking at anyway.
    """
    for index, option in enumerate(screen._rows):
        if option.label == label:
            return index
    raise AssertionError(f"no hay una fila «{label}»")


def config_text(application) -> str:
    body = application.screen.query_one("#config-list")
    return "\n".join(body.render_line(y).text for y in range(body.size.height))


def test_o_opens_the_settings_and_esc_closes_them(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
            assert isinstance(application.screen, ConfigScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert len(application.screen_stack) == 1

    asyncio.run(scenario())


def test_changing_a_setting_writes_the_file_and_takes_effect(monkeypatch, tmp_path):
    """The whole point: a change made once stays made. It used to need an
    editor, or a variable exported before launching."""
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen(application._setting_changed))
            await pilot.pause()

            assert app_module.config.DEFAULT_QUALITY == "HI_RES_LOSSLESS"
            await pilot.press("enter")  # cursor starts on Quality
            await pilot.pause()

            assert app_module.config.DEFAULT_QUALITY == "LOW"
            assert app_module.config.read_file(path)["quality"] == "LOW"
            assert "LOW" in application.status

    asyncio.run(scenario())


def test_the_settings_cycle_both_ways(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await pilot.pause()

            await pilot.press("left")
            await pilot.pause()
            assert app_module.config.DEFAULT_QUALITY == "LOSSLESS"

            await pilot.press("right")
            await pilot.pause()
            assert app_module.config.DEFAULT_QUALITY == "HI_RES_LOSSLESS"

    asyncio.run(scenario())


def test_the_settings_are_grouped_by_what_they_are_about(monkeypatch, tmp_path):
    """Ten switches in one column read as ten unrelated switches: the quality
    of the stream sat next to the colour of the borders."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen(application._setting_changed))
            await pilot.pause()
            drawn = application.screen.query_one("#config-list").render_line
            lines = [drawn(y).text for y in range(30)]
            at = {
                name: next(i for i, line in enumerate(lines) if line.strip() == name)
                for name in ("Audio", "Apariencia", "General")
            }
            assert at["Audio"] < at["Apariencia"] < at["General"]

            def row(label: str) -> int:
                return next(i for i, line in enumerate(lines) if label in line)

            assert at["Audio"] < row("Calidad") < at["Apariencia"]
            assert at["Apariencia"] < row("Transparencia") < at["General"]
            assert at["General"] < row("Idioma")

    asyncio.run(scenario())


def test_the_settings_list_scrolls_instead_of_hiding_the_cursor(monkeypatch, tmp_path):
    """The window grows to its text and stops at the terminal. On a small one
    the rows past the fold used to be selectable and invisible at once."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()
            last = len(screen._rows) - 1
            for _ in range(last):
                await pilot.press("down")
            await pilot.pause()

            widget = application.screen.query_one("#config-list")
            lines = [widget.render_line(y).text for y in range(widget.size.height)]
            assert any(screen._rows[last].label in line for line in lines)
            # And its heading came with it, so the row is not orphaned.
            assert any(line.strip() == screen._rows[last].group for line in lines)

    asyncio.run(scenario())


def test_a_modal_is_solid_until_transparency_is_turned_on(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()
            assert not screen.has_class("transparent")

            screen.cursor = config_row(screen, "Transparencia")
            await pilot.press("enter")
            await pilot.pause()

            assert app_module.config.TRANSPARENCY is True
            # On the window that is already open, not only on the next one:
            # the answer belongs under the cursor that asked for it.
            assert screen.has_class("transparent")

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


def test_theme_and_palette_change_live_and_persist(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            assert application.query_one("#main").has_class("quattro")
            assert "╭" not in transport(application)

            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()

            screen.cursor = config_row(screen, "Tema")
            await pilot.press("enter")
            await pilot.pause()
            assert app_module.config.THEME == "retro"
            assert not application.query_one("#main").has_class("quattro")
            framed = application.query_one("#transport-play").render_line(0).text
            assert "┌" in framed, "el transporte pasa a los botones cuadrados"

            screen.cursor = config_row(screen, "Paleta")
            await pilot.press("enter")
            await pilot.pause()
            assert app_module.config.PALETTE == "classic"
            assert application.tidalamp_palette.source == "classic"
            assert app_module.config.read_file(path)["theme"] == "retro"
            assert app_module.config.read_file(path)["palette"] == "classic"

    asyncio.run(scenario())


def test_choosing_columns_redraws_the_queue_that_is_already_there(monkeypatch, tmp_path):
    """It has to land on the queue on screen, not on the next one loaded."""
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 34)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [
                    Entry(
                        id=1,
                        title="Virgen",
                        artist="Adolescent's",
                        album="Ahora",
                        year=1993,
                        popularity=64,
                        duration=272,
                    )
                ],
                start=0,
            )
            application._sync_queue()
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            assert "64" not in playlist.render_line(0).text

            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = config_row(screen, "Columnas de la cola")
            await pilot.press("enter")
            await settle(pilot, lambda: isinstance(application.screen, ColumnsScreen))

            picker = application.screen
            picker.cursor = [c.name for c in columns_module.ALL].index("popularity")
            await pilot.press("enter")
            await pilot.pause()

            # Same queue, no reload: the row on screen has the column now.
            assert "popularity" in app_module.config.COLUMNS
            assert "64" in playlist.render_line(0).text
            assert "popularity" in app_module.config.read_file(path)["columns"]

    asyncio.run(scenario())


def test_a_setting_the_environment_overrides_is_labelled(monkeypatch, tmp_path):
    """Showing a value the app is not using would be a lie."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setenv("TIDALAMP_QUALITY", "HIGH")
    app_module.config.reload()

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await pilot.pause()
            assert "TIDALAMP_QUALITY" in config_text(application)

    asyncio.run(scenario())


def test_the_screen_reports_what_the_audio_stack_is_doing(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        audio_module,
        "sink",
        lambda: audio_module.Sink(name="s", description="Mi DAC", rate=48000),
    )
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: (48000,))
    monkeypatch.setattr(audio_module, "hardware_rates", lambda name: (96000,))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await settle(pilot, lambda: "Mi DAC" in config_text(application))
            drawn = config_text(application)
            assert "Mi DAC" in drawn and "48000" in drawn
            # A graph stuck on one rate is the thing worth saying out loud,
            # and without moving the cursor onto the row that fixes it: the
            # badge tells the truth about the stream while the DAC gets less.
            assert "remuestrea" in drawn
            assert "El grafo remuestrea" in drawn.split("Salida:")[1]

    asyncio.run(scenario())


def test_a_graph_that_can_change_rate_says_nothing_alarming(monkeypatch, tmp_path):
    """The warning has to mean something, so it cannot always be there."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        audio_module,
        "sink",
        lambda: audio_module.Sink(name="s", description="Mi DAC", rate=96000),
    )
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: (44100, 48000, 96000))
    monkeypatch.setattr(audio_module, "hardware_rates", lambda name: (96000,))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await settle(pilot, lambda: "Mi DAC" in config_text(application))

            assert "remuestrea" not in config_text(application)

    asyncio.run(scenario())


def test_a_bluetooth_output_says_so_where_it_cannot_be_missed(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        audio_module,
        "sink",
        lambda: audio_module.Sink(
            name="bluez_output.AA", description="Auriculares", rate=48000
        ),
    )
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: (44100, 48000))
    monkeypatch.setattr(audio_module, "hardware_rates", lambda name: ())

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await settle(pilot, lambda: "Auriculares" in config_text(application))

            assert "Bluetooth" in config_text(application)

    asyncio.run(scenario())


def test_the_way_out_of_the_settings_survives_a_short_terminal(monkeypatch, tmp_path):
    """The footer grew a line; the hint is docked so it is never the one cut."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        audio_module,
        "sink",
        lambda: audio_module.Sink(name="s", description="Mi DAC", rate=48000),
    )
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: (48000,))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await settle(pilot, lambda: "Mi DAC" in config_text(application))
            box = application.screen.query_one("#config-box")
            hint = application.screen.query_one("#config-hint")

            assert box.region.bottom <= 18
            assert hint.region.bottom <= box.region.bottom
            assert "cerrar" in hint.render_line(0).text

    asyncio.run(scenario())


def test_the_rates_row_writes_and_removes_the_drop_in(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    dropin = tmp_path / "pipewire.conf.d" / "rates.conf"
    monkeypatch.setattr(audio_module, "CONF_DIR", dropin.parent)
    monkeypatch.setattr(audio_module, "RATES_FILE", dropin)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen()
            application.push_screen(screen)
            await pilot.pause()

            screen.cursor = config_row(screen, "Ritmos hi-res en PipeWire")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert dropin.is_file()

            await pilot.press("enter")
            await pilot.pause()
            assert not dropin.exists()

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


def test_the_status_bar_is_actually_on_screen(monkeypatch):
    """It was not: an auto-height playlist pushed it past the bottom edge.

    Everything the app has to say — errors, «resolviendo…», a restored queue —
    is written there, so off-screen meant silent.
    """
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            bar = application.query_one("#statusbar")
            assert bar.region.bottom <= application.size.height
            assert bar.region.height == 1

    asyncio.run(scenario())


def test_a_missing_pillow_is_announced_instead_of_leaving_an_empty_corner(monkeypatch):
    """Without Pillow the cover widget simply never becomes visible.

    That used to be a `log.info` to a file nobody reads, so a fresh clone
    looked broken. The status line now names the extra that fixes it.
    """
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(artwork, "have_decoder", lambda: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert "Pillow" in application.status

    asyncio.run(scenario())


def test_a_status_with_square_brackets_reaches_the_screen_intact(monkeypatch):
    """`Static.update` reads a str as markup, and ate the `[art]` in the advice."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(artwork, "have_decoder", lambda: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.3)
            drawn = application.query_one("#status").render_line(0).text
            assert "tidalamp[art]" in drawn

    asyncio.run(scenario())


def test_a_present_pillow_says_nothing(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(artwork, "have_decoder", lambda: True)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert "Pillow" not in application.status

    asyncio.run(scenario())


def test_resolving_a_track_says_so_and_stops_saying_it(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    class Playable:
        url = "https://cdn/a"
        kbps = "16-bit"
        khz = "44.1"
        quality = "LOSSLESS"
        codec = "flac"

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entry = Entry(id=1, title="Schism", artist="TOOL")
            application.queue.append([entry])
            application._sync_queue()

            application._play_index(0)
            busy = application.query_one("#busy", Spinner)
            assert busy.busy
            assert busy.label == "resolviendo «Schism»…"

            application._start(entry, Playable())
            assert not busy.busy

            # A failure has to clear it too, or the app looks stuck forever.
            application._play_index(0)
            application._resolve_failed("error: sin red")
            assert not busy.busy
            assert application.status == "error: sin red"

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


def test_a_quality_downgrade_reaches_the_status_line(monkeypatch):
    isolate_runtime(monkeypatch)

    class Downgraded:
        url = "https://cdn/a"
        kbps = "320 kbps"
        khz = "44.1"
        quality = "HIGH"
        codec = "aac"
        requested = "LOSSLESS"
        downgraded = True

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entry = Entry(id=1, title="Schism", artist="TOOL")
            application._start(entry, Downgraded())

            assert "TIDAL entregó HIGH, no LOSSLESS" in application.status
            badges = application.query_one("#badges", Static)
            assert "320" in str(badges.content) and "HIGH" in str(badges.content)

    asyncio.run(scenario())


def test_source_output_and_pause_are_separate_truthful_readouts(monkeypatch):
    isolate_runtime(monkeypatch)

    class HiRes:
        url = "https://cdn/a"
        kbps = "24-bit"
        khz = "176.4"
        quality = "HI_RES_LOSSLESS"
        codec = "flac"
        requested = "HI_RES_LOSSLESS"
        downgraded = False

    async def scenario() -> None:
        mpv = FakeMpv()
        mpv.idle = False
        mpv.paused = True
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(120, 36)) as pilot:
            entry = Entry(id=1, title="Thriller", artist="Michael Jackson")
            application.queue.replace([entry], start=0)
            application._sync_queue()
            application._start(entry, HiRes())
            application._set_sink(
                audio_module.Sink(
                    name="alsa_output.usb",
                    description="FIIO BTR15",
                    rate=176400,
                    sample_format="s32le",
                )
            )
            await pilot.pause()

            source = str(application.query_one("#badges", Static).content)
            output = str(application.query_one("#output", Static).content)
            assert "SRC  FLAC" in source
            assert "24-bit" in source and "176.4 kHz" in source
            assert "HI-RES" in source and "PAUSA" in source
            assert output == "OUT  FIIO BTR15 · PCM S32LE · 176.4 kHz"
            assert application.query_one("#volume", Slider).label == "VOL/mpv"

    asyncio.run(scenario())


# ------------------------------------------------------------- terminal size


def test_a_small_terminal_gets_an_explanation_not_a_broken_layout(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(59, 17)) as pilot:
            await pilot.pause()
            notice = application.query_one("#too-small", Static)
            assert notice.display is True
            text = str(notice.content)
            assert "59×17" in text
            assert f"{TidalAmp.MIN_WIDTH}×{TidalAmp.MIN_HEIGHT}" in text

    asyncio.run(scenario())


def test_sixty_columns_use_the_compact_player_instead_of_a_warning(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(60, 18)) as pilot:
            await pilot.pause()

            assert application.query_one("#too-small", Static).display is False
            assert application.query_one("#main").has_class("compact")
            assert application.query_one(Artwork).region.width == 0
            assert application.query_one("#balance").display is False
            assert application.query_one("#playlist").size.height >= 3
            assert "↵ reproducir" in str(
                application.query_one("#pl-title", Static).content
            )
            assert "? ayuda" in str(application.query_one("#transport-menu").content)

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


def test_a_terminal_big_enough_shows_nothing_extra(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert application.query_one("#too-small", Static).display is False

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
    monkeypatch.setattr("tidalamp.screens.ensure_fresh", lambda session: False)

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


def test_favouriting_nothing_says_so_instead_of_failing(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("f")
            assert application.status == "no hay ninguna pista seleccionada"

    asyncio.run(scenario())


def test_a_favourite_that_fails_reaches_the_status_line(monkeypatch):
    isolate_runtime(monkeypatch)

    def boom(session, row, add=True):
        raise RuntimeError("sin red")

    monkeypatch.setattr("tidalamp.library.favourite", boom)
    monkeypatch.setattr("tidalamp.screens.ensure_fresh", lambda session: False)

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
    monkeypatch.setattr("tidalamp.screens.ensure_fresh", lambda session: False)

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
