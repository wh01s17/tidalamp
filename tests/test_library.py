"""Pagination: a full page hangs a "más…" row off the end, a short one does
not, and following it yields the next page."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

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


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeRequest:
    """Stands in for tidalapi's request object, counting what we ask for."""

    def __init__(self, total: int):
        self.total = total
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, path, params=None):
        params = dict(params or {})
        self.calls.append((method, path, params))
        offset, limit = params.get("offset", 0), params.get("limit", 50)
        items = [
            {"uuid": f"p{i}", "title": f"lista {i}", "numberOfTracks": i}
            for i in range(offset, min(self.total, offset + limit))
        ]
        return FakeResponse({"items": items, "totalNumberOfItems": self.total})


class FakePlaylistPrototype:
    """Stands in for ``tidalapi.Playlist``.

    The assert is the whole point of the optimisation: tidalapi's own path
    builds these *with* an id, and that constructor fetches the playlist again
    just to read an ETag — one HTTP request per row.
    """

    def __init__(self, session, playlist_id):
        assert playlist_id is None, "un id haría que tidalapi pidiera la playlist"

    def parse(self, item):
        return SimpleNamespace(
            id=item["uuid"],
            name=item["title"],
            num_tracks=item["numberOfTracks"],
            tracks=lambda limit=50, offset=0: [],
        )


class FakeSession:
    def __init__(self, total: int = 0, playlists: int = 0):
        favorites = FakeFavorites(total)
        self.favorites = favorites
        self.user = type(
            "U", (), {"favorites": favorites, "playlists": lambda: [], "id": 7}
        )()
        self.request = FakeRequest(playlists)
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


# ------------------------------------------------------- playlists, cheaply


def playlists_level(session, monkeypatch) -> list[Row]:
    monkeypatch.setattr(library.tidalapi, "Playlist", FakePlaylistPrototype)
    rows = library.root(session)
    return [r for r in rows if r.label == "Mis playlists"][0].loader()


def test_the_playlist_list_costs_one_request_per_page(monkeypatch):
    """It used to cost one per playlist: 110 playlists, 111 requests, 20 s."""
    session = FakeSession(playlists=PAGE + 10)
    rows = playlists_level(session, monkeypatch)

    assert session.request.calls == [
        ("GET", "users/7/playlists", {"limit": PAGE, "offset": 0})
    ]
    assert len(rows) == PAGE + 1
    assert rows[-1].more is not None
    assert rows[0].label == "lista 0"
    assert rows[1].detail == "1 pistas"


def test_the_playlist_list_paginates_like_every_other_level(monkeypatch):
    session = FakeSession(playlists=PAGE + 10)
    rows = playlists_level(session, monkeypatch)

    nxt = rows[-1].more()

    assert len(nxt) == 10
    assert session.request.calls[-1] == (
        "GET",
        "users/7/playlists",
        {"limit": PAGE, "offset": PAGE},
    )


def test_every_playlist_row_carries_a_cache_key(monkeypatch):
    rows = playlists_level(FakeSession(playlists=3), monkeypatch)
    assert [r.key for r in rows] == ["playlist:p0", "playlist:p1", "playlist:p2"]


# ------------------------------------------------------------------- caching


def test_a_level_is_fetched_once_and_then_remembered():
    calls: list[int] = []

    def loader() -> list[Row]:
        calls.append(1)
        return [Row(label="x")]

    cached = library.cached("nivel", loader)

    assert cached()[0].label == "x"
    assert cached()[0].label == "x"
    assert calls == [1]

    library.forget("nivel")
    cached()
    assert calls == [1, 1]


def test_the_cached_level_is_the_same_list_the_browser_extends():
    """Loading another page mutates the level in place; the cache must see it."""
    cached = library.cached("nivel", lambda: [Row(label="x")])
    rows = cached()
    rows.append(Row(label="y"))

    assert [r.label for r in cached()] == ["x", "y"]


def test_forgetting_everything_clears_every_level():
    library.cached("a", lambda: [Row(label="a")])()
    library.cached("b", lambda: [Row(label="b")])()
    library.forget()
    assert library._LEVELS == {}


def test_favourite_levels_are_cached_too(monkeypatch):
    session = FakeSession(total=3)
    library.root(session)[1].loader()
    library.root(session)[1].loader()
    assert session.favorites.calls == [(0, PAGE)]
