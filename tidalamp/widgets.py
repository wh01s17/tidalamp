"""The pieces of Winamp chrome: LCD clock, scrolling title, analyser, sliders."""

from __future__ import annotations

import random

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

# Classic seven-segment glyphs, three rows tall and three columns wide.
_SEGMENTS: dict[str, tuple[str, str, str]] = {
    "0": (" _ ", "| |", "|_|"),
    "1": ("   ", "  |", "  |"),
    "2": (" _ ", " _|", "|_ "),
    "3": (" _ ", " _|", " _|"),
    "4": ("   ", "|_|", "  |"),
    "5": (" _ ", "|_ ", " _|"),
    "6": (" _ ", "|_ ", "|_|"),
    "7": (" _ ", "  |", "  |"),
    "8": (" _ ", "|_|", "|_|"),
    "9": (" _ ", "|_|", "|_|"),
    ":": ("   ", " . ", " . "),
    "-": ("   ", " _ ", "   "),
    " ": ("   ", "   ", "   "),
}
_SEGMENTS["9"] = (" _ ", "|_|", " _|")


class TimeDisplay(Widget):
    """The big green clock. Negative ``seconds`` counts down, as Winamp does."""

    DEFAULT_CSS = "TimeDisplay { height: 3; width: 20; }"

    seconds = reactive(0.0)
    countdown = reactive(False)
    total = reactive(0.0)

    def render(self) -> Text:
        value = self.seconds
        if self.countdown and self.total:
            value = max(0.0, self.total - self.seconds)
        minutes, secs = divmod(int(value), 60)
        text = f"{'-' if self.countdown and self.total else ''}{minutes:02d}:{secs:02d}"

        rows = ["", "", ""]
        for char in text:
            glyph = _SEGMENTS.get(char, _SEGMENTS[" "])
            for i in range(3):
                rows[i] += glyph[i] + " "
        return Text("\n".join(rows), style="bold #00ff4c")


class Marquee(Widget):
    """Scrolling track title, the way the Winamp titlebar scrolls."""

    DEFAULT_CSS = "Marquee { height: 1; }"

    text = reactive("")
    _offset = reactive(0)

    def watch_text(self) -> None:
        self._offset = 0

    def tick(self) -> None:
        width = max(1, self.size.width)
        padded = f"{self.text}   ***   "
        if len(padded) > width:
            self._offset = (self._offset + 1) % len(padded)
        else:
            self._offset = 0

    def render(self) -> Text:
        width = max(1, self.size.width)
        if not self.text:
            return Text("TIDAL AMP", style="bold #00ff4c")
        padded = f"{self.text}   ***   "
        if len(padded) <= width:
            return Text(self.text[:width], style="bold #00ff4c")
        doubled = padded + padded
        return Text(doubled[self._offset : self._offset + width], style="bold #00ff4c")


class Analyzer(Widget):
    """The spectrum analyser, in one of two modes.

    With cava running (see ``spectrum.py``) the bands come from a real FFT and
    are drawn as they arrive.

    Without it we fall back to mpv's ``astats``, which reports a level and not
    a spectrum: the overall RMS sets the envelope and each band wanders inside
    it with its own decay. That fallback reacts to the music honestly, it just
    is not a frequency breakdown — and ``source`` says which of the two you are
    looking at, so the display never claims to be an FFT when it is not.
    """

    DEFAULT_CSS = "Analyzer { height: 5; }"

    BARS = 19
    BLOCKS = " ▁▂▃▄▅▆▇█"

    level = reactive(-91.0)
    active = reactive(False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Bands straight from cava, or None while we are on the RMS fallback.
        self.spectrum: list[float] | None = None
        self._bands = [0.0] * self.BARS
        self._peaks = [0.0] * self.BARS
        # Low bands carry more energy in most music; weight them like Winamp's.
        self._weights = [1.0 - (i / self.BARS) * 0.55 for i in range(self.BARS)]

    @property
    def source(self) -> str:
        """"FFT" when cava is feeding us, "RMS" when we are guessing shapes."""
        return "FFT" if self.spectrum is not None else "RMS"

    def _targets(self) -> list[float]:
        if not self.active:
            return [0.0] * self.BARS
        if self.spectrum is not None:
            # A real spectrum needs no shaping: cava already smooths it, and
            # inventing a weighting on top would only distort what it measured.
            frame = self.spectrum
            return [
                max(0.0, min(1.0, frame[i])) if i < len(frame) else 0.0
                for i in range(self.BARS)
            ]
        # -60 dBFS .. 0 dBFS mapped onto 0..1
        base = max(0.0, min(1.0, (self.level + 60.0) / 60.0))
        return [
            base * self._weights[i] * (random.uniform(0.55, 1.0) if base > 0.02 else 0.0)
            for i in range(self.BARS)
        ]

    def tick(self) -> None:
        targets = self._targets()

        for i in range(self.BARS):
            target = targets[i]
            # Fast attack, slow release — standard meter ballistics.
            if target > self._bands[i]:
                self._bands[i] += (target - self._bands[i]) * 0.7
            else:
                self._bands[i] -= min(self._bands[i], 0.08)
            self._peaks[i] = max(self._bands[i], self._peaks[i] - 0.02)
        self.refresh()

    def _bar_style(self, height_ratio: float) -> str:
        if height_ratio > 0.8:
            return "#ff3b3b"
        if height_ratio > 0.55:
            return "#ffd500"
        return "#00ff4c"

    def render(self) -> Text:
        rows = max(1, self.size.height)
        out = Text()
        for row in range(rows):
            # Row 0 is the top of the analyser.
            floor = (rows - row - 1) / rows
            for i, value in enumerate(self._bands):
                filled = value - floor
                if filled >= 1 / rows:
                    glyph = "█"
                elif filled > 0:
                    idx = int(filled * rows * (len(self.BLOCKS) - 1))
                    glyph = self.BLOCKS[max(0, min(len(self.BLOCKS) - 1, idx))]
                else:
                    glyph = " "
                peak_here = int(self._peaks[i] * rows) == (rows - row - 1)
                if glyph == " " and peak_here and self._peaks[i] > 0.02:
                    out.append("▁", style="#8fd8a0")
                else:
                    out.append(glyph, style=self._bar_style(value))
                out.append(" ")
            if row != rows - 1:
                out.append("\n")
        return out


class EqualizerBars(Widget):
    """Ten vertical faders, the way the Winamp equaliser window looks.

    Purely a view: it draws whatever gains it is handed and highlights the
    selected band. The clamping and the filter graph live in ``settings.py``.
    """

    DEFAULT_CSS = "EqualizerBars { height: 11; }"

    gains: reactive[list[float]] = reactive(list)
    selected = reactive(0)
    limit = reactive(12.0)
    labels: reactive[list[str]] = reactive(list)

    def render(self) -> Text:
        gains = list(self.gains)
        if not gains:
            return Text("")
        rows = max(3, self.size.height - 2)
        middle = rows // 2
        out = Text()
        for row in range(rows):
            for band, gain in enumerate(gains):
                # How far from the centre line this band reaches, in rows.
                extent = int(round((gain / self.limit) * middle))
                if row == middle:
                    glyph, style = "─", "#5f7f67"
                elif extent > 0 and middle - extent <= row < middle:
                    glyph, style = "█", "#00ff4c"
                elif extent < 0 and middle < row <= middle - extent:
                    glyph, style = "█", "#ffd500"
                else:
                    glyph, style = "·", "#2f3f35"
                if band == self.selected:
                    style = f"bold {style} on #123a1c" if glyph != "·" else "#4f6f57 on #123a1c"
                out.append(f" {glyph}  ", style=style)
            out.append("\n")

        for band, label in enumerate(self.labels):
            style = "bold #00ff4c" if band == self.selected else "#7f9f87"
            out.append(f"{label:>3} ", style=style)
        out.append("\n")
        for band, gain in enumerate(gains):
            style = "bold #00ff4c" if band == self.selected else "#7f9f87"
            out.append(f"{gain:>+3.0f} ", style=style)
        return out


class SeekBar(Widget):
    """Position slider with the Winamp thumb."""

    DEFAULT_CSS = "SeekBar { height: 1; }"

    position = reactive(0.0)
    total = reactive(0.0)

    def render(self) -> Text:
        width = max(4, self.size.width)
        ratio = (self.position / self.total) if self.total else 0.0
        thumb = int(ratio * (width - 1))
        bar = Text()
        for i in range(width):
            if i == thumb:
                bar.append("▓", style="bold #00ff4c")
            else:
                bar.append("─", style="#3f5f47")
        return bar


class Slider(Widget):
    """A labelled horizontal level, used for volume."""

    DEFAULT_CSS = "Slider { height: 1; }"

    value = reactive(0)
    maximum = reactive(100)
    label = reactive("VOL")

    def render(self) -> Text:
        width = max(8, self.size.width)
        track = width - len(self.label) - 6
        filled = int((self.value / self.maximum) * track) if self.maximum else 0
        bar = Text(f"{self.label} ", style="#7f9f87")
        bar.append("█" * filled, style="#00ff4c")
        bar.append("░" * max(0, track - filled), style="#2f3f35")
        bar.append(f" {self.value:>3}", style="#7f9f87")
        return bar
