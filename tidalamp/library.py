"""Browsing the user's TIDAL library.

Everything here returns ``Row`` lists. A row either plays (it carries an
``Entry``), drills down (it carries a ``loader`` that fetches the next level),
or extends the level it lives in (it carries ``more``). Loaders are called
from a worker thread, never on the UI loop.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from typing import Any, cast

import tidalapi
from tidalapi.types import AlbumOrder, ArtistOrder, ItemOrder, OrderDirection

from .config import STATE_DIR
from .i18n import _
from .net import with_retries
from .queue import Entry

log = logging.getLogger("tidalamp.library")

# TIDAL paginates. We ask for one page at a time and hang a "más…" row off the
# end when the page came back full, so a 500-track playlist is reachable
# without pulling it whole on open.
PAGE = 100
PLAYLIST_BATCH = 100


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


def _page_of(item: Any, offset: int, limit: int, **order: Any) -> list:
    """One page of the tracks inside a playlist or an album."""
    return item.tracks(limit=limit, offset=offset, **order)


def _top_tracks_of(artist: Any, offset: int, limit: int) -> list:
    return artist.get_top_tracks(limit=limit, offset=offset)


# Levels already fetched, so walking back into one is instant. In memory only:
# it dies with the process, which is the right lifetime for a view of a library
# the user can change from another device. `R` in the browser forces a refetch.
_LEVELS: dict[str, list[Row]] = {}


def cached(key: str, loader: Callable[[], list[Row]]) -> Callable[[], list[Row]]:
    """Memoise one level's rows under ``key``.

    The cached list is handed out as-is, not copied, on purpose: loading
    another page mutates the level in place (see ``BrowserScreen._merge``), so
    pages the user already pulled are still there when they come back."""

    def load() -> list[Row]:
        rows = _LEVELS.get(key)
        if rows is None:
            rows = loader()
            _LEVELS[key] = rows
        return rows

    return load


def forget_level(key: str) -> None:
    """Drop a level and every sorted copy of it (``key|name-asc`` and so on)."""
    for cached_key in [k for k in _LEVELS if k == key or k.startswith(f"{key}|")]:
        _LEVELS.pop(cached_key, None)


def forget(key: str = "") -> None:
    """Drop one cached level, or all of them when ``key`` is empty."""
    if key:
        _LEVELS.pop(key, None)
    else:
        _LEVELS.clear()


@dataclass(frozen=True, slots=True)
class Order:
    """How a level is sorted: by what, and which way round.

    ``created`` only changes the label: a playlist's date is when it was
    made, a favourite's is when it was added.
    """

    by: str
    descending: bool = False
    created: bool = False

    @property
    def code(self) -> str:
        return f"{self.by}-{'desc' if self.descending else 'asc'}"


# What each kind of level can be sorted by. Dates come newest first, names
# A to Z first, because that is what someone reaching for the order wants.
TRACK_BY = ("date", "name", "artist", "album")
ALBUM_BY = ("date", "name", "artist", "release")
ARTIST_BY = ("date", "name")
PLAYLIST_BY = ("date", "name")
# Inside an album or an artist TIDAL does not sort, and the level is one
# page, so the rows are sorted here.
ALBUM_TRACK_BY = ("name", "artist")
ARTIST_TRACK_BY = ("name", "album")

# TIDAL's name for each, shared by its order enums.
_TIDAL_BY = {
    "date": "DATE",
    "name": "NAME",
    "artist": "ARTIST",
    "album": "ALBUM",
    "release": "RELEASE_DATE",
}

# The order picked for each level, by the level's key: its code, as in
# `name-asc`. Kept on disk so a level opens the next day the way it was left;
# read the first time it is asked for. TIDAL's own order is not stored.
ORDERS_FILE = STATE_DIR / "library-orders.json"
_CHOSEN: dict[str, str] | None = None


def orders_for(by: tuple[str, ...], *, created: bool = False) -> tuple[Order | None, ...]:
    """The level as TIDAL gives it, then each kind both ways round."""
    orders: list[Order | None] = [None]
    for kind in by:
        newest_first = kind in ("date", "release")
        orders.append(Order(kind, newest_first, created))
        orders.append(Order(kind, not newest_first, created))
    return tuple(orders)


def order_label(order: Order | None) -> str:
    """An order as the sort window and the browser's title say it."""
    if order is None:
        return _("orden original")
    down = order.descending
    if order.by == "date" and order.created:
        if down:
            return _("fecha de creación: recientes primero")
        return _("fecha de creación: antiguas primero")
    if order.by == "date":
        if down:
            return _("fecha de agregado: recientes primero")
        return _("fecha de agregado: antiguas primero")
    if order.by == "release":
        return (
            _("lanzamiento: recientes primero")
            if down
            else _("lanzamiento: antiguos primero")
        )
    if order.by == "artist":
        return _("artista: Z-A") if down else _("artista: A-Z")
    if order.by == "album":
        return _("álbum: Z-A") if down else _("álbum: A-Z")
    return _("nombre: Z-A") if down else _("nombre: A-Z")


def _orders() -> dict[str, str]:
    """The orders picked so far, loaded from disk on first use.

    A missing or broken file is no orders at all: it is a convenience, and
    a level opening in TIDAL's order is no reason to refuse to start.
    """
    global _CHOSEN
    if _CHOSEN is None:
        try:
            raw = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        _CHOSEN = (
            {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
            if isinstance(raw, dict)
            else {}
        )
    return _CHOSEN


def chosen(row: Row) -> Order | None:
    """The order last picked for the level ``row`` opens, or None for TIDAL's.

    Looked up among the row's own orders by code, so a playlist's date still
    reads as its creation date, and an order the level no longer offers is
    simply TIDAL's.
    """
    code = _orders().get(row.key)
    return next(
        (order for order in row.orders if order is not None and order.code == code),
        None,
    )


def remember(row: Row, order: Order | None) -> None:
    """Keep ``order`` for the level ``row`` opens. Failing to write is not fatal."""
    orders = _orders()
    if order is None:
        orders.pop(row.key, None)
    else:
        orders[row.key] = order.code
    try:
        ORDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ORDERS_FILE.write_text(json.dumps(orders, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _tidal(order: Order | None, kind: Any) -> dict[str, Any]:
    """The keyword arguments tidalapi takes for ``order``, in its enum ``kind``."""
    if order is None:
        return {}
    direction = (
        OrderDirection.Descending if order.descending else OrderDirection.Ascending
    )
    return {"order": kind(_TIDAL_BY[order.by]), "order_direction": direction}


def _in_order(rows: list[Row], order: Order | None) -> list[Row]:
    """Sort a level here, for the levels TIDAL does not sort. «más…» stays last."""
    if order is None:
        return rows
    items = [row for row in rows if row.more is None]
    more = [row for row in rows if row.more is not None]

    def value(row: Row) -> str:
        entry = row.entry
        if entry is None:
            return _folded(row.label)
        field = {"artist": entry.artist, "album": entry.album}.get(order.by, entry.title)
        return _folded(field or "")

    return sorted(items, key=value, reverse=order.descending) + more


def _sortable(
    key: str,
    by: tuple[str, ...],
    build: Callable[[Order | None], Callable[[], list[Row]]],
    *,
    created: bool = False,
    local: bool = False,
) -> dict[str, Any]:
    """What a row needs to open its level and to open it sorted.

    Each order is a level of its own in the cache (``key|name-asc``), so
    going back to one is instant and `R` refetches only the one on screen.
    TIDAL's own order keeps the plain key, which is what everything else
    already calls the level.
    """
    base = cached(key, build(None))

    def sort(order: Order | None) -> tuple[str, Callable[[], list[Row]]]:
        if order is None:
            return key, base
        code = f"{key}|{order.code}"
        if local:
            return code, cached(code, lambda: _in_order(list(base()), order))
        return code, cached(code, build(order))

    return {
        "key": key,
        "loader": base,
        "orders": orders_for(by, created=created),
        "sort": sort,
    }


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
    # What number to draw at the head of the line, when it is not the row's
    # own position on screen. The queue sets it: under a filter the rows shown
    # are a handful out of hundreds, and renumbering them 1, 2, 3 would claim
    # a playing order that is not the one the player follows.
    number: int | None = None
    # The ways this row's level can be sorted, and how to load it in one of
    # them: ``sort`` hands back the cache key and loader. Empty when TIDAL
    # offers no order for it, as for the root and for search results' tracks.
    orders: tuple[Order | None, ...] = ()
    sort: Callable[[Order | None], tuple[str, Callable[[], list[Row]]]] | None = None

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
                    label=_("más…"),
                    detail=(
                        _("siguientes {page} de {total}").format(page=PAGE, total=total)
                        if total is not None
                        else _("siguientes {page}").format(page=PAGE)
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


def _playlist_level(playlist: Any, order: Order | None) -> Callable[[], list[Row]]:
    """A playlist's tracks, in ``order`` as TIDAL sorts them."""
    return _paged(
        partial(_page_of, playlist, **_tidal(order, ItemOrder)),
        _tracks_to_rows,
        count=partial(_count_of, playlist),
    )


def _album_level(album: Any, order: Order | None) -> Callable[[], list[Row]]:
    """An album's tracks as TIDAL gives them; ``_sortable`` sorts them here."""
    return _paged(
        partial(_page_of, album), _tracks_to_rows, count=partial(_count_of, album)
    )


def _artist_level(artist: Any, order: Order | None) -> Callable[[], list[Row]]:
    """An artist's top tracks as TIDAL gives them; sorted here, like an album."""
    return _paged(partial(_top_tracks_of, artist), _tracks_to_rows)


def _playlist_rows(playlists: Iterable[tidalapi.Playlist]) -> list[Row]:
    rows = []
    for playlist in playlists:
        count = playlist.num_tracks or 0
        rows.append(
            Row(
                label=playlist.name or "",
                detail=_("{count} pistas").format(count=count),
                **_sortable(
                    f"playlist:{playlist.id}",
                    TRACK_BY,
                    partial(_playlist_level, playlist),
                ),
            )
        )
    return rows


def _playlists_level(
    session: tidalapi.Session, order: Order | None = None
) -> Callable[[], list[Row]]:
    """The playlists the user created, one page per request.

    ``session.user.playlists()`` looks like a single call and is not: parsing
    each item runs it through ``Playlist.factory()``, which for a playlist you
    own builds a ``UserPlaylist``, and *that* constructor fetches the playlist
    again just to read its ETag. Measured on a real account: 110 playlists,
    111 HTTP requests, twenty seconds. We never edit playlists, so we parse the
    listing ourselves and skip the factory — one request, a quarter of a
    second — and paginate it like every other level.
    """

    # The same order and direction names tidalapi sends for favourites.
    ordering = (
        {}
        if order is None
        else {
            "order": _TIDAL_BY[order.by],
            "orderDirection": "DESC" if order.descending else "ASC",
        }
    )

    def fetch(offset: int, limit: int) -> list[tidalapi.Playlist]:
        response = with_retries(
            lambda: session.request.request(
                "GET",
                f"users/{_me(session).id}/playlists",
                params={"limit": limit, "offset": offset, **ordering},
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
                **_sortable(
                    f"album:{album.id}",
                    ALBUM_TRACK_BY,
                    partial(_album_level, album),
                    local=True,
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
                detail=_("artista"),
                **_sortable(
                    f"artist:{artist.id}",
                    ARTIST_TRACK_BY,
                    partial(_artist_level, artist),
                    local=True,
                ),
            )
        )
    return rows


def root(session: tidalapi.Session) -> list[Row]:
    """The top level of the browser."""
    favorites = _me(session).favorites
    return [
        Row(
            _("Mis playlists"),
            "",
            **_sortable(
                "playlists",
                PLAYLIST_BY,
                lambda order: _playlists_level(session, order),
                created=True,
            ),
        ),
        Row(
            _("Pistas favoritas"),
            "",
            **_sortable(
                "fav:tracks",
                TRACK_BY,
                lambda order: _paged(
                    lambda offset, limit: favorites.tracks(
                        limit=limit, offset=offset, **_tidal(order, ItemOrder)
                    ),
                    _tracks_to_rows,
                    count=favorites.get_tracks_count,
                ),
            ),
        ),
        Row(
            _("Álbumes favoritos"),
            "",
            **_sortable(
                "fav:albums",
                ALBUM_BY,
                lambda order: _paged(
                    lambda offset, limit: favorites.albums(
                        limit=limit, offset=offset, **_tidal(order, AlbumOrder)
                    ),
                    _album_rows,
                    count=favorites.get_albums_count,
                ),
            ),
        ),
        Row(
            _("Artistas favoritos"),
            "",
            **_sortable(
                "fav:artists",
                ARTIST_BY,
                lambda order: _paged(
                    lambda offset, limit: favorites.artists(
                        limit=limit, offset=offset, **_tidal(order, ArtistOrder)
                    ),
                    _artist_rows,
                    count=favorites.get_artists_count,
                ),
            ),
        ),
    ]


def _folded(text: str) -> str:
    """Lower-case and strip accents, so «sinfonia» finds «Sinfonía».

    Typing accents to search is a tax nobody pays willingly, and TIDAL's
    catalogue writes the same artist both ways depending on the release.
    """
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def matches(query: str, row: Row) -> bool:
    """Does ``row`` answer to ``query``?

    Every whitespace-separated term has to appear somewhere in the row: its
    label, its detail, and — for a track — its album, which is only on screen
    if the user turned that column on but is often what they remember. Terms
    rather than the whole string, so «tool lateralus» finds a line that reads
    «TOOL - Schism» with «Lateralus» in a column that may not even be shown.

    A row that carries no ``more`` and matches nothing is hidden; deciding
    what to do with the «más…» row is the caller's business, because it is
    not a piece of music but the way to reach the rest of the level.
    """
    entry = row.entry
    parts = [row.label, row.detail, entry.album if entry is not None else ""]
    return text_matches(query, " ".join(part for part in parts if part))


def text_matches(query: str, text: str) -> bool:
    """Every term of ``query`` somewhere in ``text``, accents and case aside.

    The rule `matches` applies to a row, for anything that is only text: the
    help screen searches its own lines with it, so «pausa» finds the same
    things there as it would in a list.
    """
    haystack = _folded(text)
    return all(term in haystack for term in _folded(query).split())


class NotFavouritable(RuntimeError):
    """Raised for a row that is not a thing TIDAL can favourite."""


# One entry per album id, for the whole session. A `0` in here is an album
# TIDAL has no date for, cached exactly like a real answer so that a record
# without one is asked about once and not on every redraw.
_YEARS: dict[int, int] = {}


def album_year(session: tidalapi.Session, album_id: int) -> int:
    """The release year of one album, asked for at most once per session.

    The year is the one column the API does not hand over with a track: the
    album nested inside a track listing carries an id, a title and a cover and
    no release date. So it has to be asked for separately, and the cost is one
    request per *album* rather than per track — a hundred tracks off fifteen
    records cost fifteen.

    Returns `0` when TIDAL has no date, which the column draws as an empty
    cell. That is the honest answer: the alternative was the track's own
    `streamStartDate`, which is when TIDAL began streaming it and would print
    2011 on a record released in 1997.
    """
    if album_id <= 0:
        return 0
    if album_id in _YEARS:
        return _YEARS[album_id]
    try:
        album = with_retries(lambda: session.album(str(album_id)))
        year = int(getattr(album, "year", 0) or 0)
    except Exception:
        # A failure is not cached: the next queue may as well try again.
        log.info("no se pudo obtener el año del álbum %s", album_id)
        return 0
    _YEARS[album_id] = year
    return year


class NoRadio(RuntimeError):
    """Raised when TIDAL has no radio station for a track."""


class PlaylistSaveFailed(RuntimeError):
    """A playlist exists, but only part of its queue could be added."""

    def __init__(self, title: str, added: int, total: int, cause: Exception) -> None:
        super().__init__(str(cause))
        self.title = title
        self.added = added
        self.total = total


def track_radio(session: tidalapi.Session, entry: Entry, limit: int = 100) -> list[Entry]:
    """TIDAL's radio station for one track: the songs it considers similar.

    The seed is filtered out. TIDAL puts it at the head of its own station, so
    a caller that leads with the seed — which is the only way the station does
    not look like it started on the wrong song — would show it twice.

    The station is generated per track and is not always available — a very
    obscure release simply has none — which TIDAL answers with a 404 that
    `tidalapi` raises as `MetadataNotAvailable`. That is a normal answer, not
    a failure, so it comes back as `NoRadio` for the caller to say out loud.
    """
    track = entry.resolve(session)
    try:
        tracks = with_retries(lambda: track.get_track_radio(limit=limit))
    except Exception as exc:
        # tidalapi raises MetadataNotAvailable, which lives in a module we do
        # not import; anything else here also means "no station to play".
        raise NoRadio(
            _("TIDAL no tiene radio para «{label}»").format(label=entry.label)
        ) from exc
    # By id, not by equality: the seed and the station's copy of it are two
    # Entry objects built from two API responses.
    entries = [
        Entry.from_track(found) for found in tracks if int(found.id) != int(entry.id)
    ]
    if not entries:
        raise NoRadio(_("TIDAL no tiene radio para «{label}»").format(label=entry.label))
    return entries


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
        # The favourites level, in every order it was opened in, is stale now.
        forget_level("fav:tracks")
        return entry.label

    kind, _separator, ident = row.key.partition(":")
    calls: dict[str, tuple[Callable[[str], bool], Callable[[str], bool]]] = {
        "album": (favorites.add_album, favorites.remove_album),
        "artist": (favorites.add_artist, favorites.remove_artist),
        "playlist": (favorites.add_playlist, favorites.remove_playlist),
    }
    if kind not in calls or not ident:
        raise NotFavouritable(
            _("eso no es una pista, un álbum, un artista ni una playlist")
        )
    call = calls[kind][0 if add else 1]
    with_retries(lambda: call(ident))
    if kind in ("album", "artist"):
        forget_level(f"fav:{kind}s")
    return row.label


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
    playlist = with_retries(lambda: _me(session).create_playlist(title, ""))
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
            result = with_retries(add_batch)
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
            result = with_retries(add_batch)
        except Exception as exc:
            raise PlaylistSaveFailed(title, added, len(media_ids), exc) from exc
        added += len(result)
    return added


def playlist_rows(session: tidalapi.Session) -> list[Row]:
    """Every playlist this account created, for the picker to draw.

    `users/{id}/playlists` is the ones they made; the ones they follow live
    under favourites and are not here, so nothing has to be filtered out to
    keep the picker from offering a playlist it cannot write to.
    """
    return _playlists_level(session)()


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
        (_("Álbumes"), tidalapi.Album, "albums", _album_rows),
        (_("Artistas"), tidalapi.Artist, "artists", _artist_rows),
        (_("Playlists"), tidalapi.Playlist, "playlists", _playlist_rows),
    ]
    rows = [
        Row(
            _("{label} con «{query}»").format(label=label, query=query),
            _("abrir"),
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
