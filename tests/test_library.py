"""Pagination: a full page hangs a "más…" row off the end, a short one does
not, and following it yields the next page."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import FakeTrack
from tidalapi.types import ItemOrder, OrderDirection

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
        self.orders: list[tuple[object, object]] = []

    def tracks(self, limit=50, offset=0, **kwargs):
        self.calls.append((offset, limit))
        self.orders.append((kwargs.get("order"), kwargs.get("order_direction")))
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
            tracks=lambda limit=50, offset=0, **order: [],
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
                        tracks=lambda limit=50, offset=0, **order: [],
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
                        get_top_tracks=lambda limit=50, offset=0, **order: [],
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
                    tracks=lambda limit=50, offset=0, **order: [],
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


# ------------------------------------------------------- playlist creation


class WritablePlaylist:
    def __init__(self, fail_on: int | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[tuple[list[str], bool, int, int]] = []

    def add(self, media_ids, allow_duplicates=False, position=-1, limit=100):
        batch = list(media_ids)
        self.calls.append((batch, allow_duplicates, position, limit))
        if self.fail_on == len(self.calls):
            raise RuntimeError("sin red")
        return batch


class PlaylistOwner:
    def __init__(self, playlist: WritablePlaylist) -> None:
        self.playlist = playlist
        self.calls: list[tuple[str, str]] = []

    def create_playlist(self, title: str, description: str):
        self.calls.append((title, description))
        return self.playlist


def queue_entries(count: int) -> list[Entry]:
    return [Entry(id=i, title=f"pista {i}", artist="artista") for i in range(count)]


def test_saving_a_queue_creates_and_fills_the_playlist_in_order_and_batches():
    playlist = WritablePlaylist()
    owner = PlaylistOwner(playlist)
    session = SimpleNamespace(user=owner)
    entries = queue_entries(700)
    library.cached("playlists", lambda: [Row(label="vieja")])()

    added = library.save_queue_playlist(session, "Viaje", entries)

    assert owner.calls == [("Viaje", "")]
    assert [len(call[0]) for call in playlist.calls] == [100] * 7
    assert [ident for batch, *_ in playlist.calls for ident in batch] == [
        str(entry.id) for entry in entries
    ]
    assert all(call[1:] == (True, -1, library.PLAYLIST_BATCH) for call in playlist.calls)
    assert added == 700
    assert "playlists" not in library._LEVELS


def test_a_failed_batch_reports_the_completed_count_and_keeps_the_source_queue():
    playlist = WritablePlaylist(fail_on=3)
    owner = PlaylistOwner(playlist)
    session = SimpleNamespace(user=owner)
    entries = queue_entries(205)
    before = [entry.id for entry in entries]

    with pytest.raises(library.PlaylistSaveFailed) as raised:
        library.save_queue_playlist(session, "Viaje", entries)

    assert raised.value.title == "Viaje"
    assert raised.value.added == 200
    assert raised.value.total == 205
    assert str(raised.value) == "sin red"
    assert [entry.id for entry in entries] == before
    assert len(playlist.calls) == 3


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


# ------------------------------------------------------------------- filtrar


def track_row(title: str, artist: str = "TOOL", album: str = "") -> Row:
    entry = Entry(id=1, title=title, artist=artist, album=album)
    return Row(label=entry.label, detail="4:00", entry=entry)


def test_the_filter_reads_label_and_detail():
    row = Row(label="Mis mejores canciones", detail="42 pistas")
    assert library.matches("mejores", row)
    assert library.matches("42", row)
    assert not library.matches("peores", row)


def test_the_filter_ignores_case_and_accents():
    """Typing accents to search is a tax nobody pays, and TIDAL writes the
    same name both ways depending on the release."""
    row = Row(label="Sinfonía nº 9")
    assert library.matches("sinfonia", row)
    assert library.matches("SINFONÍA", row)
    assert library.matches("sinfonía", row)


def test_every_term_has_to_match_somewhere():
    row = track_row("Schism", album="Lateralus")
    assert library.matches("tool schism", row)
    assert library.matches("schism tool", row)
    assert not library.matches("tool sober", row)


def test_a_track_is_found_by_its_album_even_when_no_column_shows_it():
    """The album is what people remember, and it is only on the line if the
    user turned that column on."""
    row = track_row("Schism", album="Lateralus")
    assert library.matches("lateralus", row)
    assert library.matches("tool lateralus", row)


def test_a_level_row_without_an_entry_is_matched_by_its_name():
    row = Row(label="Pistas favoritas", key="fav:tracks")
    assert library.matches("favoritas", row)
    assert not library.matches("albumes", row)


def test_an_empty_query_matches_everything():
    assert library.matches("   ", track_row("Schism"))


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


# ---------------------------------------------------------------- track radio


class RadioTrack(FakeTrack):
    """A track whose station is whatever the test hands it."""

    def __init__(self, id: int, station=None, error: Exception | None = None):
        super().__init__(id)
        self._station = station or []
        self._error = error
        self.asked: list[int] = []

    def get_track_radio(self, limit: int = 100):
        self.asked.append(limit)
        if self._error is not None:
            raise self._error
        return self._station


def seeded(station=None, error: Exception | None = None):
    """An entry carrying its Track, so resolve() never reaches the network."""
    track = RadioTrack(1, station, error)
    entry = Entry(id=1, title="semilla", artist="a", _track=track)
    return entry, track


def test_track_radio_returns_the_station_as_entries():
    entry, track = seeded([FakeTrack(7, "uno"), FakeTrack(8, "dos")])

    entries = library.track_radio(object(), entry, limit=25)

    assert [e.title for e in entries] == ["uno", "dos"]
    assert all(isinstance(e, Entry) for e in entries)
    assert track.asked == [25]


def test_the_seed_is_dropped_from_its_own_station():
    """TIDAL heads the station with the seed, and the caller leads with the
    seed too, so the first song appeared twice in the queue."""
    entry, _track = seeded([FakeTrack(1, "semilla"), FakeTrack(7, "uno")])

    entries = library.track_radio(object(), entry)

    assert [e.title for e in entries] == ["uno"]


def test_the_seed_is_dropped_wherever_it_turns_up():
    entry, _track = seeded(
        [FakeTrack(7, "uno"), FakeTrack(1, "semilla"), FakeTrack(8, "dos")]
    )

    assert [e.title for e in library.track_radio(object(), entry)] == ["uno", "dos"]


def test_a_station_that_is_only_the_seed_is_no_station():
    entry, _track = seeded([FakeTrack(1, "semilla")])

    with pytest.raises(library.NoRadio):
        library.track_radio(object(), entry)


def test_a_track_without_a_station_is_a_normal_answer_not_a_crash():
    """TIDAL answers 404 for an obscure release; tidalapi raises. Neither is
    a failure of ours, and both have to reach the status line as words."""
    entry, _track = seeded(error=RuntimeError("MetadataNotAvailable"))

    with pytest.raises(library.NoRadio) as raised:
        library.track_radio(object(), entry)
    assert "semilla" in str(raised.value)


def test_an_empty_station_is_treated_as_no_station():
    entry, _track = seeded([])

    with pytest.raises(library.NoRadio):
        library.track_radio(object(), entry)


# --------------------------------------------------------------- año del álbum


class FakeAlbums:
    """A session that counts how many albums it was asked about."""

    def __init__(self, years: dict[str, int | None]) -> None:
        self.years = years
        self.asked: list[str] = []

    def album(self, album_id: str):
        self.asked.append(album_id)
        if album_id not in self.years:
            raise RuntimeError("no such album")
        return type("Album", (), {"year": self.years[album_id]})()


def test_the_year_costs_one_request_per_album_and_not_per_track():
    """A hundred tracks off fifteen records cost fifteen requests. That ratio
    is the whole reason this is asked for separately."""
    library._YEARS.clear()
    session = FakeAlbums({"10": 1997, "20": 2000})

    assert library.album_year(session, 10) == 1997
    assert library.album_year(session, 10) == 1997
    assert library.album_year(session, 20) == 2000
    assert session.asked == ["10", "20"], "la segunda pista del mismo disco no pregunta"


def test_an_album_with_no_date_is_asked_about_once_and_left_empty():
    """`0` is cached like any other answer: a record TIDAL has no date for
    must not be asked about again on every redraw."""
    library._YEARS.clear()
    session = FakeAlbums({"30": None})

    assert library.album_year(session, 30) == 0
    assert library.album_year(session, 30) == 0
    assert session.asked == ["30"]


def test_a_failed_lookup_is_not_cached():
    library._YEARS.clear()
    session = FakeAlbums({})

    assert library.album_year(session, 40) == 0
    assert library.album_year(session, 40) == 0
    assert session.asked == ["40", "40"], "un fallo puede reintentarse más tarde"


def test_an_entry_with_no_album_id_asks_nothing():
    """A queue saved before the field existed carries no id, so there is
    nothing to ask about; it fills on the next reload."""
    library._YEARS.clear()
    session = FakeAlbums({"50": 1999})

    assert library.album_year(session, 0) == 0
    assert session.asked == []


# ------------------------------------------- añadir a una playlist existente


class FakeUserPlaylist:
    def __init__(self, name="Mi playlist", fail_after=None):
        self.name = name
        self.batches: list[list[str]] = []
        self._fail_after = fail_after

    def add(self, items, allow_duplicates=False, position=-1, limit=100):
        if self._fail_after is not None and len(self.batches) >= self._fail_after:
            raise RuntimeError("TIDAL dijo que no")
        self.batches.append(list(items))
        return list(range(len(items)))


class FakeReadOnlyPlaylist:
    """What a playlist someone else owns parses into: no `add`."""

    name = "De otra persona"


class FakePlaylistSession:
    def __init__(self, playlist):
        self._playlist = playlist

    def playlist(self, playlist_id):
        return self._playlist


def entries(count):
    return [Entry(id=i, title=f"t{i}", artist="a") for i in range(count)]


def test_adding_to_a_playlist_sends_every_track_in_batches():
    playlist = FakeUserPlaylist()
    added = library.add_to_playlist(
        FakePlaylistSession(playlist), "7", entries(250), batch_size=100
    )

    assert added == 250
    assert [len(b) for b in playlist.batches] == [100, 100, 50]
    assert [b[0] for b in playlist.batches] == ["0", "100", "200"], "en orden"


def test_a_batch_that_fails_keeps_what_already_went_in():
    playlist = FakeUserPlaylist(fail_after=2)

    with pytest.raises(library.PlaylistSaveFailed) as caught:
        library.add_to_playlist(
            FakePlaylistSession(playlist), "7", entries(250), batch_size=100
        )

    assert caught.value.added == 200
    assert caught.value.total == 250
    assert len(playlist.batches) == 2, "no se deshace lo que sí entró"


def test_a_playlist_this_account_cannot_write_to_is_reported():
    with pytest.raises(library.PlaylistNotWritable):
        library.add_to_playlist(
            FakePlaylistSession(FakeReadOnlyPlaylist()), "7", entries(1)
        )


def test_adding_forgets_the_listing_and_that_playlist_level():
    """Otherwise opening it afterwards shows it as it was."""
    library._LEVELS["playlists"] = ["viejo"]
    library._LEVELS["playlist:7"] = ["viejo"]

    library.add_to_playlist(FakePlaylistSession(FakeUserPlaylist()), "7", entries(1))

    assert "playlists" not in library._LEVELS
    assert "playlist:7" not in library._LEVELS


def kinds(row: Row) -> set[str]:
    return {order.by for order in row.orders if order is not None}


def test_favourite_tracks_are_sorted_by_tidal_four_ways_both_ways_round(monkeypatch):
    """TIDAL sorts the whole collection; a sort over the page already loaded
    would order 100 tracks of 766 and call it the library."""
    monkeypatch.setattr(library, "_CHOSEN", {})
    library.forget()
    session = FakeSession(total=3)
    tracks = next(row for row in library.root(session) if row.key == "fav:tracks")

    assert tracks.orders[0] is None
    assert kinds(tracks) == {"date", "name", "artist", "album"}
    assert len(tracks.orders) == 9
    # Dates newest first, names A to Z first.
    assert tracks.orders[1] == library.Order("date", descending=True)
    assert tracks.orders[3] == library.Order("name")

    key, loader = tracks.sort(library.Order("name"))
    assert key == "fav:tracks|name-asc"
    loader()
    assert session.favorites.orders[-1] == (ItemOrder.Name, OrderDirection.Ascending)
    assert tracks.sort(None)[0] == "fav:tracks"
    library.forget()


def test_each_section_offers_only_the_orders_that_mean_something():
    rows = {row.key: row for row in library.root(FakeSession())}
    assert kinds(rows["fav:albums"]) == {"date", "name", "artist", "release"}
    assert kinds(rows["fav:artists"]) == {"date", "name"}
    assert kinds(rows["playlists"]) == {"date", "name"}
    # A playlist's date is when it was made, not when it was added.
    assert library.order_label(rows["playlists"].orders[1]) == (
        "fecha de creación: recientes primero"
    )
    assert library.order_label(None) == "orden original"


def test_my_playlists_ask_tidal_for_the_order(monkeypatch):
    monkeypatch.setattr(library.tidalapi, "Playlist", FakePlaylistPrototype)
    library.forget()
    session = FakeSession(playlists=3)
    row = next(row for row in library.root(session) if row.key == "playlists")

    key, loader = row.sort(library.Order("name", descending=True, created=True))
    loader()

    assert key == "playlists|name-desc"
    assert session.request.calls[-1][2] == {
        "limit": PAGE,
        "offset": 0,
        "order": "NAME",
        "orderDirection": "DESC",
    }
    library.forget()


def test_a_level_tidal_cannot_sort_is_sorted_here_with_more_last():
    """Inside an album or an artist TIDAL takes no order. The rows are sorted
    here, into a new list: the cached level stays as TIDAL gave it."""
    titles = ["Sober", "Aenema", "Schism"]
    albums = ["Undertow", "Aenima", "Lateralus"]
    rows = [
        Row(label=title, entry=Entry(id=i, title=title, artist="TOOL", album=album))
        for i, (title, album) in enumerate(zip(titles, albums, strict=True))
    ]
    rows.append(Row(label="más…", more=list))

    by_name = library._in_order(rows, library.Order("name"))
    assert [row.label for row in by_name] == ["Aenema", "Schism", "Sober", "más…"]
    by_album = library._in_order(rows, library.Order("album", descending=True))
    assert [row.label for row in by_album] == ["Sober", "Schism", "Aenema", "más…"]
    assert [row.label for row in rows][:3] == titles
