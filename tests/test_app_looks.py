"""Layouts, palettes, themed looks and the picture behind the queue."""

from __future__ import annotations

import asyncio

import pytest
from app_helpers import (
    FakeMpv,
    _grounds,
    a_cover,
    config_row,
    isolate_config,
    isolate_runtime,
    transport,
    use_theme,
)
from rich.cells import cell_len
from rich.text import Text
from textual.widgets import Static

from tidalamp import app as app_module
from tidalamp.app import ConfigScreen, RowList, TidalAmp
from tidalamp.layouts import LAYOUT_TABLE
from tidalamp.queue import Entry
from tidalamp.screens import config_window as screens_module
from tidalamp.theme import DEFAULT_COLORS, ThemePalette
from tidalamp.widgets import (
    Artwork,
    Glide,
)


def test_running_app_follows_an_omarchy_theme_change(monkeypatch):
    isolate_runtime(monkeypatch)
    initial = ThemePalette(dict(DEFAULT_COLORS), source="omarchy")
    changed_colors = dict(DEFAULT_COLORS)
    changed_colors["accent"] = "#7aa2f7"
    changed_colors["panel"] = "#1a1b26"
    changed = ThemePalette(changed_colors, source="omarchy")
    palettes = iter((initial, changed))
    monkeypatch.setattr(
        "tidalamp.app.load_palette", lambda *args, **kwargs: next(palettes)
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.press("s")
            application._refresh_theme()

            modes = application.query_one("#transport-play", Static)
            assert application.tidalamp_palette is changed
            assert application.get_theme_variable_defaults()["tidalamp-accent"] == (
                "#7aa2f7"
            )
            assert application.query_one("#main").styles.background.hex == "#1A1B26"
            assert any("#7aa2f7" in str(span.style) for span in modes.content.spans)

    asyncio.run(scenario())


def test_the_retro_theme_squares_each_button_and_spells_the_toggles(monkeypatch):
    """The original's buttons are separate square keys, not one frame, and
    its two toggles carry the words SHUFFLE and REPEAT."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "retro")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            widget = application.query_one("#transport-play")
            top, face, bottom = (widget.render_line(y).text for y in range(3))

            # Six buttons, six frames, square corners — not one shared frame.
            assert top.count("┌") == 6 and top.count("┐") == 6
            assert bottom.count("└") == 6 and bottom.count("┘") == 6
            assert face.count("│") == 12
            assert "┐┌" in top, "los botones van pegados, no fundidos"
            # No half blocks: they fill their cell, so a row of them came out
            # as a solid slab instead of an edge.
            assert not any(glyph in top + face + bottom for glyph in "▛▜▙▟▌▐")
            assert "SHUFFLE" in face and "REPEAT" in face
            # The mark, not the colour, is what says the state.
            assert "SHUFFLE ○" in face and "REPEAT ○" in face

            await pilot.press("s")
            await pilot.pause()
            assert "SHUFFLE ●" in transport(application)

    asyncio.run(scenario())


def test_the_ascii_theme_types_its_chrome_and_keeps_the_brackets(monkeypatch):
    """Bracket keys, ASCII rules, and no glyph the chrome cannot type.

    The brackets are also the regression: `Static.update` reads a `str` as
    Rich markup, so «[ TIDAL AMP ]» came out as two rules with a hole where
    the title had been.
    """
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "ascii")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            title = application.query_one("#titlebar", Static).render_line(0).text
            heading = application.query_one("#pl-title", Static).render_line(0).text
            face = application.query_one("#transport-play").render_line(1).text

            assert "[ TIDAL AMP ]" in title
            assert "[ COLA ]" in heading
            assert "[ z << ]" in face and "[ x >  ]" in face
            assert "[ s SHUFFLE - ]" in face and "[ r REPEAT - ]" in face
            # Nothing outside ASCII in any of the three, which is the point.
            for drawn in (title, heading.split("  ")[0], face):
                assert drawn.isascii(), drawn

            await pilot.press("s")
            await pilot.press("r")
            await pilot.pause()
            face = application.query_one("#transport-play").render_line(1).text
            assert "[ s SHUFFLE * ]" in face and "[ r REPEAT * ]" in face

    asyncio.run(scenario())


def test_no_look_lets_the_cover_spill_onto_the_seek_bar(monkeypatch):
    """A graphical protocol paints over what is below it, it does not clip.

    `height` is border-box, so a layout that pads the display band takes
    those rows out of the content. Nova pads the top by one, and that one row
    put the bottom of the cover on the seek bar.
    """
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        for name in app_module.LAYOUTS:
            app_module.config.THEME = name
            application = TidalAmp(object(), FakeMpv())
            async with application.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                art = application.query_one(Artwork)
                display = application.query_one("#display")
                seek = application.query_one("#seek")
                padding = display.styles.padding

                room = display.region.height - padding.top - padding.bottom
                assert art.rows <= room, f"{name}: la carátula no cabe en su banda"
                assert display.region.bottom <= seek.region.y, name
                # And the band is not padded out further than it needs.
                assert room == max(app_module.DISPLAY_HEIGHT, art.rows), name

    asyncio.run(scenario())


def test_every_look_fits_the_smallest_supported_terminal(monkeypatch):
    """A layout that does not fit wraps into the row above and ruins both."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        for name in app_module.LAYOUTS:
            app_module.config.THEME = name
            application = TidalAmp(object(), FakeMpv())
            async with application.run_test(size=(60, 18)) as pilot:
                await pilot.pause()
                transport_row = application.query_one("#transport")
                play = application.query_one("#transport-play")
                menu = application.query_one("#transport-menu")

                assert play.size.height == 3, name
                assert play.region.right <= menu.region.x, name
                assert menu.region.right <= transport_row.region.right, name
                for y in range(3):
                    drawn = play.render_line(y).text
                    assert cell_len(drawn) <= play.size.width, f"{name} fila {y}"

    asyncio.run(scenario())


def test_a_layout_on_an_ascii_budget_draws_its_own_chrome_in_ascii(monkeypatch):
    """The key hints come from the catalogue and are shared by every look;
    what the layout itself adds (the title, the heading's frame and the
    buttons) has to be something a terminal without box drawing can type."""
    isolate_runtime(monkeypatch)
    budgeted = [layout for layout in LAYOUT_TABLE.values() if layout.ascii_only]
    assert budgeted, "ascii tiene que seguir existiendo"

    async def scenario() -> None:
        for layout in budgeted:
            for width in (20, 80, 160):
                assert layout.title(width).isascii(), layout.name
                assert layout.queue_heading(width, "").isascii(), layout.name
            app_module.config.THEME = layout.name
            application = TidalAmp(object(), FakeMpv())
            async with application.run_test(size=(120, 30)) as pilot:
                await pilot.pause()
                assert (
                    application.query_one("#titlebar", Static)
                    .render_line(0)
                    .text.isascii()
                )
                play = application.query_one("#transport-play")
                for y in range(3):
                    assert play.render_line(y).text.isascii(), f"{layout.name} fila {y}"

    asyncio.run(scenario())


def test_switching_look_remeasures_the_transport_instead_of_cropping_it(monkeypatch):
    """The three looks are different widths, and the buttons were being cut
    to whichever one was on screen when the widget was last measured."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            widget = application.query_one("#transport-play")

            for name in ("retro", "nova", "quattro"):
                app_module.config.THEME = name
                application._apply_appearance()
                await pilot.pause()
                drawn = widget.render_line(1).text

                assert cell_len(drawn) <= widget.size.width, name
                # The last button is drawn whole, not cut off after its key.
                last = (
                    "r ↻–"
                    if name == "quattro"
                    else f"r {'repeat' if name == 'nova' else 'REPEAT'} ○"
                )
                assert last in drawn, name

    asyncio.run(scenario())


def test_the_retro_theme_rules_its_two_title_bars(monkeypatch):
    """The original tells its windows apart by the texture behind the name."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "retro")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            for selector, name in (("#titlebar", "A M P"), ("#pl-title", "LISTA")):
                widget = application.query_one(selector, Static)
                drawn = widget.render_line(0).text

                assert cell_len(drawn) == widget.size.width, "la regla llena la fila"
                assert name in drawn
                assert drawn.startswith("═") and drawn.endswith("═")
                # Centred: the two halves of the rule are within a cell.
                left, right = drawn.split(" ", 1)[0], drawn.rsplit(" ", 1)[-1]
                assert abs(len(left) - len(right)) <= 1

    asyncio.run(scenario())


def test_the_nova_theme_carries_state_without_drawing_a_single_box(monkeypatch):
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "nova")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            widget = application.query_one("#transport-play")
            top, face, under = (widget.render_line(y).text for y in range(3))

            assert not any(glyph in face for glyph in "╭│▛▌"), "nova no dibuja cajas"
            assert not top.strip(), "la fila de arriba queda vacía"
            assert not under.strip(), "sin nada encendido, no hay subrayado"
            assert "s shuffle ○" in face

            await pilot.press("s")
            await pilot.pause()
            face = widget.render_line(1).text
            under = widget.render_line(2).text
            assert "s shuffle ●" in face
            # The rule sits exactly under the label it belongs to.
            start = face.index("s shuffle ●")
            assert under[start : start + len("s shuffle ●")] == "─" * 11
            assert under.strip() == "─" * 11, "sólo el que está encendido"

    asyncio.run(scenario())


def test_the_quattro_theme_separates_the_groups_without_a_frame(monkeypatch):
    """The default layout keeps the two groups legible with one divider."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            play_widget = application.query_one("#transport-play")
            play = transport(application)

            assert "╭" not in play_widget.render_line(0).text
            assert play.count("│") == 1, "un separador entre los dos grupos"
            for key, glyph in (("z", "◀◀"), ("x", "▶"), ("c", "■"), ("v", "▶▶")):
                assert f"{key} {glyph}" in play
            # The rows above and below the labels stay empty, not framed.
            assert not play_widget.render_line(0).text.strip()
            assert not play_widget.render_line(2).text.strip()

    asyncio.run(scenario())


def test_the_compact_layout_drops_the_block_and_keeps_the_clock(monkeypatch):
    """Five rows of display band is the clock and nothing else."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(70, 20)) as pilot:
            await pilot.pause()
            assert not application.query_one("#trackmeta", Glide).display
            assert application.query_one("#clock").display

    asyncio.run(scenario())


@pytest.mark.parametrize("theme", ["quattro", "retro", "nova", "ascii"])
def test_every_layout_fills_its_queue_heading_to_the_right_edge(theme, monkeypatch):
    """Each look measured that row with a number written by hand, and each
    stopped short of the edge by a different amount. Quattro did not measure
    at all and left two thirds of the row empty."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, theme)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            title = application.query_one("#pl-title", Static)
            drawn = title.render_line(0).text.rstrip()

            assert cell_len(drawn) == title.size.width, theme

    asyncio.run(scenario())


def test_the_frameless_layout_does_not_start_on_row_zero(monkeypatch):
    """The other three get that separation from their border. Nova has none,
    so it buys the row: without it the wordmark sat against the terminal."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "nova")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 40)) as pilot:
            await pilot.pause()
            assert application.query_one("#titlebar", Static).region.y == 1

            # And gives it back where there is nothing to spare.
            await pilot.resize_terminal(82, 24)
            await pilot.pause()
            assert application.query_one("#titlebar", Static).region.y == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("theme", ["nova", "retro", "ascii"])
def test_switching_layout_keeps_the_cover_off_the_seek_bar(theme, monkeypatch):
    """Each layout pads the band differently, and the height was only ever
    worked out when the cover resized: switching left it one row short, and a
    graphical protocol does not clip -- it paints over what is below."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 44)) as pilot:
            await pilot.pause()
            application.query_one(Artwork).show(a_cover())
            await pilot.pause()

            use_theme(monkeypatch, theme)
            application._apply_appearance()
            await pilot.pause()

            art = application.query_one(Artwork)
            seek = application.query_one("#seek")
            assert art.region.bottom <= seek.region.y, theme

    asyncio.run(scenario())


def test_theme_and_palette_change_live_and_persist(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            assert application.query_one("#main").has_class("quattro")
            assert "╭" not in transport(application)

            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()

            screen.cursor = config_row(screen, "Tema")
            await pilot.press("enter")
            await pilot.pause()
            assert app_module.config.THEME == "retro"
            assert not application.query_one("#main").has_class("quattro")
            framed = application.query_one("#transport-play").render_line(0).text
            assert "┌" in framed, "el transporte pasa a los botones cuadrados"

            screen.cursor = config_row(screen, "Paleta")
            await pilot.press("enter")
            await pilot.pause()
            assert app_module.config.PALETTE == "classic"
            assert application.tidalamp_palette.source == "classic"
            assert app_module.config.read_file(path)["theme"] == "retro"
            assert app_module.config.read_file(path)["palette"] == "classic"

    asyncio.run(scenario())


def test_a_paired_theme_writes_its_palette_once_and_then_lets_go(monkeypatch, tmp_path):
    """Choosing the layout brings its colours; the palette stays free after.

    No pair ships yet, so `retro` is paired with `nord` for the test. What is
    under test is the screen: one write on choosing the layout, and nothing
    that puts the pair back when the palette or another layout is chosen.
    """
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        screens_module,
        "paired_palette",
        lambda layout: "nord" if layout == "retro" else None,
    )

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()

            screen.cursor = config_row(screen, "Tema")
            await pilot.press("enter")
            await pilot.pause()
            assert app_module.config.THEME == "retro"
            assert app_module.config.PALETTE == "nord"
            assert application.tidalamp_palette.source == "builtin:nord"
            assert app_module.config.read_file(path)["palette"] == "nord"

            # The palette moves on its own and the layout stays where it was.
            screen.cursor = config_row(screen, "Paleta")
            await pilot.press("enter")
            await pilot.pause()
            chosen = app_module.config.PALETTE
            assert chosen != "nord"
            assert app_module.config.THEME == "retro"
            assert application.query_one("#main").has_class("retro")

            # And leaving the paired layout does not revert the palette.
            screen.cursor = config_row(screen, "Tema")
            await pilot.press("enter")
            await pilot.pause()
            assert app_module.config.THEME != "retro"
            assert chosen == app_module.config.PALETTE
            assert app_module.config.read_file(path)["palette"] == chosen

    asyncio.run(scenario())


# ------------------------------------------------------------- terminal size


def test_a_small_terminal_gets_an_explanation_not_a_broken_layout(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(59, 17)) as pilot:
            await pilot.pause()
            notice = application.query_one("#too-small", Static)
            assert notice.display is True
            text = str(notice.content)
            assert "59×17" in text
            assert f"{TidalAmp.MIN_WIDTH}×{TidalAmp.MIN_HEIGHT}" in text

    asyncio.run(scenario())


def test_every_look_keeps_its_title_and_parts_the_cover_from_the_frame(
    monkeypatch, tmp_path
):
    """Both arrangements, every layout. Split once swallowed quattro's title
    (a grid row does not count margins), and the cover used to sit flush on
    the frame, which read as glued to it."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        for arrangement, size in (("stacked", (120, 34)), ("split", (170, 40))):
            app_module.config.ARRANGEMENT = arrangement
            for name in app_module.LAYOUTS:
                app_module.config.THEME = name
                application = TidalAmp(object(), FakeMpv())
                async with application.run_test(size=size) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    where = f"{name}/{arrangement}"
                    title = application.query_one("#titlebar", Static)
                    assert title.size.height >= 1, where
                    drawn = "".join(
                        title.render_line(y).text for y in range(title.size.height)
                    )
                    assert any(c.isalpha() for c in drawn), where
                    # The cover is hidden until one arrives, so the band's own
                    # left padding is what says where it will sit.
                    display = application.query_one("#display")
                    assert display.styles.padding.left >= 2, where

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("arrangement", "size"), [("stacked", (140, 40)), ("split", (180, 44))]
)
def test_a_themed_look_draws_its_emblem_behind_the_queue(
    arrangement, size, monkeypatch, tmp_path
):
    """Always there, playing or not: the emblem is the queue's ground, set
    against the right edge and faded into it, with the rows on top. The
    cursor's line keeps its accent, and a look without an emblem has none."""
    pytest.importorskip("PIL", reason="the emblem is drawn with Pillow, like the cover")
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    app_module.config.set_option("arrangement", arrangement)
    use_theme(monkeypatch, "comodin")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=size) as pilot:
            application.queue.replace(
                [
                    Entry(id=n, title=f"pista {n}", artist="a", duration=9)
                    for n in range(60)
                ],
                start=0,
            )
            application._sync_queue()
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            assert playlist.backdrop
            plain = application.tidalamp_palette["display_background"].lower()
            painted = [
                y for y in range(playlist.size.height) if _grounds(playlist, y) - {plain}
            ]
            assert len(painted) > playlist.size.height // 3, "ocupa la cola"
            # Only the ground changes: every line keeps its width and its text.
            # `divide` drops what follows the last cut, and a line that came
            # back short left the terminal showing old cells in its tail.
            from textual.widget import Widget

            from tidalamp.artwork import QUADRANTS

            glyphs = 0
            for y in range(playlist.size.height):
                drawn = playlist.render_line(y)
                plain_line = Widget.render_line(playlist, y)
                assert drawn.cell_length == plain_line.cell_length == playlist.size.width
                # A blank cell may carry the emblem's glyph; a letter never
                # changes.
                for mine, theirs in zip(drawn.text, plain_line.text, strict=True):
                    assert mine == theirs or (theirs == " " and mine in QUADRANTS), y
                    glyphs += mine != theirs
            assert glyphs, "las celdas vacías llevan el dibujo, como la carátula"
            # Set against the right edge: the left of a painted line is untouched.
            first = painted[len(painted) // 2]
            left = next(iter(playlist.render_line(first)))
            assert left.style.bgcolor is None or left.style.bgcolor.name.lower() == plain
            # The cursor's line is the accent and nothing else.
            accent = application.tidalamp_palette["accent"].lower()
            cursor = playlist._cursor_line()
            assert {c.lower() for c in _grounds(playlist, cursor)} <= {accent, plain}

            app_module.config.THEME = "quattro"
            application._apply_appearance()
            await pilot.pause()
            assert not playlist.backdrop
            assert all(
                not (_grounds(playlist, y) - {plain}) or y == playlist._cursor_line()
                for y in range(playlist.size.height)
            )

    asyncio.run(scenario())


def test_the_queue_backdrop_is_a_setting_of_its_own(monkeypatch, tmp_path):
    """`auto` is the theme's picture, `none` is none, and any themed look's
    name borrows its picture, placement and all, for another theme."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    # In the file, not only in memory: every `set_option` reads it back.
    app_module.config.set_option("theme", "cuaderno")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            assert playlist.backdrop and playlist.backdrop.name == "cuaderno.png"

            for value, picture, anchor in (
                ("pirata", "pirata.png", "bottom"),
                ("none", None, None),
                ("auto", "cuaderno.png", "middle"),
            ):
                app_module.config.set_option("backdrop", value)
                application._setting_changed("backdrop")
                await pilot.pause()
                if picture is None:
                    assert playlist.backdrop is None, value
                else:
                    assert playlist.backdrop.name == picture, value
                    assert playlist._placement[0] == anchor, value

            # A theme without a picture of its own can wear one.
            app_module.config.set_option("theme", "retro")
            app_module.config.set_option("backdrop", "comodin")
            application._setting_changed("backdrop")
            await pilot.pause()
            assert playlist.backdrop.name == "comodin.png"

    asyncio.run(scenario())


def test_the_backdrop_blends_into_the_ground_the_queue_is_painted_on(monkeypatch):
    """Nova puts the queue on the panel, not on the display's ground. Blended
    into the display's, every cell the picture's edge only partly covered came
    out as a dark block round the picture."""
    pytest.importorskip("PIL")
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "nova")
    monkeypatch.setattr(app_module.config, "BACKDROP", "bosque")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            panel = application.tidalamp_palette["panel"].lstrip("#")
            want = tuple(int(panel[i : i + 2], 16) for i in (0, 2, 4))
            assert playlist._ground(application.tidalamp_palette) == want
            assert playlist.backdrop is not None
            assert playlist._backdrop()

    asyncio.run(scenario())


def test_choosing_a_themed_look_writes_its_palette_and_its_backdrop(
    monkeypatch, tmp_path
):
    """Both once, on choosing the look; after that each is the user's."""
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()
            row = config_row(screen, "Tema")
            screen.cursor = row
            while app_module.config.THEME != "pirata":
                await pilot.press("enter")
                await pilot.pause()
            assert app_module.config.PALETTE == "pirata"
            assert app_module.config.BACKDROP == "pirata"
            assert app_module.config.read_file(path)["backdrop"] == "pirata"

            screen.cursor = config_row(screen, "Fondo de la cola")
            await pilot.press("enter")
            await pilot.pause()
            chosen = app_module.config.BACKDROP
            assert chosen != "pirata"
            assert app_module.config.THEME == "pirata"
            assert app_module.config.PALETTE == "pirata"

    asyncio.run(scenario())


def test_the_cover_shape_is_a_setting_of_its_own(monkeypatch, tmp_path):
    """Round or square under any theme, the corners in the band's own ground,
    and a change draws the cover on screen again."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    app_module.config.set_option("theme", "nova")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert application._cover_look()[0] == "square"
            fetched = []
            monkeypatch.setattr(application, "_art_worker", fetched.append)
            application._art_url = "http://cover"
            application._art_look = application._cover_look()

            app_module.config.set_option("cover_shape", "round")
            application._setting_changed("cover_shape")
            await pilot.pause()
            outline, ground = application._cover_look()
            assert outline == "round"
            # Nova paints the band as the panel, and the corners follow it.
            band = application.query_one("#display").styles.background
            assert ground == (band.r, band.g, band.b)
            assert fetched == ["http://cover"]

    asyncio.run(scenario())


def test_reggae_notes_take_green_and_red_in_turn(monkeypatch):
    """Green and red along the title, between waves that are already gold;
    red, gold and green in the frame's foot. Every other glyph keeps the
    colour its widget gives it."""
    isolate_runtime(monkeypatch)
    use_theme(monkeypatch, "reggae")
    monkeypatch.setattr(app_module.config, "PALETTE", "reggae")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            palette = application.tidalamp_palette
            wanted = [palette["playable"], palette["danger"]]
            title = application._title_text(80)
            assert isinstance(title, Text)
            notes = [
                str(span.style) for span in title.spans if title.plain[span.start] in "♪♫"
            ]
            assert notes[:4] == wanted * 2
            assert all(title.plain[span.start] in "♪♫" for span in title.spans)
            # The foot keeps all three.
            foot = application._tinted(
                application.layout.frame_subtitle, application.layout.flourish_colors
            )
            assert [str(span.style) for span in foot.spans] == [
                palette["danger"],
                palette["warning"],
                palette["playable"],
            ]
            assert "♪" in application.query_one("#main").border_subtitle

            use_theme(monkeypatch, "quattro")
            application._apply_appearance()
            await pilot.pause()
            assert isinstance(application._title_text(80), str)

    asyncio.run(scenario())
