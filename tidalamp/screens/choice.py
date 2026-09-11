"""A window that offers a short list and takes one answer."""

from __future__ import annotations

from collections.abc import Sequence

from rich.cells import cell_len
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..i18n import _


class ChoiceScreen(ModalScreen[object]):
    """Pick one of a few options: ↑↓ walk, ↵ or a click picks, esc keeps what was.

    Nothing happens while the cursor moves. Whoever opened the window applies
    the answer, and only once it is chosen: that is the point for the settings
    rows that open it, where an arrow pressed by mistake used to change the
    quality, rewrite PipeWire's rates or restart PipeWire.

    Dismisses with the chosen value, or ``None`` on esc.
    """

    BINDINGS = [
        Binding("escape", "close", _("cerrar")),
        Binding("up,left", "up", "", show=False),
        Binding("down,right", "down", "", show=False),
        Binding("enter,space", "choose", _("elegir"), show=False),
    ]

    def __init__(
        self,
        heading: str,
        options: Sequence[tuple[object, str]],
        current: object = None,
        *,
        cursor: int | None = None,
        hint: str | None = None,
        keys: tuple[str, ...] = (),
        key_value: object = None,
    ) -> None:
        super().__init__()
        self._heading = heading
        self._options = list(options)
        self._current = current
        values = [value for value, _label in self._options]
        if cursor is None:
            cursor = values.index(current) if current in values else 0
        self.cursor = cursor
        self._hint = hint if hint is not None else _(" ↑↓ elegir  ↵ aplicar  esc cerrar")
        # Keys that answer ``key_value`` at once: the key that asked the
        # question, pressed again. The app's own bindings do not reach a key
        # pressed while this window is in front, so the window listens itself.
        self._keys = keys
        self._key_value = key_value

    def compose(self) -> ComposeResult:
        with Vertical(id="choice-box"):
            yield Static(self._heading, id="choice-title", markup=False)
            for index in range(len(self._options)):
                yield Static("", id=f"choice-{index}", classes="choice-row", markup=False)
            yield Static(self._hint, id="choice-hint", markup=False)

    def on_mount(self) -> None:
        # As wide as its longest line and no wider: a list of four qualities
        # in a box sized for a sentence reads as a form with most of it blank.
        widest = max(
            [cell_len(label) for _value, label in self._options]
            + [cell_len(self._hint), cell_len(self._heading)]
        )
        self.query_one("#choice-box").styles.width = widest + 8
        self._redraw()

    def _redraw(self) -> None:
        for index, (value, label) in enumerate(self._options):
            mark = "●" if value == self._current else " "
            row = self.query_one(f"#choice-{index}", Static)
            row.update(f" {mark} {label}")
            row.set_class(index == self.cursor, "-cursor")

    def action_up(self) -> None:
        self.cursor = max(0, self.cursor - 1)
        self._redraw()

    def action_down(self) -> None:
        self.cursor = min(len(self._options) - 1, self.cursor + 1)
        self._redraw()

    def action_choose(self) -> None:
        self.dismiss(self._options[self.cursor][0])

    def on_key(self, event: events.Key) -> None:
        if event.key in self._keys:
            event.stop()
            self.dismiss(self._key_value)

    def on_click(self, event: events.Click) -> None:
        """A click on an option picks it, the way ↵ on it would."""
        widget = event.widget
        if widget is not None and widget.id and widget.id.startswith("choice-"):
            suffix = widget.id.removeprefix("choice-")
            if suffix.isdigit():
                self.cursor = int(suffix)
                self.action_choose()

    def action_close(self) -> None:
        self.dismiss(None)
