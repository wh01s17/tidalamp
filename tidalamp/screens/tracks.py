"""The track menu and the playlist picker it opens."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static

from .. import library
from ..i18n import _
from ..library import Row
from ..theme import palette_for
from .rowlist import RowList

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    pass


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
    ("playlist", "≡", "l", _("añadir a una playlist")),
)


class PlaylistPickerScreen(ModalScreen[str | None]):
    """Which playlist to add to. Dismisses with its cache key, or None.

    A pane of its own rather than the browser: the browser answers with what
    to play or queue, and this question has a different answer.
    """

    BINDINGS = [
        Binding("escape", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("pageup", "page_up", "", show=False),
        Binding("pagedown", "page_down", "", show=False),
        Binding("enter", "choose", _("elegir"), show=False),
    ]

    def __init__(self, session) -> None:
        super().__init__()
        self._session = session

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-box"):
            yield Static(_("▓ AÑADIR A UNA PLAYLIST ▓"), id="picker-title")
            yield RowList(id="picker-list")
            yield Static(_(" ↑↓ elegir   ↵ añadir   esc cancelar"), id="picker-hint")

    def on_mount(self) -> None:
        widget = self.query_one(RowList)
        widget.empty_text = _("cargando…")
        self._load()

    @work(thread=True, exclusive=True, group="playlists")
    def _load(self) -> None:
        try:
            rows = library.playlist_rows(self._session)
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self._ready, rows)

    def _failed(self, exc: Exception) -> None:
        widget = self.query_one(RowList)
        widget.empty_text = _("error: {error}").format(error=exc)
        widget.refresh()

    def _ready(self, rows: list[Row]) -> None:
        widget = self.query_one(RowList)
        # The «más…» row fetches another page and cannot be added to.
        widget.empty_text = _("no tienes playlists")
        widget.set_rows([row for row in rows if row.more is None])

    def action_up(self) -> None:
        self.query_one(RowList).move(-1)

    def action_down(self) -> None:
        self.query_one(RowList).move(1)

    def action_page_up(self) -> None:
        self.query_one(RowList).move(-10)

    def action_page_down(self) -> None:
        self.query_one(RowList).move(10)

    def action_choose(self) -> None:
        row = self.query_one(RowList).current
        self.dismiss(row.key if row is not None and row.key else None)

    def action_close(self) -> None:
        self.dismiss(None)


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

    def action_pick_playlist(self) -> None:
        self.dismiss("playlist")
