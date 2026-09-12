"""The library browser, and the footer and messages it shares with the app."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, cast

from rich.cells import cell_len
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from .. import library
from ..auth import ensure_fresh
from ..i18n import _
from ..library import Row
from ..widgets import Spinner
from .choice import ChoiceScreen
from .help import HelpScreen
from .rowlist import RowList
from .tracks import CONTAINER_ACTIONS, TrackActionsScreen

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    from ..app import TidalAmp


# The browser's footer: key, what it does, and how early it goes when the
# window is too narrow to hold the whole line — higher leaves first. Every one
# of these is in the help window too, so the line keeps what nobody would
# guess and drops what they would: `A` is `a` again on the whole level and
# reads as its pair, while `f/F` is a TIDAL account you can only find here.
BROWSER_HINTS: tuple[tuple[str, str, int], ...] = (
    # The rest of the keys live in `?`, which shows the browser's and no
    # others: a footer that tried to list them all dropped half of them on any
    # terminal narrower than the list.
    ("?", _("ayuda"), 1),
    ("esc", _("cerrar"), 0),
)


# Between two entries of the footer.
HINT_GAP = "   "


def fit_hints(hints: tuple[tuple[str, str, int], ...], width: int) -> str:
    """As much of the footer as fits, dropping by priority rather than by
    cropping the end.

    It used to be one literal string, and at 84 columns — the browser's own
    width — the terminal ate «R recargar   esc cerrar» off the right edge.
    A hint the user cannot read is not a hint, so the line now gives up whole
    entries, from the least essential, until the rest fits.
    """
    keep = list(hints)
    while keep:
        line = " " + HINT_GAP.join(f"{key} {label}" for key, label, _drop in keep)
        if cell_len(line) <= width:
            return line
        keep.remove(max(keep, key=lambda hint: (hint[2], hints.index(hint))))
    return ""


def favourite_message(session, row: Row, add: bool) -> str:
    """Do the favourite and phrase the result. Shared by both screens."""
    ensure_fresh(session)
    label = library.favourite(session, row, add)
    if add:
        return _("«{label}» añadido a favoritos").format(label=label)
    return _("«{label}» quitado de favoritos").format(label=label)


class BrowserScreen(ModalScreen[tuple | None]):
    """Drill-down browser over the library and over search results.

    Dismisses with ``("play", entries, index)`` or ``("append", entries, 0)``.
    """

    BINDINGS = [
        Binding("escape", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("pageup", "page_up", "", show=False),
        Binding("pagedown", "page_down", "", show=False),
        Binding("enter", "choose", _("abrir/reproducir"), show=False),
        Binding("slash", "filter", _("filtrar"), show=False),
        Binding("backspace,left", "back", _("atrás"), show=False),
        Binding("a", "append_one", _("añadir"), show=False),
        Binding("A", "append_all", _("añadir todo"), show=False),
        Binding("m", "menu", _("menú"), show=False),
        Binding("R", "reload", _("recargar"), show=False),
        Binding("s", "sort", _("ordenar"), show=False),
        Binding("d,delete", "remove", _("quitar"), show=False),
        Binding("question_mark", "help", _("ayuda"), show=False),
        Binding("f", "favourite", _("favorito"), show=False),
        Binding("F", "unfavourite", _("quitar favorito"), show=False),
    ]

    @property
    def player(self) -> TidalAmp:
        """The app this screen belongs to. Textual only types it as ``App``."""
        return cast("TidalAmp", self.app)

    def __init__(self, title: str, loader, key: str = "") -> None:
        super().__init__()
        self._root_title = title
        self._root_loader = loader
        self._root_key = key
        # Stack of (title, rows, key, loader, source) so backspace can walk
        # back up, `R` can refetch the level it is looking at, and `s` can ask
        # the row that opened it (`source`) how else it can be ordered.
        self._stack: list[tuple[str, list[Row], str, object, Row | None]] = []
        # The filter lives here, not in `RowList`: what it narrows is the level
        # on the stack, and the widget only ever shows the part that matched.
        self._filter = ""
        # What the list says when it has no rows to show, which is not the same
        # sentence while loading, after an error, and under a filter.
        self._empty = _("cargando…")

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-box"):
            with Horizontal(id="browser-head"):
                # markup=False: the title is a TIDAL name, and «[Deluxe
                # Edition]» would be read as a markup tag and dropped.
                yield Static(self._root_title, id="browser-title", markup=False)
                yield Spinner(id="browser-spinner")
            yield RowList(id="browser-list")
            # The filter bar, Firefox-style: it opens at the foot of the window
            # without covering the level, so the list narrows under the eyes of
            # whoever is typing. Hidden until `/`.
            with Horizontal(id="browser-filter-bar"):
                yield Input(placeholder=_("filtrar este nivel…"), id="browser-filter")
                # markup=False here and below: both carry text the user typed
                # or a TIDAL name, and a «[» in either would be read as a tag.
                yield Static("", id="browser-filter-count", markup=False)
            yield Static("", id="browser-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one("#browser-filter-bar", Horizontal).display = False
        self.query_one(RowList).empty_text = self._empty
        self._render_hint()
        self._busy(_("cargando {level}…").format(level=self._root_title.lower()))
        self._load(self._root_title, self._root_loader, self._root_key)

    def on_resize(self, event) -> None:
        self._render_hint()

    def _busy(self, label: str) -> None:
        self.query_one(Spinner).start(label)

    def _idle(self) -> None:
        self.query_one(Spinner).stop()

    @work(thread=True, exclusive=True)
    def _load(self, title: str, loader, key: str = "", source: Row | None = None) -> None:
        try:
            rows = loader()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self._push, title, rows, key, loader, source)

    def _failed(self, exc: Exception) -> None:
        self._idle()
        self._empty = _("error: {error}").format(error=exc)
        widget = self.query_one(RowList)
        widget.empty_text = self._empty
        widget.refresh()

    def _push(
        self,
        title: str,
        rows: list[Row],
        key: str = "",
        loader=None,
        source: Row | None = None,
    ) -> None:
        self._idle()
        self._stack.append((title, rows, key, loader, source))
        self._empty = _("vacío")
        # A filter belongs to the level it was typed in: opening another one
        # with the last level's word still applied would hide most of it.
        self._clear_filter()
        self.query_one("#browser-title", Static).update(self._titled(title, source))

    @staticmethod
    def _titled(title: str, source: Row | None) -> str:
        """The level's title, and its order when it is not TIDAL's own."""
        order = library.chosen(source) if source is not None else None
        if order is None:
            return title
        return f"{title}  ·  {library.order_label(order)}"

    # ----------------------------------------------------------------- view

    def _level(self) -> list[Row]:
        """The rows of the level on screen, filter or no filter.

        This is the list the cache handed out, so pages pulled with «más…» are
        spliced into it and are still there on the way back into the level.
        """
        return self._stack[-1][1] if self._stack else []

    def _visible(self) -> list[Row]:
        """The part of the level the filter lets through.

        The «más…» row always survives it. A level is one page deep until
        somebody asks for the rest, and a filter that hid the only way to ask
        would quietly claim that 12 of 766 favourites are all there is.
        """
        rows = self._level()
        if not self._filter:
            return rows
        return [
            row
            for row in rows
            if row.more is not None or library.matches(self._filter, row)
        ]

    def _show(self, cursor: int = 0) -> None:
        """Put the visible rows on screen with the cursor at ``cursor``."""
        widget = self.query_one(RowList)
        rows = self._visible()
        widget.empty_text = (
            _("nada coincide con «{query}»").format(query=self._filter)
            if self._filter
            else self._empty
        )
        widget.set_rows(rows)
        widget.cursor = max(0, min(cursor, len(rows) - 1))
        widget.refresh()
        self._render_hint()

    def _render_hint(self) -> None:
        """The footer, and the match count next to the filter box."""
        width = self.query_one("#browser-hint", Static).size.width
        self.query_one("#browser-hint", Static).update(fit_hints(BROWSER_HINTS, width))
        if not self.query_one("#browser-filter-bar", Horizontal).display:
            return
        # Rows, not lines: the «más…» row is neither a match nor a candidate.
        shown = sum(1 for row in self._visible() if row.more is None)
        total = sum(1 for row in self._level() if row.more is None)
        self.query_one("#browser-filter-count", Static).update(
            _("{shown} de {total}").format(shown=shown, total=total)
            if self._filter
            else _("{total} en este nivel").format(total=total)
        )

    # --------------------------------------------------------------- filter

    def action_filter(self) -> None:
        """Open the filter bar and start typing into it."""
        self.query_one("#browser-filter-bar", Horizontal).display = True
        self._render_hint()
        self.query_one("#browser-filter", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        value = event.value.strip()
        # `_clear_filter` empties the box itself; the message it posts arrives
        # afterwards and must not throw the cursor back to the top of a level
        # the user is already looking at.
        if value == self._filter:
            return
        self._filter = value
        self._show()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """↵ hands the keys back to the list and leaves the filter applied."""
        self.query_one("#browser-filter", Input).blur()
        self.set_focus(None)

    def _clear_filter(self) -> None:
        """Drop the filter and close its bar, keeping the cursor on the row it
        was on: the whole point of narrowing a level is to reach a row in it."""
        current = self.query_one(RowList).current
        self._filter = ""
        self.query_one("#browser-filter", Input).value = ""
        self.query_one("#browser-filter-bar", Horizontal).display = False
        self.set_focus(None)
        rows = self._level()
        self._show(next((i for i, row in enumerate(rows) if row is current), 0))

    # ------------------------------------------------------------------ keys

    def action_up(self) -> None:
        self.query_one(RowList).move(-1)

    def action_down(self) -> None:
        self.query_one(RowList).move(1)

    def action_page_up(self) -> None:
        self.query_one(RowList).move(-10)

    def action_page_down(self) -> None:
        self.query_one(RowList).move(10)

    def action_back(self) -> None:
        if len(self._stack) <= 1:
            self.dismiss(None)
            return
        # Going back while a level is still loading: the answer, when it
        # lands, is for a level the user has left.
        self._idle()
        self._stack.pop()
        title, _rows, _key, _loader, source = self._stack[-1]
        self._empty = _("vacío")
        self._clear_filter()
        self.query_one("#browser-title", Static).update(self._titled(title, source))

    def action_close(self) -> None:
        # esc closes the filter before it closes the window, the way it does
        # everywhere else: the first one undoes what the last key did.
        if self.query_one("#browser-filter-bar", Horizontal).display:
            self._clear_filter()
            return
        self.dismiss(None)

    def action_reload(self) -> None:
        """Refetch this level, past the cache.

        Levels are cached for the whole session, which is what makes walking
        the library feel instant — but a playlist created on the phone would
        otherwise never show up until tidalamp restarts. This is the way back.
        """
        if not self._stack:
            return
        title, _rows, key, loader, source = self._stack[-1]
        if loader is None:
            return
        library.forget(key)
        self._stack.pop()
        self._empty = _("cargando…")
        self._busy(_("recargando {level}…").format(level=title))
        self._load(title, loader, key, source)

    def action_sort(self) -> None:
        """Choose how the level on screen is ordered.

        The choice is remembered for this level until tidalamp quits, so
        walking out and back in keeps it. Each order is its own cached level:
        TIDAL sorts the whole collection, which a sort over the page already
        loaded could not do.
        """
        source = self._stack[-1][4] if self._stack else None
        if source is None or source.sort is None or not source.orders:
            self.player.status = _("este nivel no se puede ordenar")
            return
        # By code, not by the order itself: TIDAL's own order is None, and
        # None is also what the window answers on esc.
        by_code = {
            (order.code if order is not None else "original"): order
            for order in source.orders
        }
        current = library.chosen(source)
        self.app.push_screen(
            ChoiceScreen(
                _("ORDENAR"),
                [(code, library.order_label(order)) for code, order in by_code.items()],
                current.code if current is not None else "original",
            ),
            lambda code: self._sorted(source, by_code[code]) if code in by_code else None,
        )

    def _sorted(self, source: Row, order: library.Order | None) -> None:
        if order == library.chosen(source) or source.sort is None:
            return
        library.remember(source, order)
        key, loader = source.sort(order)
        title = self._stack[-1][0]
        self._stack.pop()
        self._empty = _("cargando…")
        self._busy(_("orden: {order}").format(order=library.order_label(order)))
        self._load(title, loader, key, source)

    def action_help(self) -> None:
        """The help window, with the browser's keys and nothing else."""
        # Here and not at the top: `app` imports this module.
        from ..app import keys_for

        self.app.push_screen(HelpScreen(keys_for, only="browser"))

    def action_remove(self) -> None:
        """Take the row out of where it is: favourites, or the playlist open.

        Asked first, with the cursor on «cancel», like restarting PipeWire:
        adding a track back to a playlist does not put it back where it was.
        """
        row = self.query_one(RowList).current
        source = self._stack[-1][4] if self._stack else None
        where = ""
        if row is not None and row.more is None and source is not None:
            kind, _sep, ident = source.key.partition(":")
            if source.key.startswith("fav:"):
                where = _("favoritos")
            elif kind == "playlist" and ident and row.entry is not None:
                where = f"«{source.label}»"
        if not where or row is None or source is None:
            self.player.status = _("aquí no hay de dónde quitar")
            return
        self.app.push_screen(
            ChoiceScreen(
                _("QUITAR"),
                [
                    (
                        "remove",
                        _("quitar «{label}» de {where}").format(
                            label=row.label, where=where
                        ),
                    ),
                    ("cancel", _("cancelar")),
                ],
                cursor=1,
            ),
            lambda answer: self._remove(row, source) if answer == "remove" else None,
        )

    def _remove(self, row: Row, source: Row) -> None:
        self._busy(_("quitando…"))
        self._remove_worker(row, source)

    @work(thread=True, exclusive=True, group="remove")
    def _remove_worker(self, row: Row, source: Row) -> None:
        session = self.player.session
        gone: Row | None = row
        try:
            if source.key.startswith("fav:"):
                message = favourite_message(session, row, False)
            else:
                assert row.entry is not None
                ensure_fresh(session)
                playlist = library.remove_from_playlist(
                    session, source.key.partition(":")[2], row.entry
                )
                message = _("«{label}» quitada de «{playlist}»").format(
                    label=row.label, playlist=playlist
                )
        except library.TrackNotInPlaylist:
            message = _("«{label}» ya no está en la playlist").format(label=row.label)
        except library.PlaylistNotWritable as exc:
            title = exc.args[0] if exc.args else ""
            message = _("«{title}» es de otra cuenta: no se puede quitar nada").format(
                title=title
            )
            gone = None
        except Exception as exc:
            message = _("quitar: {error}").format(error=exc)
            gone = None
        self.app.call_from_thread(self._removed, message, gone)

    def _removed(self, message: str, row: Row | None) -> None:
        self._idle()
        self.player.status = message
        if row is not None:
            self._drop(row)

    def action_choose(self) -> None:
        widget = self.query_one(RowList)
        row = widget.current
        if row is None:
            return
        if row.more is not None:
            # The title stays put: losing it to say "loading" costs the user
            # the one label that says where they are.
            self._busy(_("cargando más…"))
            self._load_more(row, row.more)
            return
        if row.loader is not None:
            self._empty = _("cargando…")
            widget.empty_text = self._empty
            self._busy(_("abriendo {label}…").format(label=row.label))
            key, loader = self._level_of(row)
            self._load(row.label, loader, key, row)
            return
        # A track offers more than one thing worth doing, so ask instead of
        # assuming. `a` still means what ↵ used to do on its own.
        self.app.push_screen(TrackActionsScreen(row.label), self._act_on_track)

    @staticmethod
    def _level_of(row: Row) -> tuple[str, Callable[[], list[Row]]]:
        """The cache key and loader a container opens to, in the order last
        picked for it, if one was."""
        order = library.chosen(row)
        if order is not None and row.sort is not None:
            return row.sort(order)
        assert row.loader is not None
        return row.key, row.loader

    def action_menu(self) -> None:
        """`m`: the track's menu on a track, and on an album, an artist or a
        playlist the same verbs over everything inside it."""
        row = self.query_one(RowList).current
        if row is None:
            return
        if row.entry is not None:
            self.app.push_screen(TrackActionsScreen(row.label), self._act_on_track)
        elif row.loader is not None:
            self.app.push_screen(
                TrackActionsScreen(row.label, CONTAINER_ACTIONS),
                partial(self._act_on_container, row),
            )

    def _act_on_container(self, row: Row, action: str | None) -> None:
        if action is None:
            return
        if action == "favourite":
            self._busy(_("añadiendo a favoritos…"))
            self._favourite_worker(row, True)
            return
        self._busy(_("cargando {label}…").format(label=row.label))
        self._container_worker(row, action)

    @work(thread=True, exclusive=True)
    def _container_worker(self, row: Row, action: str) -> None:
        _key, loader = self._level_of(row)
        try:
            entries = library.all_entries(loader)
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self.dismiss, (action, entries, 0))

    def _act_on_track(self, action: str | None) -> None:
        """Turn the menu's answer into the tuple the app already understands."""
        if action is None:
            return
        widget = self.query_one(RowList)
        row = widget.current
        if row is None or row.entry is None:
            return
        if action == "play":
            # The whole level goes into the queue, so the rest follows on —
            # the level as shown, so a filtered one queues what it narrowed to.
            entries = [r.entry for r in widget.rows if r.entry is not None]
            index = entries.index(row.entry) if row.entry in entries else 0
            self.dismiss(("play", entries, index))
            return
        self.dismiss((action, [row.entry], 0))

    @work(thread=True, exclusive=True)
    def _load_more(self, marker: Row, more) -> None:
        try:
            rows = more()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self._merge, marker, rows)

    def _merge(self, marker: Row, rows: list[Row]) -> None:
        """Turn the «más…» row into the page it just fetched, in place.

        By the row itself and not by its number, because under a filter the
        number on screen is not the number in the level. The splice lands on
        the level list — the one the cache handed out — so the page stays put
        for the next visit, and then the filter is applied again over it.
        """
        self._idle()
        level = self._level()
        index = next((i for i, row in enumerate(level) if row is marker), -1)
        if index < 0:
            return
        cursor = self.query_one(RowList).cursor
        level[index : index + 1] = rows
        self._show(cursor)

    def action_append_one(self) -> None:
        row = self.query_one(RowList).current
        if row is None:
            return
        if row.entry is not None:
            self.dismiss(("append", [row.entry], 0))
        elif row.loader is not None:
            # Appending a container means appending everything inside it.
            self._busy(_("añadiendo {label}…").format(label=row.label))
            self._append_container(self._level_of(row)[1])

    def action_favourite(self) -> None:
        self._favourite(True)

    def action_unfavourite(self) -> None:
        self._favourite(False)

    def _favourite(self, add: bool) -> None:
        row = self.query_one(RowList).current
        if row is None:
            return
        self._busy(_("añadiendo a favoritos…") if add else _("quitando de favoritos…"))
        self._favourite_worker(row, add)

    # Its own group again: an exclusive worker cancels its group, and the
    # level being loaded next door is not this one's business.
    @work(thread=True, exclusive=True, group="favourite")
    def _favourite_worker(self, row: Row, add: bool) -> None:
        try:
            message = favourite_message(self.player.session, row, add)
        except Exception as exc:
            self.app.call_from_thread(
                self._favourite_done, _("favoritos: {error}").format(error=exc)
            )
            return
        self.app.call_from_thread(self._favourite_done, message, row, add)

    def _favourite_done(
        self, message: str, row: Row | None = None, add: bool = True
    ) -> None:
        self._idle()
        self.player.status = message
        # `F` inside a favourites level takes the row out of it, as `d` does.
        source = self._stack[-1][4] if self._stack else None
        in_favourites = source is not None and source.key.startswith("fav:")
        if row is not None and not add and in_favourites:
            self._drop(row)

    def _drop(self, row: Row) -> None:
        """Take a row out of the level on screen, keeping the cursor's place."""
        level = self._level()
        index = next((i for i, candidate in enumerate(level) if candidate is row), -1)
        if index < 0:
            return
        cursor = self.query_one(RowList).cursor
        del level[index]
        self._show(cursor)

    @work(thread=True, exclusive=True)
    def _append_container(self, loader) -> None:
        try:
            # All of it, not the first page the level would open on.
            entries = library.all_entries(loader)
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self.dismiss, ("append", entries, 0))

    def action_append_all(self) -> None:
        widget = self.query_one(RowList)
        entries = [r.entry for r in widget.rows if r.entry is not None]
        if entries:
            self.dismiss(("append", entries, 0))
            return
        # A level made only of containers has nothing to append wholesale, so
        # fall back to appending the container under the cursor.
        self.action_append_one()
