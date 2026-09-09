"""The pieces of Winamp chrome: LCD clock, scrolling title, analyser, sliders."""

from __future__ import annotations

import contextlib
import random

from rich.cells import set_cell_size, split_graphemes
from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget

from .artwork import Cover, Protocol, kitty_delete
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
        graphemes, cells = split_graphemes(padded)
        if cells > width:
            self._offset = (self._offset + 1) % len(graphemes)
        else:
            self._offset = 0

    def render(self) -> Text:
        width = max(1, self.size.width)
        style = f"bold {palette_for(self)['accent']}"
        if not self.text:
            return Text("TIDAL AMP", style=style)
        padded = f"{self.text}   ***   "
        graphemes, cells = split_graphemes(padded)
        if cells <= width:
            return Text(set_cell_size(self.text, width), style=style)
        # Offset and crop on grapheme boundaries. Code-point slicing split
        # combining accents and made CJK/emoji rows wider than their widget.
        start = graphemes[self._offset % len(graphemes)][0]
        rotated = padded[start:] + padded[:start]
        return Text(set_cell_size(rotated + rotated, width), style=style)


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
        """ "FFT" when cava is feeding us, "RMS" when we are guessing shapes."""
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
        palette = palette_for(self)
        if height_ratio > 0.8:
            return palette["danger"]
        if height_ratio > 0.55:
            return palette["warning"]
        return palette["accent"]

    def render(self) -> Text:
        rows = max(1, self.size.height)
        palette = palette_for(self)
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
                    out.append("▁", style=palette["peak"])
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

    def render(self) -> Text:
        width = max(4, self.size.width)
        palette = palette_for(self)
        ratio = (self.position / self.total) if self.total else 0.0
        thumb = int(ratio * (width - 1))
        bar = Text()
        for i in range(width):
            if i == thumb:
                bar.append("▓", style=f"bold {palette['accent']}")
            else:
                bar.append("─", style=palette["input_border"])
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

    def render(self) -> Text:
        width = max(8, self.size.width)
        palette = palette_for(self)
        track = width - len(self.label) - 6
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
            top = cover.pixels[y * 2] if y * 2 < len(cover.pixels) else ()
            bottom = cover.pixels[y * 2 + 1] if y * 2 + 1 < len(cover.pixels) else ()
            segments = [
                Segment(
                    "▀",
                    Style(
                        color=Color.from_rgb(*top[x]) if x < len(top) else None,
                        bgcolor=Color.from_rgb(*bottom[x]) if x < len(bottom) else None,
                    ),
                )
                for x in range(min(width, len(top)))
            ]
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
