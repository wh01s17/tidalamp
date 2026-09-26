"""Text that moves: lines that glide when they do not fit, the scrolling
title, and the two surfaces the lyrics are read on."""

from __future__ import annotations

import contextlib

from rich.cells import cell_len, set_cell_size, split_graphemes
from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from .lyrics import LyricsDocument, fit, last_start
from .theme import palette_for


def window(text: str, start: int, width: int) -> str:
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
        # repaints the whole blend for a line nobody is reading. A line in the
        # modal itself is the one being read.
        with contextlib.suppress(Exception):
            if self.screen is not self.app.screen:
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

    def _line_styles(self) -> list[str]:
        """A style for each line, over `_style`; none by default. A line
        past the end of the list takes `_style` alone."""
        return []

    def render(self) -> Text:
        width = max(1, self.size.width)
        styles = self._line_styles()
        out = Text(style=self._style(), no_wrap=True)
        for index, line in enumerate(self._lines_to_draw()):
            shift = max(0, min(self._offset, cell_len(line) - width))
            if index:
                out.append("\n")
            out.append(
                window(line, shift, width),
                style=styles[index] if index < len(styles) else "",
            )
        return out


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


class LyricsBoard(Widget):
    """The words, wrapped to the width they are given, following the song.

    Read in two places: the window `y` opens over the player, and the panel
    beside the cover in the full-screen view. The same lyrics, drawn the same
    way, so moving from one to the other is the same page in another frame.

    A verse wider than the surface takes two or three rows, so which lines
    show is decided **by rows** (`lyrics.fit`) with the sung one centred:
    counted by lines it fell below the bottom. Plain lyrics have no
    timestamps to follow: the window scrolls them by hand, and the panel,
    which has no keys of its own (they belong to the queue), carries them
    along with the track -- `drift=True`.

    A lyric shorter than the surface is centred in it, and with `centre=True`
    the block is centred across it as well: in a column beside the cover the
    words are a page of their own, and left hanging from the top left corner
    of a tall panel they read as spilt rather than laid out.
    """

    # The cells the marker, «▶ » or two spaces, takes at the start of a row.
    MARKER = 2

    # The widest a centred block is set: about a line of prose, so a verse
    # that has to wrap comes back to a left edge the eye can find again.
    COLUMN = 56

    def __init__(self, *, drift: bool = False, centre: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.document: LyricsDocument | None = None
        # Why there are no words, when there are none: loading, or the error.
        self.message = ""
        self.drifts = drift
        self.centres = centre
        self._position = 0.0
        self._active: int | None = None
        # The first plain line on screen, in lines: the row it starts at is
        # worked out when it is drawn, at the width it is drawn to.
        self._offset = 0

    def show(self, document: LyricsDocument | None, message: str = "") -> None:
        """Swap the words, or put a line saying why there are none."""
        self.document, self.message = document, message
        self._active = None
        self._offset = 0
        self.refresh()

    def follow(self, position: float, duration: float = 0.0) -> None:
        """Move with the track, repainting only when what shows changes.

        Called four times a second; a line lasts seconds, so almost every
        call is a comparison and nothing else.
        """
        self._position = position
        document = self.document
        if document is None:
            return
        if not document.synced:
            if self.drifts:
                self._drift(duration)
            return
        active = document.active_index(position)
        if active != self._active:
            self._active = active
            self.refresh()

    def _drift(self, duration: float) -> None:
        """Where plain lyrics sit, for how far into the track it is: the last
        line is on screen by the end of the song."""
        rows = self._rows()
        if not rows or duration <= 0:
            return
        progress = max(0.0, min(1.0, self._position / duration))
        offset = round(progress * last_start(rows, self._height()))
        if offset != self._offset:
            self._offset = offset
            self.refresh()

    def scroll_lines(self, amount: int) -> None:
        """Move plain lyrics by hand. Synced ones follow the song instead."""
        document = self.document
        if document is None or document.synced or self.drifts:
            return
        last = last_start(self._rows(), self._height())
        self._offset = max(0, min(self._offset + amount, last))
        self.refresh()

    # --------------------------------------------------------------- drawing

    def _height(self) -> int:
        return max(5, self.size.height)

    def _wrap(self, text: str) -> list[str]:
        """``text`` in rows of the width left by the marker, split on words."""
        if not text:
            return [""]
        return [
            part.plain.rstrip()
            for part in Text(text).wrap(self.app.console, self._column())
        ]

    def _column(self) -> int:
        """How wide the words are set, which is not always the whole surface.

        A centred block takes half the view when the queue is closed, and a
        verse run across eighty or a hundred cells is a line the eye loses
        its way back from. It is set in a column of reading width and that
        column is centred; the window, which the reader sized, keeps using
        all of itself.
        """
        width = max(10, self.size.width - self.MARKER)
        return min(width, self.COLUMN) if self.centres else width

    def _wrapped(self) -> list[list[str]]:
        document = self.document
        return [self._wrap(line.text) for line in document.lines] if document else []

    def _rows(self) -> list[int]:
        """How many rows each line takes, once wrapped."""
        return [len(parts) for parts in self._wrapped()]

    def render(self) -> Text:
        palette = palette_for(self)
        document = self.document
        if document is None:
            return Text(f"  {self.message}", style=palette["muted"])
        wrapped = self._wrapped()
        rows = [len(parts) for parts in wrapped]
        height = self._height()
        if document.synced:
            active = document.active_index(self._position)
            start, end = fit(rows, active or 0, height)
        else:
            active = None
            # Clamped here and not where it is moved: the last screenful
            # depends on the width the lines are wrapped to, which is this
            # widget's, and the window is resizable.
            self._offset = max(0, min(self._offset, last_start(rows, height)))
            start = self._offset
            end = fit(rows[start:], 0, height)[1] + start
        out = Text(no_wrap=True, overflow="crop")
        # A lyric shorter than the surface is centred in it rather than hung
        # from the top edge: beside the cover a dozen lines with a screenful
        # of nothing under them read as a page half printed.
        used = sum(rows[start:end])
        if start == 0 and end == len(rows) and used < height:
            out.append("\n" * ((height - used) // 2))
        indent = " " * self._indent(wrapped)
        for index in range(start, end):
            style = (
                f"bold {palette['active_foreground']} on {palette['accent']}"
                if index == active
                else palette["body"]
            )
            for row, part in enumerate(wrapped[index]):
                marker = "▶ " if index == active and row == 0 else "  "
                # The indent outside the style: the lit line is the words and
                # the marker, not the air the block is centred by.
                out.append(indent)
                out.append(f"{marker}{part}\n", style=style)
        return out

    def _indent(self, wrapped: list[list[str]]) -> int:
        """The air on the left that centres the block, where it is centred.

        Measured over the whole lyric and not over the lines on screen: with
        the widest verse deciding it, the block holds still while the song
        goes by instead of shifting under every change of window.
        """
        if not self.centres:
            return 0
        widest = max((cell_len(part) for parts in wrapped for part in parts), default=0)
        return max(0, (self.size.width - self.MARKER - widest) // 2)


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
        # The first plain line on screen (`follow`).
        self._start = 0
        # A themed look's line, for the time there are no words to show:
        # nothing playing, or a track without lyrics.
        self.tagline = ""

    def show(self, document: LyricsDocument | None, message: str = "") -> None:
        """Swap the words, or put a line saying why there are none."""
        self.document, self.message = document, message
        self._active = None
        self._start = 0
        self.refresh()

    def follow(self, position: float, duration: float = 0.0) -> None:
        """Move with the track, repainting only when what shows changes.

        Called four times a second; a line lasts seconds, so almost every call
        is a comparison and nothing else. Synced lyrics follow the sung line.
        Plain ones have no timestamps, and the pane has no keys of its own to
        scroll with (those belong to the queue), so they move through the
        track instead: the window slides from the first line to the last as
        the song goes, and the end of the words is on screen by the end of it.
        """
        self._position = position
        document = self.document
        if document is None:
            return
        if not document.synced:
            start = self._plain_start(duration)
            if start != self._start:
                self._start = start
                self.refresh()
            return
        active = document.active_index(position)
        if active != self._active:
            self._active = active
            self.refresh()

    def _plain_start(self, duration: float) -> int:
        """Where plain lyrics start, for how far into the track it is."""
        document = self.document
        overflow = len(document.lines) - self.size.height if document else 0
        if overflow <= 0 or duration <= 0:
            return 0
        progress = max(0.0, min(1.0, self._position / duration))
        return round(progress * overflow)

    def render(self) -> Text:
        palette = palette_for(self)
        width, height = self.size.width, self.size.height
        document = self.document
        if document is None:
            if self.tagline:
                return self._idle(palette, width, height)
            return Text(f"  {self.message}", style=palette["muted"])
        if document.synced:
            start, lines, active = document.window(self._position, height)
        else:
            start, active = self._start, None
            lines = document.lines[start : start + height]
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
