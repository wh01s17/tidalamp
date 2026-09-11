"""The pieces of Winamp chrome: LCD clock, scrolling title, analyser, sliders."""

from __future__ import annotations

import contextlib
import random

from rich.cells import cell_len, set_cell_size, split_graphemes
from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget

from .artwork import Cover, Protocol, kitty_delete, quadrant_cell
from .lyrics import LyricsDocument
from .theme import palette_for

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
        return Text("\n".join(rows), style=f"bold {palette_for(self)['accent']}")


def _window(text: str, start: int, width: int) -> str:
    """`width` cells of `text` from cell `start`, cut on grapheme boundaries.

    Code-point slicing split combining accents and made CJK and emoji rows
    wider than their widget. A wide glyph straddling the left edge is dropped
    and the gap padded, rather than drawn half.
    """
    graphemes, _cells = split_graphemes(text)
    used = 0
    first = len(text)
    for begin, _end, cells in graphemes:
        if used >= start:
            first = begin
            break
        used += cells
    lead = " " * (used - start) if used > start else ""
    return set_cell_size(lead + text[first:], width)


class Glide(Widget):
    """Lines that fit are shown whole; lines that do not glide to show the rest.

    Where a line is wider than the widget it holds still for a moment, slides
    slowly left until its end is in view, holds again, and slides back. A
    crop hid the end of an album title for good, and a loop that wraps round
    reads the name in two pieces with the join in the middle; going there and
    back shows the whole of it, in order, whatever the room.

    Several lines share one phase and each stops at its own end, so a short
    line waits while a long one finishes and they set off again together.
    """

    DEFAULT_CSS = "Glide { height: 1; }"

    # Ten calls a second, a cell every three: slow enough to read while it
    # moves. The hold is in those steps: about two seconds at either end.
    EVERY = 3
    HOLD = 7

    def __init__(self, text: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._lines = text.split("\n") if text else []
        self._offset = 0
        self._direction = 1
        self._wait = self.HOLD
        self._calls = 0

    def on_mount(self) -> None:
        self.set_interval(1 / 10, self._timed)

    def update(self, text: str) -> None:
        """The same call as `Static.update`; the glide restarts on new text."""
        lines = text.split("\n") if text else []
        if lines == self._lines:
            return
        self._lines = lines
        self._offset, self._direction, self._wait = 0, 1, self.HOLD
        self.refresh()

    @property
    def content(self) -> str:
        """The whole text, as `Static.content` gives it: not the window."""
        return "\n".join(self._lines)

    def _overflow(self) -> int:
        width = self.size.width
        lines = self._lines_to_draw()
        return max((cell_len(line) - width for line in lines), default=0)

    def _timed(self) -> None:
        # Nothing behind a modal is worth animating: the player under a scrim
        # repaints the whole blend for a line nobody is reading.
        with contextlib.suppress(Exception):
            if len(self.app.screen_stack) > 1:
                return
        self.tick()

    def tick(self) -> None:
        overflow = self._overflow()
        if overflow <= 0:
            if self._offset:
                self._offset = 0
                self.refresh()
            return
        self._calls = (self._calls + 1) % self.EVERY
        if self._calls:
            return
        if self._wait:
            self._wait -= 1
            return
        self._offset += self._direction
        if self._offset >= overflow or self._offset <= 0:
            self._offset = max(0, min(self._offset, overflow))
            self._direction = -self._direction
            self._wait = self.HOLD
        self.refresh()

    def _lines_to_draw(self) -> list[str]:
        return self._lines

    def _style(self) -> str:
        return ""

    def render(self) -> Text:
        width = max(1, self.size.width)
        rows = []
        for line in self._lines_to_draw():
            shift = max(0, min(self._offset, cell_len(line) - width))
            rows.append(_window(line, shift, width))
        return Text("\n".join(rows), style=self._style(), no_wrap=True)


class Marquee(Glide):
    """The track title, gliding there and back when it does not fit.

    It used to loop like the Winamp title bar, `***` and round again, fast.
    It now moves like every other line in the band: slowly, and back.
    """

    DEFAULT_CSS = "Marquee { height: 1; }"

    text = reactive("")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # What it says while nothing is playing: the player's name, or a
        # themed look's line.
        self.idle_text = "TIDAL AMP"

    def on_mount(self) -> None:
        # The app's fast tick drives it, as it always has; no timer of its own.
        pass

    def watch_text(self, text: str) -> None:
        self.update(text)

    def _lines_to_draw(self) -> list[str]:
        return self._lines or [self.idle_text]

    def _style(self) -> str:
        return f"bold {palette_for(self)['accent']}"


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


class SeekBar(Widget):
    """Position slider with the Winamp thumb."""

    DEFAULT_CSS = "SeekBar { height: 1; }"

    position = reactive(0.0)
    total = reactive(0.0)

    def value_at(self, x: int) -> float | None:
        """Translate a widget-relative click into an absolute track position."""
        if self.total <= 0:
            return None
        width = max(4, self.size.width)
        content_x = max(0, min(width - 1, x - self.content_offset.x))
        return self.total * content_x / (width - 1)

    def render(self) -> Text:
        width = max(4, self.size.width)
        palette = palette_for(self)
        ratio = (self.position / self.total) if self.total else 0.0
        thumb = int(ratio * (width - 1))
        # A dot on a line, the played part a heavier line in the accent. The
        # thumb was a full `▓` cell, which on a one-row bar looked like a block
        # stuck through it rather than a handle riding on it.
        bar = Text()
        if thumb:
            bar.append("━" * thumb, style=palette["accent"])
        bar.append("●", style=f"bold {palette['accent']}")
        bar.append("─" * (width - thumb - 1), style=palette["input_border"])
        return bar


class Slider(Widget):
    """A labelled horizontal level.

    Volume fills from the left; balance is ``centred``, filling outwards from
    the middle in whichever direction it leans, which is the only way a value
    that can be negative reads correctly at a glance.
    """

    DEFAULT_CSS = "Slider { height: 1; }"

    value = reactive(0)
    maximum = reactive(100)
    label = reactive("VOL")
    centred = reactive(False)

    def _track(self) -> tuple[int, int]:
        """The first content cell and number of cells occupied by the track."""
        width = max(8, self.size.width)
        start = len(self.label) + 1
        track = max(1, width - len(self.label) - 6)
        if self.centred:
            # Rendering always includes a real centre cell. Keep clicks on the
            # same odd-width track, even if the available width happened to be even.
            track = (track // 2) * 2 + 1
        return start, track

    def value_at(self, x: int) -> int:
        """Translate a widget-relative click into this slider's value."""
        start, track = self._track()
        content_x = x - self.content_offset.x
        cell = max(0, min(track - 1, content_x - start))
        if self.centred:
            centre = track // 2
            if centre == 0 or cell == centre:
                return 0
            return round((cell - centre) / centre * self.maximum)
        if track == 1:
            return 0
        return round(cell / (track - 1) * self.maximum)

    def render(self) -> Text:
        palette = palette_for(self)
        _start, track = self._track()
        bar = Text(f"{self.label} ", style=palette["muted"])
        if self.centred:
            half = track // 2
            offset = int((self.value / self.maximum) * half) if self.maximum else 0
            left = max(0, min(half, -offset))
            right = max(0, min(half, offset))
            bar.append("░" * (half - left), style=palette["bar_empty"])
            bar.append("█" * left, style=palette["accent"])
            bar.append("│", style=palette["empty"])
            bar.append("█" * right, style=palette["accent"])
            bar.append("░" * (half - right), style=palette["bar_empty"])
        else:
            ratio = (self.value / self.maximum) if self.maximum else 0.0
            # Clamped, not trusted: a value past `maximum` used to draw a bar
            # wider than the track, which pushed the number off the widget and,
            # far enough out, made the whole line too long to render at all.
            filled = max(0, min(track, int(ratio * track)))
            bar.append("█" * filled, style=palette["accent"])
            bar.append("░" * (track - filled), style=palette["bar_empty"])
        bar.append(f" {self.value:>3}", style=palette["muted"])
        return bar


# What each letter of an emblem paints with. Roles rather than colours, so a
# themed look's drawing follows the palette the user picks after it.
EMBLEM_ROLES = {
    "A": "accent",
    "B": "body",
    "C": "container",
    "G": "playable",
    "K": "screen",
    "M": "muted",
    "R": "danger",
    "Y": "warning",
}


def shrink(rows, width: int, height: int) -> list[str]:
    """`rows` reduced to fit `width` x `height` pixels, keeping its shape.

    Each new pixel takes the role most of its source block has, except that
    the roles that carry detail (anything but the see-through and the
    drawing's own main fill) count for more: an eye or a thin limb is a
    minority in any block it falls in, and a plain vote erased them. Four
    to one: at double, the unit lost its eye in the smallest box.
    """
    source_h, source_w = len(rows), len(rows[0])
    factor = max(source_w / max(1, width), source_h / max(1, height), 1.0)
    if factor == 1.0:
        return list(rows)
    counts: dict[str, int] = {}
    for char in "".join(rows):
        if char != ".":
            counts[char] = counts.get(char, 0) + 1
    fill = max(counts, key=counts.get) if counts else "."
    target_w, target_h = int(source_w / factor), int(source_h / factor)
    out = []
    for y in range(target_h):
        top, bottom = int(y * factor), max(int((y + 1) * factor), int(y * factor) + 1)
        line = ""
        for x in range(target_w):
            left, right = int(x * factor), max(int((x + 1) * factor), int(x * factor) + 1)
            votes: dict[str, int] = {}
            for row in rows[top:bottom]:
                for char in row[left:right]:
                    votes[char] = votes.get(char, 0) + (1 if char in (".", fill) else 4)
            line += max(votes, key=votes.get)
        out.append(line)
    return out


def _blend(colour: str, ground: str, amount: float) -> str:
    """`colour` laid over `ground` at `amount`, as `#rrggbb`."""
    top, base = colour.lstrip("#")[:6], ground.lstrip("#")[:6]
    mixed = (
        round(int(top[i : i + 2], 16) * amount + int(base[i : i + 2], 16) * (1 - amount))
        for i in (0, 2, 4)
    )
    return "#" + "".join(f"{value:02x}" for value in mixed)


def backdrop_runs(
    rows, palette, width: int, height: int, amount: float = 0.35
) -> dict[int, list[tuple[int, int, str]]]:
    """Where an emblem sits behind a list, as runs of cells per line.

    A pixel is two cells wide and one tall, which is square on screen; there
    is no half block behind text, so this is as fine as a backdrop gets. The
    drawing is scaled to most of the height, shrunk if it does not fit, and
    set against the right edge where it covers the short columns rather than
    the titles. Its colours are mixed into the list's ground so the rows on
    top of it still read.
    """
    if not rows or width < 8 or height < 4:
        return {}
    room_w, room_h = (width - 2) // 2, height
    source_h, source_w = len(rows), len(rows[0])
    scale = max(1, min(room_w // source_w, room_h // source_h))
    art = shrink(rows, room_w, room_h)
    if scale > 1:
        art = [
            "".join(char * scale for char in row) for row in art for _copy in range(scale)
        ]
    ground = palette["display_background"]
    colours = {
        char: _blend(palette[role], ground, amount) for char, role in EMBLEM_ROLES.items()
    }
    left = width - 2 - len(art[0]) * 2
    top = (height - len(art)) // 2
    runs: dict[int, list[tuple[int, int, str]]] = {}
    for offset, row in enumerate(art):
        line = []
        start, current = 0, None
        for index, char in enumerate(row + "."):
            colour = colours.get(char)
            if colour != current:
                if current is not None:
                    line.append((left + start * 2, left + index * 2, current))
                start, current = index, colour
        if line:
            runs[top + offset] = line
    return runs


class LyricsPane(Widget):
    """The playing track's lyrics, in the column `split` frees above the player.

    Stacked, the player is a band and the queue has the rest, so there is no
    room for words and `y` opens them in a window. Split, the player has a
    column of its own and a band nine rows tall left most of it empty; the
    lyrics are what fills it. The document is the one `y` loads and caches.

    Synced lyrics keep the sung line centred, lit in the accent, with what has
    been sung dimmed above it. Plain lyrics are shown from the top: with no
    timestamps there is nothing to follow.
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.document: LyricsDocument | None = None
        self.message = ""
        self._position = 0.0
        self._active: int | None = None
        # A themed look's line, for the time there are no words to show:
        # nothing playing, or a track without lyrics.
        self.tagline = ""

    def show(self, document: LyricsDocument | None, message: str = "") -> None:
        """Swap the words, or put a line saying why there are none."""
        self.document, self.message = document, message
        self._active = None
        self.refresh()

    def follow(self, position: float) -> None:
        """Move with the track, repainting only when the sung line changes.

        Called four times a second; a line lasts seconds, so almost every call
        is a comparison and nothing else.
        """
        self._position = position
        document = self.document
        if document is None or not document.synced:
            return
        active = document.active_index(position)
        if active != self._active:
            self._active = active
            self.refresh()

    def render(self) -> Text:
        palette = palette_for(self)
        width, height = self.size.width, self.size.height
        document = self.document
        if document is None:
            if self.tagline:
                return self._idle(palette, width, height)
            return Text(f"  {self.message}", style=palette["muted"])
        start, lines, active = document.window(self._position, height)
        out = Text()
        for offset, line in enumerate(lines):
            index = start + offset
            if index == active:
                style = f"bold {palette['accent']}"
            elif active is not None and index < active:
                style = palette["muted"]
            else:
                style = palette["body"]
            # Cropped rather than wrapped: a wrapped line would take two rows
            # and push the sung one off the centre it is supposed to hold.
            row = Text(f"  {line.text}", style=style, no_wrap=True)
            row.truncate(width, overflow="ellipsis")
            if offset:
                out.append("\n")
            out.append_text(row)
        return out

    def _idle(self, palette, width: int, height: int) -> Text:
        """The look's line, and the reason there are no words under it,
        centred in the pane."""
        words = [(self.tagline, f"bold {palette['accent']}")]
        if self.message:
            words.append((self.message, palette["muted"]))
        out = Text("\n" * max(0, (height - len(words)) // 2), no_wrap=True)
        for index, (text, style) in enumerate(words):
            if index:
                out.append("\n")
            line = Text(text, style=style, no_wrap=True)
            line.truncate(width, overflow="ellipsis")
            out.append(" " * max(0, (width - line.cell_len) // 2))
            out.append_text(line)
        return out


class Spinner(Widget):
    """A one-line "working on it" indicator.

    Everything slow in this app runs in a worker so the UI keeps painting,
    which is right — but a UI that keeps painting the old screen while it
    waits is indistinguishable from a frozen one. This says what is being
    waited for and moves while it waits.
    """

    DEFAULT_CSS = "Spinner { height: 1; }"

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    INTERVAL = 1 / 12

    # layout=True: the widget is auto-width, so appearing and disappearing has
    # to re-run the layout or it stays measured at zero and never shows.
    label = reactive("", layout=True)
    _frame = reactive(0)

    def on_mount(self) -> None:
        self.set_interval(self.INTERVAL, self._advance)

    def _advance(self) -> None:
        # Idle costs nothing: with no label there is no repaint to trigger.
        if self.label:
            self._frame = (self._frame + 1) % len(self.FRAMES)

    @property
    def busy(self) -> bool:
        return bool(self.label)

    def start(self, label: str) -> None:
        self.label = label

    def stop(self) -> None:
        self.label = ""

    def render(self) -> Text:
        if not self.label:
            return Text("")
        palette = palette_for(self)
        spun = Text(f"{self.FRAMES[self._frame]} ", style=f"bold {palette['accent']}")
        label = Text(self.label, style=palette["muted"])
        # Labels carry a playlist name, which can be long; the frame has to
        # survive whatever room is left, so the text is what gives way.
        room = self.size.width - 2
        if room > 0:
            label.truncate(room, overflow="ellipsis")
        spun.append_text(label)
        return spun


class Artwork(Widget):
    """The album cover, drawn with whatever the terminal supports.

    Two very different jobs behind one widget. With half blocks the cover is
    ordinary text and the compositor handles it like any other widget. With
    kitty or sixel the pixels live in a layer the compositor knows nothing
    about, so the escape goes out as a Rich *control* segment — zero cells
    wide, emitted in the middle of the line Textual is already drawing — and
    it is our job to delete the image again when the widget goes away.
    """

    # A cell is about twice as tall as it is wide, so twice as many columns as
    # rows is square on screen — which is the shape every album cover comes in.
    # 9 rows is the smallest box worth drawing and what fits the 76x20 minimum;
    # the app grows it with the terminal through `resize`.
    MIN_ROWS = 9
    MAX_ROWS = 20

    DEFAULT_CSS = "Artwork { width: 18; height: 9; display: none; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cover: Cover | None = None
        self.rows = self.MIN_ROWS
        self.cols = self.MIN_ROWS * 2
        # kitty addresses images by id; keeping one means a new cover replaces
        # the old one instead of stacking up in the terminal's memory.
        self.image_id = 1

    def resize(self, rows: int) -> bool:
        """Set the box to ``rows`` tall, twice that wide. True if it changed.

        The cover already on screen is at the old size, so the caller has to
        render it again; dropping it here keeps a stretched one from showing
        in between.
        """
        rows = max(self.MIN_ROWS, min(rows, self.MAX_ROWS))
        if rows == self.rows:
            return False
        self.rows, self.cols = rows, rows * 2
        self.styles.width = self.cols
        self.styles.height = self.rows
        if self.cover is not None:
            self.show(None)
        return True

    def show(self, cover: Cover | None) -> None:
        """Swap the cover. ``None`` hides the widget and reclaims its columns."""
        if cover is None and self.cover is not None:
            self._erase()
        self.cover = cover
        self.styles.display = "none" if cover is None else "block"
        self.refresh()

    def _erase(self) -> None:
        """Ask the terminal to drop the image we transmitted, if any."""
        if self.cover is None or self.cover.protocol is not Protocol.KITTY:
            return
        driver = getattr(self.app, "_driver", None)
        if driver is not None:
            # A cover left on screen is ugly; a crash on the way out is worse.
            # Terminals drop their images when the app exits anyway.
            with contextlib.suppress(Exception):
                driver.write(kitty_delete(self.image_id))

    def on_unmount(self) -> None:
        self._erase()

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        cover = self.cover
        if cover is None:
            return Strip.blank(width, Style())

        if cover.pixels is not None:
            # Two sample rows and two sample columns per cell: `artwork.blocks`
            # gives four pixels where `▀` alone took one wide and two tall.
            top = cover.pixels[y * 2] if y * 2 < len(cover.pixels) else ()
            bottom = cover.pixels[y * 2 + 1] if y * 2 + 1 < len(cover.pixels) else ()
            cells = min(width, len(top) // 2, len(bottom) // 2)
            segments = []
            for x in range(cells):
                glyph, fg, bg = quadrant_cell(
                    (top[x * 2], top[x * 2 + 1], bottom[x * 2], bottom[x * 2 + 1])
                )
                segments.append(
                    Segment(
                        glyph,
                        Style(color=Color.from_rgb(*fg), bgcolor=Color.from_rgb(*bg)),
                    )
                )
            return Strip(segments, len(segments)).adjust_cell_length(width, Style())

        # Pixel protocols draw the whole cover from one anchor, so the escape
        # belongs on the first line only; the rest of the box stays blank and
        # the image floats over it.
        if y == 0 and cover.escape:
            # Rich only asks whether `control` is truthy; its type says a list
            # of control codes, and there is no code for "an APC the terminal
            # will read". True is what makes the segment measure zero cells.
            escape = Segment(cover.escape, Style(), True)  # type: ignore[arg-type]
            return Strip([escape, Segment(" " * width, Style())], width)
        return Strip.blank(width, Style())
