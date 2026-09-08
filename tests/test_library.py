"""Pagination: a full page hangs a "más…" row off the end, a short one does
not, and following it yields the next page."""

from __future__ import annotations

from tidalamp import library
from tidalamp.library import PAGE, Row, search_rows

from conftest import FakeTrack


class FakeFavorites:
    def __init__(self, total: int):
        self.total = total
        self.calls: list[tuple[int, int]] = []

    def tracks(self, limit=50, offset=0, **kwargs):
        self.calls.append((offset, limit))
        return [FakeTrack(i) for i in range(offset, min(self.total, offset + limit))]

    def albums(self, limit=50, offset=0, **kwargs):
        return []

    def artists(self, limit=50, offset=0, **kwargs):
        return []


class FakeSession:
    def __init__(self, total: int = 0):
        favorites = FakeFavorites(total)
        self.favorites = favorites
        self.user = type("U", (), {"favorites": favorites, "playlists": lambda: []})()
        self.searched: list[tuple[int, int]] = []
        self._total = total

    def search(self, query, models=None, limit=50, offset=0):
        self.searched.append((offset, limit))
        tracks = [FakeTrack(i) for i in range(offset, min(self._total, offset + limit))]
        return {"tracks": tracks}


def favourite_tracks_level(session) -> list[Row]:
    rows = library.root(session)
    return [r for r in rows if r.label == "Pistas favoritas"][0].loader()


def test_a_short_page_has_no_more_row():
    rows = favourite_tracks_level(FakeSession(total=7))
    assert len(rows) == 7
    assert all(r.more is None for r in rows)


def test_a_full_page_offers_more():
    rows = favourite_tracks_level(FakeSession(total=PAGE + 5))
    assert len(rows) == PAGE + 1
    assert rows[-1].more is not None
    assert rows[-1].entry is None


def test_following_more_fetches_the_next_offset():
    session = FakeSession(total=PAGE + 5)
    rows = favourite_tracks_level(session)
    nxt = rows[-1].more()
    assert session.favorites.calls == [(0, PAGE), (PAGE, PAGE)]
    assert len(nxt) == 5
    assert all(r.more is None for r in nxt)


def test_an_exact_multiple_offers_one_empty_page():
    # We cannot tell a full last page from a truncated one, so we offer "más…"
    # and it resolves to an empty level rather than lying about the count.
    session = FakeSession(total=PAGE)
    rows = favourite_tracks_level(session)
    assert rows[-1].more is not None
    assert rows[-1].more() == []


def test_search_is_paginated_too():
    session = FakeSession(total=PAGE + 1)
    rows = search_rows(session, "tool")
    assert session.searched == [(0, PAGE)]
    assert rows[-1].more is not None
    assert len(rows[-1].more()) == 1
