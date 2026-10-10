"""Browsing TIDAL: search, the playlist listing, favourites, the radio, the
album year, TIDAL's own orders, the artist and the album of a track, and
«Lofi sin copyright»."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import FakeTrack
from library_fakes import FakePlaylistPrototype, FakeSession, track_row
from tidalapi.types import ItemOrder, OrderDirection

from tidalamp import levels, library
from tidalamp.levels import PAGE, Row
from tidalamp.library import search_rows
from tidalamp.queue import Entry


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


def kinds(row: Row) -> set[str]:
    return {order.by for order in row.orders if order is not None}


def test_favourite_tracks_are_sorted_by_tidal_four_ways_both_ways_round(monkeypatch):
    """TIDAL sorts the whole collection; a sort over the page already loaded
    would order 100 tracks of 766 and call it the library."""
    monkeypatch.setattr(levels, "_CHOSEN", {})
    levels.forget()
    session = FakeSession(total=3)
    tracks = next(row for row in library.root(session) if row.key == "fav:tracks")

    assert tracks.orders[0] is None
    assert kinds(tracks) == {"date", "name", "artist", "album"}
    assert len(tracks.orders) == 9
    # Dates newest first, names A to Z first.
    assert tracks.orders[1] == levels.Order("date", descending=True)
    assert tracks.orders[3] == levels.Order("name")

    key, loader = tracks.sort(levels.Order("name"))
    assert key == "fav:tracks|name-asc"
    loader()
    assert session.favorites.orders[-1] == (ItemOrder.Name, OrderDirection.Ascending)
    assert tracks.sort(None)[0] == "fav:tracks"
    levels.forget()


def test_each_section_offers_only_the_orders_that_mean_something():
    rows = {row.key: row for row in library.root(FakeSession())}
    assert kinds(rows["fav:albums"]) == {"date", "name", "artist", "release"}
    assert kinds(rows["fav:artists"]) == {"date", "name"}
    assert kinds(rows["playlists"]) == {"date", "name"}
    # A playlist's date is when it was made, not when it was added.
    assert levels.order_label(rows["playlists"].orders[1]) == (
        "fecha de creación: recientes primero"
    )
    assert levels.order_label(None) == "orden original"


def test_my_playlists_ask_tidal_for_the_order(monkeypatch):
    monkeypatch.setattr(library.tidalapi, "Playlist", FakePlaylistPrototype)
    levels.forget()
    session = FakeSession(playlists=3)
    row = next(row for row in library.root(session) if row.key == "playlists")

    key, loader = row.sort(levels.Order("name", descending=True, created=True))
    loader()

    assert key == "playlists|name-desc"
    assert session.request.calls[-1][2] == {
        "limit": PAGE,
        "offset": 0,
        "order": "NAME",
        "orderDirection": "DESC",
    }
    levels.forget()


def test_unfavouriting_forgets_the_favourites_level_in_every_order(monkeypatch):
    monkeypatch.setattr(
        levels,
        "_LEVELS",
        {"fav:tracks": [], "fav:tracks|name-asc": [], "fav:albums": []},
    )
    session, favorites = writer_session()

    library.favourite(session, track_row("Schism"), add=False)

    assert favorites.calls == [("remove_track", "1")]
    assert set(levels._LEVELS) == {"fav:albums"}


def a_disc(ident: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=ident,
        name=name,
        year=2001,
        artist=SimpleNamespace(name="TOOL"),
        num_tracks=2,
        tracks=lambda limit=50, offset=0, **order: [
            FakeTrack(ident * 10 + i) for i in range(2)
        ][offset : offset + limit],
    )


def an_artist(albums, singles, other) -> SimpleNamespace:
    def listing(items):
        return lambda limit=None, offset=0: items[offset : offset + (limit or 50)]

    return SimpleNamespace(
        id=7,
        name="TOOL",
        get_top_tracks=listing([FakeTrack(1), FakeTrack(2)]),
        get_albums=listing(albums),
        get_ep_singles=listing(singles),
        get_other=listing(other),
    )


def test_an_artist_opens_to_its_discs_and_leaves_out_an_empty_section():
    """It used to open to its top tracks and nothing else: no way to reach a
    record from the artist. An artist with no «other» discs shows three
    sections, not four with one of them empty."""
    artist = an_artist(
        albums=[a_disc(1, "Lateralus"), a_disc(2, "Ænima")],
        singles=[a_disc(3, "Schism")],
        other=[],
    )
    row = library._artist_rows([artist])[0]
    assert row.key == "artist:7"  # what favourites read the artist's id from

    sections = row.loader()
    assert [s.label for s in sections] == ["Populares", "Álbumes", "EPs y sencillos"]

    albums = sections[1].loader()
    assert [a.label for a in albums] == ["TOOL - Lateralus", "TOOL - Ænima"]
    assert [r.entry.id for r in albums[0].loader() if r.entry] == [10, 11]

    # The popular tracks can still be sorted here, since TIDAL does not.
    assert sections[0].sort is not None


def test_m_on_an_artist_still_plays_its_popular_tracks():
    """The discs are there to be opened; `m` and `a` keep playing what they
    played when the popular tracks were the whole level."""
    artist = an_artist(albums=[a_disc(1, "Lateralus")], singles=[], other=[])
    row = library._artist_rows([artist])[0]

    assert row.tracks is not None
    assert [e.id for e in levels.all_entries(row.tracks)] == [1, 2]


def a_linked_session(asked: list[str]) -> SimpleNamespace:
    """A session that knows track 5 is TOOL's, on Lateralus."""
    track = FakeTrack(5)
    track.artist.id = 7
    track.album = SimpleNamespace(id=1)

    def record(what, value):
        def call(ident):
            asked.append(f"{what}:{ident}")
            return value

        return call

    return SimpleNamespace(
        track=record("track", track),
        artist=record("artist", an_artist(albums=[], singles=[], other=[])),
        album=record("album", a_disc(1, "Lateralus")),
    )


def test_go_to_the_artist_asks_for_it_by_the_id_the_entry_carries():
    asked: list[str] = []
    entry = Entry(id=5, title="Schism", artist="TOOL", artist_id=7)

    row = library.go_to(a_linked_session(asked), entry, "artist")

    assert asked == ["artist:7"]
    assert row.key == "artist:7" and row.label == "TOOL"


def test_go_to_from_a_queue_saved_before_the_artist_id_resolves_the_track():
    """A queue saved before `artist_id` existed restores without it. The
    track knows its artist, so it is asked once, and the id is kept."""
    asked: list[str] = []
    entry = Entry.from_dict({"id": 5, "title": "Schism", "artist": "TOOL"})
    assert entry.artist_id == 0

    row = library.go_to(a_linked_session(asked), entry, "artist")

    assert asked == ["track:5", "artist:7"]
    assert entry.artist_id == 7
    assert row.key == "artist:7"


def test_go_to_the_album_opens_to_its_tracks():
    asked: list[str] = []
    entry = Entry.from_dict({"id": 5, "title": "Schism", "artist": "TOOL"})

    row = library.go_to(a_linked_session(asked), entry, "album")

    assert asked == ["track:5", "album:1"]
    assert row.key == "album:1"
    assert [r.entry.id for r in row.loader() if r.entry] == [10, 11]


def test_a_track_that_says_nothing_of_its_artist_explains_itself():
    track = FakeTrack(5)
    track.artist = None
    session = SimpleNamespace(track=lambda ident: track)
    entry = Entry(id=5, title="x", artist="")

    with pytest.raises(library.NotLinked):
        library.go_to(session, entry, "artist")


def test_the_artist_id_survives_a_save_and_a_restore():
    entry = Entry(id=5, title="Schism", artist="TOOL", artist_id=7)
    assert Entry.from_dict(entry.to_dict()).artist_id == 7


def test_the_artists_of_a_track_come_main_first_and_once_each():
    """For «ir al artista» with several artists: the list to pick from. The
    main one leads, and TIDAL lists it again inside `artists`."""
    track = FakeTrack(5)
    track.artist = SimpleNamespace(id=7, name="TOOL")
    track.artists = [
        SimpleNamespace(id=7, name="TOOL"),
        SimpleNamespace(id=9, name="Tori Amos"),
    ]
    entry = Entry(id=5, title="Schism", artist="TOOL", _track=track)

    assert library.track_artists(object(), entry) == [(7, "TOOL"), (9, "Tori Amos")]
    assert entry.artist_id == 7


def test_a_track_with_no_artist_ids_cannot_list_them():
    track = FakeTrack(5)
    track.artist = None
    entry = Entry(id=5, title="x", artist="", _track=track)

    with pytest.raises(library.NotLinked):
        library.track_artists(object(), entry)


def test_go_to_the_artist_that_was_picked_asks_for_that_one():
    asked: list[str] = []
    entry = Entry(id=5, title="Schism", artist="TOOL", artist_id=7)

    library.go_to(a_linked_session(asked), entry, "artist", artist_id=9)

    assert asked == ["artist:9"]


# ------------------------------------------- «Lofi sin copyright»: a station,
# the only level in the browser that is not TIDAL's


def free_tracks(n: int = 3):
    from tidalamp.music import Track

    return [
        Track(
            url=f"https://archive.org/download/x/{i}.mp3",
            title=f"pista {i}",
            artist=f"artista {i}",
            album="Tame The Beast",
            licence="CC BY",
            duration=174,
            track_num=i,
            codec="MP3",
            art_url="https://archive.org/services/img/x",
        )
        for i in range(1, n + 1)
    ]


def fake_archive(monkeypatch, albums=None, songs=None):
    """Stand in for the Internet Archive, station and catalogue both.

    Both, always: a test that patched only one of them went out to the real
    network for the other, which is how the first draft of these passed
    against live data without anybody noticing.
    """
    from tidalamp.archive import Album

    records = (
        albums
        if albums is not None
        else [
            Album("x", "Tame The Beast", "Lofi Lion", "CC BY", 2021),
            Album("y", "Field Experience", "", "CC0", 2012),
        ]
    )
    picked = free_tracks() if songs is None else songs
    monkeypatch.setattr(library.archive, "albums", lambda offset=0, limit=100: records)
    monkeypatch.setattr(library.archive, "tracks", lambda album: picked)
    monkeypatch.setattr(library.freemusic, "station", lambda day=None: picked)
    # No client id, so the catalogue row is there to test: with Jamendo it
    # would be a browse of some other library (`_free_level`).
    monkeypatch.setattr(library.jamendo.config, "JAMENDO_ID", "")
    return records, picked


def free_level(monkeypatch, session=None) -> list[Row]:
    levels.forget()
    rows = library.root(session or FakeSession())
    return next(r for r in rows if r.key == "free").loader()


def test_the_free_section_is_the_last_row_of_the_root():
    """Last on purpose. The four levels above it are what the account holds
    and the tests that count on their positions must keep counting right."""
    rows = library.root(FakeSession())
    assert rows[-1].key == "free"
    assert rows[-1].label == "Lofi sin copyright"
    # Experimental, and saying so: the «lofi hip hop radio» sound is a
    # label's catalogue and none of it is Creative Commons, so the row has to
    # be honest about being the closest a free one gets.
    assert rows[-1].detail == "experimental · la selección de hoy"
    assert [r.key for r in rows[:4]] == [
        "playlists",
        "fav:tracks",
        "fav:albums",
        "fav:artists",
    ]


def test_the_section_opens_straight_onto_music(monkeypatch):
    """A station, not a catalogue. Opening it used to land on a list of
    strangers' records to audition one at a time; it now lands on the day."""
    fake_archive(monkeypatch)
    rows = free_level(monkeypatch)
    assert [row.label for row in rows[:3]] == [
        "artista 1 - pista 1",
        "artista 2 - pista 2",
        "artista 3 - pista 3",
    ]
    assert all(row.is_playable for row in rows[:-1])


def test_playing_the_whole_row_plays_the_day_and_not_the_catalogue_row(monkeypatch):
    """`a` on «Lofi sin copyright» is the station's play button."""
    fake_archive(monkeypatch)
    levels.forget()
    row = next(r for r in library.root(FakeSession()) if r.key == "free")
    assert row.loader is not None
    entries = levels.all_entries(row.loader)
    assert [entry.title for entry in entries] == ["pista 1", "pista 2", "pista 3"]


def test_the_catalogue_is_the_last_row_and_opens_to_the_records(monkeypatch):
    """Where the «más…» of every other level sits: there for whoever wants to
    dig, out of the way of whoever wants to listen."""
    fake_archive(monkeypatch)
    last = free_level(monkeypatch)[-1]
    assert last.label == "Todos los discos"
    assert not last.is_playable
    assert last.loader is not None
    records = last.loader()
    assert [row.label for row in records] == [
        "Lofi Lion - Tame The Beast",
        "Field Experience",
    ]


def test_the_catalogue_has_no_more_row_because_it_is_one_level(monkeypatch):
    """The Archive's count includes what the junk filter then drops, so a
    «más…» built from it would lead to nothing."""
    fake_archive(monkeypatch)
    records = free_level(monkeypatch)[-1].loader()
    assert all(row.more is None for row in records)


def test_a_free_record_shows_its_licence_where_an_album_shows_its_year(monkeypatch):
    fake_archive(monkeypatch)
    records = free_level(monkeypatch)[-1].loader()
    assert records[0].detail == "2021 · CC BY"
    # No creator: the licence carries the byline, so the tile is not blank.
    assert records[1].byline == "CC0"


def test_nothing_in_the_section_is_tidals(monkeypatch):
    """What the menus read to decide which verbs to offer."""
    fake_archive(monkeypatch)
    rows = free_level(monkeypatch)
    assert not rows[0].is_tidal, "la pista del día"
    assert not rows[-1].is_tidal, "la fila del catálogo"
    assert not rows[-1].loader()[0].is_tidal, "un disco del catálogo"
    assert all(row.is_tidal for row in library.root(FakeSession())[:-1])


def test_opening_a_record_from_the_catalogue_gives_playable_rows(monkeypatch):
    fake_archive(monkeypatch)
    tracks = free_level(monkeypatch)[-1].loader()[0].loader()
    assert [row.label for row in tracks] == [
        "artista 1 - pista 1",
        "artista 2 - pista 2",
        "artista 3 - pista 3",
    ]
    entry = tracks[0].entry
    assert entry is not None and not entry.is_tidal
    assert entry.url.endswith("/1.mp3")
    assert entry.licence == "CC BY"


def test_a_free_row_cannot_be_favourited(monkeypatch):
    """Favourites belong to a TIDAL account and nothing here is in one. The
    message has to say that rather than «eso no es una pista»."""
    fake_archive(monkeypatch)
    record = free_level(monkeypatch)[-1].loader()[0]
    with pytest.raises(library.NotFavouritable, match="no está en TIDAL"):
        library.favourite(FakeSession(), record)


def test_a_free_track_cannot_be_favourited_either(monkeypatch):
    fake_archive(monkeypatch)
    with pytest.raises(library.NotFavouritable, match="no está en TIDAL"):
        library.favourite(FakeSession(), free_level(monkeypatch)[0])


def test_under_a_jamendo_day_there_is_no_archive_catalogue(monkeypatch):
    """The catalogue is the Internet Archive's, so it only belongs under a
    day the Archive drew. Under a Jamendo day it would be a browse of some
    other library, with other records and other artists."""
    fake_archive(monkeypatch)
    monkeypatch.setattr(library.jamendo.config, "JAMENDO_ID", "testing")
    rows = free_level(monkeypatch)
    assert all(row.is_playable for row in rows), "sólo pistas, sin fila de catálogo"
    assert not any(row.label == "Todos los discos" for row in rows)
