"""The pieces of Winamp chrome: LCD clock, sliders, spinner, cover.

The analyser and the equaliser faders live in `analyzer.py`, the moving text
in `scrolling.py`; both are re-exported here so imports keep one home."""

from __future__ import annotations

import contextlib

from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget

from .analyzer import Analyzer, EqualizerBars
from .artwork import Cover, Protocol, kitty_delete, quadrant_cell
from .scrolling import Glide, LyricsPane, Marquee
from .theme import palette_for

__all__ = [
    "Analyzer",
    "Artwork",
    "EqualizerBars",
    "Glide",
    "LyricsPane",
    "Marquee",
    "SeekBar",
    "Slider",
    "Spinner",
    "TimeDisplay",
]

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
