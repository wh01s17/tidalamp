"""Focused Textual workflow regressions."""

from __future__ import annotations

import asyncio
import threading

from textual.screen import Screen
from textual.widgets import Static

from tidalamp.app import BrowserScreen, TidalAmp
from tidalamp.artwork import Cover, Protocol
from tidalamp import library
from tidalamp.library import Row
from tidalamp.queue import Entry, Queue
from tidalamp.settings import Settings
from tidalamp.theme import DEFAULT_COLORS, ThemePalette
from tidalamp.widgets import Artwork, Spinner


async def settle(pilot, done, tries: int = 100) -> None:
    """Pump the event loop until a worker's result has landed."""
    for _ in range(tries):
        await pilot.pause()
        if done():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("el worker no terminó")


class FakeMpv:
    alive = True
    position = 0.0
    duration = 0.0
    volume = 100
    paused = False
    idle = True

    def __init__(self) -> None:
        self.filter_calls: list[tuple[str, str | None]] = []
        self.loaded: str | None = None

    def load(self, url: str) -> None:
        self.loaded = url

    def set_filter(self, label: str, graph: str | None) -> None:
        self.filter_calls.append((label, graph))

    def rms(self) -> float:
        return -91.0

    def close(self) -> None:
        pass


def isolate_runtime(monkeypatch) -> None:
    async def no_mpris(self) -> None:
        return None

    monkeypatch.setattr(Queue, "load", lambda self: False)
    monkeypatch.setattr(Queue, "save", lambda self: None)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings()))
    monkeypatch.setattr(TidalAmp, "_start_spectrum", lambda self: None)
    monkeypatch.setattr(TidalAmp, "_start_mpris", no_mpris)


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


def test_shuffle_and_repeat_have_persistent_indicators(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            modes = application.query_one("#modes", Static)
            assert modes.content.plain == "   SHUF OFF     REP OFF "

            await pilot.press("s")
            assert modes.content.plain == "   SHUF ON     REP OFF "

            await pilot.press("r")
            assert modes.content.plain == "   SHUF ON     REP ALL "

            application.mpris_set_loop_status("Track")
            application.mpris_set_shuffle(False)
            assert modes.content.plain == "   SHUF OFF     REP 1 "

    asyncio.run(scenario())


def test_running_app_follows_an_omarchy_theme_change(monkeypatch):
    isolate_runtime(monkeypatch)
    initial = ThemePalette(dict(DEFAULT_COLORS), source="omarchy")
    changed_colors = dict(DEFAULT_COLORS)
    changed_colors["accent"] = "#7aa2f7"
    changed_colors["panel"] = "#1a1b26"
    changed = ThemePalette(changed_colors, source="omarchy")
    palettes = iter((initial, changed))
    monkeypatch.setattr("tidalamp.app.load_palette", lambda: next(palettes))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.press("s")
            application._refresh_theme()

            modes = application.query_one("#modes", Static)
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


def test_a_modal_takes_the_cover_down_and_the_tick_puts_it_back(monkeypatch):
    """kitty images float above the text, so a modal would open under them."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            art = application.query_one(Artwork)
            cover = a_cover()
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


def test_the_same_cover_is_not_fetched_twice(monkeypatch):
    isolate_runtime(monkeypatch)
    asked: list[str] = []
    monkeypatch.setattr(TidalAmp, "_art_worker", lambda self, url: asked.append(url))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
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
    monkeypatch.setattr("tidalamp.artwork.detect_protocol", lambda env=None: Protocol.NONE)
    asked: list[str] = []
    monkeypatch.setattr(TidalAmp, "_art_worker", lambda self, url: asked.append(url))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            application._load_art(Entry(id=1, title="t", artist="a", art_url="https://c/1.jpg"))
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
        return [Row(label="Mi playlist", loader=lambda: [])]

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


def test_resolving_a_track_says_so_and_stops_saying_it(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    class Playable:
        url = "https://cdn/a"
        kbps = "1411"
        khz = "44.1"
        quality = "LOSSLESS"

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
        return [Row(label="Mi playlist", loader=lambda: [])]

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
        kbps = "320"
        khz = "44"
        quality = "HIGH"
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


# ------------------------------------------------------------- terminal size


def test_a_small_terminal_gets_an_explanation_not_a_broken_layout(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            notice = application.query_one("#too-small", Static)
            assert notice.display is True
            text = str(notice.content)
            assert "60×18" in text
            assert f"{TidalAmp.MIN_WIDTH}×{TidalAmp.MIN_HEIGHT}" in text

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

            await pilot.resize_terminal(70, 40)
            await pilot.pause()
            assert notice.display is True

            await pilot.resize_terminal(100, 40)
            await pilot.pause()
            assert notice.display is False

    asyncio.run(scenario())
