"""The window that picks and orders the queue's columns."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static

from .. import columns, config
from ..i18n import _
from ..theme import palette_for

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    pass


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


def _crop(text: str, width: int) -> str:
    """One line, ellipsised rather than wrapped."""
    if cell_len(text) <= width:
        return text
    if width <= 0:
        return ""
    return set_cell_size(text, max(0, width - 1)) + "…"
