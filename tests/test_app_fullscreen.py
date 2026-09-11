"""The full-screen view: `w` in, esc out, the queue beside the cover."""

from __future__ import annotations

import asyncio
import io

import pytest
from app_helpers import FakeMpv, isolate_runtime, settle
from rich.cells import cell_len

from tidalamp import app as app_module
from tidalamp import artwork
from tidalamp.app import TidalAmp
from tidalamp.queue import Entry
from tidalamp.screens import FullscreenScreen, HelpScreen, RowList
from tidalamp.screens.fullscreen import FullArtwork


def a_queue_playing(application, playing: int = 0) -> None:
    application.queue.replace(
        [
            Entry(id=i, title=title, artist="TOOL", art_url=f"http://cover/{i}")
            for i, title in enumerate(["Schism", "Parabola", "Lateralus"])
        ],
        start=playing,
    )
    application._sync_queue()


def test_w_opens_the_full_screen_view_and_esc_comes_back(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            a_queue_playing(application, 1)

            await pilot.press("w")
            await pilot.pause()
            assert isinstance(application.screen, FullscreenScreen)
            track = application.screen.query_one("#fs-track").render_line(0).text
            assert "Parabola" in track
            # The queue's button against the right edge, less the padding.
            side = application.screen.query_one("#fs-side")
            button = side.render_line(1).text
            assert button.rstrip().endswith("cola")
            assert len(button.rstrip()) >= side.size.width - 2

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(application.screen, FullscreenScreen)
            assert len(application.screen_stack) == 1
            assert application.queue.playing == 1
            assert len(application.queue) == 3

    asyncio.run(scenario())


def test_tab_shows_the_queue_beside_the_cover_and_enter_plays_from_it(monkeypatch):
    isolate_runtime(monkeypatch)
    started: list[int] = []
    monkeypatch.setattr(TidalAmp, "_play_index", lambda self, i: started.append(i))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            a_queue_playing(application, 0)
            await pilot.press("w")
            await pilot.pause()
            screen = application.screen
            panel = screen.query_one("#fs-queue")
            assert not panel.display

            await pilot.press("tab")
            await pilot.pause()
            assert panel.display
            listing = screen.query_one("#fs-queue-list", RowList)
            assert [row.entry.title for row in listing.rows] == [
                "Schism",
                "Parabola",
                "Lateralus",
            ]
            await pilot.press("down", "enter")
            assert started == [1]

            await pilot.press("tab")
            await pilot.pause()
            assert not panel.display

    asyncio.run(scenario())


def test_the_controls_are_clickable_and_act_on_the_player(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            a_queue_playing(application)
            await pilot.press("w")
            await pilot.pause()
            screen = application.screen
            start, end, _action = next(h for h in screen._hits if h[2] == "shuffle")
            await pilot.click("#fs-controls", offset=((start + end) // 2, 0))
            await pilot.pause()
            assert application.queue.shuffle is True

    asyncio.run(scenario())


def test_the_pixel_cover_stays_up_here_and_hides_under_a_window(monkeypatch):
    """The cover is drawn in this view, not hidden as under a window; a
    window opened over the view does hide it, and closing it brings it back."""
    pil_image = pytest.importorskip("PIL.Image")
    isolate_runtime(monkeypatch)
    buffer = io.BytesIO()
    pil_image.new("RGB", (64, 64), (200, 20, 20)).save(buffer, "PNG")
    monkeypatch.setattr(artwork, "fetch", lambda url, **kwargs: buffer.getvalue())

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            application.art_protocol = artwork.Protocol.KITTY
            a_queue_playing(application)
            await pilot.press("w")
            screen = application.screen
            art = screen.query_one(FullArtwork)
            await settle(pilot, lambda: art.cover is not None)
            assert art.cover.protocol is artwork.Protocol.KITTY
            assert art.rows > app_module.Artwork.MAX_ROWS

            application.push_screen(HelpScreen(app_module.keys_for))
            await pilot.pause()
            assert art.cover is None

            await pilot.press("escape")
            await pilot.pause()
            assert application.screen is screen
            assert art.cover is not None

    asyncio.run(scenario())


def test_every_look_fits_the_full_screen_view_at_the_minimum(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        for name in app_module.LAYOUTS:
            app_module.config.THEME = name
            application = TidalAmp(object(), FakeMpv())
            size = (TidalAmp.MIN_WIDTH, TidalAmp.MIN_HEIGHT)
            async with application.run_test(size=size) as pilot:
                await pilot.pause()
                a_queue_playing(application)
                await pilot.press("w")
                await pilot.pause()
                screen = application.screen
                assert isinstance(screen, FullscreenScreen), name
                controls = screen.query_one("#fs-controls")
                line = controls.render_line(0).text
                assert cell_len(line.rstrip()) <= controls.size.width, name
                art = screen.query_one(FullArtwork)
                bar = screen.query_one("#fs-bar")
                assert art.region.bottom <= bar.region.y, name

    asyncio.run(scenario())
