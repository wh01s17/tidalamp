"""Browsing the user's TIDAL library.

Everything here returns ``Row`` lists (see `levels`, which also holds the
cache, the orders and the paging every level shares). Loaders are called from
a worker thread, never on the UI loop. Writing to a playlist is in
`playlists`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from functools import partial
from typing import Any, cast

import tidalapi
from tidalapi.types import AlbumOrder, ArtistOrder, ItemOrder, OrderDirection

from . import archive, freemusic, jamendo
from .i18n import _
from .levels import (
    ALBUM_BY,
    ALBUM_TRACK_BY,
    ARTIST_BY,
    ARTIST_TRACK_BY,
    PLAYLIST_BY,
    TRACK_BY,
    Order,
    Row,
    _paged,
    _sortable,
    cached,
    forget_level,
)
from .music import Track
from .net import with_retries
from .queue import FREE, Entry

log = logging.getLogger("tidalamp.library")


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


# TIDAL's name for each, shared by its order enums.
_TIDAL_BY = {
    "date": "DATE",
    "name": "NAME",
    "artist": "ARTIST",
    "album": "ALBUM",
    "release": "RELEASE_DATE",
}


def _tidal(order: Order | None, kind: Any) -> dict[str, Any]:
    """The keyword arguments tidalapi takes for ``order``, in its enum ``kind``."""
    if order is None:
        return {}
    direction = (
        OrderDirection.Descending if order.descending else OrderDirection.Ascending
    )
    return {"order": kind(_TIDAL_BY[order.by]), "order_direction": direction}


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


def _art_of(item: Any, px: int = 160) -> str:
    """The URL of ``item``'s picture at ``px``, or "" when it has none.

    tidalapi raises rather than answering None when an album carries no cover
    id or a playlist no square picture, and a tile without a cover is still a
    tile: the grid draws a placeholder.
    """
    try:
        if isinstance(item, tidalapi.Playlist):
            # Not the wide banner a playlist may have instead: the grid's
            # tiles are square.
            return item.image(px, wide_fallback=False) or ""
        return item.image(px) or ""
    except Exception:
        return ""


def _playlist_rows(playlists: Iterable[tidalapi.Playlist]) -> list[Row]:
    rows = []
    for playlist in playlists:
        count = playlist.num_tracks or 0
        rows.append(
            Row(
                label=playlist.name or "",
                detail=_("{count} pistas").format(count=count),
                art=_art_of(playlist),
                description=getattr(playlist, "description", "") or "",
                **_sortable(
                    f"playlist:{playlist.id}",
                    TRACK_BY,
                    partial(_playlist_level, playlist),
                ),
            )
        )
    return rows


def _own_playlist_rows(playlists: Iterable[tidalapi.Playlist]) -> list[Row]:
    """The rows of «Mis playlists»: every one of them can be edited."""
    rows = _playlist_rows(playlists)
    for row in rows:
        row.editable = True
    return rows


def _playlists_level(
    session: tidalapi.Session, order: Order | None = None
) -> Callable[[], list[Row]]:
    """The playlists the user created, one page per request.

    ``session.user.playlists()`` looks like a single call and is not: parsing
    each item runs it through ``Playlist.factory()``, which for a playlist you
    own builds a ``UserPlaylist``, and *that* constructor fetches the playlist
    again just to read its ETag. Measured on a real account: 110 playlists,
    111 HTTP requests, twenty seconds. Showing a playlist needs none of that,
    so we parse the listing ourselves and skip the factory — one request, a
    quarter of a second — and paginate it like every other level. Editing one
    builds the `UserPlaylist` then, for that playlist alone (`_writable`).
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

    return _paged(fetch, _own_playlist_rows, count=count)


def _album_rows(albums: Iterable[tidalapi.Album]) -> list[Row]:
    rows = []
    for album in albums:
        artist = getattr(getattr(album, "artist", None), "name", "") or ""
        rows.append(
            Row(
                label=f"{artist} - {album.name}" if artist else (album.name or ""),
                detail=str(getattr(album, "year", "") or ""),
                art=_art_of(album),
                caption=album.name or "",
                byline=artist,
                **_sortable(
                    f"album:{album.id}",
                    ALBUM_TRACK_BY,
                    partial(_album_level, album),
                    local=True,
                ),
            )
        )
    return rows


def _discs_of(method: str) -> Callable[[Any, int, int], list]:
    """One of an artist's disc listings, paged the way `_paged` asks."""

    def fetch(artist: Any, offset: int, limit: int) -> list:
        return getattr(artist, method)(limit=limit, offset=offset)

    return fetch


# The sections an artist opens to, in the order they are shown: exactly the
# ones the API has and no more. A live record goes where TIDAL puts it, among
# the albums; telling it apart by its title would be guessing.
_ARTIST_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("albums", "get_albums", _("Álbumes")),
    ("singles", "get_ep_singles", _("EPs y sencillos")),
    ("other", "get_other", _("Otros: recopilatorios y colaboraciones")),
)


def _artist_sections(artist: Any) -> Callable[[], list[Row]]:
    """The level an artist opens to: its popular tracks, then its discs.

    Each section is a paged level of its own, and each disc in it opens to
    its tracks like any album. A section with nothing in it is left out,
    which costs one small request per section to find out.
    """
    key = f"artist:{artist.id}"

    def level() -> list[Row]:
        rows = []
        if with_retries(lambda: _top_tracks_of(artist, 0, 1)):
            rows.append(
                Row(
                    label=_("Populares"),
                    **_sortable(
                        f"{key}:top",
                        ARTIST_TRACK_BY,
                        partial(_artist_level, artist),
                        local=True,
                    ),
                )
            )
        for name, method, label in _ARTIST_SECTIONS:
            fetch = partial(_discs_of(method), artist)
            if not with_retries(partial(fetch, 0, 1)):
                continue
            section = f"{key}:{name}"
            rows.append(
                Row(
                    label=label,
                    key=section,
                    loader=cached(section, _paged(fetch, _album_rows)),
                )
            )
        return rows

    return level


def _artist_rows(artists: Iterable[tidalapi.Artist]) -> list[Row]:
    rows = []
    for artist in artists:
        key = f"artist:{artist.id}"
        rows.append(
            Row(
                label=artist.name or "",
                detail=_("artista"),
                art=_art_of(artist),
                key=key,
                loader=cached(key, _artist_sections(artist)),
                # `m` and `a` on an artist play its popular tracks, as they
                # did when that was the whole level: the discs are there to
                # be opened, not to be queued all at once.
                tracks=cached(f"{key}:top", _artist_level(artist, None)),
            )
        )
    return rows


def _is_mix(item: object) -> bool:
    """Whether a page item is a mix. The page of your mixes can carry other
    things besides them, and TIDAL rearranges it more often than favourites."""
    return getattr(item, "mix_type", None) is not None and callable(
        getattr(item, "items", None)
    )


def _mix_level(mix: Any, session: Any = None) -> Callable[[], list[Row]]:
    """A mix's tracks. One page, as TIDAL makes them, and no order but its
    own: a mix is not sorted and not edited, so its rows offer neither.

    The mixes on the pages of Descubrir are `MixV2`, which say what they are
    and not what they hold: that one is asked for in full when it is opened.
    """

    def level() -> list[Row]:
        full = mix
        if not callable(getattr(full, "items", None)):
            full = with_retries(lambda: session.mix(mix.id))
        try:
            items = with_retries(full.items)
        except ValueError:
            # tidalapi's word for a mix that came back with nothing in it.
            return []
        return _tracks_to_rows(
            item for item in items if not isinstance(item, tidalapi.media.Video)
        )

    return level


def _mix_rows(mixes: Iterable[Any], session: Any = None) -> list[Row]:
    rows = []
    for mix in mixes:
        key = f"mix:{mix.id}"
        rows.append(
            Row(
                label=mix.title or "",
                detail=getattr(mix, "sub_title", "") or "",
                key=key,
                loader=cached(key, _mix_level(mix, session)),
                art=_art_of(mix, 320),
            )
        )
    return rows


def _mixes_level(session: tidalapi.Session) -> Callable[[], list[Row]]:
    """Your mixes: the daily ones, discovery, new releases, and the rest of
    what TIDAL makes for the account, each opening like a playlist.

    `session.mixes()` is the page the official client shows as My Mixes.
    `user.mixes()` is another thing, the mixes someone saved as favourites.
    """

    def level() -> list[Row]:
        # Iterating a tidalapi Page yields its items, typed as callables.
        page: Any = with_retries(session.mixes)
        return _mix_rows((item for item in page if _is_mix(item)), session)

    return level


# ------------------------------------------------------------------ discover

# The pages Descubrir opens to, as TIDAL's own client names them. Home is the
# long one: what you played lately, albums and mixes made for you, new
# tracks. Explore is links, by genre, mood and decade, each a page of its own.
_DISCOVER_PAGES: tuple[tuple[str, str], ...] = (
    ("home", _("Inicio")),
    ("for_you", _("Para ti")),
    ("explore", _("Explorar")),
)


def _page_link(item: object) -> bool:
    """A link to another page of TIDAL's, as explore's genres are."""
    return isinstance(getattr(item, "api_path", None), str) and hasattr(item, "title")


def _item_rows(session: Any, items: Iterable[Any]) -> list[Row]:
    """The rows for whatever a page's category holds, in the order it gives.

    A category can mix kinds, as «Recently played» does. Anything the player
    cannot play or open is left out: videos, TIDAL's featured banners, text,
    and the items tidalapi could not parse, which it hands over as None.
    """
    rows: list[Row] = []
    for item in items:
        if item is None or isinstance(item, tidalapi.media.Video):
            continue
        if isinstance(item, tidalapi.Track):
            rows.extend(_tracks_to_rows([item]))
        elif isinstance(item, tidalapi.Album):
            rows.extend(_album_rows([item]))
        elif isinstance(item, tidalapi.Artist):
            rows.extend(_artist_rows([item]))
        elif isinstance(item, tidalapi.Playlist):
            rows.extend(_playlist_rows([item]))
        # By class and not by `mix_type`: the mixes on the home page come
        # with none (seen on 2026-09-14), and whole categories of them fell out.
        elif isinstance(item, tidalapi.mix.Mix | tidalapi.mix.MixV2):
            rows.extend(_mix_rows([item], session))
        elif _page_link(item):
            path = cast(str, item.api_path)
            key = f"page:{path}"
            rows.append(
                Row(
                    label=getattr(item, "title", "") or "",
                    detail=_("página"),
                    key=key,
                    loader=cached(
                        key, _page_level(session, partial(_page_at, session, path))
                    ),
                )
            )
    return rows


def _page_at(session: Any, path: str) -> Any:
    """The page at ``path``, fetched into a page object of its own.

    Not `PageLink.get`, which calls a `session.parse_page` tidalapi 0.8.11
    does not have; and not `session.page`, which `Page.get` overwrites and
    two levels loading at once would share.
    """
    from tidalapi.page import Page

    return Page(session, "").get(path)


def _page_level(session: Any, fetch: Callable[[], Any]) -> Callable[[], list[Row]]:
    """A page of TIDAL's as a level: one row per category, each opening to
    what it holds. A category with nothing playable in it is left out."""

    def level() -> list[Row]:
        page = with_retries(fetch)
        rows = []
        for category in getattr(page, "categories", None) or []:
            inner = _item_rows(session, getattr(category, "items", None) or [])
            if not inner:
                continue
            title = getattr(category, "title", "") or _("Más")
            rows.append(
                Row(
                    label=title,
                    detail=(
                        _("1 elemento")
                        if len(inner) == 1
                        else _("{count} elementos").format(count=len(inner))
                    ),
                    # Not cached by key: a page's categories have no id, and
                    # the page itself is, so its rows live as long as it does.
                    loader=partial(list, inner),
                )
            )
        return rows

    return level


def _discover_rows(session: Any) -> list[Row]:
    rows = []
    for name, label in _DISCOVER_PAGES:
        key = f"discover:{name}"
        rows.append(
            Row(
                label=label,
                key=key,
                loader=cached(key, _page_level(session, getattr(session, name))),
            )
        )
    return rows


def _free_track_rows(tracks: Iterable[Track]) -> list[Row]:
    rows = []
    for track in tracks:
        entry = Entry.from_free(track)
        rows.append(Row(label=entry.label, detail=entry.length, entry=entry))
    return rows


def _free_album_level(
    album: archive.Album, order: Order | None = None
) -> Callable[[], list[Row]]:
    """One item's tracks. A single request brings all of them, so there is no
    «más…» here and the level sorts locally like an album's does — which is
    why ``order`` is taken and ignored, exactly as `_album_level` does under
    ``local=True``."""
    return lambda: _free_track_rows(archive.tracks(album))


def _free_album_rows(albums: Iterable[archive.Album]) -> list[Row]:
    rows = []
    for album in albums:
        rows.append(
            Row(
                label=(
                    f"{album.creator} - {album.title}" if album.creator else album.title
                ),
                # The licence where a TIDAL album shows its year: it is the
                # reason this section exists, so it goes where it is read.
                detail=" · ".join(
                    part for part in (str(album.year or ""), album.licence) if part
                ),
                art=album.art_url,
                caption=album.title,
                byline=album.creator or album.licence,
                source=FREE,
                **_sortable(
                    f"free:{album.identifier}",
                    ALBUM_TRACK_BY,
                    partial(_free_album_level, album),
                    local=True,
                ),
            )
        )
    return rows


def _free_catalogue_level() -> Callable[[], list[Row]]:
    """Every record in the pool, in one level and one request.

    Not paged: the genre filter cut the pool to some 120 records, which is a
    level the browser draws without noticing, and `_paged` would have to trust
    the Archive's count — which counts what the junk filter then throws away,
    so it would offer a «más…» leading to nothing.
    """
    return lambda: _free_album_rows(archive.albums(limit=archive.POOL))


def _free_level() -> Callable[[], list[Row]]:
    """The day's station: its tracks, and the catalogue behind the last row.

    Tracks and not records, because this is a station: `a` on the row plays
    the day straight through, ↵ on a track plays that one, and nobody has to
    audition strangers a record at a time to hear something. The catalogue is
    still there for whoever wants to dig, as the last row, where the «más…»
    of every other level sits.
    """

    def load() -> list[Row]:
        rows = _free_track_rows(freemusic.station())
        # The catalogue is the Internet Archive's, so it only belongs under a
        # day the Archive drew. Under a Jamendo day it would be a browse of
        # some other library, with other records and other artists, which is
        # a worse thing to offer than nothing at all.
        if not jamendo.configured():
            rows.append(
                Row(
                    label=_("Todos los discos"),
                    detail=_("el catálogo entero"),
                    key="free:all",
                    loader=cached("free:all", _free_catalogue_level()),
                    source=FREE,
                )
            )
        return rows

    return load


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
        # Last, not next to the playlists: the four above are what the
        # account holds, and the tests and the muscle memory both count on
        # where they are.
        Row(
            _("Mis mixes"),
            "",
            key="mixes",
            loader=cached("mixes", _mixes_level(session)),
        ),
        # What TIDAL proposes rather than what you keep: its home page, the
        # one made for you, and explore's genres, moods and decades.
        Row(
            _("Descubrir"),
            "",
            key="discover",
            loader=cached("discover", partial(_discover_rows, session)),
        ),
        # The only level that is not TIDAL's. Last, after everything the
        # account holds and everything TIDAL proposes, because it is the odd
        # one out: no subscription, no session, and a licence on every row.
        Row(
            _("Lofi sin copyright"),
            # Experimental, and it says so, because what it can promise and
            # what somebody arrives wanting are not the same thing: the
            # «lofi hip hop radio» sound is a label's catalogue and none of
            # it is Creative Commons. This is the closest a free catalogue
            # gets, and the label is what keeps that honest.
            _("experimental · la selección de hoy"),
            key="free",
            loader=cached("free", _free_level()),
        ),
    ]


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


class NotLinked(RuntimeError):
    """The track does not say which artist or album it belongs to."""


def track_artists(session: tidalapi.Session, entry: Entry) -> list[tuple[int, str]]:
    """Every artist on ``entry``'s track as ``(id, name)``, the main one first.

    For «ir al artista», which asks which one when there are several. The
    track is resolved, which costs a request only on an entry restored from
    disk: one from a listing already carries it. Keeps the main one's id in
    `artist_id`, as `go_to` would.
    """
    track = with_retries(lambda: entry.resolve(session))
    main = getattr(track, "artist", None)
    found: list[tuple[int, str]] = []
    for artist in [main, *(getattr(track, "artists", None) or [])]:
        ident = int(getattr(artist, "id", 0) or 0)
        if ident and all(ident != known for known, _name in found):
            found.append((ident, getattr(artist, "name", "") or ""))
    if not found:
        raise NotLinked(_("TIDAL no dice de qué artista es esta pista"))
    entry.artist_id = found[0][0]
    return found


def go_to(session: tidalapi.Session, entry: Entry, kind: str, artist_id: int = 0) -> Row:
    """The row for the artist or the album of ``entry``, for the browser to
    open. For «ir al artista» and «ir al álbum» in the track menu.

    Network, so for a worker: one request for the artist or the album, and
    one more to resolve the track when the entry does not carry the id, as
    in a queue saved before `artist_id` existed. ``artist_id`` is the one
    picked when the track has several (see `track_artists`); without it,
    the main one.
    """
    if kind == "artist" and artist_id:
        artist = with_retries(lambda: session.artist(str(artist_id)))
        return _artist_rows([artist])[0]
    if kind == "album":
        if not entry.album_id:
            track = with_retries(lambda: entry.resolve(session))
            entry.album_id = int(getattr(getattr(track, "album", None), "id", 0) or 0)
        if not entry.album_id:
            raise NotLinked(_("TIDAL no dice de qué álbum es esta pista"))
        album = with_retries(lambda: session.album(str(entry.album_id)))
        return _album_rows([album])[0]
    if not entry.artist_id:
        track = with_retries(lambda: entry.resolve(session))
        entry.artist_id = int(getattr(getattr(track, "artist", None), "id", 0) or 0)
    if not entry.artist_id:
        raise NotLinked(_("TIDAL no dice de qué artista es esta pista"))
    artist = with_retries(lambda: session.artist(str(entry.artist_id)))
    return _artist_rows([artist])[0]


def favourite(session: tidalapi.Session, row: Row, add: bool = True) -> str:
    """Add or remove one row from the user's TIDAL favourites.

    There is deliberately no toggle. TIDAL's API offers no "is this a
    favourite?" question, so a toggle would have to either pull the whole
    favourites list or guess — and guessing wrong deletes something the user
    wanted. Two explicit verbs never lie.

    Returns a label for the status line; raises :class:`NotFavouritable` for a
    row that is a heading, a "más…" or a level rather than a piece of music.
    """
    if not row.is_tidal:
        # Not a failure to report as an error: favourites are a TIDAL
        # account's, and nothing in «Lofi sin copyright» is in one.
        raise NotFavouritable(
            _("«Lofi sin copyright» no está en TIDAL: no hay dónde guardarlo")
        )
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
