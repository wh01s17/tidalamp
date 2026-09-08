"""Focused Textual workflow regressions."""

from __future__ import annotations

import asyncio

from textual.widgets import Static

from tidalamp.app import TidalAmp
from tidalamp.queue import Queue
from tidalamp.settings import Settings
from tidalamp.theme import DEFAULT_COLORS, ThemePalette


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
