"""Pagination: a full page hangs a "más…" row off the end, a short one does
not, and following it yields the next page."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import FakeTrack

from tidalamp import library
from tidalamp.library import PAGE, Row, search_rows
from tidalamp.queue import Entry


class FakeFavorites:
    """TIDAL's favourites, including its habit of returning short pages.

    ``filtered`` drops that many items from every page *after* the limit is
    applied, which is what the real endpoint does and what used to make the
    browser stop at the first page.
    """

    def __init__(self, total: int, filtered: int = 0, counts: bool = True):
        self.total = total
        self.filtered = filtered
        self.counts = counts
        self.calls: list[tuple[int, int]] = []

    def tracks(self, limit=50, offset=0, **kwargs):
        self.calls.append((offset, limit))
        window = [FakeTrack(i) for i in range(offset, min(self.total, offset + limit))]
        return window[: max(0, len(window) - self.filtered)]

    def get_tracks_count(self):
        return self.total if self.counts else None

    def albums(self, limit=50, offset=0, **kwargs):
        return []

    def get_albums_count(self):
        return 0

    def artists(self, limit=50, offset=0, **kwargs):
        return []

    def get_artists_count(self):
        return 0


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
    def __init__(
        self, total: int = 0, playlists: int = 0, filtered: int = 0, counts: bool = True
    ):
        favorites = FakeFavorites(total, filtered=filtered, counts=counts)
        self.favorites = favorites
        self.user = type("U", (), {"favorites": favorites, "playlists": list, "id": 7})()
        self.request = FakeRequest(playlists)
        self.searched: list[tuple[int, int]] = []
        self.searched_models: list[str] = []
        self._total = total

    def search(self, query, models=None, limit=50, offset=0):
        name = models[0].__name__.lower() if models else "track"
        self.searched.append((offset, limit))
        self.searched_models.append(name)
        span = range(offset, min(self._total, offset + limit))
        if name == "track":
            return {"tracks": [FakeTrack(i) for i in span]}
        if name == "album":
            return {
                "albums": [
                    SimpleNamespace(
                        id=i,
                        name=f"álbum {i}",
                        year=2000 + i,
                        artist=SimpleNamespace(name="a"),
                        tracks=lambda limit=50, offset=0: [],
                    )
                    for i in span
                ]
            }
        if name == "artist":
            return {
                "artists": [
                    SimpleNamespace(
                        id=i,
                        name=f"artista {i}",
                        get_top_tracks=lambda limit=50, offset=0: [],
                    )
                    for i in span
                ]
            }
        return {
            "playlists": [
                SimpleNamespace(
                    id=f"p{i}",
                    name=f"lista {i}",
                    num_tracks=i,
                    tracks=lambda limit=50, offset=0: [],
                )
                for i in span
            ]
        }


def favourite_tracks_level(session) -> list[Row]:
    rows = library.root(session)
    return next(r for r in rows if r.label == "Pistas favoritas").loader()


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


def test_an_exact_multiple_does_not_offer_an_empty_page_when_the_count_is_known():
    session = FakeSession(total=PAGE)
    rows = favourite_tracks_level(session)
    assert len(rows) == PAGE
    assert all(r.more is None for r in rows)


def test_an_exact_multiple_offers_one_empty_page_without_a_count():
    # With no count we cannot tell a full last page from a truncated one, so we
    # offer "más…" and it resolves to an empty level rather than lying.
    session = FakeSession(total=PAGE, counts=False)
    rows = favourite_tracks_level(session)
    assert rows[-1].more is not None
    assert rows[-1].more() == []


def test_a_short_page_is_not_the_end_when_the_count_says_otherwise():
    """The real bug: 100 favourites asked for, 90 returned, 766 in the account.

    Reading the short page as the end meant the other 676 were unreachable.
    """
    session = FakeSession(total=766, filtered=10)
    rows = favourite_tracks_level(session)

    assert len(rows) == 91  # 90 pistas y la fila «más…»
    assert rows[-1].more is not None
    assert rows[-1].detail == f"siguientes {PAGE} de 766"

    # And it keeps going: the offset advances by the page size, not by how
    # many survived the filter.
    second = rows[-1].more()
    assert session.favorites.calls == [(0, PAGE), (PAGE, PAGE)]
    assert second[-1].more is not None


def test_paging_a_filtered_level_reaches_the_end():
    session = FakeSession(total=250, filtered=10)
    rows = favourite_tracks_level(session)
    pages = 1
    while rows[-1].more is not None:
        rows = rows[-1].more()
        pages += 1
        assert pages < 10, "no debería hacer falta paginar eternamente"

    assert pages == 3  # offsets 0, 100 y 200
    assert session.favorites.calls == [(0, PAGE), (PAGE, PAGE), (2 * PAGE, PAGE)]


def test_search_is_paginated_too():
    session = FakeSession(total=PAGE + 1)
    rows = search_rows(session, "tool")
    assert session.searched == [(0, PAGE)]
    assert rows[-1].more is not None
    assert len(rows[-1].more()) == 1


# ------------------------------------------------------- search by category


def test_search_offers_albums_artists_and_playlists_besides_tracks():
    session = FakeSession(total=3)
    rows = search_rows(session, "tool")

    heads = [r.label for r in rows[:3]]
    assert heads == [
        "Álbumes con «tool»",
        "Artistas con «tool»",
        "Playlists con «tool»",
    ]
    assert all(r.loader is not None and r.entry is None for r in rows[:3])
    # The tracks still come inline: reaching one must not cost a keystroke.
    assert [r.entry.title for r in rows[3:]] == ["pista 0", "pista 1", "pista 2"]


def test_opening_search_only_asks_for_the_tracks():
    """Each category costs a request when it is opened, and not before."""
    session = FakeSession(total=2)
    search_rows(session, "tool")
    assert session.searched_models == ["track"]


def test_each_category_asks_for_its_own_model_when_opened():
    session = FakeSession(total=2)
    rows = search_rows(session, "tool")

    albums = rows[0].loader()
    artists = rows[1].loader()
    playlists = rows[2].loader()

    assert session.searched_models == ["track", "album", "artist", "playlist"]
    assert [r.label for r in albums] == ["a - álbum 0", "a - álbum 1"]
    assert [r.label for r in artists] == ["artista 0", "artista 1"]
    assert [r.label for r in playlists] == ["lista 0", "lista 1"]


def test_a_category_of_search_results_paginates():
    session = FakeSession(total=PAGE + 4)
    rows = search_rows(session, "tool")
    albums = rows[0].loader()

    assert albums[-1].more is not None
    assert len(albums[-1].more()) == 4


def test_search_categories_are_cached_per_query():
    session = FakeSession(total=2)
    rows = search_rows(session, "tool")
    rows[0].loader()
    rows[0].loader()
    assert session.searched_models.count("album") == 1

    # A different query must not be served the first one's results.
    other = search_rows(session, "opeth")
    other[0].loader()
    assert session.searched_models.count("album") == 2


# ------------------------------------------------------- playlists, cheaply


def playlists_level(session, monkeypatch) -> list[Row]:
    monkeypatch.setattr(library.tidalapi, "Playlist", FakePlaylistPrototype)
    rows = library.root(session)
    return next(r for r in rows if r.label == "Mis playlists").loader()


def test_the_playlist_list_costs_one_request_per_page(monkeypatch):
    """It used to cost one per playlist: 110 playlists, 111 requests, 20 s.

    Two requests now, not one: the count decides whether there is another
    page, because a short page does not mean the end. Two is still 109 fewer.
    """
    session = FakeSession(playlists=PAGE + 10)
    rows = playlists_level(session, monkeypatch)

    assert session.request.calls == [
        ("GET", "users/7/playlists", {"limit": 1, "offset": 0}),
        ("GET", "users/7/playlists", {"limit": PAGE, "offset": 0}),
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


# ----------------------------------------------------------------- favoritos


class FakeFavoritesWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def _record(self, name):
        def call(ident):
            self.calls.append((name, ident))
            return True

        return call

    def __getattr__(self, name):
        if name.startswith(("add_", "remove_")):
            return self._record(name)
        raise AttributeError(name)


def writer_session():
    favorites = FakeFavoritesWriter()
    return SimpleNamespace(user=SimpleNamespace(favorites=favorites)), favorites


def test_a_track_row_favourites_the_track():
    session, favorites = writer_session()
    row = Row(label="x", entry=Entry(id=42, title="Schism", artist="TOOL"))

    assert library.favourite(session, row, add=True) == "TOOL - Schism"
    assert library.favourite(session, row, add=False) == "TOOL - Schism"
    # As a string: tidalapi joins ids with "," and types the argument as str.
    assert favorites.calls == [("add_track", "42"), ("remove_track", "42")]


@pytest.mark.parametrize(
    "key, added, removed",
    [
        ("album:99", "add_album", "remove_album"),
        ("artist:7", "add_artist", "remove_artist"),
        ("playlist:abc-uuid", "add_playlist", "remove_playlist"),
    ],
)
def test_a_container_row_favourites_by_the_kind_in_its_key(key, added, removed):
    session, favorites = writer_session()
    row = Row(label="Lateralus", key=key, loader=list)

    library.favourite(session, row, add=True)
    library.favourite(session, row, add=False)

    ident = key.split(":", 1)[1]
    assert favorites.calls == [(added, ident), (removed, ident)]


@pytest.mark.parametrize("key", ["", "playlists", "fav:tracks", "search:albums:tool"])
def test_a_heading_is_not_a_thing_you_can_favourite(key):
    session, favorites = writer_session()
    row = Row(label="Mis playlists", key=key, loader=list)

    with pytest.raises(library.NotFavouritable):
        library.favourite(session, row)
    assert favorites.calls == []


def test_a_more_row_is_not_favouritable():
    session, favorites = writer_session()
    with pytest.raises(library.NotFavouritable):
        library.favourite(session, Row(label="más…", more=list))
    assert favorites.calls == []
