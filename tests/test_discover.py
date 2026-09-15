"""Descubrir, the covers the grid draws, and the changes only your own
playlists take: renaming, describing, deleting and moving a track."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import tidalapi

from tidalamp import library
from tidalamp.queue import Entry


def _url(kind: str, ident: object, px: int) -> str:
    return f"https://resources.tidal.com/images/{kind}/{ident}/{px}x{px}.jpg"


class FakeAlbum(tidalapi.Album):
    year = 1997  # A property on the real one, read off a release date.

    def __init__(self, ident: int, name: str = "Around the Fur") -> None:
        self.id = ident
        self.name = name
        self.artist = SimpleNamespace(name="Deftones")

    def image(self, dimensions=320, default=None):
        return _url("album", self.id, dimensions)


class CoverlessAlbum(FakeAlbum):
    def image(self, dimensions=320, default=None):
        # What tidalapi does for an album that carries no cover id.
        raise AttributeError("no cover")


class FakeTrack(tidalapi.Track):
    def __init__(self, ident: int, name: str = "") -> None:
        self.id = ident
        self.name = name or f"pista {ident}"
        self.artist = SimpleNamespace(name="Deftones", id=7)
        self.album = None
        self.duration = 200


class FakeVideo(tidalapi.media.Video):
    def __init__(self) -> None:
        self.id = 99
        self.name = "un vídeo"


class FakeMixV2(tidalapi.mix.MixV2):
    """What the pages carry: a mix that says what it is, not what it holds.

    With no `mix_type`, as the ones on the real home page come: seen there
    on 2026-09-14 in «Your listening history», «Personal radio stations»
    and «Custom mixes», which the first cut of Descubrir left out whole.
    """

    mix_type = None

    def __init__(self, ident: str) -> None:
        self.id = ident
        self.title = "Discovery"
        self.sub_title = "para ti"

    def image(self, dimensions=320):
        return _url("mix", self.id, dimensions)


class FakeLink:
    def __init__(self, title: str, api_path: str) -> None:
        self.title = title
        self.api_path = api_path


def _page(*categories):
    return SimpleNamespace(categories=list(categories))


def _category(title, *items):
    return SimpleNamespace(title=title, items=list(items))


# -------------------------------------------------------------------- pages


def test_a_page_opens_to_its_categories_and_drops_what_cannot_play():
    page = _page(
        _category("Recently played", FakeAlbum(1), FakeTrack(2), FakeMixV2("m1")),
        _category("Videos", FakeVideo(), None),
        _category("", FakeLink("Rock", "pages/genre_rock")),
    )
    rows = library._page_level(None, lambda: page)()

    assert [row.label for row in rows] == ["Recently played", "Más"]
    assert rows[0].detail == "3 elementos"


def test_a_category_holds_rows_of_every_kind_in_its_own_order():
    page = _page(
        _category("Mixed", FakeAlbum(1), FakeTrack(2), FakeMixV2("m1"), FakeVideo())
    )
    inside = library._page_level(None, lambda: page)()[0].loader()

    assert [row.key or "track" for row in inside] == ["album:1", "track", "mix:m1"]
    assert inside[1].entry is not None and inside[1].entry.id == 2
    # The album and the mix bring their covers for the grid; the track none.
    assert inside[0].art == _url("album", 1, 160)
    assert inside[2].art == _url("mix", "m1", 320)
    assert inside[1].art == ""


def test_a_mix_from_a_page_is_asked_for_in_full_when_opened():
    asked: list[str] = []

    def mix(ident):
        asked.append(ident)
        return SimpleNamespace(items=lambda: [FakeTrack(5), FakeVideo()])

    session = SimpleNamespace(mix=mix)
    row = library._mix_rows([FakeMixV2("m1")], session)[0]

    assert asked == []  # Listing it costs nothing.
    assert [r.entry.id for r in row.loader() if r.entry] == [5]
    assert asked == ["m1"]


def test_a_link_opens_the_page_it_points_to(monkeypatch):
    opened: list[str] = []

    def page_at(session, path):
        opened.append(path)
        return _page(_category("Rock albums", FakeAlbum(3)))

    monkeypatch.setattr(library, "_page_at", page_at)
    page = _page(_category("Genres", FakeLink("Rock", "pages/genre_rock")))
    link = library._page_level(None, lambda: page)()[0].loader()[0]

    assert (link.label, link.detail) == ("Rock", "página")
    assert [row.label for row in link.loader()] == ["Rock albums"]
    assert opened == ["pages/genre_rock"]


def test_discover_is_the_last_row_of_the_library_and_lists_three_pages():
    session = SimpleNamespace(
        # `root` hands the counters to the levels it builds, uncalled.
        user=SimpleNamespace(
            favorites=SimpleNamespace(
                get_tracks_count=None, get_albums_count=None, get_artists_count=None
            )
        ),
        home=lambda: _page(),
        for_you=lambda: _page(),
        explore=lambda: _page(),
    )
    rows = library.root(session)

    assert rows[-1].label == "Descubrir"
    assert [row.label for row in rows[-1].loader()] == ["Inicio", "Para ti", "Explorar"]


def test_an_album_tile_says_the_name_first_and_the_artist_under_it():
    """The label is «artist - name», and a tile sixteen cells wide kept only
    the artist of it: seen on the first real grid, «Tiro De Gracia -»."""
    row = library._album_rows([FakeAlbum(1, "Around the Fur")])[0]
    assert row.label == "Deftones - Around the Fur"
    assert (row.caption, row.byline, row.detail) == ("Around the Fur", "Deftones", "1997")


def test_an_album_without_a_cover_is_still_a_row_with_no_art():
    row = library._album_rows([CoverlessAlbum(4)])[0]
    assert row.key == "album:4" and row.art == ""


# ---------------------------------------------------------------- playlists


class FakePlaylist:
    """A `UserPlaylist`, as far as the writes need one."""

    _base_url = "playlists/%s"

    def __init__(self, ids: list[int], *, land_off_by_one: bool = False) -> None:
        self.id = "p1"
        self.name = "Viaje"
        self.description = "para el coche"
        self.ids = list(ids)
        self.num_tracks = len(ids)
        self.land_off_by_one = land_off_by_one
        self.sent: list[tuple] = []
        self.deleted = 0
        self.request = SimpleNamespace(request=self._request)

    def _request(self, method, path, data=None):
        self.sent.append((method, path, data))
        return SimpleNamespace(ok=True)

    def tracks(self, limit=100, offset=0):
        return [SimpleNamespace(id=i) for i in self.ids[offset : offset + limit]]

    def remove_by_index(self, index):  # Only a UserPlaylist has it.
        raise AssertionError("not here")

    def move_by_index(self, index, position):
        track = self.ids.pop(index)
        # TIDAL's `toIndex` is where the track ends up.
        self.ids.insert(position - 1 if self.land_off_by_one else position, track)
        return True

    def delete(self):
        self.deleted += 1
        return True


def _session(playlist):
    return SimpleNamespace(playlist=lambda ident: playlist)


def test_only_the_rows_of_my_playlists_can_be_edited():
    listing = [SimpleNamespace(id="p1", name="Viaje", num_tracks=3, description="")]
    assert library._own_playlist_rows(listing)[0].editable
    assert not library._playlist_rows(listing)[0].editable


def test_renaming_keeps_the_description_it_had():
    playlist = FakePlaylist([1, 2])
    old = library.edit_playlist(_session(playlist), "p1", title="Ruta")

    assert old == "Viaje"
    assert playlist.sent == [
        ("POST", "playlists/p1", {"title": "Ruta", "description": "para el coche"})
    ]


def test_an_empty_description_clears_it_instead_of_keeping_the_old_one():
    playlist = FakePlaylist([1, 2])
    library.edit_playlist(_session(playlist), "p1", description="")

    assert playlist.sent[-1][2] == {"title": "Viaje", "description": ""}


def test_someone_elses_playlist_is_not_written_to():
    theirs = SimpleNamespace(name="Ajena")
    with pytest.raises(library.PlaylistNotWritable):
        library.edit_playlist(_session(theirs), "p9", title="Mía")
    with pytest.raises(library.PlaylistNotWritable):
        library.delete_playlist(_session(theirs), "p9")


def test_deleting_a_playlist_forgets_the_listing_and_the_playlist():
    playlist = FakePlaylist([1])
    library._LEVELS.update(
        {"playlists": [], "playlists|name-asc": [], "playlist:p1": [], "other": []}
    )

    assert library.delete_playlist(_session(playlist), "p1") == "Viaje"
    assert playlist.deleted == 1
    assert set(library._LEVELS) == {"other"}


def test_a_track_moves_one_place_down_and_the_move_is_checked():
    playlist = FakePlaylist([10, 11, 12])
    entry = Entry(id=11, title="b", artist="x")

    library.move_in_playlist(_session(playlist), "p1", entry, 1, 1)

    assert playlist.ids == [10, 12, 11]


def test_a_move_that_lands_elsewhere_says_so():
    playlist = FakePlaylist([10, 11, 12, 13], land_off_by_one=True)
    entry = Entry(id=10, title="a", artist="x")

    with pytest.raises(library.MoveNotConfirmed):
        library.move_in_playlist(_session(playlist), "p1", entry, 0, 2)


def test_a_track_that_is_no_longer_there_is_not_moved():
    playlist = FakePlaylist([10, 12])
    entry = Entry(id=11, title="b", artist="x")

    with pytest.raises(library.TrackNotInPlaylist):
        library.move_in_playlist(_session(playlist), "p1", entry, 1, 1)
    assert playlist.ids == [10, 12]


def test_the_first_track_does_not_move_up():
    playlist = FakePlaylist([10, 11])
    library.move_in_playlist(
        _session(playlist), "p1", Entry(id=10, title="a", artist="x"), 0, -1
    )
    assert playlist.ids == [10, 11]
