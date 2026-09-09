"""Chrome that has to keep its shape whatever it is handed."""

from __future__ import annotations

import asyncio
import unicodedata

import pytest
from rich.cells import cell_len
from textual.app import App, ComposeResult

from tidalamp.library import Row
from tidalamp.queue import Entry
from tidalamp.screens import RowList
from tidalamp.widgets import Marquee, Slider

# Wide enough that the track has room to be wrong in a visible way.
WIDTH = 44
TRACK = WIDTH - len("VOL") - 6


class SliderApp(App):
    CSS = f"Slider {{ width: {WIDTH}; height: 1; }}"

    def compose(self) -> ComposeResult:
        yield Slider(id="s")


def drawn(value: int, *, centred: bool = False, maximum: int = 100) -> str:
    async def scenario() -> str:
        app = SliderApp()
        async with app.run_test(size=(WIDTH + 4, 6)) as pilot:
            slider = app.query_one(Slider)
            slider.centred = centred
            slider.maximum = maximum
            slider.value = value
            await pilot.pause()
            return slider.render_line(0).text

    return asyncio.run(scenario())


@pytest.mark.parametrize("value", [-9999, -50, 0, 1, 50, 99, 100, 101, 105, 130, 9999])
def test_the_bar_never_outgrows_its_track(value):
    """It did, and it took the readout out with it.

    `filled` was unclamped, so a value past `maximum` drew a bar wider than
    the track: at 105 the number was shoved sideways, at 115 off the widget
    entirely, and at 130 the line was too long to render at all — the bar
    disappeared and only «VOL» was left on screen.
    """
    line = drawn(value)
    assert line.startswith("VOL ")
    assert line.count("█") + line.count("░") == TRACK


@pytest.mark.parametrize("value", [-100, -50, 0, 1, 50, 99, 100])
def test_the_number_stays_on_screen_across_the_whole_range(value):
    """The readout budget is a sign and three digits, which covers volume
    (0..100) and balance (-100..100). That is the range the app can produce."""
    assert str(value) in drawn(value)


def test_the_bar_fills_in_proportion_between_the_ends():
    assert drawn(0).count("█") == 0
    assert drawn(0).count("░") == TRACK
    assert drawn(100).count("█") == TRACK
    assert drawn(100).count("░") == 0
    half = drawn(50).count("█")
    assert 0 < half < TRACK
    assert abs(half - TRACK // 2) <= 1


def test_a_maximum_of_zero_does_not_divide_by_it():
    line = drawn(50, maximum=0)
    assert line.count("█") == 0
    assert line.count("░") == TRACK


def test_the_centred_bar_leans_without_breaking():
    """Balance runs -100..100 and was already clamped; keep it that way."""
    for value in (-9999, -100, -50, 0, 50, 100, 9999):
        line = drawn(value, centred=True)
        assert line.startswith("VOL ")
        assert line.count("│") == 1
        assert line.count("█") + line.count("░") + 1 == (TRACK // 2) * 2 + 1


class TextWidthApp(App):
    CSS = "Marquee { width: 12; height: 1; } RowList { width: 120; height: 2; }"

    def compose(self) -> ComposeResult:
        yield Marquee(id="marquee")
        yield RowList(id="rows")


def test_marquee_scrolls_on_graphemes_and_terminal_cells():
    async def scenario() -> None:
        app = TextWidthApp()
        async with app.run_test(size=(124, 8)) as pilot:
            marquee = app.query_one(Marquee)
            marquee.text = "東京 e\u0301 🎧 música"
            await pilot.pause()

            for _ in range(30):
                line = marquee.render().plain
                assert cell_len(line) == marquee.size.width
                assert not (line and unicodedata.combining(line[0]))
                marquee.tick()

    asyncio.run(scenario())


def test_rows_align_unicode_and_show_album_only_when_there_is_room():
    async def scenario() -> None:
        app = TextWidthApp()
        async with app.run_test(size=(124, 8)) as pilot:
            rows = app.query_one(RowList)
            entry = Entry(
                id=1,
                title="東京 e\u0301 🎧",
                artist="アーティスト",
                album="Álbum edición especial",
                duration=245,
            )
            rows.set_rows([Row(label=entry.label, detail=entry.length, entry=entry)])
            await pilot.pause()

            line = rows.render().plain.splitlines()[0]
            assert cell_len(line) == rows.size.width
            # Wide: title, artist and album each in their own column, and the
            # duration last. The album is cropped to its column, not dropped.
            assert "アーティスト" in line
            assert "Álbum edición" in line
            assert line.index("東京") < line.index("アーティスト") < line.index("Álbum")
            assert line.endswith("4:05")

            rows.styles.width = 40
            await pilot.pause()
            compact = rows.render().plain.splitlines()[0]
            assert cell_len(compact) == 40
            # Narrow: back to «artist - title» on one line, no columns.
            assert "Álbum" not in compact
            assert "アーティスト - 東京" in compact
            assert compact.endswith("4:05")

    asyncio.run(scenario())


def test_the_album_column_does_not_move_when_a_track_passes_ten_minutes():
    """The detail column is measured over the whole list, not per row.

    Measured per row, a `11:53` is one cell wider than a `5:07`, and the album
    beside it was pushed a cell to the left. A column that only lines up while
    every track is under ten minutes is not a column.
    """

    async def scenario() -> None:
        app = TextWidthApp()
        async with app.run_test(size=(124, 8)) as pilot:
            rows = app.query_one(RowList)
            durations = (307, 713, 382, 764, 3724)
            # RowList paints as many rows as it is given; give it all of them.
            rows.styles.height = len(durations)
            rows.set_rows(
                [
                    Row(label=entry.label, detail=entry.length, entry=entry)
                    for entry in (
                        Entry(
                            id=index,
                            title=f"Pista {index}",
                            artist="TOOL",
                            album="Fear Inoculum",
                            duration=duration,
                        )
                        for index, duration in enumerate(durations, 1)
                    )
                ]
            )
            await pilot.pause()

            lines = rows.render().plain.splitlines()[: len(durations)]
            assert len({line.index("Fear Inoculum") for line in lines}) == 1
            # And the durations line up on their right edge, longest included.
            assert {cell_len(line.rstrip()) for line in lines} == {
                cell_len(lines[0].rstrip())
            }
            assert lines[-1].rstrip().endswith("62:04")
            assert lines[0].rstrip().endswith("5:07")

    asyncio.run(scenario())


def test_the_queue_shows_artist_album_year_and_duration_as_columns():
    """Four columns, and each one dropped in the order it can be spared."""

    async def scenario() -> None:
        app = TextWidthApp()
        async with app.run_test(size=(200, 8)) as pilot:
            rows = app.query_one(RowList)
            rows.styles.height = 2
            entries = [
                Entry(
                    id=1,
                    title="Oh Qué Será?",
                    artist="Willie Colón",
                    album="Greatest Hits",
                    year=1995,
                    duration=304,
                ),
                # No year: the column stays, this row just leaves it blank.
                Entry(id=2, title="Virgen", artist="Adolescent's", album="Ahora"),
            ]
            rows.set_rows([Row(label=e.label, detail=e.length, entry=e) for e in entries])

            rows.styles.width = 160
            await pilot.pause()
            first, second = rows.render().plain.splitlines()[:2]
            assert cell_len(first) == 160
            for column in ("Oh Qué Será?", "Willie Colón", "Greatest Hits", "1995"):
                assert column in first
            assert first.rstrip().endswith("5:04")
            # Order left to right, and the artist is out of the title.
            assert (
                first.index("Oh Qué Será?")
                < first.index("Willie Colón")
                < first.index("Greatest Hits")
                < first.index("1995")
            )
            assert "Willie Colón - Oh" not in first
            # Every column starts at the same cell on every row.
            assert first.index("Willie Colón") == second.index("Adolescent's")
            assert first.index("Greatest Hits") == second.index("Ahora")
            # An entry with no year leaves its cell blank rather than «0».
            slot = first.index("1995")
            assert second[slot : slot + 4].strip() == ""

            # Narrower: the year goes first, the rest of the columns stay.
            rows.styles.width = 100
            await pilot.pause()
            line = rows.render().plain.splitlines()[0]
            assert cell_len(line) == 100
            assert "1995" not in line
            assert "Willie Colón" in line and "Greatest Hits" in line

            # Narrower still: back to one label per row.
            rows.styles.width = 80
            await pilot.pause()
            line = rows.render().plain.splitlines()[0]
            assert cell_len(line) == 80
            assert "Greatest Hits" not in line
            assert "Willie Colón - Oh Qué Será?" in line

    asyncio.run(scenario())
