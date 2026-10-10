"""Writing to the playlists this TIDAL account made.

Creating one from the queue, adding to one, taking a track out, moving one,
renaming, describing and deleting. Every write forgets the levels it made
stale, so the browser fetches them again. Reading the playlists is browsing,
and lives in `library` with the rest of the tree.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial
from typing import Any

import tidalapi

from .i18n import _
from .levels import PAGE, forget, forget_level
from .library import _count_of, _me
from .net import with_retries
from .queue import Entry

# TIDAL takes at most this many tracks in one add request.
PLAYLIST_BATCH = 100


class PlaylistSaveFailed(RuntimeError):
    """A playlist exists, but only part of its queue could be added."""

    def __init__(self, title: str, added: int, total: int, cause: Exception) -> None:
        super().__init__(str(cause))
        self.title = title
        self.added = added
        self.total = total


def save_queue_playlist(
    session: tidalapi.Session,
    title: str,
    entries: Iterable[Entry],
    batch_size: int = PLAYLIST_BATCH,
) -> int:
    """Create a TIDAL playlist from a snapshot of the queue, in queue order.

    TIDAL accepts at most 100 items per add request. Once creation succeeds the
    playlist is deliberately kept even if a later batch fails: silently deleting
    the batches that did make it would lose more user work. The raised exception
    carries the exact completed count so the UI can say what remains in TIDAL.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    media_ids = [str(entry.id) for entry in entries]
    # Not retried on a lost answer: that would be a second playlist.
    playlist = with_retries(
        lambda: _me(session).create_playlist(title, ""), idempotent=False
    )
    # A partially filled playlist is still a new playlist and must appear the
    # next time the user opens this level.
    forget("playlists")

    added = 0
    for offset in range(0, len(media_ids), batch_size):
        batch = media_ids[offset : offset + batch_size]

        def add_batch(items: list[str] = batch) -> list[int]:
            return playlist.add(
                items,
                allow_duplicates=True,
                position=-1,
                limit=batch_size,
            )

        try:
            # Nor a batch: TIDAL may have added it already.
            result = with_retries(add_batch, idempotent=False)
        except Exception as exc:
            raise PlaylistSaveFailed(title, added, len(media_ids), exc) from exc
        added += len(result)
    return added


class PlaylistNotWritable(RuntimeError):
    """TIDAL handed back a playlist this account cannot add to."""


class TrackNotInPlaylist(RuntimeError):
    """The track is no longer in the playlist the browser showed it in."""


def remove_from_playlist(
    session: tidalapi.Session, playlist_id: str, entry: Entry
) -> str:
    """Take one track out of a playlist the user owns. Returns the playlist's name.

    By index, looked up here page by page in the playlist's own order.
    tidalapi's ``remove_by_id`` reads a single page of TIDAL's default size
    and reports a track past it as absent; and the browser may be showing the
    playlist sorted, so the row's number on screen is no index at all. A track
    that is in the playlist twice loses its first appearance.

    The DELETE is not retried: it removes by position, and a retry after a
    lost answer would take out the track that moved into that position.
    """
    playlist = with_retries(lambda: session.playlist(playlist_id))
    title = getattr(playlist, "name", "") or ""
    if not hasattr(playlist, "remove_by_index"):
        # A playlist someone else owns parses fine and cannot be written to.
        raise PlaylistNotWritable(title)
    wanted = str(entry.id)
    total = _count_of(playlist)
    offset = 0
    while total is None or offset < total:
        page = with_retries(partial(playlist.tracks, limit=PAGE, offset=offset))
        if not page and total is None:
            break
        for position, track in enumerate(page):
            if str(getattr(track, "id", "")) == wanted:
                index = _position_of(playlist, wanted, offset + position, offset)
                if index is None:
                    raise TrackNotInPlaylist(entry.label)
                playlist.remove_by_index(index)
                forget("playlists")
                forget_level(f"playlist:{playlist_id}")
                return title
        offset += PAGE
    raise TrackNotInPlaylist(entry.label)


def _is_at(playlist: Any, index: int, wanted: str) -> bool:
    page = with_retries(partial(playlist.tracks, limit=1, offset=index))
    return bool(page) and str(getattr(page[0], "id", "")) == wanted


def _position_of(playlist: Any, wanted: str, guess: int, start: int) -> int | None:
    """Where ``wanted`` really is, checked before anything is deleted.

    ``guess`` counts what the page handed back, and TIDAL can leave a track
    it cannot serve out of a page after applying the limit, as it does with
    favourites: then every position after the gap is one short, and deleting
    by it would take out the neighbour. One single-track read confirms the
    guess; if it does not hold, the page's window is walked a track at a
    time, which is the rare case and a hundred small reads at most.
    """
    if _is_at(playlist, guess, wanted):
        return guess
    for index in range(start, start + PAGE):
        if _is_at(playlist, index, wanted):
            return index
    return None


def add_to_playlist(
    session: tidalapi.Session,
    playlist_id: str,
    entries: Iterable[Entry],
    batch_size: int = PLAYLIST_BATCH,
) -> int:
    """Append tracks to a playlist that already exists, in the order given.

    The same hundred-per-request batching as creating one, and the same rule
    when a batch fails: what already went in stays, and the exception carries
    how many made it. Duplicates are allowed on purpose — asking for a queue to
    be added twice is a thing someone can mean, and deduplicating behind their
    back is a decision this does not get to take.

    Writing needs `factory()`, not the cheap `parse()` the listing uses: only a
    `UserPlaylist` has `add`, and that is the one thing the listing deliberately
    avoids building because it costs a request per row. One request here, at
    the moment of writing, is the right place to spend it.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    media_ids = [str(entry.id) for entry in entries]
    playlist = with_retries(lambda: session.playlist(playlist_id))
    title = getattr(playlist, "name", "") or ""
    if not hasattr(playlist, "add"):
        # A playlist someone else owns parses fine and cannot be written to.
        raise PlaylistNotWritable(title)

    # The list of playlists changes (its track count) and so does that
    # playlist's own level, which the browser caches separately.
    forget("playlists")
    forget(f"playlist:{playlist_id}")

    added = 0
    for offset in range(0, len(media_ids), batch_size):
        batch = media_ids[offset : offset + batch_size]

        def add_batch(items: list[str] = batch) -> list[int]:
            return playlist.add(
                items,
                allow_duplicates=True,
                position=-1,
                limit=batch_size,
            )

        try:
            # Nor a batch: TIDAL may have added it already.
            result = with_retries(add_batch, idempotent=False)
        except Exception as exc:
            raise PlaylistSaveFailed(title, added, len(media_ids), exc) from exc
        added += len(result)
    return added


class MoveNotConfirmed(RuntimeError):
    """TIDAL answered the move, and the track is not where it was sent."""


def _writable(session: tidalapi.Session, playlist_id: str) -> Any:
    """The playlist as a `UserPlaylist`, the only kind that can be written.

    One request, for this playlist alone: see `_playlists_level` for why the
    listing does not build them.
    """
    playlist = with_retries(lambda: session.playlist(playlist_id))
    if not hasattr(playlist, "remove_by_index"):
        # A playlist someone else owns parses fine and cannot be written to.
        raise PlaylistNotWritable(getattr(playlist, "name", "") or "")
    return playlist


def edit_playlist(
    session: tidalapi.Session,
    playlist_id: str,
    title: str | None = None,
    description: str | None = None,
) -> str:
    """Rename a playlist, or change its description. Returns its old name.

    Not tidalapi's `edit`, which reads an empty description as «keep the one
    it has», so a description could never be cleared. The same request, with
    what was asked for. Retried like a read: sending the same name twice
    leaves the same name.
    """
    playlist = _writable(session, playlist_id)
    old = getattr(playlist, "name", "") or ""
    data = {
        "title": title if title else old,
        "description": (
            description
            if description is not None
            else getattr(playlist, "description", "") or ""
        ),
    }
    response = with_retries(
        lambda: playlist.request.request(
            "POST", playlist._base_url % playlist.id, data=data
        )
    )
    if not getattr(response, "ok", True):
        raise RuntimeError(_("TIDAL no aceptó el cambio"))
    forget_level("playlists")
    return old


def delete_playlist(session: tidalapi.Session, playlist_id: str) -> str:
    """Delete a playlist this account made. Returns its name.

    Not retried after a lost answer: the second DELETE would find nothing and
    report a failure over a playlist that is gone.
    """
    playlist = _writable(session, playlist_id)
    title = getattr(playlist, "name", "") or ""
    if not with_retries(playlist.delete, idempotent=False):
        raise RuntimeError(_("TIDAL no aceptó el cambio"))
    forget_level("playlists")
    forget_level(f"playlist:{playlist_id}")
    return title


def move_in_playlist(
    session: tidalapi.Session, playlist_id: str, entry: Entry, index: int, delta: int
) -> str:
    """Move one track of a playlist ``delta`` places. Returns the playlist's name.

    ``index`` is where the browser shows it, in the playlist's own order: the
    caller refuses a playlist shown sorted, where the row's place is no
    position at all. Checked before and after. Before, because TIDAL can
    leave a track out of a page and every position after it is one short
    (`_position_of`); after, because TIDAL's `toIndex` is where the track
    ends, and a move that lands elsewhere must say so rather than leave the
    list on screen lying.

    Not retried: a second move after a lost answer moves it again.
    """
    playlist = _writable(session, playlist_id)
    title = getattr(playlist, "name", "") or ""
    wanted = str(entry.id)
    at = _position_of(playlist, wanted, index, index - index % PAGE)
    if at is None:
        raise TrackNotInPlaylist(entry.label)
    target = at + delta
    total = _count_of(playlist)
    if target < 0 or (total is not None and target >= total):
        return title
    with_retries(lambda: playlist.move_by_index(at, target), idempotent=False)
    # Every sorted copy of it is stale, and so is the plain one: the browser
    # keeps the list it has on screen and swaps the two rows itself.
    forget_level(f"playlist:{playlist_id}")
    if not _is_at(playlist, target, wanted):
        raise MoveNotConfirmed(entry.label)
    return title
