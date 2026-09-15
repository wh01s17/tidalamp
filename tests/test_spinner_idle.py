"""The status line's spinner takes no room while nothing is loading."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime, settle

from tidalamp.app import TidalAmp
from tidalamp.widgets import Spinner


def test_the_idle_spinner_leaves_no_block_before_the_status_line(monkeypatch):
    """Seen on a real terminal: two cells of the spinner's own ground, its
    padding, at the head of «queue restored…» with nothing spinning."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            busy = application.query_one("#busy", Spinner)
            assert busy.has_class("-idle")
            assert busy.size.width == 0

            busy.start("cargando…")
            await settle(pilot, lambda: busy.size.width > 2)
            assert not busy.has_class("-idle")

            busy.stop()
            await settle(pilot, lambda: busy.size.width == 0)
            assert busy.size.width == 0

    asyncio.run(scenario())
