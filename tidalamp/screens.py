"""The modal windows stacked over the main panel: search, library, EQ, lyrics.

They own no player state. Each one is handed what it needs at construction —
a session, a loader, a `Settings` — and reports back through `dismiss`, which
is what keeps `app.py` from having to know how any of them are laid out.

`RowList` lives here rather than in `widgets.py` because it renders a
`library.Row`, and `library` imports tidalapi: putting it there would drag
TIDAL into the one module that is deliberately ignorant of it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Static

from . import about, audio, columns, config, library
from .auth import ensure_fresh
from .i18n import _
from .library import Row
from .lyrics import LyricsDocument
from .settings import BAND_LABELS, GAIN_LIMIT, Settings
from .theme import LAYOUTS, available_palettes, palette_for
from .widgets import EqualizerBars, Slider, Spinner

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    from .app import TidalAmp


class RowList(Widget):
    """A scrolling list of rows with a cursor. Used by both panes."""

    cursor = reactive(0)
    marked = reactive(-1)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows: list[Row] = []
        self.empty_text = ""

    def set_rows(self, rows: list[Row]) -> None:
        self.rows = rows
        self.cursor = 0
        self.refresh()

    def extend_at(self, index: int, rows: list[Row]) -> None:
        """Replace the row at ``index`` with ``rows``. This is how a "más…"
        row turns into the page it just fetched, in place, without losing the
        user's scroll position."""
        if not 0 <= index < len(self.rows):
            return
        self.rows[index : index + 1] = rows
        self.cursor = min(index, max(0, len(self.rows) - 1))
        self.refresh()

    def move(self, delta: int) -> None:
        if self.rows:
            self.cursor = max(0, min(len(self.rows) - 1, self.cursor + delta))
            self.refresh()

    @property
    def current(self) -> Row | None:
        if 0 <= self.cursor < len(self.rows):
            return self.rows[self.cursor]
        return None

    # The gap between two columns, and the room the title needs before it
    # stops being worth having columns at all.
    GAP = 2
    TITLE_MIN = 24

    # A flexible column takes a share of the list, floored so one that appears
    # at all can say something and capped so a very wide terminal spends its
    # slack on the title — generously enough that «Tú Me Vuelves Loco
    # (Bailable)» still fits.
    SHARE = 6
    SHARE_MIN = 12
    SHARE_MAX = 30

    @staticmethod
    def _cell(text: str, width: int, align: str) -> str:
        """One column, cropped to its width. Right-aligned pads on the left,
        so digits and years line up on their last cell."""
        if align != "right":
            return set_cell_size(text, width)
        trimmed = set_cell_size(text, min(cell_len(text), width))
        return " " * (width - cell_len(trimmed)) + trimmed

    @classmethod
    def _fit(cls, chosen: list, width: int, detail_width: int) -> list[tuple]:
        """Which of the chosen columns fit, and how wide each one is.

        Drops from the least useful end until the title has room to breathe,
        rather than picking thresholds by hand: that way a column added to the
        catalogue needs no new number here.
        """
        share = min(cls.SHARE_MAX, max(cls.SHARE_MIN, width // cls.SHARE))
        keep = sorted(chosen, key=lambda column: column.drop, reverse=True)
        while keep:
            sized = [
                (
                    column,
                    detail_width
                    if column.name == "duration"
                    else (column.width or share),
                )
                for column in chosen
                if column in keep
            ]
            spent = sum(size + cls.GAP for _column, size in sized)
            if width - spent >= cls.TITLE_MIN:
                return sized
            keep.pop(0)
        return []

    @classmethod
    def _line(
        cls, row: Row, index: int, marked: int, width: int, detail_width: int
    ) -> str:
        """Fit one row by terminal cells, in columns when there is room.

        `detail_width` is the widest detail in the whole list, not this row's
        own. Measured per row, a `11:53` next to a `5:07` moved the album
        column a cell to the left on the longer ones, and a column that only
        lines up when every track is under ten minutes is not a column.

        A row with no entry — an album, an artist, a playlist in the browser —
        has nothing to put in those columns, so it keeps the whole line for
        its own name, with its detail on the right as before.
        """
        marker = "▶" if index == marked else (" " if row.is_playable else "›")
        entry = row.entry
        chosen = [
            columns.BY_NAME[name] for name in config.COLUMNS if name in columns.BY_NAME
        ]
        sized = cls._fit(chosen, width, detail_width) if entry is not None else []
        # A row of nothing but the duration is the old layout with extra
        # steps, and it would drop the artist on the floor: the artist only
        # leaves the label when it has a column of its own to go to.
        shown = {column.name for column, _size in sized}
        if not shown - {"duration"}:
            sized = []

        if sized and entry is not None:
            head = f"{marker}{index + 1:>3}. "
            title_width = width - sum(size + cls.GAP for _c, size in sized)
            name = entry.title if "artist" in shown else row.label
            line = head + set_cell_size(name, title_width - cell_len(head))
            for column, size in sized:
                # `duration` draws the row's detail, not the entry's: a
                # browser row that is not a track puts «101 pistas» there.
                text = row.detail if column.name == "duration" else column.read(entry)
                line += " " * cls.GAP + cls._cell(text, size, column.align)
            return set_cell_size(line, width)

        detail = cls._cell(row.detail, detail_width, "right") if detail_width else ""
        left = f"{marker}{index + 1:>3}. {row.label}"
        left_width = width - detail_width - (1 if detail else 0)
        line = set_cell_size(left, max(0, left_width))
        if detail:
            line += f" {detail}"
        return set_cell_size(line, width)

    def render(self) -> Text:
        palette = palette_for(self)
        if not self.rows:
            return Text(f"  {self.empty_text}", style=palette["empty"])

        height = max(1, self.size.height)
        width = max(1, self.size.width)
        # Keep the cursor in view without a full scrolling container.
        start = max(0, min(self.cursor - height // 2, len(self.rows) - height))
        # One column width for the whole list, from the widest detail on it.
        detail_width = min(
            max(cell_len(row.detail) for row in self.rows), max(0, width // 3)
        )
        out = Text()
        for i in range(start, min(len(self.rows), start + height)):
            row = self.rows[i]
            line = self._line(row, i, self.marked, width, detail_width)
            if i == self.cursor:
                out.append(
                    line,
                    style=(f"bold {palette['active_foreground']} on {palette['accent']}"),
                )
            elif i == self.marked:
                out.append(line, style=f"bold {palette['accent']}")
            elif not row.is_playable:
                out.append(line, style=palette["container"])
            else:
                out.append(line, style=palette["playable"])
            out.append("\n")
        return out


class SearchScreen(ModalScreen[str]):
    """The search prompt."""

    BINDINGS = [Binding("escape", "dismiss_search", _("cancelar"))]

    def compose(self) -> ComposeResult:
        with Vertical(id="search-box"):
            yield Static(_("BUSCAR EN TIDAL"), id="search-title")
            yield Input(placeholder=_("artista, canción o álbum…"), id="search-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_dismiss_search(self) -> None:
        self.dismiss("")


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
        Binding("backspace,left", "back", _("atrás"), show=False),
        Binding("a", "append_one", _("añadir"), show=False),
        Binding("A", "append_all", _("añadir todo"), show=False),
        Binding("R", "reload", _("recargar"), show=False),
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
        # Stack of (title, rows, key, loader) so backspace can walk back up and
        # `R` can refetch the level it is looking at.
        self._stack: list[tuple[str, list[Row], str, object]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-box"):
            with Horizontal(id="browser-head"):
                # markup=False: the title is a TIDAL name, and «[Deluxe
                # Edition]» would be read as a markup tag and dropped.
                yield Static(self._root_title, id="browser-title", markup=False)
                yield Spinner(id="browser-spinner")
            yield RowList(id="browser-list")
            yield Static(
                _(
                    " ↵ abrir/reproducir   a añadir   A añadir todo   f/F favorito"
                    "   ⌫ atrás   R recargar   esc cerrar"
                ),
                id="browser-hint",
            )

    def on_mount(self) -> None:
        self.query_one(RowList).empty_text = _("cargando…")
        self._busy(_("cargando {level}…").format(level=self._root_title.lower()))
        self._load(self._root_title, self._root_loader, self._root_key)

    def _busy(self, label: str) -> None:
        self.query_one(Spinner).start(label)

    def _idle(self) -> None:
        self.query_one(Spinner).stop()

    @work(thread=True, exclusive=True)
    def _load(self, title: str, loader, key: str = "") -> None:
        try:
            rows = loader()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self._push, title, rows, key, loader)

    def _failed(self, exc: Exception) -> None:
        self._idle()
        widget = self.query_one(RowList)
        widget.empty_text = _("error: {error}").format(error=exc)
        widget.refresh()

    def _push(self, title: str, rows: list[Row], key: str = "", loader=None) -> None:
        self._idle()
        self._stack.append((title, rows, key, loader))
        widget = self.query_one(RowList)
        widget.empty_text = _("vacío")
        widget.set_rows(rows)
        self.query_one("#browser-title", Static).update(title)

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
        title, rows, _key, _loader = self._stack[-1]
        widget = self.query_one(RowList)
        widget.set_rows(rows)
        self.query_one("#browser-title", Static).update(title)

    def action_close(self) -> None:
        self.dismiss(None)

    def action_reload(self) -> None:
        """Refetch this level, past the cache.

        Levels are cached for the whole session, which is what makes walking
        the library feel instant — but a playlist created on the phone would
        otherwise never show up until tidalamp restarts. This is the way back.
        """
        if not self._stack:
            return
        title, _rows, key, loader = self._stack[-1]
        if loader is None:
            return
        library.forget(key)
        self._stack.pop()
        self._busy(_("recargando {level}…").format(level=title))
        self._load(title, loader, key)

    def action_choose(self) -> None:
        widget = self.query_one(RowList)
        row = widget.current
        if row is None:
            return
        if row.more is not None:
            # The title stays put: losing it to say "loading" costs the user
            # the one label that says where they are.
            self._busy(_("cargando más…"))
            self._load_more(widget.cursor, row.more)
            return
        if row.loader is not None:
            self.query_one(RowList).empty_text = _("cargando…")
            self._busy(_("abriendo {label}…").format(label=row.label))
            self._load(row.label, row.loader, row.key)
            return
        # A track offers more than one thing worth doing, so ask instead of
        # assuming. `a` still means what ↵ used to do on its own.
        self.app.push_screen(TrackActionsScreen(row.label), self._act_on_track)

    def _act_on_track(self, action: str | None) -> None:
        """Turn the menu's answer into the tuple the app already understands."""
        if action is None:
            return
        widget = self.query_one(RowList)
        row = widget.current
        if row is None or row.entry is None:
            return
        if action == "play":
            # The whole level goes into the queue, so the rest follows on.
            entries = [r.entry for r in widget.rows if r.entry is not None]
            index = entries.index(row.entry) if row.entry in entries else 0
            self.dismiss(("play", entries, index))
            return
        self.dismiss((action, [row.entry], 0))

    @work(thread=True, exclusive=True)
    def _load_more(self, index: int, more) -> None:
        try:
            rows = more()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self._merge, index, rows)

    def _merge(self, index: int, rows: list[Row]) -> None:
        self._idle()
        widget = self.query_one(RowList)
        widget.extend_at(index, rows)
        # The stack holds the level so backspace can restore it; keep it in
        # sync with what is now on screen.
        if self._stack:
            title, _rows, key, loader = self._stack[-1]
            self._stack[-1] = (title, widget.rows, key, loader)
            self.query_one("#browser-title", Static).update(title)

    def action_append_one(self) -> None:
        row = self.query_one(RowList).current
        if row is None:
            return
        if row.entry is not None:
            self.dismiss(("append", [row.entry], 0))
        elif row.loader is not None:
            # Appending a container means appending everything inside it.
            self._busy(_("añadiendo {label}…").format(label=row.label))
            self._append_container(row.loader)

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
        self.app.call_from_thread(self._favourite_done, message)

    def _favourite_done(self, message: str) -> None:
        self._idle()
        self.player.status = message

    @work(thread=True, exclusive=True)
    def _append_container(self, loader) -> None:
        try:
            rows = loader()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        entries = [r.entry for r in rows if r.entry is not None]
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


class ColumnsScreen(ModalScreen[None]):
    """Pick the queue's columns.

    A window of its own rather than more rows on the settings screen: this is
    a set of toggles, and the settings screen cycles values. The order is the
    catalogue's, not the order they were switched on, so the list reads the
    same as the queue it describes.
    """

    BINDINGS = [
        Binding("escape,o", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("enter,space", "pick", _("marcar"), show=False),
        Binding("0", "reset", _("por defecto"), show=False),
    ]

    cursor = reactive(0)

    def __init__(self, on_change=None) -> None:
        super().__init__()
        self._on_change = on_change
        self._chosen = list(config.COLUMNS)

    def compose(self) -> ComposeResult:
        with Vertical(id="columns-box"):
            yield Static(_("▓ COLUMNAS DE LA COLA ▓"), id="columns-title")
            yield Static("", id="columns-list", markup=False)
            yield Static(
                _(" ↑↓ elegir   ↵ marcar   0 reset   o/esc cerrar"),
                id="columns-hint",
            )

    def on_mount(self) -> None:
        self._render_list()

    def watch_cursor(self) -> None:
        if self.is_mounted:
            self._render_list()

    def _render_list(self) -> None:
        palette = palette_for(self)
        widget = self.query_one("#columns-list", Static)
        room = widget.size.width or 46
        labels = max(cell_len(column_label(c.name)) for c in columns.ALL)

        rendered = Text()
        for index, column in enumerate(columns.ALL):
            selected = index == self.cursor
            style = (
                f"bold {palette['active_foreground']} on {palette['accent']}"
                if selected
                else palette["body"]
            )
            mark = "x" if column.name in self._chosen else " "
            row = (
                f" {'›' if selected else ' '} [{mark}] "
                f"{set_cell_size(column_label(column.name), labels)}"
            )
            rendered.append(_crop(row, room) + "\n", style=style)
        rendered.append("\n")
        rendered.append(
            _crop(
                _("  {count} de {total} · nº de cola y título van siempre").format(
                    count=len(self._chosen), total=len(columns.ALL)
                ),
                room,
            ),
            style=palette["muted"],
        )
        widget.update(rendered)

    # --------------------------------------------------------------- actions

    def action_up(self) -> None:
        self.cursor = (self.cursor - 1) % len(columns.ALL)

    def action_down(self) -> None:
        self.cursor = (self.cursor + 1) % len(columns.ALL)

    def action_pick(self) -> None:
        name = columns.ALL[self.cursor].name
        if name in self._chosen:
            self._chosen.remove(name)
        else:
            self._chosen.append(name)
        self._save()

    def action_reset(self) -> None:
        self._chosen = list(columns.DEFAULT)
        self._save()

    def _save(self) -> None:
        # Written in the catalogue's order, so the file reads the way the
        # queue is drawn rather than in the order things were clicked.
        ordered = [c.name for c in columns.ALL if c.name in self._chosen]
        config.set_option("columns", ",".join(ordered))
        if self._on_change is not None:
            self._on_change("columns")
        self._render_list()

    def action_close(self) -> None:
        self.dismiss(None)


def column_label(name: str) -> str:
    """The catalogue's names are for the config file; these are for people.

    Looked up at call time rather than stored on the Column, so switching
    language re-translates them instead of freezing whatever was current at
    import.
    """
    return {
        "track": _("Nº dentro del álbum"),
        "version": _("Versión"),
        "artist": _("Artista"),
        "album": _("Álbum"),
        "year": _("Año"),
        "quality": _("Calidad del stream"),
        "explicit": _("Explícito"),
        "popularity": _("Popularidad"),
        "disc": _("Disco"),
        "isrc": _("ISRC"),
        "duration": _("Duración"),
    }.get(name, name)


class EqScreen(ModalScreen[None]):
    """The equaliser window: ten bands and a balance, applied live.

    Every change goes straight to mpv rather than waiting for an OK button —
    an equaliser you cannot hear while you move it is useless.
    """

    BINDINGS = [
        Binding("escape,e", "close", _("cerrar")),
        Binding("left", "prev_band", _("banda anterior"), show=False),
        Binding("right", "next_band", _("banda siguiente"), show=False),
        Binding("up", "boost", _("subir"), show=False),
        Binding("down", "cut", _("bajar"), show=False),
        Binding("0", "reset", _("plano"), show=False),
        Binding("comma", "balance_left", _("balance izq"), show=False),
        Binding("full_stop", "balance_right", _("balance der"), show=False),
        Binding("backslash", "balance_centre", _("centrar"), show=False),
    ]

    def __init__(self, settings: Settings, apply) -> None:
        super().__init__()
        self.settings = settings
        self._apply = apply

    def compose(self) -> ComposeResult:
        with Vertical(id="eq-box"):
            yield Static(_("▓ ECUALIZADOR ▓"), id="eq-title")
            yield EqualizerBars(id="eq-bars")
            yield Slider(id="eq-balance")
            yield Static(
                _(" ←→ banda  ↑↓ ±1 dB  0 plano  ,. balance  \\ centro  esc"),
                id="eq-hint",
            )

    def on_mount(self) -> None:
        bars = self.query_one(EqualizerBars)
        bars.labels = BAND_LABELS
        bars.limit = GAIN_LIMIT
        balance = self.query_one("#eq-balance", Slider)
        balance.label = "BAL"
        balance.centred = True
        self._redraw()

    def _redraw(self) -> None:
        bars = self.query_one(EqualizerBars)
        bars.gains = list(self.settings.gains)
        self.query_one("#eq-balance", Slider).value = int(self.settings.balance * 100)
        bars.refresh()

    def _band(self) -> int:
        return self.query_one(EqualizerBars).selected

    def _nudge(self, delta: float) -> None:
        band = self._band()
        self.settings.set_gain(band, self.settings.gains[band] + delta)
        self._apply()
        self._redraw()

    def action_prev_band(self) -> None:
        bars = self.query_one(EqualizerBars)
        bars.selected = max(0, bars.selected - 1)
        bars.refresh()

    def action_next_band(self) -> None:
        bars = self.query_one(EqualizerBars)
        bars.selected = min(len(self.settings.gains) - 1, bars.selected + 1)
        bars.refresh()

    def action_boost(self) -> None:
        self._nudge(1.0)

    def action_cut(self) -> None:
        self._nudge(-1.0)

    def action_reset(self) -> None:
        self.settings.reset_eq()
        self._apply()
        self._redraw()

    def _slide(self, delta: float) -> None:
        self.settings.set_balance(self.settings.balance + delta)
        self._apply()
        self._redraw()

    def action_balance_left(self) -> None:
        self._slide(-0.1)

    def action_balance_right(self) -> None:
        self._slide(0.1)

    def action_balance_centre(self) -> None:
        self.settings.set_balance(0.0)
        self._apply()
        self._redraw()

    def action_close(self) -> None:
        self.dismiss(None)


class LyricsScreen(ModalScreen[None]):
    """Lyrics for one track, synchronized to the player when LRC is present."""

    BINDINGS = [
        Binding("escape,y", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("pageup", "page_up", "", show=False),
        Binding("pagedown", "page_down", "", show=False),
    ]

    def __init__(
        self,
        title: str,
        loader: Callable[[], LyricsDocument],
        position: Callable[[], float],
    ) -> None:
        super().__init__()
        self._track_title = title
        self._loader = loader
        self._position = position
        self._document: LyricsDocument | None = None
        self._plain_offset = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="lyrics-box"):
            with Horizontal(id="lyrics-head"):
                yield Static(
                    _("▓ LETRA ▓  {title}").format(title=self._track_title),
                    id="lyrics-title",
                    markup=False,
                )
                yield Spinner(id="lyrics-spinner")
            yield Static("  " + _("cargando…"), id="lyrics-body", markup=False)
            yield Static(_(" ↑↓ desplazar   y/esc cerrar"), id="lyrics-hint")

    def on_mount(self) -> None:
        self.query_one(Spinner).start(_("buscando la letra…"))
        self._load()
        self.set_interval(1 / 4, self._refresh_lyrics)

    @work(thread=True, exclusive=True)
    def _load(self) -> None:
        try:
            document = self._loader()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self._loaded, document)

    def _loaded(self, document: LyricsDocument) -> None:
        self.query_one(Spinner).stop()
        self._document = document
        mode = _("sincronizada") if document.synced else _("texto")
        provider = f" · {document.provider}" if document.provider else ""
        self.query_one("#lyrics-title", Static).update(
            _("▓ LETRA ▓  {title} · {mode}{provider}").format(
                title=self._track_title, mode=mode, provider=provider
            )
        )
        self._refresh_lyrics()

    def _failed(self, exc: Exception) -> None:
        self.query_one(Spinner).stop()
        self.query_one("#lyrics-body", Static).update(f"  {exc}")

    def _refresh_lyrics(self) -> None:
        document = self._document
        if document is None:
            return
        body = self.query_one("#lyrics-body", Static)
        height = max(5, body.size.height)
        if document.synced:
            start, lines, active = document.window(self._position(), height)
        else:
            self._plain_offset = max(
                0, min(self._plain_offset, max(0, len(document.lines) - height))
            )
            start = self._plain_offset
            lines = document.lines[start : start + height]
            active = None

        rendered = Text()
        palette = palette_for(self)
        for offset, line in enumerate(lines):
            index = start + offset
            marker = "▶ " if index == active else "  "
            style = (
                f"bold {palette['active_foreground']} on {palette['accent']}"
                if index == active
                else palette["body"]
            )
            rendered.append(f"{marker}{line.text}\n", style=style)
        body.update(rendered)

    def _scroll_plain(self, amount: int) -> None:
        if self._document is None or self._document.synced:
            return
        self._plain_offset += amount
        self._refresh_lyrics()

    def action_up(self) -> None:
        self._scroll_plain(-1)

    def action_down(self) -> None:
        self._scroll_plain(1)

    def action_page_up(self) -> None:
        self._scroll_plain(-8)

    def action_page_down(self) -> None:
        self._scroll_plain(8)

    def action_close(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    """Every key the app answers to, plus who wrote it and what changed.

    Built from the *effective* bindings, not from a hardcoded list: `keys` is
    the app's resolver, so a key rebound in `config.toml` shows up here as the
    key the user actually has to press.
    """

    BINDINGS = [
        Binding("escape,question_mark,h", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("pageup", "page_up", "", show=False),
        Binding("pagedown", "page_down", "", show=False),
        Binding("home", "top", "", show=False),
        Binding("end", "bottom", "", show=False),
    ]

    def __init__(self, keys: Callable[[str], str]) -> None:
        super().__init__()
        self._keys = keys
        self._offset = 0
        # Built once on mount: nothing in it changes while the screen is open.
        self._lines: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static(
                _("▓ AYUDA ▓  {name} {version}").format(
                    name="TIDAL AMP", version=about.version()
                ),
                id="help-title",
            )
            yield Static("", id="help-body", markup=False)
            yield Static(_(" ↑↓ desplazar   ?/h/esc cerrar"), id="help-hint")

    def on_mount(self) -> None:
        self._lines = self._build()
        self._render_window()

    # ------------------------------------------------------------- content

    def _build(self) -> list[tuple[str, str]]:
        """The whole document as (style, text) pairs, top to bottom.

        A flat list rather than a scrolling container: the screen windows it
        by hand, the way the plain-text lyrics do, so it needs no widget that
        the compositor would have to scroll.
        """
        lines: list[tuple[str, str]] = []

        for section in about.shortcuts(self._keys):
            lines.append(("heading", section.title))
            width = max(len(key) for key, _description in section.rows)
            for key, description in section.rows:
                lines.append(("row", f"  {key:<{width}}   {description}"))
            lines.append(("blank", ""))

        lines.append(("heading", _("Acerca de")))
        for text in (
            _("Cliente de TIDAL para terminal con la estética de Winamp 2.x."),
            _("Reproduce con mpv; el catálogo y los streams vienen de tidalapi."),
        ):
            lines.append(("row", f"  {text}"))
        lines.append(("blank", ""))
        for label, value in (
            (_("Versión"), about.version()),
            (_("Autor"), about.AUTHOR),
            (_("Repositorio"), about.REPO_URL),
            (_("Licencia"), about.LICENSE),
            ("", about.LICENSE_URL),
        ):
            # An empty label is a continuation line — the licence URL under
            # the licence name — and must not grow a stray colon.
            field = f"{label}:" if label else ""
            lines.append(("row", f"  {field:<14}{value}"))
        lines.append(("blank", ""))
        for text in (
            _("Software libre, sin garantía de ningún tipo."),
            _("Sin relación con TIDAL, Aspiro ni los dueños de la marca Winamp."),
        ):
            lines.append(("row", f"  {text}"))
        lines.append(("blank", ""))

        lines.append(("heading", _("Cambios por versión")))
        for release in about.releases():
            lines.append(("row", f"  {release.version} — {release.date}"))
            for change in release.changes:
                lines.append(("row", f"    · {change}"))
            lines.append(("blank", ""))

        while lines and lines[-1][0] == "blank":
            lines.pop()
        return lines

    # ------------------------------------------------------------ scrolling

    def _height(self) -> int:
        return max(5, self.query_one("#help-body", Static).size.height)

    def _render_window(self) -> None:
        height = self._height()
        self._offset = max(0, min(self._offset, max(0, len(self._lines) - height)))
        palette = palette_for(self)
        styles = {
            "heading": f"bold {palette['accent']}",
            "row": palette["body"],
            "blank": palette["body"],
        }
        rendered = Text()
        for kind, text in self._lines[self._offset : self._offset + height]:
            rendered.append(f"{text}\n", style=styles[kind])
        self.query_one("#help-body", Static).update(rendered)

    def _scroll(self, amount: int) -> None:
        self._offset += amount
        self._render_window()

    def on_resize(self, event) -> None:
        self._render_window()

    def action_up(self) -> None:
        self._scroll(-1)

    def action_down(self) -> None:
        self._scroll(1)

    def action_page_up(self) -> None:
        self._scroll(-self._height())

    def action_page_down(self) -> None:
        self._scroll(self._height())

    def action_top(self) -> None:
        self._offset = 0
        self._render_window()

    def action_bottom(self) -> None:
        self._offset = len(self._lines)
        self._render_window()

    def action_close(self) -> None:
        self.dismiss(None)


# What ↵ on a track offers, in the order the menu shows them: the action the
# browser reports back, the icon, and the label. The letters are the keys, and
# they double as the first letter of nothing else in the list.
# Literal _() here, the way every BINDINGS list in this file does it: the
# catalogue is chosen when i18n is imported, which is before this module.
TRACK_ACTIONS: tuple[tuple[str, str, str, str], ...] = (
    ("play", "▶", "a", _("reproducir ahora")),
    ("next", "↳", "c", _("reproducir a continuación")),
    ("radio", "≈", "d", _("reproducir la radio de la pista")),
    ("favourite", "♥", "v", _("añadir a favoritos")),
)


class TrackActionsScreen(ModalScreen[str | None]):
    """The little menu ↵ opens over a track.

    Four things a user wants from a search result, none of which the browser
    could offer before: ↵ always queued the whole level. Dismisses with the
    action name, or ``None`` when the user backs out.
    """

    BINDINGS = [
        Binding("escape", "close", _("cancelar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("enter", "choose", _("elegir"), show=False),
        *[
            Binding(letter, f"pick_{action}", "", show=False)
            for action, _icon, letter, _label in TRACK_ACTIONS
        ],
    ]

    cursor = reactive(0)

    def __init__(self, label: str) -> None:
        super().__init__()
        self._label = label

    def compose(self) -> ComposeResult:
        with Vertical(id="actions-box"):
            yield Static(self._label, id="actions-title", markup=False)
            yield Static("", id="actions-list", markup=False)
            yield Static(_(" ↑↓ elegir   ↵ aceptar   esc cancelar"), id="actions-hint")

    def on_mount(self) -> None:
        self._render_list()

    def watch_cursor(self) -> None:
        # Fires before compose on the way up, when there is nothing to draw.
        if self.is_mounted:
            self._render_list()

    def _render_list(self) -> None:
        palette = palette_for(self)
        rendered = Text()
        for index, (_action, icon, letter, label) in enumerate(TRACK_ACTIONS):
            selected = index == self.cursor
            # «›», not the «▶» the playlist uses: one of the icons is itself a
            # «▶», and two of them side by side read as one smudge.
            marker = "›" if selected else " "
            style = (
                f"bold {palette['active_foreground']} on {palette['accent']}"
                if selected
                else palette["body"]
            )
            line = f" {marker} {icon}  {label}  [{letter}]"
            rendered.append(line, style=style)
            if index < len(TRACK_ACTIONS) - 1:
                rendered.append("\n")
        self.query_one("#actions-list", Static).update(rendered)

    def action_up(self) -> None:
        self.cursor = (self.cursor - 1) % len(TRACK_ACTIONS)

    def action_down(self) -> None:
        self.cursor = (self.cursor + 1) % len(TRACK_ACTIONS)

    def action_choose(self) -> None:
        self.dismiss(TRACK_ACTIONS[self.cursor][0])

    def action_close(self) -> None:
        self.dismiss(None)

    def action_pick_play(self) -> None:
        self.dismiss("play")

    def action_pick_next(self) -> None:
        self.dismiss("next")

    def action_pick_radio(self) -> None:
        self.dismiss("radio")

    def action_pick_favourite(self) -> None:
        self.dismiss("favourite")


def _crop(text: str, width: int) -> str:
    """One line, ellipsised rather than wrapped."""
    if cell_len(text) <= width:
        return text
    if width <= 0:
        return ""
    return set_cell_size(text, max(0, width - 1)) + "…"


@dataclass(frozen=True)
class Option:
    """One line of the config screen.

    ``key`` is the config file's, when the row writes one; ``choices`` are the
    values ↵ cycles through. A row with neither is a system action, and
    ``action`` names which one.
    """

    label: str
    key: str = ""
    choices: tuple[str, ...] = ()
    action: str = ""
    note: str = ""


class ConfigScreen(ModalScreen[None]):
    """Everything the config file holds, plus the audio stack under it.

    The settings were only reachable by editing `config.toml` or by exporting
    a variable before launching, which meant the two things a user changes
    most — quality and whether the DAC is being handed hi-res at all — were
    the two least visible. Every row here writes the file, so a change made
    once stays made.
    """

    BINDINGS = [
        Binding("escape,o", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("enter,right,space", "advance", _("cambiar"), show=False),
        Binding("left", "back", "", show=False),
    ]

    cursor = reactive(0)

    QUALITIES = ("LOW", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS")
    ARTWORKS = ("auto", "kitty", "sixel", "blocks", "off")
    LANGUAGES = ("auto", "es", "en")
    SWITCH = ("false", "true")

    def __init__(self, on_change=None) -> None:
        super().__init__()
        # Called after a setting is written, so the app can apply what it can
        # apply without a restart.
        self._on_change = on_change
        self._sink = audio.Sink()
        self._allowed: tuple[int, ...] = ()
        self._hardware: tuple[int, ...] = ()
        self._rows: list[Option] = []

    # ------------------------------------------------------------------ rows

    def _options(self) -> list[Option]:
        return [
            Option(
                _("Calidad"),
                key="quality",
                choices=self.QUALITIES,
                note=_("se aplica a la siguiente pista"),
            ),
            Option(
                _("Carátula"),
                key="artwork",
                choices=self.ARTWORKS,
                note=_("al reiniciar"),
            ),
            Option(
                _("Idioma"),
                key="language",
                choices=self.LANGUAGES,
                note=_("al reiniciar"),
            ),
            Option(
                _("Columnas de la cola"),
                action="columns",
                note=_("qué metadatos se ven en la lista"),
            ),
            Option(
                _("Tema"),
                key="theme",
                choices=LAYOUTS,
                note=_("estructura visual; se aplica al instante"),
            ),
            Option(
                _("Paleta"),
                key="palette",
                choices=available_palettes(),
                note=_("auto sigue Omarchy; las demás funcionan en cualquier Linux"),
            ),
            Option(_("Registro de depuración"), key="debug", choices=self.SWITCH),
            Option(_("Ritmos hi-res en PipeWire"), action="rates"),
            Option(_("Reiniciar PipeWire"), action="restart"),
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="config-box"):
            yield Static(_("▓ CONFIGURACIÓN ▓"), id="config-title")
            yield Static("", id="config-list", markup=False)
            yield Static(_(" ↑↓ elegir   ↵ cambiar   o/esc cerrar"), id="config-hint")

    def on_mount(self) -> None:
        self._rows = self._options()
        self._probe()

    @work(thread=True, exclusive=True, group="config")
    def _probe(self) -> None:
        """Ask the audio stack what it is doing. Off the UI loop: it shells out."""
        found = (audio.sink(), audio.allowed_rates())
        hardware = audio.hardware_rates(found[0].name)
        self.app.call_from_thread(self._probed, found[0], found[1], hardware)

    def _probed(self, found, allowed, hardware) -> None:
        self._sink, self._allowed, self._hardware = found, allowed, hardware
        self._render_list()

    def watch_cursor(self) -> None:
        if self.is_mounted:
            self._render_list()

    # --------------------------------------------------------------- drawing

    def _value(self, option: Option) -> str:
        if option.key:
            current = getattr(config, _ATTRIBUTES[option.key])
            # `debug` is a bool in the file and "true"/"false" in the choices.
            return str(current).lower() if isinstance(current, bool) else str(current)
        if option.action == "rates":
            if audio.rates_configured():
                return _("configurado")
            return _("sin configurar")
        if option.action == "columns":
            return _("{count} de {total}").format(
                count=len(config.COLUMNS), total=len(columns.ALL)
            )
        return _("acción")

    def _detail(self, option: Option) -> str:
        """The line under a row: why it matters here, on this machine."""
        if option.key:
            shadowing = config.overridden(option.key)
            if shadowing:
                return _("lo pisa {variable} del entorno").format(variable=shadowing)
            return option.note
        if option.action == "rates":
            return self._rates_detail()
        if option.action == "columns":
            return option.note
        return _("corta el audio un momento; la reproducción se detiene antes")

    def _rates_detail(self) -> str:
        if not self._sink.known:
            return _("no se pudo consultar PipeWire")
        if self._sink.bluetooth:
            return _("la salida es Bluetooth: no hay hi-res real por ahí")
        if len(self._allowed) == 1:
            return _("el grafo está fijo en {rate} Hz y remuestrea todo").format(
                rate=self._allowed[0]
            )
        if self._hardware:
            return _("el DAC llega a {rate} Hz").format(rate=max(self._hardware))
        return _("el grafo puede cambiar de ritmo")

    def _render_list(self) -> None:
        palette = palette_for(self)
        widget = self.query_one("#config-list", Static)
        # Cropped, not wrapped: a detail that wrapped came back at column
        # zero and broke the indent that ties it to its own row.
        room = widget.size.width or 72
        labels = max(cell_len(option.label) for option in self._rows)

        rendered = Text()
        for index, option in enumerate(self._rows):
            selected = index == self.cursor
            marker = "›" if selected else " "
            style = (
                f"bold {palette['active_foreground']} on {palette['accent']}"
                if selected
                else palette["body"]
            )
            row = (
                f" {marker} {set_cell_size(option.label, labels)}   {self._value(option)}"
            )
            rendered.append(_crop(row, room) + "\n", style=style)
        current = self._rows[self.cursor]
        detail = f"     {current.label}: {self._detail(current)}"
        rendered.append("\n" + _crop(detail, room) + "\n", style=palette["muted"])
        rendered.append(_crop(self._status(), room), style=palette["muted"])
        warning = self._warning()
        if warning:
            rendered.append("\n" + _crop(warning, room), style=palette["warning"])
        widget.update(rendered)

    def _status(self) -> str:
        if not self._sink.known:
            return _("  Salida: desconocida")
        name = self._sink.description or self._sink.name
        return _("  Salida: {name} · {rate} Hz {format}").format(
            name=name, rate=self._sink.rate or "?", format=self._sink.sample_format
        )

    def _warning(self) -> str:
        """What the output line cannot say on its own.

        A graph pinned to one rate belongs here and not only in the detail of
        the row that fixes it: the badge tells the truth about the stream
        while the DAC receives something else, and nothing else on screen
        gives that away. Its own line, in the warning colour, because a tail
        appended to the output line was the first thing to be cropped away.
        """
        if not self._sink.known:
            return ""
        if self._sink.bluetooth:
            return _("  Bluetooth: no hay hi-res real por esta salida")
        if len(self._allowed) == 1:
            return _("  El grafo remuestrea todo a {rate} Hz").format(
                rate=self._allowed[0]
            )
        return ""

    # --------------------------------------------------------------- actions

    def action_up(self) -> None:
        self.cursor = (self.cursor - 1) % len(self._rows)

    def action_down(self) -> None:
        self.cursor = (self.cursor + 1) % len(self._rows)

    def action_advance(self) -> None:
        self._change(1)

    def action_back(self) -> None:
        self._change(-1)

    def _change(self, step: int) -> None:
        option = self._rows[self.cursor]
        if option.key:
            self._cycle(option, step)
            return
        if option.action == "rates":
            self._toggle_rates()
        elif option.action == "columns":
            self.app.push_screen(ColumnsScreen(self._on_change), self._columns_closed)
        elif option.action == "restart":
            self._restart()

    def _columns_closed(self, _result) -> None:
        self._render_list()

    def _cycle(self, option: Option, step: int) -> None:
        current = self._value(option)
        try:
            index = option.choices.index(current)
        except ValueError:
            index = 0
            step = 0
        value: object = option.choices[(index + step) % len(option.choices)]
        if option.key == "debug":
            value = value == "true"
        config.set_option(option.key, value)
        if self._on_change is not None:
            self._on_change(option.key)
        self._render_list()

    def _toggle_rates(self) -> None:
        if audio.rates_configured():
            audio.remove_rates()
            message = _("ritmos hi-res quitados; reinicia PipeWire para aplicarlo")
        else:
            audio.write_rates()
            message = _("ritmos hi-res escritos; reinicia PipeWire para aplicarlo")
        self.player.status = message
        self._render_list()

    def _restart(self) -> None:
        # mpv is holding the sink; let go of it before the daemon goes away.
        self.player.action_stop()
        self.player.status = _("reiniciando PipeWire…")
        self._restart_worker()

    @work(thread=True, exclusive=True, group="config")
    def _restart_worker(self) -> None:
        message = audio.restart()
        self.app.call_from_thread(self._restarted, message)

    def _restarted(self, message: str) -> None:
        self.player.status = message
        self._probe()

    @property
    def player(self) -> TidalAmp:
        return cast("TidalAmp", self.app)

    def action_close(self) -> None:
        self.dismiss(None)


# The module attribute each config key is resolved into.
_ATTRIBUTES = {
    "quality": "DEFAULT_QUALITY",
    "artwork": "ARTWORK",
    "language": "LANGUAGE",
    "theme": "THEME",
    "palette": "PALETTE",
    "debug": "DEBUG",
}
