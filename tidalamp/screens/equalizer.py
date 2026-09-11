"""The equalizer and balance window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..i18n import _
from ..settings import BAND_LABELS, GAIN_LIMIT, MANUAL, PRESETS, Settings
from ..widgets import EqualizerBars, Slider

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    pass


PRESET_LABELS: dict[str, str] = {
    "flat": _("plano"),
    "rock": _("rock"),
    "pop": _("pop"),
    "jazz": _("jazz"),
    "classical": _("clásica"),
    "vocal": _("voz"),
    "bass": _("graves"),
    "treble": _("agudos"),
    MANUAL: _("manual"),
}


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
        Binding("p", "next_preset", _("preset siguiente"), show=False),
        Binding("P", "prev_preset", _("preset anterior"), show=False),
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
            # The curve's name, under the bands: without it, cycling presets
            # is eight anonymous shapes.
            yield Static("", id="eq-preset", markup=False)
            yield Slider(id="eq-balance")
            yield Static(
                _(" ←→ banda  ↑↓ ±1 dB  0 plano  p/P preset  ,. balance  esc"),
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

    def action_next_preset(self) -> None:
        self._cycle_preset(1)

    def action_prev_preset(self) -> None:
        self._cycle_preset(-1)

    def _cycle_preset(self, step: int) -> None:
        """Move along the catalogue, applying as it goes.

        From `manual` it starts at the first, because there is nowhere in the
        list to step from: the bands are somewhere the catalogue does not
        describe, and the nearest curve is nobody's idea of the next one.
        """
        names = [name for name, _gains in PRESETS]
        current = self.settings.preset
        index = names.index(current) + step if current in names else 0
        self.settings.apply_preset(names[index % len(names)])
        self._apply()
        self._redraw()

    def _redraw(self) -> None:
        bars = self.query_one(EqualizerBars)
        bars.gains = list(self.settings.gains)
        self.query_one("#eq-preset", Static).update(
            _("  preset: {name}").format(
                name=PRESET_LABELS.get(self.settings.preset, self.settings.preset)
            )
        )
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
