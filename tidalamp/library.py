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


@dataclass(slots=True)
class Row:
    """One line in the browser."""

    label: str
    detail: str = ""
    entry: Entry | None = None
    loader: Callable[[], list["Row"]] | None = None
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


def _playlist_rows(session: tidalapi.Session) -> list[Row]:
    # user.playlists() has no offset in tidalapi; it returns them all.
    rows = []
    for playlist in with_retries(session.user.playlists):
        count = playlist.num_tracks or 0
        rows.append(
            Row(
                label=playlist.name,
                detail=f"{count} pistas",
                loader=_paged(
                    lambda offset, limit, p=playlist: p.tracks(limit=limit, offset=offset),
                    _tracks_to_rows,
                ),
            )
        )
    return rows


def _album_rows(albums: Iterable[tidalapi.Album]) -> list[Row]:
    rows = []
    for album in albums:
        artist = getattr(getattr(album, "artist", None), "name", "") or ""
        rows.append(
            Row(
                label=f"{artist} - {album.name}" if artist else album.name,
                detail=str(getattr(album, "year", "") or ""),
                loader=_paged(
                    lambda offset, limit, a=album: a.tracks(limit=limit, offset=offset),
                    _tracks_to_rows,
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
                loader=_paged(
                    lambda offset, limit, a=artist: a.get_top_tracks(
                        limit=limit, offset=offset
                    ),
                    _tracks_to_rows,
                ),
            )
        )
    return rows


def root(session: tidalapi.Session) -> list[Row]:
    """The top level of the browser."""
    favorites = session.user.favorites
    return [
        Row("Mis playlists", "", loader=lambda: _playlist_rows(session)),
        Row(
            "Pistas favoritas",
            "",
            loader=_paged(
                lambda offset, limit: favorites.tracks(limit=limit, offset=offset),
                _tracks_to_rows,
            ),
        ),
        Row(
            "Álbumes favoritos",
            "",
            loader=_paged(
                lambda offset, limit: favorites.albums(limit=limit, offset=offset),
                _album_rows,
            ),
        ),
        Row(
            "Artistas favoritos",
            "",
            loader=_paged(
                lambda offset, limit: favorites.artists(limit=limit, offset=offset),
                _artist_rows,
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
