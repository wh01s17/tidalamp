"""Focused Textual workflow regressions."""

from __future__ import annotations

import asyncio

from textual.screen import Screen
from textual.widgets import Static

from tidalamp.app import TidalAmp
from tidalamp.artwork import Cover, Protocol
from tidalamp.queue import Entry, Queue
from tidalamp.settings import Settings
from tidalamp.theme import DEFAULT_COLORS, ThemePalette
from tidalamp.widgets import Artwork


class FakeMpv:
    alive = True
    position = 0.0
    duration = 0.0
    volume = 100
    paused = False
    idle = True

    def __init__(self) -> None:
        self.filter_calls: list[tuple[str, str | None]] = []

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
