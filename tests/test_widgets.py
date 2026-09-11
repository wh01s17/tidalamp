"""Chrome that has to keep its shape whatever it is handed."""

from __future__ import annotations

import asyncio
import itertools
import unicodedata

import pytest
from rich.cells import cell_len
from textual.app import App, ComposeResult

from tidalamp.library import Row
from tidalamp.queue import Entry
from tidalamp.screens import RowList
from tidalamp.widgets import Glide, Marquee, Slider, TimeDisplay

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
    """The default columns, in order, each starting at the same cell."""

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
            assert (
                first.index("Oh Qué Será?")
                < first.index("Willie Colón")
                < first.index("Greatest Hits")
                < first.index("1995")
            )
            # The artist has a column, so it leaves the title alone.
            assert "Willie Colón - Oh" not in first
            # Every column starts at the same cell on every row.
            assert first.index("Willie Colón") == second.index("Adolescent's")
            assert first.index("Greatest Hits") == second.index("Ahora")
            # An entry with no year leaves its cell blank rather than «0».
            slot = first.index("1995")
            assert second[slot : slot + 4].strip() == ""

    asyncio.run(scenario())


def test_columns_are_dropped_in_the_order_the_catalogue_says():
    """Narrowing the list must not drop a column out of turn.

    Asserted as an order rather than against fixed widths: the widths are
    tuning and will move, while «the year goes before the album» is the
    decision worth protecting.
    """

    async def scenario() -> None:
        app = TextWidthApp()
        async with app.run_test(size=(200, 8)) as pilot:
            rows = app.query_one(RowList)
            # Short, distinctive values: a long one gets cropped as its
            # column narrows, and the probe below would read the crop as the
            # column having gone away.
            entry = Entry(
                id=1,
                title="Titulo",
                artist="ARTISTA",
                album="ALBUM",
                year=1995,
                duration=304,
            )
            rows.set_rows([Row(label=entry.label, detail=entry.length, entry=entry)])

            seen: list[tuple[int, str]] = []
            for width in range(180, 39, -1):
                rows.styles.width = width
                await pilot.pause()
                line = rows.render().plain.splitlines()[0]
                assert cell_len(line) == width, width
                present = tuple(
                    name
                    for name, text in (
                        ("artist", "ARTISTA"),
                        ("album", "ALBUM"),
                        ("year", "1995"),
                    )
                    if text in line
                )
                if not seen or seen[-1][1] != present:
                    seen.append((width, present))

            drawn = [present for _width, present in seen]
            # Everything, then the year, then the album. The artist is not on
            # this list at the end because it moves into the title rather
            # than disappearing — see the test below.
            assert drawn[0] == ("artist", "album", "year")
            assert ("artist", "album") in drawn
            assert "album" not in drawn[-1] and "year" not in drawn[-1]
            # The year always goes before the album, never the other way.
            assert drawn.index(("artist", "album")) < len(drawn) - 1
            # No column ever comes back as the list narrows further.
            for earlier, later in itertools.pairwise(drawn):
                assert set(later) <= set(earlier), (earlier, later)

    asyncio.run(scenario())


def test_the_artist_stays_in_the_title_when_it_has_no_column_of_its_own():
    """Otherwise a narrow list would simply lose who is playing."""

    async def scenario() -> None:
        app = TextWidthApp()
        async with app.run_test(size=(200, 8)) as pilot:
            rows = app.query_one(RowList)
            entry = Entry(
                id=1, title="Virgen", artist="Adolescent's", album="Ahora", duration=272
            )
            rows.set_rows([Row(label=entry.label, detail=entry.length, entry=entry)])
            rows.styles.width = 40
            await pilot.pause()

            line = rows.render().plain.splitlines()[0]
            assert cell_len(line) == 40
            assert "Adolescent's - Virgen" in line
            assert line.rstrip().endswith("4:32")

    asyncio.run(scenario())


class GlideApp(App):
    CSS = "Glide { width: 10; height: 2; }"

    def compose(self) -> ComposeResult:
        yield Glide(id="glide")


def test_a_line_that_does_not_fit_glides_to_its_end_and_back():
    """Shown whole where it fits; otherwise it holds, slides until its end is
    in view, holds, and slides back, each line stopping at its own end."""

    async def scenario() -> None:
        app = GlideApp()
        async with app.run_test(size=(40, 6)) as pilot:
            glide = app.query_one(Glide)
            # Driven by hand: the widget's own timer is left out of it.
            glide._timed = lambda: None
            glide.update("corto\nBob Marley & The Wailers")
            await pilot.pause()

            def rows() -> list[str]:
                return glide.render().plain.split("\n")

            assert rows() == ["corto     ", "Bob Marley"]
            seen = []
            for _ in range(Glide.EVERY * (Glide.HOLD * 2 + 40)):
                glide.tick()
                seen.append(rows())
                for row in seen[-1]:
                    assert cell_len(row) == 10
            long_rows = [r[1] for r in seen]
            assert any(r.endswith("Wailers") for r in long_rows), "llega al final"
            assert all(r[0] == "corto     " for r in seen), "la corta no se mueve"
            # And it comes back to the start after reaching the end.
            end = next(i for i, r in enumerate(long_rows) if r.endswith("Wailers"))
            assert any(r == "Bob Marley" for r in long_rows[end:])

            # The same text again does not restart the glide.
            glide.update("corto\nBob Marley & The Wailers")
            assert rows() == seen[-1]

    asyncio.run(scenario())


class ClockApp(App):
    CSS = "TimeDisplay { width: 20; height: 3; }"

    def compose(self) -> ComposeResult:
        yield TimeDisplay()


@pytest.mark.parametrize(
    ("seconds", "total", "countdown", "shown"),
    [
        (197.0, 217.0, False, "03:17"),
        (20.0, 217.0, True, "-03:17"),
        (44.0, 944.0, True, "-15:00"),
        (0.0, 0.0, True, "00:00"),
    ],
)
def test_the_clock_keeps_to_its_width_counting_down(seconds, total, countdown, shown):
    """`t` shows the time left, one glyph longer than the time played. At
    three columns a glyph it no longer fitted: the rows wrapped and the
    digits broke up across the band."""

    async def scenario() -> None:
        app = ClockApp()
        async with app.run_test(size=(30, 5)) as pilot:
            clock = app.query_one(TimeDisplay)
            clock.total, clock.seconds, clock.countdown = total, seconds, countdown
            await pilot.pause()
            # What the clock asks to draw, before Textual crops it to the
            # widget: cropped, the overflow never shows as a long line.
            rows = [row.rstrip() for row in clock.render().plain.split("\n")]
            for row in rows:
                assert cell_len(row) <= 20, (shown, rows)
            # The minus is the middle bar of the first column, then the digits.
            assert rows[1].startswith("_") == shown.startswith("-"), rows

    asyncio.run(scenario())
