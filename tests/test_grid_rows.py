"""The foot of the grid: the next line of covers peeks in while there is one,
and nothing does once the last line is on screen."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime, settle

from tidalamp import config
from tidalamp.app import BrowserScreen, TidalAmp
from tidalamp.library import Row
from tidalamp.screens import browser as browser_module
from tidalamp.screens import grid as grid_module
from tidalamp.screens.grid import GridList

BLOCK = ((("█", (200, 30, 30), (0, 0, 0)),) * GridList.COVER_W,) * GridList.COVER_H


def _albums(count: int) -> list[Row]:
    return [
        Row(label=f"Disco {i}", detail="1997", key=f"album:{i}", loader=list, art=f"u{i}")
        for i in range(count)
    ]


def _grid_at_the_foot(monkeypatch, check) -> None:
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(config, "LIBRARY_VIEW", "grid")
    monkeypatch.setattr(browser_module, "cover_cells", lambda url: BLOCK)
    rows = _albums(60)
    for row in rows:
        grid_module._CELLS[row.art] = BLOCK

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        # A height that leaves the foot some lines past the whole tiles.
        async with application.run_test(size=(120, 45)) as pilot:
            application.push_screen(BrowserScreen("MI BIBLIOTECA", lambda: rows))
            await pilot.pause()
            grid = application.screen.query_one(GridList)
            await settle(pilot, lambda: grid.rows and grid.display)
            await check(pilot, grid)

    try:
        asyncio.run(scenario())
    finally:
        grid_module._CELLS.clear()


def test_the_next_line_of_covers_peeks_in_at_the_foot(monkeypatch):
    """Seen on a real terminal: with only whole tiles drawn, the empty foot
    read as the end of the collection."""

    async def check(pilot, grid) -> None:
        whole = grid.per_screen * GridList.TILE_H
        height = grid.size.height
        assert 0 < height - whole < GridList.COVER_H
        # Every line of the foot is the top of the next covers.
        for y in range(whole, height):
            assert "█" in grid.render_line(y).text
        # The whole lines keep their names.
        name = whole - GridList.TILE_H + GridList.COVER_H
        assert "Disco" in grid.render_line(name).text

    _grid_at_the_foot(monkeypatch, check)


def test_nothing_peeks_in_under_the_last_line(monkeypatch):
    async def check(pilot, grid) -> None:
        grid.cursor = len(grid.rows) - 1
        await pilot.pause()
        start = grid._window_start()
        lines = -(-len(grid.rows) // grid.columns)
        end = (lines - start) * GridList.TILE_H
        for y in range(end, grid.size.height):
            assert grid.render_line(y).text.strip() == ""

    _grid_at_the_foot(monkeypatch, check)
