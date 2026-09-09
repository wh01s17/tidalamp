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
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Static

from . import about, library
from .auth import ensure_fresh
from .i18n import _
from .library import Row
from .lyrics import LyricsDocument
from .settings import BAND_LABELS, GAIN_LIMIT, Settings
from .theme import palette_for
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

    def render(self) -> Text:
        palette = palette_for(self)
        if not self.rows:
            return Text(f"  {self.empty_text}", style=palette["empty"])

        height = max(1, self.size.height)
        width = max(20, self.size.width)
        # Keep the cursor in view without a full scrolling container.
        start = max(0, min(self.cursor - height // 2, len(self.rows) - height))
        out = Text()
        for i in range(start, min(len(self.rows), start + height)):
            row = self.rows[i]
            marker = "▶" if i == self.marked else (" " if row.is_playable else "›")
            line = f"{marker}{i + 1:>3}. {row.label}"
            pad = max(1, width - len(line) - len(row.detail) - 1)
            line = f"{line}{' ' * pad}{row.detail}"[:width]
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
        # Play this track, queueing the whole level so the rest follows.
        entries = [r.entry for r in widget.rows if r.entry is not None]
        index = entries.index(row.entry) if row.entry in entries else 0
        self.dismiss(("play", entries, index))

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
