"""The library's grid: albums, playlists, artists and mixes by their covers."""

from __future__ import annotations

from rich.cells import set_cell_size
from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget

from .. import artwork
from ..library import Row
from ..theme import palette_for

Pixel = tuple[int, int, int]
Cells = tuple[tuple[tuple[str, Pixel, Pixel], ...], ...]

# Covers already cut into cells, by URL, for the whole session: walking back
# into a level draws at once. Cleared rather than trimmed when it fills,
# because a grid only ever shows a few dozen at a time.
_CELLS: dict[str, Cells] = {}
_CELLS_MAX = 600


def cached_cells(url: str) -> Cells | None:
    return _CELLS.get(url)


# Whether this terminal draws sextants, asked once: the environment does not
# change under a running app, and the cache above holds one kind of cell.
_SEXTANTS: bool | None = None


def _sextants() -> bool:
    global _SEXTANTS
    if _SEXTANTS is None:
        _SEXTANTS = artwork.draws_sextants()
    return _SEXTANTS


def cover_cells(url: str) -> Cells | None:
    """One tile's cover in half blocks. Network and Pillow, so a worker's.

    Only half blocks, never kitty or sixel: an image sent with those is
    painted by the terminal over the text, and the grid lives in a window
    that the menu, the help and every question open on top of.
    """
    found = _CELLS.get(url)
    if found is not None:
        return found
    width, height = GridList.COVER_W, GridList.COVER_H
    image = artwork.decode(artwork.fetch(url), width, height)
    if image is None:
        return None
    # Six pixels a cell where the terminal draws the glyphs itself, the four
    # of the quadrants everywhere else: the cells come out the same shape.
    if _sextants():
        cells = artwork.sextant_cells(image, width, height)
    else:
        cells = artwork.block_cells(artwork.blocks(image, width, height))
    if len(_CELLS) >= _CELLS_MAX:
        _CELLS.clear()
    _CELLS[url] = cells
    return cells


def spread(width: int, columns: int, tile: int, gap: int) -> tuple[int, list[int]]:
    """Where the tiles go across ``width``: the room before the first, and
    the gap before each of the others.

    The room left over goes into the gaps, as CSS's space-between does, so the
    first tile sits on the left edge and the last on the right: with a fixed
    gap the whole slack piled up on the right, a column's worth of empty
    band. The gaps differ by a cell at most, the wider ones first, and every
    line uses the same ones, so a short last line stays in its columns. A
    single column has no gaps to take the slack, and is centred instead.
    """
    slack = max(0, width - columns * tile - (columns - 1) * gap)
    if columns <= 1:
        return slack // 2, []
    share, extra = divmod(slack, columns - 1)
    return 0, [gap + share + (1 if i < extra else 0) for i in range(columns - 1)]


class GridList(Widget):
    """Tiles of cover, name and detail, with a cursor that moves both ways.

    The same surface as `RowList` (``rows``, ``cursor``, ``current``,
    ``move``, ``set_rows``, ``empty_text``), so the browser drives whichever
    one is showing without asking which.
    """

    cursor = reactive(0)

    # A square cover in half blocks: a cell is about twice as tall as wide.
    COVER_W = 16
    COVER_H = 8
    GAP = 2
    # The cover, three lines of text (name, artist, detail) and a line of air.
    TEXT_LINES = 3
    TILE_H = COVER_H + TEXT_LINES + 1

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows: list[Row] = []
        self.empty_text = ""
        # Covers that could not be had (no Pillow, a broken download): drawn
        # as the placeholder, and not asked for again on every move.
        self.failed: set[str] = set()
        # The first line of tiles on screen, kept between repaints.
        self._start = 0

    def set_rows(self, rows: list[Row]) -> None:
        self.rows = rows
        self.cursor = 0
        self._start = 0
        self.refresh()

    @property
    def current(self) -> Row | None:
        if 0 <= self.cursor < len(self.rows):
            return self.rows[self.cursor]
        return None

    @property
    def columns(self) -> int:
        width = max(1, self.size.width)
        return max(1, (width + self.GAP) // (self.COVER_W + self.GAP))

    @property
    def per_screen(self) -> int:
        """How many lines of tiles fit, at least one."""
        # The last line of a tile is air, and the bottom of the widget is air
        # enough: a tile missing only that one still counts as whole. What is
        # left at the foot shows the top of the next line of covers, which
        # `render_line` draws as far as it goes: with the foot empty, a grid
        # read as if it had no more.
        return max(1, (self.size.height + 1) // self.TILE_H)

    def move(self, delta: int) -> None:
        if self.rows:
            self.cursor = max(0, min(len(self.rows) - 1, self.cursor + delta))

    def move_lines(self, delta: int) -> None:
        """Up or down a line of tiles, staying in the column where there is one."""
        self.move(delta * self.columns)

    def watch_cursor(self) -> None:
        self.refresh()

    def _window_start(self) -> int:
        """The first line of tiles shown: where it was, unless the cursor left."""
        columns = self.columns
        per = self.per_screen
        line = self.cursor // columns
        start = self._start
        if line < start:
            start = line
        elif line >= start + per:
            start = line - per + 1
        lines = -(-len(self.rows) // columns)
        return max(0, min(start, max(0, lines - per)))

    def shown_rows(self) -> list[Row]:
        """The rows on screen, and one line more: their covers are the ones
        worth fetching first. Not ``visible``, which Textual's widgets already
        have and read to decide whether to draw at all."""
        columns = self.columns
        start = self._window_start()
        return self.rows[start * columns : (start + self.per_screen + 1) * columns]

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        palette = palette_for(self)
        ground = Style(bgcolor=palette["display_background"])
        if not self.rows:
            if y != 0:
                return Strip.blank(width, ground)
            text = set_cell_size(f"  {self.empty_text}", width)
            empty = Style(color=palette["empty"], bgcolor=palette["display_background"])
            return Strip([Segment(text, empty)], width)
        start = self._start = self._window_start()
        columns = self.columns
        line = y % self.TILE_H
        first = (start + y // self.TILE_H) * columns
        lead, gaps = spread(width, columns, self.COVER_W, self.GAP)
        segments: list[Segment] = [Segment(" " * lead, ground)] if lead else []
        used = lead
        for column, index in enumerate(
            range(first, min(len(self.rows), first + columns))
        ):
            if column:
                gap = gaps[column - 1]
                segments.append(Segment(" " * gap, ground))
                used += gap
            segments.extend(self._tile_line(index, line, palette, ground))
            used += self.COVER_W
        return Strip(segments, used).adjust_cell_length(width, ground)

    def _tile_line(self, index: int, line: int, palette, ground: Style) -> list[Segment]:
        """One line of one tile, exactly ``COVER_W`` cells wide."""
        row = self.rows[index]
        width = self.COVER_W
        selected = index == self.cursor
        if line < self.COVER_H:
            cells = _CELLS.get(row.art) if row.art else None
            if cells is not None and line < len(cells):
                segments = [
                    Segment(
                        glyph,
                        Style(color=Color.from_rgb(*fg), bgcolor=Color.from_rgb(*bg)),
                    )
                    for glyph, fg, bg in cells[line][:width]
                ]
                missing = width - len(segments)
                if missing > 0:
                    segments.append(Segment(" " * missing, ground))
                return segments
            # No cover (yet, or ever): a square of panel colour, so the tile
            # keeps its place, with «más…» or the name's first letter in it.
            square = Style(color=palette["container"], bgcolor=palette["panel"])
            text = ""
            if line == self.COVER_H // 2:
                text = row.label if row.more is not None else row.label[:1].upper()
            return [Segment(set_cell_size(text.center(width), width), square)]
        text_line = line - self.COVER_H
        if text_line >= self.TEXT_LINES:
            return [Segment(" " * width, ground)]
        # The name, then the artist and the detail, each moving up a line
        # when there is none: a playlist has no artist to put there.
        texts = [row.caption or row.label]
        texts += [text for text in (row.byline, row.detail) if text]
        text = texts[text_line] if text_line < len(texts) else ""
        if selected:
            # The whole block lit, so the tile reads as one thing chosen.
            style = Style(
                bold=text_line == 0,
                color=palette["active_foreground"],
                bgcolor=palette["accent"],
            )
        else:
            style = Style(
                color=palette["container"] if text_line == 0 else palette["empty"],
                bgcolor=palette["display_background"],
            )
        return [Segment(set_cell_size(text, width), style)]
