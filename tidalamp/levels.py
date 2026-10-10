"""What every level of the browser is made of, whoever it comes from.

A level is a list of ``Row``. A row either plays (it carries an ``Entry``),
drills down (it carries a ``loader`` that fetches the next level), or extends
the level it lives in (it carries ``more``). Here are the row itself, the
cache of levels already fetched, the orders a level can be sorted in, the
paging that hangs «más…» off a long one and the matching the filters use.
Nothing here asks TIDAL anything: `library` builds TIDAL's levels out of it.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import STATE_DIR, write_atomically
from .i18n import _
from .net import with_retries
from .queue import TIDAL, Entry

# TIDAL paginates. We ask for one page at a time and hang a "más…" row off the
# end when the page came back full, so a 500-track playlist is reachable
# without pulling it whole on open.
PAGE = 100


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


def remember(row: Row, order: Order | None) -> OSError | None:
    """Keep ``order`` for the level ``row`` opens. Failing to write is not
    fatal: the order still holds for this session, and the error comes back
    so the app can say so."""
    orders = _orders()
    if order is None:
        orders.pop(row.key, None)
    else:
        orders[row.key] = order.code
    try:
        ORDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(ORDERS_FILE, json.dumps(orders, ensure_ascii=False))
    except OSError as exc:
        return exc
    return None


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
    # What `m` and `a` play when the level this row opens is not the tracks
    # themselves: an artist opens to its sections, and plays its popular ones.
    tracks: Callable[[], list[Row]] | None = None
    # The cover the grid draws for this row: an album's, a playlist's, an
    # artist's picture or a mix's. Empty for tracks and for headings.
    art: str = ""
    # A playlist this account made, which can be renamed, described, deleted
    # and reordered. Only the rows of «Mis playlists» are: a playlist found in
    # a search or in Descubrir may be someone else's.
    editable: bool = False
    description: str = ""
    # What a tile in the grid says, when it is not the label: an album's
    # label is «artist - name», and sixteen cells of that keep only the
    # artist. The name goes on the tile's first line and the artist under it.
    caption: str = ""
    byline: str = ""
    # Where the level under this row comes from, as `Entry.source` says it
    # for a track. Only «Lofi sin copyright» is not TIDAL's, and the screens
    # read it to know which verbs to offer over the row.
    source: str = TIDAL

    @property
    def is_playable(self) -> bool:
        return self.entry is not None

    @property
    def is_tidal(self) -> bool:
        """Whether TIDAL can be asked about this row: favourites, playlists,
        the radio, the artist behind it."""
        if self.entry is not None:
            return self.entry.is_tidal
        return self.source == TIDAL


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


def all_entries(loader: Callable[[], list[Row]]) -> list[Entry]:
    """Every track a level holds, following its "más…" rows to the end.

    Opening a level shows one page; playing or adding a whole album or
    playlist means all of it, not the first hundred tracks.
    """
    entries: list[Entry] = []
    rows = loader()
    while True:
        entries.extend(row.entry for row in rows if row.entry is not None)
        more = next((row.more for row in rows if row.more is not None), None)
        if more is None:
            return entries
        rows = more()


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
