"""The cover of the record that was playing does not come back over the new
one, and a cover that cannot be had takes the old one down."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, a_cover, isolate_runtime, settle
from textual.screen import Screen

from tidalamp import artwork
from tidalamp.app import TidalAmp
from tidalamp.artwork import Protocol
from tidalamp.widgets import Artwork


def test_a_cover_that_lands_as_the_window_closes_is_not_undone_by_the_tick(
    monkeypatch,
):
    """Seen on 2026-09-14: another record picked in the browser, its cover in
    the cache lands the moment the browser closes, and the next tick puts the
    last record's cover back, the one the browser had hidden."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            art = application.query_one(Artwork)
            old = a_cover(Protocol.KITTY, escape="\x1b_Gold\x1b\\")
            new = a_cover(Protocol.KITTY, escape="\x1b_Gnew\x1b\\")
            art.show(old)
            await pilot.pause()

            application.push_screen(Screen())
            await pilot.pause()
            assert art.cover is None and application._art_hidden

            application.pop_screen()
            await pilot.pause()
            # Before any tick has run.
            application._art_ready(new)
            assert art.cover is new

            application._tick_slow()
            assert art.cover is new
            assert not application._art_hidden

    asyncio.run(scenario())


def test_a_cover_that_cannot_be_had_takes_the_last_one_down(monkeypatch):
    isolate_runtime(monkeypatch)

    def broken(url, **kwargs):
        raise OSError("sin red")

    monkeypatch.setattr(artwork, "fetch", broken)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            art = application.query_one(Artwork)
            art.show(a_cover(Protocol.KITTY, escape="\x1b_Gold\x1b\\"))
            await pilot.pause()

            application._art_url = "https://x/new/320x320.jpg"
            application._art_worker(application._art_url)
            await settle(pilot, lambda: art.cover is None)
            assert art.cover is None
            assert "sin red" in application.status

    asyncio.run(scenario())


def test_no_cover_behind_a_window_takes_the_hidden_one_with_it(monkeypatch):
    """A failed cover while a window is open: nothing to show, and nothing
    for the tick to bring back once the window closes."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            art = application.query_one(Artwork)
            art.show(a_cover(Protocol.KITTY, escape="\x1b_Gold\x1b\\"))
            await pilot.pause()
            application.push_screen(Screen())
            await pilot.pause()

            application._art_ready(None)
            application.pop_screen()
            await pilot.pause()
            application._tick_slow()
            assert art.cover is None
            assert application._pending_art is None

    asyncio.run(scenario())
