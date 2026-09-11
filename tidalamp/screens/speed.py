"""The playback speed window."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..i18n import _
from ..player import Mpv


def speed_text(speed: float) -> str:
    """A speed as the transport and this window write it: `1×`, `0.75×`."""
    return f"{speed:g}×"


class SpeedScreen(ModalScreen[float | None]):
    """Pick how fast the track plays, from a quarter to double.

    Applied on ↵ rather than while the cursor moves: walking past 0.25 on the
    way to 1.5 would drag the song through every speed in between.
    """

    BINDINGS = [
        Binding("escape", "close", _("cerrar")),
        Binding("up,left", "up", _("más lento"), show=False),
        Binding("down,right", "down", _("más rápido"), show=False),
        Binding("enter", "choose", _("aplicar"), show=False),
    ]

    def __init__(self, current: float) -> None:
        super().__init__()
        speeds = Mpv.SPEEDS
        self.cursor = speeds.index(current) if current in speeds else speeds.index(1.0)
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="speed-box"):
            yield Static(_("▓ VELOCIDAD ▓"), id="speed-title")
            for index, _speed in enumerate(Mpv.SPEEDS):
                yield Static("", id=f"speed-{index}", classes="speed-row", markup=False)
            yield Static(_(" ↑↓ elegir  ↵ aplicar  esc cerrar"), id="speed-hint")

    def on_mount(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        for index, speed in enumerate(Mpv.SPEEDS):
            mark = "●" if speed == self.current else " "
            name = _("normal") if speed == 1.0 else ""
            row = self.query_one(f"#speed-{index}", Static)
            row.update(f" {mark} {speed_text(speed):<6}{name}")
            row.set_class(index == self.cursor, "-cursor")

    def action_up(self) -> None:
        self.cursor = max(0, self.cursor - 1)
        self._redraw()

    def action_down(self) -> None:
        self.cursor = min(len(Mpv.SPEEDS) - 1, self.cursor + 1)
        self._redraw()

    def action_choose(self) -> None:
        self.dismiss(Mpv.SPEEDS[self.cursor])

    def on_click(self, event: events.Click) -> None:
        """A click on a speed picks it, the way ↵ on it would."""
        widget = event.widget
        if widget is not None and widget.id and widget.id.startswith("speed-"):
            suffix = widget.id.removeprefix("speed-")
            if suffix.isdigit():
                self.cursor = int(suffix)
                self.action_choose()

    def action_close(self) -> None:
        self.dismiss(None)
