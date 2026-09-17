"""The question before a logout, with the settings as a box to tick."""

from __future__ import annotations

from rich.cells import cell_len
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..i18n import _


class LogoutScreen(ModalScreen[object]):
    """Log out, and say whether the rest of the app's data goes too.

    Not a `ChoiceScreen`: that one takes a single answer, and this question has
    two, the logout and what it takes with it. Losing the session is the
    logout itself; losing the rest of the app's data is a choice, so it is a
    box, unticked, and nothing is deleted until «cerrar sesión» is chosen.

    Dismisses with ``"session"``, ``"everything"`` when the box was ticked, or
    ``None`` on «cancelar» and esc. Shares the choice window's look.
    """

    BINDINGS = [
        Binding("escape", "close", _("cerrar")),
        Binding("up,left", "up", "", show=False),
        Binding("down,right", "down", "", show=False),
        Binding("enter,space", "choose", _("elegir"), show=False),
    ]

    BOX, LOGOUT, CANCEL = range(3)

    def __init__(self) -> None:
        super().__init__()
        self.data_too = False
        # On «cancelar», like Restart PipeWire: ↵ by reflex must not log out.
        self.cursor = self.CANCEL
        self._message = _(
            "Se borra la sesión guardada y tidalamp se cierra.\n"
            "Para volver a entrar hará falta: tidalamp login\n\n"
            "Los datos son la configuración, la cola, el ecualizador,\n"
            "la caché y el acceso directo del menú."
        )
        self._hint = _(" ↑↓ elegir  ↵ marcar o aplicar  esc cerrar")

    def _labels(self) -> list[str]:
        mark = "x" if self.data_too else " "
        return [
            _("[{mark}] borrar también los datos de tidalamp").format(mark=mark),
            _("cerrar sesión"),
            _("cancelar"),
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="choice-box"):
            yield Static(_("¿CERRAR SESIÓN?"), id="choice-title", markup=False)
            yield Static(self._message, id="choice-message", markup=False)
            for index in range(len(self._labels())):
                yield Static("", id=f"choice-{index}", classes="choice-row", markup=False)
            yield Static(self._hint, id="choice-hint", markup=False)

    def on_mount(self) -> None:
        widest = max(
            [cell_len(label) + 3 for label in self._labels()]
            + [cell_len(line) + 2 for line in self._message.splitlines()]
            + [cell_len(self._hint)]
        )
        self.query_one("#choice-box").styles.width = widest + 8
        self._redraw()

    def _redraw(self) -> None:
        for index, label in enumerate(self._labels()):
            row = self.query_one(f"#choice-{index}", Static)
            row.update(f"   {label}")
            row.set_class(index == self.cursor, "-cursor")

    def action_up(self) -> None:
        self.cursor = max(0, self.cursor - 1)
        self._redraw()

    def action_down(self) -> None:
        self.cursor = min(self.CANCEL, self.cursor + 1)
        self._redraw()

    def action_choose(self) -> None:
        if self.cursor == self.BOX:
            self.data_too = not self.data_too
            self._redraw()
        elif self.cursor == self.LOGOUT:
            self.dismiss("everything" if self.data_too else "session")
        else:
            self.dismiss(None)

    def on_click(self, event: events.Click) -> None:
        """A click on a row does what ↵ on it would."""
        widget = event.widget
        if widget is not None and widget.id and widget.id.startswith("choice-"):
            suffix = widget.id.removeprefix("choice-")
            if suffix.isdigit():
                self.cursor = int(suffix)
                self.action_choose()

    def action_close(self) -> None:
        self.dismiss(None)
