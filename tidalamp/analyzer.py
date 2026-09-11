"""The spectrum analyser and the equaliser faders: the two widgets that draw
bands."""

from __future__ import annotations

import random

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from .theme import palette_for


class Analyzer(Widget):
    """The spectrum analyser: two sources, four shapes.

    With cava running (see ``spectrum.py``) the bands come from a real FFT and
    are drawn as they arrive.

    Without it we fall back to mpv's ``astats``, which reports a level and not
    a spectrum: the overall RMS sets the envelope and each band wanders inside
    it with its own decay. That fallback reacts to the music honestly, it just
    is not a frequency breakdown — and ``source`` says which of the two you are
    looking at, so the display never claims to be an FFT when it is not.

    ``mode`` picks the shape. All of them are drawn in the same place — the
    readout column, beside the cover and under the track details — and all of
    them use the whole of it, out to the right edge of the window. They read
    the same frame, so switching between them costs a redraw and nothing else.
    """

    DEFAULT_CSS = "Analyzer { height: 5; }"

    # What cava is asked for, once, for every shape. Each of them resamples
    # this to what it draws, so neither a resize nor a change of shape has to
    # restart the FFT — and restarting it is the one thing that would put a
    # gap in the music's picture. Generous enough that the shapes are
    # averaging it down rather than stretching it out on any normal terminal.
    BANDS = 128
    # A floor for the band count, so a widget that has not been laid out yet
    # still has something to hold its ballistics in.
    MIN_BANDS = 4
    # And a ceiling for the shapes made of bars. See `count` for why.
    MAX_BARS = 64
    BLOCKS = " ▁▂▃▄▅▆▇█"
    # A Braille cell is a 2x4 grid of dots, and one code point carries all
    # eight of them: U+2800 plus a bit per dot. Eight addressable points in
    # the space of one block, which is what lets the `fine` shape draw a line
    # instead of a row of glyphs. Left column top to bottom, then right.
    BRAILLE = 0x2800
    DOTS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))
    # The shapes, as they are written in `config.toml`.
    MODES = ("bars", "mirror", "curve", "fine")

    level = reactive(-91.0)
    active = reactive(False)
    mode = reactive("bars")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Bands straight from cava, or None while we are on the RMS fallback.
        self.spectrum: list[float] | None = None
        # Sized for real on the first tick, once there is a width to read.
        self._bands = [0.0] * self.MIN_BANDS
        self._peaks = [0.0] * self.MIN_BANDS
        # Low bands carry more energy in most music; weight them like Winamp's.
        self._weights = self._weighting(self.MIN_BANDS)

    @property
    def source(self) -> str:
        """ "FFT" when cava is feeding us, "RMS" when we are guessing shapes."""
        return "FFT" if self.spectrum is not None else "RMS"

    # ------------------------------------------------------------ the bands

    @staticmethod
    def _weighting(count: int) -> list[float]:
        return [1.0 - (i / count) * 0.55 for i in range(count)]

    @property
    def count(self) -> int:
        """How many bands this shape draws at this size."""
        width = max(self.MIN_BANDS, self.size.width)
        if self.mode == "fine":
            # Two dots across per cell, so two bands per column.
            return width * 2
        if self.mode == "curve":
            # One value per column, for the shape that draws a line.
            return width
        # A bar and its gap, for as many as fit — and then no more. On a 4K
        # terminal the column is 380 cells and 190 bars of one cell each cost
        # 950 style runs a frame, which is 950 escape sequences the terminal
        # has to chew through ten times a second. Capped, the same width is
        # covered by fewer, wider bars, which is also what Winamp's looked
        # like. `_slots` is what keeps them reaching the right edge.
        return max(self.MIN_BANDS, min(self.MAX_BARS, width // 2))

    def _slots(self) -> list[int]:
        """How many cells each band gets, gap included, summing to the width.

        Distributed rather than divided: a plain `width // count` leaves a
        remainder of up to `count` cells unpainted on the right, which is the
        edge these shapes exist to reach.
        """
        count = max(1, len(self._bands))
        width = max(count, self.size.width)
        edges = [width * i // count for i in range(count + 1)]
        return [edges[i + 1] - edges[i] for i in range(count)]

    @staticmethod
    def _resample(frame: list[float], count: int) -> list[float]:
        """``frame`` spread over ``count`` slots.

        Averaged when there are more bands than slots, interpolated when there
        are fewer: the second is a smoother drawing of the same curve, not a
        finer measurement of it, and nothing downstream treats it as one.
        """
        size = len(frame)
        if size == 0:
            return [0.0] * count
        if size == count:
            return [max(0.0, min(1.0, value)) for value in frame]
        out: list[float] = []
        if count > size:
            for i in range(count):
                position = i * (size - 1) / max(1, count - 1)
                low = min(size - 1, int(position))
                high = min(size - 1, low + 1)
                weight = position - low
                out.append(frame[low] * (1 - weight) + frame[high] * weight)
        else:
            for i in range(count):
                first = int(i * size / count)
                last = max(first + 1, int((i + 1) * size / count))
                chunk = frame[first:last]
                out.append(sum(chunk) / len(chunk))
        return [max(0.0, min(1.0, value)) for value in out]

    def _targets(self, count: int | None = None) -> list[float]:
        count = self.count if count is None else count
        if not self.active:
            return [0.0] * count
        if self.spectrum is not None:
            # A real spectrum needs no shaping: cava already smooths it, and
            # inventing a weighting on top would only distort what it measured.
            return self._resample(self.spectrum, count)
        # -60 dBFS .. 0 dBFS mapped onto 0..1
        base = max(0.0, min(1.0, (self.level + 60.0) / 60.0))
        if len(self._weights) != count:
            self._weights = self._weighting(count)
        return [
            base * self._weights[i] * (random.uniform(0.55, 1.0) if base > 0.02 else 0.0)
            for i in range(count)
        ]

    def _resize(self, count: int) -> None:
        self._bands = [0.0] * count
        self._peaks = [0.0] * count
        self._weights = self._weighting(count)

    def watch_mode(self, mode: str) -> None:
        self._resize(self.count)
        self.refresh()

    def tick(self) -> None:
        count = self.count
        if len(self._bands) != count:
            self._resize(count)
        targets = self._targets(count)

        for i in range(count):
            target = targets[i]
            # Fast attack, slow release — standard meter ballistics.
            if target > self._bands[i]:
                self._bands[i] += (target - self._bands[i]) * 0.7
            else:
                self._bands[i] -= min(self._bands[i], 0.08)
            self._peaks[i] = max(self._bands[i], self._peaks[i] - 0.02)
        self.refresh()

    # --------------------------------------------------------------- drawing

    def _styles(self, values: list[float] | None = None) -> list[str]:
        """One colour per band, worked out once for the whole frame.

        It used to be a call per cell, and a call that resolved the palette
        each time: five rows of a 4K-wide analyser meant a thousand of them
        between one frame and the next.
        """
        palette = palette_for(self)
        accent, warning, danger = (
            palette["accent"],
            palette["warning"],
            palette["danger"],
        )
        return [
            danger if value > 0.8 else warning if value > 0.55 else accent
            for value in (self._bands if values is None else values)
        ]

    @staticmethod
    def _runs(cells: list[tuple[str, str]], out: Text) -> None:
        """Write one line, one span per run of cells sharing a style.

        Rich turns every span into its own escape sequence, and the shapes
        that reach the right edge of a wide terminal are mostly long stretches
        of the same colour: a bar and its gap, a row of silence. Merging them
        is the difference between a few dozen sequences a frame and a
        thousand, which is what a 4K terminal was choking on.
        """
        run_style: str | None = None
        run: list[str] = []
        for text, style in cells:
            if style != run_style:
                if run:
                    out.append("".join(run), style=run_style)
                run_style, run = style, []
            run.append(text)
        if run:
            out.append("".join(run), style=run_style)

    def render(self) -> Text:
        # A mirror needs a row above the centre line and one below it. In the
        # compact layout the analyser is one row tall, and there it draws the
        # plain bars instead of a third of a shape.
        if self.mode == "mirror" and self.size.height >= 3:
            return self._render_mirror()
        if self.mode == "curve":
            return self._render_curve()
        if self.mode == "fine":
            return self._render_fine()
        return self._render_bars()

    def _render_bars(self) -> Text:
        rows = max(1, self.size.height)
        palette = palette_for(self)
        peak_style = palette["peak"]
        styles = self._styles()
        slots = self._slots()
        blocks = self.BLOCKS
        last = len(blocks) - 1
        out = Text()
        for row in range(rows):
            # Row 0 is the top of the analyser.
            floor = (rows - row - 1) / rows
            cells: list[tuple[str, str]] = []
            for i, value in enumerate(self._bands):
                width = slots[i]
                filled = value - floor
                if filled >= 1 / rows:
                    glyph = "█"
                elif filled > 0:
                    idx = int(filled * rows * last)
                    glyph = blocks[max(0, min(last, idx))]
                else:
                    glyph = " "
                peak = self._peaks[i]
                if glyph == " " and int(peak * rows) == (rows - row - 1) and peak > 0.02:
                    cells.append(("▁" * (width - 1) + " ", peak_style))
                else:
                    cells.append((glyph * (width - 1) + " ", styles[i]))
            self._runs(cells, out)
            if row != rows - 1:
                out.append("\n")
        return out

    def _render_mirror(self) -> Text:
        """Bars growing both ways from a centre line.

        Half blocks on both halves rather than the eighth ramp the upright
        bars use: the shape's whole point is the symmetry, and a top half
        drawn eight times finer than the bottom one does not have it.
        """
        rows = max(3, self.size.height)
        middle = rows // 2
        empty = palette_for(self)["empty"]
        styles = self._styles()
        slots = self._slots()
        out = Text()
        for row in range(rows):
            cells: list[tuple[str, str]] = []
            for i, value in enumerate(self._bands):
                width = slots[i]
                if row == middle:
                    cells.append(("─" * (width - 1) + " ", empty))
                    continue
                distance = (middle - 1 - row) if row < middle else (row - middle - 1)
                filled = value * middle - distance
                if filled >= 1:
                    glyph = "█"
                elif filled > 0:
                    glyph = "▄" if row < middle else "▀"
                else:
                    glyph = " "
                cells.append((glyph * (width - 1) + " ", styles[i]))
            self._runs(cells, out)
            if row != rows - 1:
                out.append("\n")
        return out

    def _render_fine(self) -> Text:
        """The spectrum as a thin trace, on the Braille dot grid.

        What it buys over `curve` is not vertical precision — the eighth-block
        ramp has eight steps to a cell and the dots have four — but the two
        things that make a line a line. Twice the horizontal resolution, two
        dots to a column; and the dots between one sample and the next lit as
        well, meeting the neighbours halfway, so the shape is a stroke and not
        a row of loose marks with gaps down every steep edge.

        It needs a font with Braille. Most do — every Nerd Font, DejaVu, the
        Noto family — but a font without it draws boxes, and there is no way
        to ask a terminal beforehand. That is why this is a shape you choose
        and not one anything falls back to.
        """
        rows = max(1, self.size.height)
        values = self._bands
        cells = max(1, len(values) // 2)
        subrows = rows * 4
        top = subrows - 1
        # Dot 0 is the bottom of the widget, `top` the ceiling.
        heights = [min(top, int(value * subrows)) for value in values]
        grid = [[0] * cells for _ in range(rows)]
        dots = self.DOTS
        for x, y in enumerate(heights):
            cell = x // 2
            if cell >= cells:
                break
            low = high = y
            if x:
                middle = (y + heights[x - 1]) // 2
                low, high = min(low, middle), max(high, middle)
            if x + 1 < len(heights):
                middle = (y + heights[x + 1]) // 2
                low, high = min(low, middle), max(high, middle)
            column = dots[x % 2]
            for dot in range(low, high + 1):
                grid[rows - 1 - dot // 4][cell] |= column[3 - dot % 4]

        # One colour per cell, from the louder of the two bands in it: a cell
        # is one glyph and cannot be two colours.
        styles = self._styles(
            [max(values[2 * i], values[2 * i + 1]) for i in range(cells)]
        )
        braille = self.BRAILLE
        out = Text()
        for row in range(rows):
            line: list[tuple[str, str]] = []
            for cell, bits in enumerate(grid[row]):
                # No style on an empty cell, so a quiet row is a single run.
                line.append((chr(braille + bits), styles[cell]) if bits else (" ", ""))
            self._runs(line, out)
            if row != rows - 1:
                out.append("\n")
        return out

    def _render_curve(self) -> Text:
        """The contour of the spectrum, one glyph per column and nothing under
        it: the shape is a line, not a filled area."""
        rows = max(1, self.size.height)
        styles = self._styles()
        blocks = self.BLOCKS
        last = len(blocks) - 1
        out = Text()
        for row in range(rows):
            floor = (rows - row - 1) / rows
            cells: list[tuple[str, str]] = []
            for i, value in enumerate(self._bands):
                filled = value - floor
                if 0 < filled <= 1 / rows:
                    idx = int(filled * rows * last)
                    cells.append((blocks[max(1, min(last, idx))], styles[i]))
                else:
                    # No style at all, so a whole row of quiet is one run.
                    cells.append((" ", ""))
            self._runs(cells, out)
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
        palette = palette_for(self)
        rows = max(3, self.size.height - 2)
        middle = rows // 2
        out = Text()
        for row in range(rows):
            for band, gain in enumerate(gains):
                # How far from the centre line this band reaches, in rows.
                extent = round((gain / self.limit) * middle)
                if row == middle:
                    glyph, style = "─", palette["empty"]
                elif extent > 0 and middle - extent <= row < middle:
                    glyph, style = "█", palette["accent"]
                elif extent < 0 and middle < row <= middle - extent:
                    glyph, style = "█", palette["warning"]
                else:
                    glyph, style = "·", palette["bar_empty"]
                if band == self.selected:
                    foreground = style if glyph != "·" else palette["eq_inactive"]
                    style = f"bold {foreground} on {palette['eq_background']}"
                out.append(f" {glyph}  ", style=style)
            out.append("\n")

        for band, label in enumerate(self.labels):
            style = (
                f"bold {palette['accent']}" if band == self.selected else palette["muted"]
            )
            out.append(f"{label:>3} ", style=style)
        out.append("\n")
        for band, gain in enumerate(gains):
            style = (
                f"bold {palette['accent']}" if band == self.selected else palette["muted"]
            )
            out.append(f"{gain:>+3.0f} ", style=style)
        return out
