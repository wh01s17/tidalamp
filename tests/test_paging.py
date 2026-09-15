"""The next page comes in as the cursor nears the end of a level, and the
filter brings in the rest, so nobody has to press ↵ on «más…»."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime, settle

from tidalamp.app import BrowserScreen, RowList, TidalAmp
from tidalamp.library import Row
from tidalamp.queue import Entry


class Pages:
    """A level of ``pages`` pages of ``size`` tracks, counting what is asked."""

    def __init__(self, pages: int, size: int) -> None:
        self.pages = pages
        self.size = size
        self.asked: list[int] = []

    def page(self, number: int) -> list[Row]:
        rows = [
            Row(
                label=f"pista {number}-{i}",
                detail="1:00",
                entry=Entry(
                    id=number * 1000 + i, title=f"pista {number}-{i}", artist="a"
                ),
            )
            for i in range(self.size)
        ]
        if number + 1 < self.pages:
            rows.append(Row(label="más…", more=lambda: self.more(number + 1)))
        return rows

    def more(self, number: int) -> list[Row]:
        self.asked.append(number)
        return self.page(number)


def _browse(monkeypatch, pages: Pages, check, *, search: bool = False, size=(100, 30)):
    isolate_runtime(monkeypatch)
    first = pages.page(0)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=size) as pilot:
            application.push_screen(BrowserScreen("NIVEL", lambda: first, search=search))
            await pilot.pause()
            listed = application.screen.query_one(RowList)
            await settle(pilot, lambda: listed.rows)
            await check(pilot, application.screen, listed)

    asyncio.run(scenario())


def test_the_next_page_comes_in_as_the_cursor_nears_the_end(monkeypatch):
    pages = Pages(pages=3, size=60)

    async def check(pilot, screen, listed) -> None:
        # Far from the end: nothing asked yet.
        assert pages.asked == []
        # Near the end: within a screen of «más…».
        for _ in range(55):
            await pilot.press("down")
        await settle(pilot, lambda: pages.asked == [1] and len(listed.rows) > 61)
        assert pages.asked == [1]
        # The cursor stayed on the row it had reached.
        assert listed.current.label == "pista 0-55"

    _browse(monkeypatch, pages, check)


def test_a_page_is_asked_for_once_however_many_keys_arrive(monkeypatch):
    pages = Pages(pages=3, size=60)

    async def check(pilot, screen, listed) -> None:
        for _ in range(50):
            await pilot.press("down")
        await settle(pilot, lambda: len(listed.rows) > 61)
        await pilot.pause()
        assert pages.asked.count(1) == 1

    _browse(monkeypatch, pages, check)


def test_a_level_shorter_than_the_screen_fills_it_at_once(monkeypatch):
    pages = Pages(pages=2, size=5)

    async def check(pilot, screen, listed) -> None:
        await settle(pilot, lambda: pages.asked == [1])
        assert [row.label for row in listed.rows][-1] == "pista 1-4"

    _browse(monkeypatch, pages, check)


def test_the_filter_brings_in_every_page_before_it_answers(monkeypatch):
    """«nada coincide» used to be about the pages loaded, not the level."""
    pages = Pages(pages=4, size=60)

    async def check(pilot, screen, listed) -> None:
        await pilot.press("slash")
        for character in "3-7":
            await pilot.press(character)
        await settle(pilot, lambda: pages.asked == [1, 2, 3] and listed.rows)
        assert [row.label for row in listed.rows] == ["pista 3-7"]
        assert not screen._resting

    _browse(monkeypatch, pages, check)


def test_a_filter_over_a_search_does_not_fetch_every_page(monkeypatch):
    pages = Pages(pages=4, size=60)

    async def check(pilot, screen, listed) -> None:
        await pilot.press("slash")
        for character in "3-7":
            await pilot.press(character)
        await pilot.pause()
        await pilot.pause()
        assert pages.asked == []

    _browse(monkeypatch, pages, check, search=True)
