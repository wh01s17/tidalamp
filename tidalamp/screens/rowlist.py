"""The scrolling list with a cursor that the queue and every pane share."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.cells import cell_len, set_cell_size
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.geometry import Region
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget

from .. import artwork, columns, config
from ..library import Row
from ..theme import palette_for

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    pass


def _hex(pixel: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*pixel)


# One emblem cell ready to paint: the glyph for a blank cell and the styles
# that go with it, both built once per size and palette, not per repaint.
_Paint = tuple[str, Style, Style]


class RowList(Widget):
    """A scrolling list of rows with a cursor. Used by both panes."""

    # No repaint of its own: `watch_cursor` repaints only what moved.
    cursor = reactive(0, repaint=False)
    marked = reactive(-1)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows: list[Row] = []
        self.empty_text = ""
        # A themed look's emblem, drawn behind the rows the way a cover is
        # drawn in its box (`artwork.emblem_cells`). The queue has one; the
        # browser's lists do not.
        self.backdrop: Path | None = None
        # The first row on screen, kept between repaints (`_window_start`).
        self._start = 0
        self._placement: tuple[str, float] = ("middle", 1.0)
        self._cells_key: tuple | None = None
        self._cells: dict[int, dict[int, _Paint]] = {}
        # Painted lines, by what the row drew there. A repaint that changes
        # nothing (the cursor moving two rows away, a tick) reuses them.
        self._painted: dict[tuple, Strip] = {}
        # A row's style with an emblem cell's ground, for the cells that have
        # a letter in them (`_paint`).
        self._mix: dict[tuple, Style] = {}

    def set_backdrop(
        self, path: Path | None, anchor: str = "middle", scale: float = 1.0
    ) -> None:
        placement = (anchor, scale)
        if path != self.backdrop or placement != self._placement:
            self.backdrop, self._placement = path, placement
            self.refresh()

    def set_rows(self, rows: list[Row]) -> None:
        self.rows = rows
        self.cursor = 0
        self.refresh()

    def move(self, delta: int) -> None:
        if self.rows:
            self.cursor = max(0, min(len(self.rows) - 1, self.cursor + delta))

    def _window_start(self) -> int:
        """The first row on screen: where it was, unless the cursor left.

        It used to follow the cursor to the middle of the list, so past the
        middle every keypress moved every row and the whole list was drawn
        and sent to the terminal again. With a themed emblem behind it that
        was the heaviest thing on screen, hundreds of kilobytes a keypress on
        a 4K terminal; now the list only moves when the cursor reaches an
        edge, and then by half a screen.
        """
        height = max(1, self.size.height)
        start = self._start
        # Leaving by either edge re-centres the cursor rather than creeping
        # a row at a time: one repaint of the whole list, then half a screen
        # of moves that only redraw the two rows they touch.
        if self.cursor < start or self.cursor >= start + height:
            start = self.cursor - height // 2
        return max(0, min(start, max(0, len(self.rows) - height)))

    def watch_cursor(self, old: int, new: int) -> None:
        """Repaint the two rows that changed, or all of them if it scrolled."""
        start = self._window_start()
        height = self.size.height
        if start != self._start or not height:
            self.refresh()
            return
        width = self.size.width
        for row in (old, new):
            if 0 <= row - start < height:
                self.refresh(Region(0, row - start, width, 1))

    @property
    def current(self) -> Row | None:
        if 0 <= self.cursor < len(self.rows):
            return self.rows[self.cursor]
        return None

    # The gap between two columns, and the room the title needs before it
    # stops being worth having columns at all.
    GAP = 2
    TITLE_MIN = 24

    # A flexible column takes a share of the list, floored so one that appears
    # at all can say something and capped so a very wide terminal spends its
    # slack on the title — generously enough that «Tú Me Vuelves Loco
    # (Bailable)» still fits.
    SHARE = 6
    SHARE_MIN = 12
    SHARE_MAX = 30

    @staticmethod
    def _cell(text: str, width: int, align: str) -> str:
        """One column, cropped to its width. Right-aligned pads on the left,
        so digits and years line up on their last cell."""
        if align != "right":
            return set_cell_size(text, width)
        trimmed = set_cell_size(text, min(cell_len(text), width))
        return " " * (width - cell_len(trimmed)) + trimmed

    @classmethod
    def _fit(cls, chosen: list, width: int, detail_width: int) -> list[tuple]:
        """Which of the chosen columns fit, and how wide each one is.

        Drops from the least useful end until the title has room to breathe,
        rather than picking thresholds by hand: that way a column added to the
        catalogue needs no new number here.
        """
        share = min(cls.SHARE_MAX, max(cls.SHARE_MIN, width // cls.SHARE))
        keep = sorted(chosen, key=lambda column: column.drop, reverse=True)
        while keep:
            sized = [
                (
                    column,
                    detail_width
                    if column.name == "duration"
                    else (column.width or share),
                )
                for column in chosen
                if column in keep
            ]
            spent = sum(size + cls.GAP for _column, size in sized)
            if width - spent >= cls.TITLE_MIN:
                return sized
            keep.pop(0)
        return []

    @classmethod
    def _line(
        cls, row: Row, index: int, marked: int, width: int, detail_width: int
    ) -> str:
        """Fit one row by terminal cells, in columns when there is room.

        `detail_width` is the widest detail in the whole list, not this row's
        own. Measured per row, a `11:53` next to a `5:07` moved the album
        column a cell to the left on the longer ones, and a column that only
        lines up when every track is under ten minutes is not a column.

        A row with no entry — an album, an artist, a playlist in the browser —
        has nothing to put in those columns, so it keeps the whole line for
        its own name, with its detail on the right as before.
        """
        marker = "▶" if index == marked else (" " if row.is_playable else "›")
        # The row's own number when it carries one — a filtered queue keeps
        # the positions it really has — and its place on screen otherwise.
        number = index + 1 if row.number is None else row.number
        entry = row.entry
        chosen = [
            columns.BY_NAME[name] for name in config.COLUMNS if name in columns.BY_NAME
        ]
        sized = cls._fit(chosen, width, detail_width) if entry is not None else []
        # A row of nothing but the duration is the old layout with extra
        # steps, and it would drop the artist on the floor: the artist only
        # leaves the label when it has a column of its own to go to.
        shown = {column.name for column, _size in sized}
        if not shown - {"duration"}:
            sized = []

        if sized and entry is not None:
            head = f"{marker}{number:>3}. "
            title_width = width - sum(size + cls.GAP for _c, size in sized)
            name = entry.title if "artist" in shown else row.label
            line = head + set_cell_size(name, title_width - cell_len(head))
            for column, size in sized:
                # `duration` draws the row's detail, not the entry's: a
                # browser row that is not a track puts «101 pistas» there.
                text = row.detail if column.name == "duration" else column.read(entry)
                line += " " * cls.GAP + cls._cell(text, size, column.align)
            return set_cell_size(line, width)

        detail = cls._cell(row.detail, detail_width, "right") if detail_width else ""
        left = f"{marker}{number:>3}. {row.label}"
        left_width = width - detail_width - (1 if detail else 0)
        line = set_cell_size(left, max(0, left_width))
        if detail:
            line += f" {detail}"
        return set_cell_size(line, width)

    def _ground(self, palette) -> tuple[int, int, int]:
        """The colour the queue is actually painted on, for the emblem to blend
        into. Not always the display's: nova and cuaderno put the queue on the
        panel, and an emblem blended into the wrong ground left a dark block
        round every cell its edge only partly covered."""
        background = self.styles.background
        if background.a:
            return (background.r, background.g, background.b)
        ground = palette["display_background"].lstrip("#")
        return (int(ground[0:2], 16), int(ground[2:4], 16), int(ground[4:6], 16))

    def _backdrop(self) -> dict[int, dict[int, _Paint]]:
        """The emblem's cells for this size and palette, worked out once."""
        palette = palette_for(self)
        ground = self._ground(palette)
        key = (self.backdrop, self._placement, self.size, id(palette), ground)
        if key != self._cells_key:
            self._cells_key = key
            self._painted.clear()
            self._mix.clear()
            lines = (
                artwork.emblem_cells(
                    self.backdrop,
                    self.size.width,
                    self.size.height,
                    ground,
                    anchor=self._placement[0],
                    scale=self._placement[1],
                )
                if self.backdrop is not None
                else {}
            )
            # One style object per pair of colours, shared by every cell that
            # uses it, so neighbours compare as the same style and merge.
            styles: dict[tuple, Style] = {}

            def style(fg, bg) -> Style:
                found = styles.get((fg, bg))
                if found is None:
                    found = styles[(fg, bg)] = Style(
                        color=_hex(fg) if fg else None, bgcolor=_hex(bg)
                    )
                return found

            self._cells = {
                y: {
                    x: (glyph, style(fg, bg), style(None, mean))
                    for x, glyph, fg, bg, mean in cells
                }
                for y, cells in lines.items()
            }
        return self._cells

    def _cursor_line(self) -> int | None:
        """Which line on screen the cursor is drawn on."""
        if not self.rows:
            return None
        return self.cursor - self._window_start()

    def render_line(self, y: int) -> Strip:
        """The rendered row, with the emblem drawn behind it cell by cell.

        A cell the row leaves blank gets the emblem's quadrant glyph and its
        two colours, as a cover does; a cell with a letter in it keeps the
        letter and its colour and takes the mean of the four pixels as its
        ground. The cursor's line keeps the accent it is drawn on.
        """
        strip = super().render_line(y)
        if self.backdrop is None or y == self._cursor_line():
            return strip
        cells = self._backdrop().get(y)
        if not cells:
            return strip
        # Textual does not pad a line to the widget: the one after the last
        # row is empty, and a short line used to swallow every emblem cell
        # past its end. Painted to the full width, whatever it was handed,
        # and in the widget's own ground: padded with bare spaces, that line
        # had no background at all, and a translucent terminal showed its
        # wallpaper through it as a band across the queue.
        width = self.content_region.width or max(0, self.size.width - 2)
        if strip.cell_length < width:
            strip = strip.extend_cell_length(width, self.visual_style.rich_style)
        key = (y, strip.text, tuple(segment.style for segment in strip))
        painted = self._painted.get(key)
        if painted is None:
            painted = self._paint(strip, cells)
            if len(self._painted) > 1024:
                self._painted.clear()
            self._painted[key] = painted
        return painted

    def _paint(self, strip: Strip, cells: dict[int, _Paint]) -> Strip:
        """One pass over the line, cell by cell, merging runs of one style.

        It used to cut the line at every emblem cell with `Strip.divide`,
        which cost six times the render of the list itself. And on a 4K
        terminal the emblem is some twelve thousand cells of distinct colour:
        combining each with the row's style went through Rich's `Style +`,
        whose cache holds a thousand, so every repaint rebuilt them all. A
        blank cell now takes the emblem's own style as it is, since there is
        no letter whose colour could matter, and the cells with a letter keep
        their combinations in a cache of their own.
        """
        mix = self._mix
        out: list[Segment] = []
        text: list[str] = []
        current: Style | None = None
        x = 0
        for segment in strip:
            if segment.control:
                if text:
                    out.append(Segment("".join(text), current))
                    text.clear()
                out.append(segment)
                continue
            base = segment.style
            for char in segment.text:
                size = 1 if char.isascii() else cell_len(char)
                cell = cells.get(x) if size == 1 else None
                if cell is None:
                    style = base
                elif char == " ":
                    char, style = cell[0], cell[1]
                else:
                    style = mix.get((base, cell[2]))
                    if style is None:
                        style = mix[(base, cell[2])] = (base or Style()) + cell[2]
                if style is not current and style != current and text:
                    out.append(Segment("".join(text), current))
                    text.clear()
                current = style
                text.append(char)
                x += size
        if text:
            out.append(Segment("".join(text), current))
        return Strip(out, strip.cell_length)

    def render(self) -> Text:
        palette = palette_for(self)
        if not self.rows:
            return Text(f"  {self.empty_text}", style=palette["empty"])

        height = max(1, self.size.height)
        width = max(1, self.size.width)
        # Keep the cursor in view without a full scrolling container.
        start = self._start = self._window_start()
        # One column width for the whole list, from the widest detail on it.
        detail_width = min(
            max(cell_len(row.detail) for row in self.rows), max(0, width // 3)
        )
        out = Text()
        for i in range(start, min(len(self.rows), start + height)):
            row = self.rows[i]
            line = self._line(row, i, self.marked, width, detail_width)
            if i == self.cursor:
                out.append(
                    line,
                    style=(f"bold {palette['active_foreground']} on {palette['accent']}"),
                )
            elif i == self.marked:
                out.append(line, style=f"bold {palette['accent']}")
            elif not row.is_playable:
                out.append(line, style=palette["container"])
            else:
                out.append(line, style=palette["playable"])
            out.append("\n")
        return out
