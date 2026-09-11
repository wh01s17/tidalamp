"""The help window: every key, the credits and the release notes."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from .. import about, library
from ..i18n import _
from ..theme import palette_for

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    pass


class HelpScreen(ModalScreen[None]):
    """Every key the app answers to, plus who wrote it and what changed.

    Two tabs rather than one long document: the keys are what the screen is
    opened for, and the credits and the release notes were three screenfuls
    of scrolling below them. → moves to «Acerca de», ← comes back, and each
    tab remembers where it was left.

    Built from the *effective* bindings, not from a hardcoded list: `keys` is
    the app's resolver, so a key rebound in `config.toml` shows up here as the
    key the user actually has to press.
    """

    BINDINGS = [
        Binding("escape,question_mark,h", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("right", "next_tab", _("acerca de"), show=False),
        Binding("left", "prev_tab", _("ayuda"), show=False),
        Binding("pageup", "page_up", "", show=False),
        Binding("pagedown", "page_down", "", show=False),
        Binding("home", "top", "", show=False),
        Binding("end", "bottom", "", show=False),
        Binding("slash", "search", _("buscar"), show=False),
    ]

    # The tabs, left to right. `→` walks towards the end of this tuple and
    # `←` back towards its start, so the order here is the order on screen.
    SHORTCUTS, ABOUT = 0, 1

    def __init__(self, keys: Callable[[str], str], only: str = "") -> None:
        super().__init__()
        self._keys = keys
        # A section's name (`about.Section.name`) to show alone, for a window
        # that opens its own help: the browser's `?` shows the browser's keys
        # and nothing else, without the «Acerca de» tab.
        self._only = only
        self._tab = self.SHORTCUTS
        # One scroll position per tab: coming back to the keys should land
        # where you left them, not at the top.
        self._offsets = [0, 0]
        # Built once on mount: nothing in them changes while the screen is
        # open, and building both costs less than rebuilding on every →.
        self._pages: list[list[tuple[str, str]]] = [[], []]
        # What the search box holds. It narrows whichever tab is showing, so
        # it survives `→`: looking a word up in the release notes is the
        # same question as looking it up in the keys.
        self._query = ""

    # The rest of the screen scrolls «the current page», so both of these read
    # through the tab instead of every caller having to index it.

    @property
    def _lines(self) -> list[tuple[str, str]]:
        page = self._pages[self._tab]
        return self._matching(page, self._query) if self._query else page

    @property
    def _offset(self) -> int:
        return self._offsets[self._tab]

    @_offset.setter
    def _offset(self, value: int) -> None:
        self._offsets[self._tab] = value

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static("", id="help-title", markup=False)
            yield Static("", id="help-body", markup=False)
            # Under the text, the way the queue's and the browser's are: the
            # page narrows under the eyes of whoever is typing.
            with Horizontal(id="help-filter-bar"):
                yield Input(placeholder=_("buscar en la ayuda…"), id="help-filter")
                yield Static("", id="help-filter-count", markup=False)
            yield Static("", id="help-hint", markup=False)

    def on_mount(self) -> None:
        self._pages = (
            [self._build_shortcuts()]
            if self._only
            else [self._build_shortcuts(), self._build_about()]
        )
        self.query_one("#help-filter-bar", Horizontal).display = False
        self._render_tabs()
        self._render_window()

    # ---------------------------------------------------------------- tabs

    def _titles(self) -> tuple[str, ...]:
        """Translated at call time, like everything else the screen draws."""
        if self._only:
            return (_("AYUDA"),)
        return (_("AYUDA"), _("ACERCA DE"))

    def _render_tabs(self) -> None:
        """The title bar, with the tab you are on marked and the other dim.

        The version rides at the end because it is the one thing a user is
        asked to quote in a bug report; a narrow terminal clips it and loses
        nothing the «Acerca de» tab does not repeat.
        """
        palette = palette_for(self)
        bar = Text()
        for index, title in enumerate(self._titles()):
            if index == self._tab:
                bar.append(f"▓ {title} ▓", style=f"bold {palette['accent']}")
            else:
                bar.append(f"  {title}  ", style=palette["inactive"])
        bar.append(f"  TIDAL AMP {about.version()}", style=palette["title_foreground"])
        self.query_one("#help-title", Static).update(bar)

        if self._searching():
            hint = _(" escribe para filtrar   ↵ listo   esc quitar la búsqueda")
        elif self._only:
            hint = _(" ↑↓ desplazar   / buscar   ?/esc cerrar")
        elif self._tab == self.SHORTCUTS:
            hint = _(" ↑↓ desplazar   / buscar   → acerca de   ?/h/esc cerrar")
        else:
            hint = _(" ↑↓ desplazar   / buscar   ← ayuda   ?/h/esc cerrar")
        self.query_one("#help-hint", Static).update(hint)

    def _go_to(self, tab: int) -> None:
        tab = max(0, min(tab, len(self._pages) - 1))
        if tab == self._tab:
            return
        self._tab = tab
        self._render_tabs()
        self._render_window()
        if self._searching():
            self._render_count()

    def action_next_tab(self) -> None:
        self._go_to(self._tab + 1)

    def action_prev_tab(self) -> None:
        self._go_to(self._tab - 1)

    # --------------------------------------------------------------- search

    @staticmethod
    def _matching(lines: list[tuple[str, str]], query: str) -> list[tuple[str, str]]:
        """The rows that answer to `query`, each under its section's heading.

        A matching row without its heading would say `x` and not what `x`
        does it for, so every section that keeps a row keeps its title too,
        and a heading that matches brings its whole section along.
        """
        kept: list[tuple[str, str]] = []
        heading: tuple[str, str] | None = None
        whole = False
        for kind, text in lines:
            if kind == "heading":
                heading = (kind, text)
                whole = library.text_matches(query, text)
                if whole:
                    if kept:
                        kept.append(("blank", ""))
                    kept.append(heading)
                continue
            if kind == "blank" or not (whole or library.text_matches(query, text)):
                continue
            if heading is not None and heading not in kept[-1:] and not whole:
                if kept:
                    kept.append(("blank", ""))
                kept.append(heading)
                heading = None
            kept.append((kind, text))
        return kept

    def _searching(self) -> bool:
        return bool(self.query("#help-filter-bar")) and bool(
            self.query_one("#help-filter-bar", Horizontal).display
        )

    def action_search(self) -> None:
        """Open the search box under the page and start typing into it."""
        self.query_one("#help-filter-bar", Horizontal).display = True
        self.query_one("#help-filter", Input).focus()
        self._render_tabs()
        self._render_count()
        self.call_after_refresh(self._render_window)

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        if query == self._query:
            return
        self._query = query
        self._offset = 0
        self._render_window()
        self._render_count()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """↵ hands the arrows back to the page and leaves the filter on."""
        self.query_one("#help-filter", Input).blur()
        self.set_focus(None)

    def _render_count(self) -> None:
        page = self._pages[self._tab]
        total = sum(1 for kind, _text in page if kind == "row")
        shown = sum(1 for kind, _text in self._lines if kind == "row")
        self.query_one("#help-filter-count", Static).update(
            _("{shown} de {total}").format(shown=shown, total=total)
        )

    def _clear_search(self) -> None:
        self._query = ""
        self.query_one("#help-filter", Input).value = ""
        self.query_one("#help-filter-bar", Horizontal).display = False
        self.set_focus(None)
        self._render_tabs()
        self._render_window()
        # The page just gained the row the box was using, and only the next
        # layout knows it: drawn now, it came out a line short.
        self.call_after_refresh(self._render_window)

    # ------------------------------------------------------------- content

    def _build_shortcuts(self) -> list[tuple[str, str]]:
        """The key map as (style, text) pairs, top to bottom.

        A flat list rather than a scrolling container: the screen windows it
        by hand, the way the plain-text lyrics do, so it needs no widget that
        the compositor would have to scroll.
        """
        lines: list[tuple[str, str]] = []

        for section in about.shortcuts(self._keys):
            if self._only and section.name != self._only:
                continue
            lines.append(("heading", section.title))
            width = max(len(key) for key, _description in section.rows)
            for key, description in section.rows:
                lines.append(("row", f"  {key:<{width}}   {description}"))
            lines.append(("blank", ""))

        return self._trimmed(lines)

    def _build_about(self) -> list[tuple[str, str]]:
        """Who wrote it, under what licence, and what each version brought."""
        lines: list[tuple[str, str]] = []

        lines.append(("heading", _("Acerca de")))
        for text in (
            _("Cliente de TIDAL para terminal, con una interfaz retro."),
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

        return self._trimmed(lines)

    @staticmethod
    def _trimmed(lines: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Without the separator the last block left hanging under itself."""
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
        if self._query and not self._lines:
            rendered.append(
                "  " + _("nada coincide con «{query}»").format(query=self._query),
                style=palette["muted"],
            )
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
        # esc takes the search away before it closes the window, as it does
        # in the browser: the first one undoes what the last key did.
        if self._searching():
            self._clear_search()
            return
        self.dismiss(None)
