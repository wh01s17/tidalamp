"""Who made the track, and what its licence asks of you.

CC BY and CC BY-SA do not merely permit attribution, they require it, and the
form they ask for is well known enough to have a name: **TASL** — Title,
Author, Source, Licence. So that is the shape of this window, and the line at
the bottom is those four things already assembled, ready to be copied into
whatever the music ends up in.

A window and not a permanent line under the cover: the credit matters when
somebody is about to *use* the music, which is a moment they go looking for,
and the player's band has no room to spend on a URL that is read once.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..i18n import _
from ..queue import Entry
from ..theme import palette_for

# What each licence asks of whoever reuses the work, in one line. Keyed by the
# short name `freemusic.licence_name` produces, so the two stay in step.
DEMANDS: dict[str, str] = {
    "CC0": _("no pide nada: está en el dominio público"),
    "CC BY": _("cita al autor, y puedes usarla para lo que quieras"),
    "CC BY-SA": _("cita al autor, y comparte los cambios con esta misma licencia"),
}


def attribution(entry: Entry) -> str:
    """The credit line, in the order Creative Commons asks for it.

    Everything that is known and nothing else: a track with no source page
    gets a line without one rather than a line with a gap in it.
    """
    parts = [f"«{entry.title}»"]
    if entry.artist:
        parts.append(_("de {artist}").format(artist=entry.artist))
    if entry.source_url:
        parts.append(f"({entry.source_url})")
    if entry.licence:
        parts.append(f"— {entry.licence}")
    return " ".join(parts)


class CreditsScreen(ModalScreen[None]):
    """The track's credit, as its licence asks for it."""

    BINDINGS = [
        Binding("escape,enter,space", "close", _("cerrar")),
    ]

    def __init__(self, entry: Entry) -> None:
        super().__init__()
        self._entry = entry

    def compose(self) -> ComposeResult:
        with Vertical(id="credits-box"):
            yield Static(_("▓ CRÉDITOS ▓"), id="credits-title")
            yield Static("", id="credits-body", markup=False)
            yield Static(_(" esc cerrar"), id="credits-hint")

    def on_mount(self) -> None:
        self.query_one("#credits-body", Static).update(self._rendered())

    def action_close(self) -> None:
        self.dismiss(None)

    def _rendered(self) -> Text:
        palette = palette_for(self)
        entry = self._entry
        out = Text(no_wrap=False)

        def row(label: str, value: str) -> None:
            if not value:
                return
            out.append(f"{label:<10}", style=palette["muted"])
            out.append(f"{value}\n", style=palette["body"])

        row(_("Título"), entry.title)
        row(_("Autor"), entry.artist)
        row(_("Álbum"), entry.album)
        row(_("Fuente"), entry.source_url)
        row(_("Licencia"), entry.licence)

        demand = DEMANDS.get(entry.licence)
        if demand:
            out.append("\n")
            out.append(demand, style=palette["muted"])
            out.append("\n")

        out.append("\n")
        out.append(_("Para citarla:"), style=palette["muted"])
        out.append("\n")
        out.append(attribution(entry), style=f"bold {palette['accent']}")
        return out
