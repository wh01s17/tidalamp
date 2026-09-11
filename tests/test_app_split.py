"""The split arrangement: two columns, the lyrics pane, the queue beside the player."""

from __future__ import annotations

import asyncio

import pytest
from app_helpers import (
    FakeMpv,
    a_cover,
    isolate_config,
    isolate_runtime,
    use_theme,
)
from rich.cells import cell_len
from textual.widgets import Static

from tidalamp import app as app_module
from tidalamp.app import RowList, TidalAmp
from tidalamp.artwork import Protocol
from tidalamp.queue import Entry
from tidalamp.widgets import (
    Artwork,
    Marquee,
)

# ------------------------------------------------------------------ split


def test_switching_to_split_moves_the_halves_without_remounting_them(
    monkeypatch, tmp_path
):
    """Two columns are a class on the panel, not a new widget tree.

    Reparenting would be remove() and mount(): the queue would jump back to
    its first row and the cover would be decoded again. The same objects have
    to be there before and after, with the cursor where it was.
    """
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(200, 40)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=n, title=f"t{n}", artist="a", duration=9) for n in range(30)],
                start=0,
            )
            application._sync_queue()
            playlist = application.query_one("#playlist", RowList)
            art = application.query_one(Artwork)
            transport = application.query_one("#transport")
            playlist.cursor = 17
            await pilot.pause()

            player = application.query_one("#player-half")
            queue = application.query_one("#queue-half")
            assert queue.region.y > player.region.y, "apilada: la cola va debajo"

            app_module.config.set_option("arrangement", "split")
            application._setting_changed("arrangement")
            await pilot.pause()
            await pilot.pause()

            assert application.split
            assert application.query_one("#playlist", RowList) is playlist
            assert application.query_one(Artwork) is art
            assert application.query_one("#transport") is transport
            assert playlist.cursor == 17
            assert queue.region.x >= player.region.right, "split: la cola a la derecha"
            assert queue.region.y == player.region.y

            # The width-dependent chrome was redrawn for the half it is in.
            heading = application.query_one("#pl-title", Static)
            assert cell_len(heading.render_line(0).text) == heading.size.width
            assert heading.size.width < 100

            app_module.config.set_option("arrangement", "stacked")
            application._setting_changed("arrangement")
            await pilot.pause()
            await pilot.pause()
            assert not application.split
            assert application.query_one("#playlist", RowList) is playlist
            assert playlist.cursor == 17
            # Back at full width, the hints go back to the right edge instead
            # of stopping where the half used to end.
            drawn = heading.render_line(0).text
            assert heading.size.width > 150
            assert cell_len(drawn.rstrip()) >= heading.size.width - 2

    asyncio.run(scenario())


def test_split_falls_back_to_stacked_where_it_does_not_fit(monkeypatch, tmp_path):
    """Asked for on an ordinary terminal, two columns would be two broken
    halves. It stays stacked, says why, and splits once there is room."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    app_module.config.set_option("arrangement", "split")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            assert not application.split
            application._setting_changed("arrangement")
            assert "160" in application.status

            await pilot.resize_terminal(170, 34)
            await pilot.pause()
            assert application.split

            await pilot.resize_terminal(170, 20)
            await pilot.pause()
            assert not application.split, "demasiado bajo para dos columnas"

    asyncio.run(scenario())


def test_every_look_fits_both_halves_of_the_narrowest_split(monkeypatch, tmp_path):
    """At the threshold each half is about 80 columns: the transport runs
    under both, and the cover must not spill onto the seek bar."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    app_module.config.set_option("arrangement", "split")

    async def scenario() -> None:
        for name in app_module.LAYOUTS:
            app_module.config.THEME = name
            application = TidalAmp(object(), FakeMpv())
            size = (TidalAmp.SPLIT_MIN_WIDTH, TidalAmp.SPLIT_MIN_HEIGHT)
            async with application.run_test(size=size) as pilot:
                await pilot.pause()
                await pilot.pause()
                assert application.split, name
                queue = application.query_one("#queue-half")
                transport = application.query_one("#transport")
                play = application.query_one("#transport-play")
                menu = application.query_one("#transport-menu")
                # Under both columns, not squeezed into the player's.
                assert transport.region.y >= queue.region.bottom, name
                assert transport.region.right >= queue.region.right, name
                assert play.region.right <= menu.region.x, name
                assert menu.region.right <= transport.region.right, name
                for y in range(3):
                    assert cell_len(play.render_line(y).text) <= play.size.width, name

                display = application.query_one("#display")
                seek = application.query_one("#seek")
                assert display.region.bottom <= seek.region.y, name
                assert application.query_one(Artwork).rows >= app_module.DISPLAY_HEIGHT
                # The rule under the lyrics is drawn on the pane's ground; on
                # any other ground than the band's it left half a row of the
                # wrong colour under the line.
                pane = application.query_one("#lyrics-pane")
                assert pane.styles.background == display.styles.background, name

    asyncio.run(scenario())


def test_split_shows_the_lyrics_above_the_player_and_follows_the_song(
    monkeypatch, tmp_path
):
    """Split gives the player a column of its own, and the rows the band and
    the keys do not use go to the words: fetched once per track through the
    same cache `y` uses, with the sung line lit. Stacked, there is no room
    and the pane is not drawn at all."""
    from tidalamp.lyrics import parse_lyrics
    from tidalamp.widgets import LyricsPane

    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    app_module.config.set_option("arrangement", "split")
    fetched: list[int] = []

    def lyrics_for(self, entry):
        fetched.append(entry.id)
        return parse_lyrics(
            subtitles=(
                "[00:01.00]primera línea\n[00:05.00]segunda línea\n[00:09.00]tercera"
            )
        )

    monkeypatch.setattr(TidalAmp, "_lyrics_for", lyrics_for)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(200, 44)) as pilot:
            application.queue.replace(
                [Entry(id=7, title="t", artist="a", duration=60)], start=0
            )
            mpv.position = 6.0
            await pilot.pause(0.6)
            await pilot.pause(0.3)

            pane = application.query_one(LyricsPane)
            assert pane.display and pane.size.height > 10
            drawn = [pane.render_line(y).text for y in range(pane.size.height)]
            assert any("segunda línea" in row for row in drawn)
            accent = application.tidalamp_palette["accent"].lower()
            lit = [
                segment.text
                for y in range(pane.size.height)
                for segment in pane.render_line(y)
                if segment.style
                and segment.style.color
                and segment.style.color.name.lower() == accent
            ]
            assert "segunda línea" in "".join(lit), "la línea que suena, en el acento"
            # The band and the keys sit under the lyrics, at their stacked height.
            display = application.query_one("#display")
            assert display.region.y >= pane.region.bottom
            assert display.region.height < 20

            mpv.position = 10.0
            await pilot.pause(0.6)
            lit = [
                segment.text
                for y in range(pane.size.height)
                for segment in pane.render_line(y)
                if segment.style
                and segment.style.color
                and segment.style.color.name.lower() == accent
            ]
            assert "tercera" in "".join(lit)
            assert fetched == [7], "una sola carga por pista"

            app_module.config.set_option("arrangement", "stacked")
            application._setting_changed("arrangement")
            await pilot.pause()
            assert not pane.display or pane.size.height == 0

    asyncio.run(scenario())


def test_split_shows_the_looks_line_while_there_are_no_lyrics(monkeypatch, tmp_path):
    from tidalamp.widgets import LyricsPane

    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    app_module.config.set_option("arrangement", "split")
    use_theme(monkeypatch, "runas")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(180, 44)) as pilot:
            await pilot.pause(0.5)
            pane = application.query_one(LyricsPane)
            rows = [pane.render_line(y).text for y in range(pane.size.height)]
            assert any("anillo" in row for row in rows)
            marquee = application.query_one(Marquee).render().plain
            assert "anillo" in marquee

    asyncio.run(scenario())


def test_the_emblem_is_painted_on_a_short_line_too(monkeypatch, tmp_path):
    """Textual does not pad a line to the widget: the one after the last row
    comes back empty, and the emblem's cells past a line's end were dropped.
    Where the queue ends in the middle of the picture, the picture goes on."""
    from tidalamp.artwork import QUADRANTS

    pytest.importorskip("PIL", reason="the emblem is drawn with Pillow, like the cover")
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    app_module.config.set_option("arrangement", "split")
    use_theme(monkeypatch, "cuaderno")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            lines = sorted(playlist._backdrop())
            middle = lines[len(lines) // 2]
            application.queue.replace(
                [
                    Entry(id=n, title=f"t{n}", artist="a", duration=9)
                    for n in range(middle)
                ],
                start=0,
            )
            application._sync_queue()
            await pilot.pause()
            for y in (middle, middle + 1):
                drawn = playlist.render_line(y)
                assert drawn.cell_length == playlist.content_region.width, y
                assert any(c in QUADRANTS[1:] for c in drawn.text), y
                # Every cell carries a ground: a bare one lets a translucent
                # terminal show its wallpaper through, as a band.
                bare = [s.text for s in drawn if not (s.style and s.style.bgcolor)]
                assert not bare, (y, bare)

    asyncio.run(scenario())


def test_moving_the_cursor_repaints_two_rows_not_the_whole_queue(monkeypatch):
    """Past the middle the list used to follow the cursor, so every keypress
    redrew and resent every row, emblem and all: hundreds of kilobytes on a
    4K terminal. Inside the window only the two rows that changed are dirty;
    leaving it re-centres the cursor, so the next half screen is cheap too."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            application.queue.replace(
                [Entry(id=n, title=f"t{n}", artist="a", duration=9) for n in range(200)],
                start=0,
            )
            application._sync_queue()
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            height = playlist.size.height
            playlist.render_lines(playlist.size.region)

            playlist.move(1)
            dirty = playlist._styles_cache._dirty_lines
            assert len(dirty) == 2, sorted(dirty)
            await pilot.pause()

            # Down to the last row on screen, then one more: a jump.
            playlist.cursor = height - 1
            await pilot.pause()
            playlist.move(1)
            await pilot.pause()
            assert playlist._cursor_line() == height // 2

    asyncio.run(scenario())


def test_falling_back_from_split_redraws_a_pixel_cover_where_it_now_is(
    monkeypatch, tmp_path
):
    """Leaving split moves the cover's band without always resizing it, and a
    kitty picture stays where it was drawn until it is deleted. Put back
    through `show`, it is deleted first, and it is still up afterwards."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    app_module.config.set_option("arrangement", "split")
    erased: list[int] = []
    original = Artwork._erase

    def erase(self) -> None:
        erased.append(1)
        original(self)

    monkeypatch.setattr(Artwork, "_erase", erase)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(180, 44)) as pilot:
            await pilot.pause()
            assert application.split
            art = application.query_one(Artwork)
            cover = a_cover(Protocol.KITTY)
            application._art_ready(cover)
            erased.clear()

            await pilot.resize_terminal(150, 44)
            await pilot.pause()
            assert not application.split
            assert erased, "la colocación vieja se borra"
            assert art.cover is not None, "y la carátula sigue puesta"

    asyncio.run(scenario())


def test_plain_lyrics_move_through_the_track_in_the_split_pane(monkeypatch, tmp_path):
    """Without timestamps there is no line to follow, and the pane has no keys
    of its own; the words slide from the first line to the last as the song
    goes, so the end of them is on screen by the end of it."""
    from tidalamp.lyrics import parse_lyrics
    from tidalamp.widgets import LyricsPane

    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    app_module.config.set_option("arrangement", "split")

    async def scenario() -> None:
        mpv = FakeMpv()
        mpv.duration = 200.0
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(180, 44)) as pilot:
            await pilot.pause()
            pane = application.query_one(LyricsPane)
            pane.show(parse_lyrics(text="\n".join(f"verso {n}" for n in range(100))))
            await pilot.pause()

            def shown() -> str:
                return "\n".join(
                    pane.render_line(y).text for y in range(pane.size.height)
                )

            mpv.position = 0.0
            await pilot.pause(0.5)
            assert "verso 0" in shown() and "verso 99" not in shown()
            mpv.position = 100.0
            await pilot.pause(0.5)
            assert "verso 0" not in shown() and "verso 99" not in shown()
            mpv.position = 200.0
            await pilot.pause(0.5)
            assert "verso 99" in shown()

    asyncio.run(scenario())
