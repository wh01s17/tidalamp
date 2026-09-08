"""Browsing the user's TIDAL library.

Everything here returns ``Row`` lists. A row either plays (it carries an
``Entry``), drills down (it carries a ``loader`` that fetches the next level),
or extends the level it lives in (it carries ``more``). Loaders are called
from a worker thread, never on the UI loop.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from typing import Any, cast

import tidalapi

from .net import with_retries
from .queue import Entry

# TIDAL paginates. We ask for one page at a time and hang a "más…" row off the
# end when the page came back full, so a 500-track playlist is reachable
# without pulling it whole on open.
PAGE = 100


def _me(session: tidalapi.Session) -> tidalapi.user.LoggedInUser:
    """The logged-in user.

    ``session.user`` is typed as a union that includes ``None``, because a
    tidalapi session need not be logged in. Ours always is: ``load_session``
    refuses to return one that is not.
    """
    return cast("tidalapi.user.LoggedInUser", session.user)


def _count_of(item: object) -> int | None:
    """How many tracks a playlist or an album holds, when it says so."""
    count = getattr(item, "num_tracks", None)
    return int(count) if count is not None else None


def _page_of(item: Any, offset: int, limit: int) -> list:
    """One page of the tracks inside a playlist or an album."""
    return item.tracks(limit=limit, offset=offset)


def _top_tracks_of(artist: Any, offset: int, limit: int) -> list:
    return artist.get_top_tracks(limit=limit, offset=offset)


# Levels already fetched, so walking back into one is instant. In memory only:
# it dies with the process, which is the right lifetime for a view of a library
# the user can change from another device. `R` in the browser forces a refetch.
_LEVELS: dict[str, list[Row]] = {}


def cached(key: str, loader: Callable[[], list[Row]]) -> Callable[[], list[Row]]:
    """Memoise one level's rows under ``key``.

    The cached list is handed out as-is, not copied, on purpose: loading
    another page mutates the level in place (see ``RowList.extend_at``), so the
    pages the user already pulled are still there when they come back."""

    def load() -> list[Row]:
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
    loader: Callable[[], list[Row]] | None = None
    # Identifies the level ``loader`` returns, for the cache above and for the
    # browser's reload key. Empty means "do not cache this".
    key: str = ""
    # Fetches the next page and gets appended to *this* level in place,
    # replacing the row itself.
    more: Callable[[], list[Row]] | None = None

    @property
    def is_playable(self) -> bool:
        return self.entry is not None


def _paged(
    fetch: Callable[[int, int], list],
    render: Callable[[list], list[Row]],
    count: Callable[[], int | None] | None = None,
) -> Callable[[], list[Row]]:
    """Build a loader that returns one page plus a "más…" row when there is more.

    **A short page is not the end of the list.** TIDAL applies the limit and
    *then* filters the window, so asking for 100 favourite tracks came back
    with 90 — out of 766. Reading that as the end meant the user could never
    see past the first page: 90 tracks of 766, 100 albums of 539.

    So when the level can tell us how many items it holds, ``count`` decides,
    and the offset advances by the page size because TIDAL counts offsets over
    the unfiltered collection. Where there is no count — an artist's top
    tracks, a search — the old rule stands: a full page offers another one, an
    exact multiple offers one empty page, which is better than lying about the
    total.
    """

    def level(offset: int = 0, total: int | None = None) -> list[Row]:
        if total is None and count is not None:
            total = with_retries(count)
        items = with_retries(lambda: fetch(offset, PAGE))
        rows = render(items)
        remaining = None if total is None else total - (offset + PAGE)
        more = remaining > 0 if remaining is not None else len(items) >= PAGE
        if more:
            rows.append(
                Row(
                    label="más…",
                    detail=(
                        f"siguientes {PAGE} de {total}"
                        if total is not None
                        else f"siguientes {PAGE}"
                    ),
                    more=lambda: level(offset + PAGE, total),
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
                label=playlist.name or "",
                detail=f"{count} pistas",
                key=f"playlist:{playlist.id}",
                loader=cached(
                    f"playlist:{playlist.id}",
                    _paged(
                        partial(_page_of, playlist),
                        _tracks_to_rows,
                        count=partial(_count_of, playlist),
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
                f"users/{_me(session).id}/playlists",
                params={"limit": limit, "offset": offset},
            )
        )
        # parse() fills a Playlist from the listing without asking the API for
        # anything; it is factory() that costs a request per row.
        prototype = tidalapi.Playlist(session, None)
        return [prototype.parse(item) for item in response.json().get("items", [])]

    def count() -> int | None:
        response = with_retries(
            lambda: session.request.request(
                "GET",
                f"users/{_me(session).id}/playlists",
                params={"limit": 1, "offset": 0},
            )
        )
        return response.json().get("totalNumberOfItems")

    return _paged(fetch, _playlist_rows, count=count)


def _album_rows(albums: Iterable[tidalapi.Album]) -> list[Row]:
    rows = []
    for album in albums:
        artist = getattr(getattr(album, "artist", None), "name", "") or ""
        rows.append(
            Row(
                label=f"{artist} - {album.name}" if artist else (album.name or ""),
                detail=str(getattr(album, "year", "") or ""),
                key=f"album:{album.id}",
                loader=cached(
                    f"album:{album.id}",
                    _paged(
                        partial(_page_of, album),
                        _tracks_to_rows,
                        count=partial(_count_of, album),
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
                label=artist.name or "",
                detail="artista",
                key=f"artist:{artist.id}",
                loader=cached(
                    f"artist:{artist.id}",
                    _paged(
                        partial(_top_tracks_of, artist),
                        _tracks_to_rows,
                    ),
                ),
            )
        )
    return rows


def root(session: tidalapi.Session) -> list[Row]:
    """The top level of the browser."""
    favorites = _me(session).favorites
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
                    count=favorites.get_tracks_count,
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
                    count=favorites.get_albums_count,
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
                    count=favorites.get_artists_count,
                ),
            ),
        ),
    ]


class NotFavouritable(RuntimeError):
    """Raised for a row that is not a thing TIDAL can favourite."""


def favourite(session: tidalapi.Session, row: Row, add: bool = True) -> str:
    """Add or remove one row from the user's TIDAL favourites.

    There is deliberately no toggle. TIDAL's API offers no "is this a
    favourite?" question, so a toggle would have to either pull the whole
    favourites list or guess — and guessing wrong deletes something the user
    wanted. Two explicit verbs never lie.

    Returns a label for the status line; raises :class:`NotFavouritable` for a
    row that is a heading, a "más…" or a level rather than a piece of music.
    """
    favorites = _me(session).favorites
    entry = row.entry
    if entry is not None:
        track = favorites.add_track if add else favorites.remove_track
        with_retries(lambda: track(str(entry.id)))
        return entry.label

    kind, _, ident = row.key.partition(":")
    calls: dict[str, tuple[Callable[[str], bool], Callable[[str], bool]]] = {
        "album": (favorites.add_album, favorites.remove_album),
        "artist": (favorites.add_artist, favorites.remove_artist),
        "playlist": (favorites.add_playlist, favorites.remove_playlist),
    }
    if kind not in calls or not ident:
        raise NotFavouritable("eso no es una pista, un álbum, un artista ni una playlist")
    call = calls[kind][0 if add else 1]
    with_retries(lambda: call(ident))
    return row.label


def _search_level(
    session: tidalapi.Session,
    query: str,
    model: type,
    bucket: str,
    render: Callable[[list], list[Row]],
) -> Callable[[], list[Row]]:
    """One category of search results, paginated like any other level."""

    def fetch(offset: int, limit: int) -> list:
        results = with_retries(
            lambda: session.search(query, models=[model], limit=limit, offset=offset)
        )
        # SearchResults is a TypedDict and we index it by a runtime key.
        return list(cast("dict[str, list]", results).get(bucket, []))

    return _paged(fetch, render)


def search_rows(session: tidalapi.Session, query: str) -> list[Row]:
    """Search results, shaped like any other browser level.

    Albums, artists and playlists hang off their own rows; the tracks come
    inline underneath. A track is what people are usually after, and asking
    for one more keystroke to reach it would be a step backwards — but only
    the tracks are fetched on open. Each category costs a request when, and
    only when, it is opened.
    """
    categories: list[tuple[str, type, str, Callable[[list], list[Row]]]] = [
        ("Álbumes", tidalapi.Album, "albums", _album_rows),
        ("Artistas", tidalapi.Artist, "artists", _artist_rows),
        ("Playlists", tidalapi.Playlist, "playlists", _playlist_rows),
    ]
    rows = [
        Row(
            f"{label} con «{query}»",
            "abrir",
            key=f"search:{bucket}:{query}",
            loader=cached(
                f"search:{bucket}:{query}",
                _search_level(session, query, model, bucket, render),
            ),
        )
        for label, model, bucket, render in categories
    ]
    rows.extend(
        _search_level(session, query, tidalapi.Track, "tracks", _tracks_to_rows)()
    )
    return rows
