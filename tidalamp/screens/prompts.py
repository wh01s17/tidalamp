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
    """Ask for the name of a playlist that will receive the queue."""

    BINDINGS = [Binding("escape", "dismiss_playlist", _("cancelar"))]

    def compose(self) -> ComposeResult:
        with Vertical(id="playlist-name-box"):
            yield Static(_("GUARDAR COLA COMO PLAYLIST"), id="playlist-name-title")
            yield Input(placeholder=_("nombre de la playlist…"), id="playlist-name-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_dismiss_playlist(self) -> None:
        self.dismiss(None)
