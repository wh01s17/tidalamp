"""Browsing the user's TIDAL library.

Everything here returns ``Row`` lists. A row either plays (it carries an
``Entry``), drills down (it carries a ``loader`` that fetches the next level),
or extends the level it lives in (it carries ``more``). Loaders are called
from a worker thread, never on the UI loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import tidalapi

from .net import with_retries
from .queue import Entry

# TIDAL paginates. We ask for one page at a time and hang a "más…" row off the
# end when the page came back full, so a 500-track playlist is reachable
# without pulling it whole on open.
PAGE = 100

# Levels already fetched, so walking back into one is instant. In memory only:
# it dies with the process, which is the right lifetime for a view of a library
# the user can change from another device. `R` in the browser forces a refetch.
_LEVELS: dict[str, list["Row"]] = {}


def cached(key: str, loader: Callable[[], list["Row"]]) -> Callable[[], list["Row"]]:
    """Memoise one level's rows under ``key``.

    The cached list is handed out as-is, not copied, on purpose: loading
    another page mutates the level in place (see ``RowList.extend_at``), so the
    pages the user already pulled are still there when they come back."""

    def load() -> list["Row"]:
        rows = _LEVELS.get(key)
        if rows is None:
            rows = loader()
            _LEVELS[key] = rows
        return rows

    return load


def forget(key: str = "") -> None:
    """Drop one cached level, or all of them when ``key`` is empty."""
    if key:
        _LEVELS.pop(key, None)
    else:
        _LEVELS.clear()


@dataclass(slots=True)
class Row:
    """One line in the browser."""

    label: str
    detail: str = ""
    entry: Entry | None = None
    loader: Callable[[], list["Row"]] | None = None
    # Identifies the level ``loader`` returns, for the cache above and for the
    # browser's reload key. Empty means "do not cache this".
    key: str = ""
    # Fetches the next page and gets appended to *this* level in place,
    # replacing the row itself.
    more: Callable[[], list["Row"]] | None = None

    @property
    def is_playable(self) -> bool:
        return self.entry is not None


def _paged(
    fetch: Callable[[int, int], list],
    render: Callable[[list], list[Row]],
) -> Callable[[], list[Row]]:
    """Build a loader that returns one page plus a "más…" row when there is
    likely another one. A page that comes back short is the end of the list."""

    def level(offset: int = 0) -> list[Row]:
        items = with_retries(lambda: fetch(offset, PAGE))
        rows = render(items)
        if len(items) >= PAGE:
            rows.append(
                Row(
                    label="más…",
                    detail=f"siguientes {PAGE}",
                    more=lambda: level(offset + PAGE),
                )
            )
        return rows

    return level


def _tracks_to_rows(tracks: Iterable[tidalapi.Track]) -> list[Row]:
    rows = []
    for track in tracks:
        entry = Entry.from_track(track)
        rows.append(Row(label=entry.label, detail=entry.length, entry=entry))
    return rows


def _playlist_rows(playlists: Iterable[tidalapi.Playlist]) -> list[Row]:
    rows = []
    for playlist in playlists:
        count = playlist.num_tracks or 0
        rows.append(
            Row(
                label=playlist.name,
                detail=f"{count} pistas",
                key=f"playlist:{playlist.id}",
                loader=cached(
                    f"playlist:{playlist.id}",
                    _paged(
                        lambda offset, limit, p=playlist: p.tracks(
                            limit=limit, offset=offset
                        ),
                        _tracks_to_rows,
                    ),
                ),
            )
        )
    return rows


def _playlists_level(session: tidalapi.Session) -> Callable[[], list[Row]]:
    """The playlists the user created, one page per request.

    ``session.user.playlists()`` looks like a single call and is not: parsing
    each item runs it through ``Playlist.factory()``, which for a playlist you
    own builds a ``UserPlaylist``, and *that* constructor fetches the playlist
    again just to read its ETag. Measured on a real account: 110 playlists,
    111 HTTP requests, twenty seconds. We never edit playlists, so we parse the
    listing ourselves and skip the factory — one request, a quarter of a
    second — and paginate it like every other level.
    """

    def fetch(offset: int, limit: int) -> list[tidalapi.Playlist]:
        response = with_retries(
            lambda: session.request.request(
                "GET",
                f"users/{session.user.id}/playlists",
                params={"limit": limit, "offset": offset},
            )
        )
        # parse() fills a Playlist from the listing without asking the API for
        # anything; it is factory() that costs a request per row.
        prototype = tidalapi.Playlist(session, None)
        return [prototype.parse(item) for item in response.json().get("items", [])]

    return _paged(fetch, _playlist_rows)


def _album_rows(albums: Iterable[tidalapi.Album]) -> list[Row]:
    rows = []
    for album in albums:
        artist = getattr(getattr(album, "artist", None), "name", "") or ""
        rows.append(
            Row(
                label=f"{artist} - {album.name}" if artist else album.name,
                detail=str(getattr(album, "year", "") or ""),
                key=f"album:{album.id}",
                loader=cached(
                    f"album:{album.id}",
                    _paged(
                        lambda offset, limit, a=album: a.tracks(
                            limit=limit, offset=offset
                        ),
                        _tracks_to_rows,
                    ),
                ),
            )
        )
    return rows


def _artist_rows(artists: Iterable[tidalapi.Artist]) -> list[Row]:
    rows = []
    for artist in artists:
        rows.append(
            Row(
                label=artist.name,
                detail="artista",
                key=f"artist:{artist.id}",
                loader=cached(
                    f"artist:{artist.id}",
                    _paged(
                        lambda offset, limit, a=artist: a.get_top_tracks(
                            limit=limit, offset=offset
                        ),
                        _tracks_to_rows,
                    ),
                ),
            )
        )
    return rows


def root(session: tidalapi.Session) -> list[Row]:
    """The top level of the browser."""
    favorites = session.user.favorites
    return [
        Row(
            "Mis playlists",
            "",
            key="playlists",
            loader=cached("playlists", _playlists_level(session)),
        ),
        Row(
            "Pistas favoritas",
            "",
            key="fav:tracks",
            loader=cached(
                "fav:tracks",
                _paged(
                    lambda offset, limit: favorites.tracks(limit=limit, offset=offset),
                    _tracks_to_rows,
                ),
            ),
        ),
        Row(
            "Álbumes favoritos",
            "",
            key="fav:albums",
            loader=cached(
                "fav:albums",
                _paged(
                    lambda offset, limit: favorites.albums(limit=limit, offset=offset),
                    _album_rows,
                ),
            ),
        ),
        Row(
            "Artistas favoritos",
            "",
            key="fav:artists",
            loader=cached(
                "fav:artists",
                _paged(
                    lambda offset, limit: favorites.artists(limit=limit, offset=offset),
                    _artist_rows,
                ),
            ),
        ),
    ]


def search_rows(session: tidalapi.Session, query: str) -> list[Row]:
    """Search results, shaped like any other browser level."""

    def fetch(offset: int, limit: int) -> list:
        results = with_retries(
            lambda: session.search(
                query, models=[tidalapi.Track], limit=limit, offset=offset
            )
        )
        return results.get("tracks", [])

    return _paged(fetch, _tracks_to_rows)()
