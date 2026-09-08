"""Browsing the user's TIDAL library.

Everything here returns ``Row`` lists. A row either plays (it carries an
``Entry``) or drills down (it carries a ``loader`` that fetches the next
level). Loaders are called from a worker thread, never on the UI loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import tidalapi

from .queue import Entry

# TIDAL paginates; these caps keep a level to one request and one screenful of
# scrolling rather than pulling an entire library.
PAGE = 100


@dataclass(slots=True)
class Row:
    """One line in the browser."""

    label: str
    detail: str = ""
    entry: Entry | None = None
    loader: Callable[[], list["Row"]] | None = None

    @property
    def is_playable(self) -> bool:
        return self.entry is not None


def _tracks_to_rows(tracks: list[tidalapi.Track]) -> list[Row]:
    rows = []
    for track in tracks:
        entry = Entry.from_track(track)
        rows.append(Row(label=entry.label, detail=entry.length, entry=entry))
    return rows


def _playlist_rows(session: tidalapi.Session) -> list[Row]:
    rows = []
    for playlist in session.user.playlists():
        count = playlist.num_tracks or 0
        rows.append(
            Row(
                label=playlist.name,
                detail=f"{count} pistas",
                loader=lambda p=playlist: _tracks_to_rows(p.tracks(limit=PAGE)),
            )
        )
    return rows


def _album_rows(albums: list[tidalapi.Album]) -> list[Row]:
    rows = []
    for album in albums:
        artist = getattr(getattr(album, "artist", None), "name", "") or ""
        rows.append(
            Row(
                label=f"{artist} - {album.name}" if artist else album.name,
                detail=str(getattr(album, "year", "") or ""),
                loader=lambda a=album: _tracks_to_rows(a.tracks(limit=PAGE)),
            )
        )
    return rows


def _artist_rows(artists: list[tidalapi.Artist]) -> list[Row]:
    rows = []
    for artist in artists:
        rows.append(
            Row(
                label=artist.name,
                detail="artista",
                loader=lambda a=artist: _tracks_to_rows(a.get_top_tracks(limit=PAGE)),
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
            loader=lambda: _tracks_to_rows(favorites.tracks(limit=PAGE)),
        ),
        Row(
            "Álbumes favoritos",
            "",
            loader=lambda: _album_rows(favorites.albums(limit=PAGE)),
        ),
        Row(
            "Artistas favoritos",
            "",
            loader=lambda: _artist_rows(favorites.artists(limit=PAGE)),
        ),
    ]


def search_rows(session: tidalapi.Session, query: str) -> list[Row]:
    """Search results, shaped like any other browser level."""
    results = session.search(query, models=[tidalapi.Track], limit=50)
    return _tracks_to_rows(results.get("tracks", []))
