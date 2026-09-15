"""The two small windows that ask for a line of text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ..i18n import _

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    pass


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


class PlaylistNameScreen(ModalScreen[str | None]):
    """Ask for a line about a playlist: the name of the one the queue goes
    to, or a new name or description for one of yours, typed over the one
    it has."""

    BINDINGS = [Binding("escape", "dismiss_playlist", _("cancelar"))]

    def __init__(self, title: str = "", value: str = "", placeholder: str = "") -> None:
        super().__init__()
        self._title = title or _("GUARDAR COLA COMO PLAYLIST")
        self._value = value
        self._placeholder = placeholder or _("nombre de la playlist…")

    def compose(self) -> ComposeResult:
        with Vertical(id="playlist-name-box"):
            # markup=False: a playlist's name can carry a «[».
            yield Static(self._title, id="playlist-name-title", markup=False)
            yield Input(
                value=self._value, placeholder=self._placeholder, id="playlist-name-input"
            )

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_dismiss_playlist(self) -> None:
        self.dismiss(None)
