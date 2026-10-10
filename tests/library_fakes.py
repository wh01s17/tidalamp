"""A TIDAL session that answers from memory, for the tests of the library,
its levels and its playlists."""

from __future__ import annotations

from types import SimpleNamespace

from conftest import FakeTrack

from tidalamp import library
from tidalamp.levels import Row
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


def track_row(title: str, artist: str = "TOOL", album: str = "") -> Row:
    entry = Entry(id=1, title=title, artist=artist, album=album)
    return Row(label=entry.label, detail="4:00", entry=entry)
