"""Text that moves: lines that glide when they do not fit, the scrolling
title, and the lyrics pane that follows the song."""

from __future__ import annotations

import contextlib

from rich.cells import cell_len, set_cell_size, split_graphemes
from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from .lyrics import LyricsDocument
from .theme import palette_for


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
