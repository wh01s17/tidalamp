"""Focused Textual workflow regressions."""

from __future__ import annotations

import asyncio

from tidalamp.app import TidalAmp
from tidalamp.queue import Queue
from tidalamp.settings import Settings


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


def test_slow_tick_does_not_reapply_audio_filters(monkeypatch):
    """Changing filters may create an audible gap; polling must stay read-only."""
    async def no_mpris(self) -> None:
        return None

    monkeypatch.setattr(Queue, "load", lambda self: False)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings()))
    monkeypatch.setattr(TidalAmp, "_start_spectrum", lambda self: None)
    monkeypatch.setattr(TidalAmp, "_start_mpris", no_mpris)

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
