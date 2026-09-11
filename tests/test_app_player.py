"""The rest of the player: startup, audio stack notices and small widgets."""

from __future__ import annotations

import asyncio

from app_helpers import (
    FakeMpv,
    a_cover,
    config_text,
    isolate_config,
    isolate_runtime,
    open_browser,
    settle,
)
from rich.cells import cell_len
from textual.widgets import Static

from tidalamp import app as app_module
from tidalamp import artwork
from tidalamp import audio as audio_module
from tidalamp.app import ConfigScreen, TidalAmp
from tidalamp.artwork import Protocol
from tidalamp.screens import (
    BROWSER_HINTS,
)
from tidalamp.widgets import (
    Analyzer,
    Artwork,
    Spinner,
)


def test_a_pixel_protocol_goes_out_as_a_zero_width_control_segment(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            art = application.query_one(Artwork)
            art.show(a_cover(Protocol.KITTY, escape="\033_Ga=T;AAAA\033\\"))
            await pilot.pause()

            strip = art.render_line(0)
            control = [segment for segment in strip if segment.is_control]
            assert control and control[0].text.startswith("\033_G")
            # The escape must not eat cells, or the compositor would shift the
            # rest of the row to the left.
            assert strip.cell_length == art.size.width
            # One anchor draws the whole image; the other rows stay empty.
            assert not any(segment.is_control for segment in art.render_line(1))

    asyncio.run(scenario())


def test_pushing_a_screen_before_the_ui_exists_is_harmless(monkeypatch):
    """Textual pushes the default screen while compose has not run yet."""
    isolate_runtime(monkeypatch)
    application = TidalAmp(object(), FakeMpv())
    application._hide_art()
    application._restore_art()
    assert application._artwork() is None


# ---------------------------------------------------------------- loading state


def test_the_spinner_is_silent_until_there_is_something_to_wait_for():
    spinner = Spinner()
    assert spinner.busy is False
    assert spinner.render().plain == ""

    # Idle must not animate: a frame change would repaint the screen forever.
    spinner._advance()
    assert spinner._frame == 0

    spinner.start("cargando playlists…")
    spinner._advance()
    assert spinner.busy is True
    assert spinner._frame == 1
    assert spinner.render().plain == f"{Spinner.FRAMES[1]} cargando playlists…"

    spinner.stop()
    assert spinner.render().plain == ""


def test_the_footer_drops_whole_hints_instead_of_cropping_one(monkeypatch):
    """It was one literal, and at the browser's own width the terminal ate
    «R recargar   esc cerrar», leaving a stray «R» against the border."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_browser(application)
            await pilot.pause()
            hint = application.screen.query_one("#browser-hint")
            line = hint.render_line(0).text

            assert cell_len(line) <= hint.size.width
            assert line.rstrip().endswith("esc cerrar")
            assert "? ayuda" in line
            # Whatever survived, survived whole.
            for key, label, _drop in BROWSER_HINTS:
                assert (f"{key} {label}" in line) or (label not in line)

    asyncio.run(scenario())


def test_a_shape_that_is_not_one_of_the_three_falls_back_to_bars(monkeypatch):
    """The setting comes from a file the user edits by hand."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(app_module.config, "VISUALIZER", "espiral")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            assert application.query_one("#analyzer", Analyzer).mode == "bars"

    asyncio.run(scenario())


def test_the_screen_reports_what_the_audio_stack_is_doing(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        audio_module,
        "sink",
        lambda: audio_module.Sink(name="s", description="Mi DAC", rate=48000),
    )
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: (48000,))
    monkeypatch.setattr(audio_module, "hardware_rates", lambda name: (96000,))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await settle(pilot, lambda: "Mi DAC" in config_text(application))
            drawn = config_text(application)
            assert "Mi DAC" in drawn and "48000" in drawn
            # A graph stuck on one rate is the thing worth saying out loud,
            # and without moving the cursor onto the row that fixes it: the
            # badge tells the truth about the stream while the DAC gets less.
            assert "remuestrea" in drawn
            assert "El grafo remuestrea" in drawn.split("Salida:")[1]

    asyncio.run(scenario())


def test_a_graph_that_can_change_rate_says_nothing_alarming(monkeypatch, tmp_path):
    """The warning has to mean something, so it cannot always be there."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        audio_module,
        "sink",
        lambda: audio_module.Sink(name="s", description="Mi DAC", rate=96000),
    )
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: (44100, 48000, 96000))
    monkeypatch.setattr(audio_module, "hardware_rates", lambda name: (96000,))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await settle(pilot, lambda: "Mi DAC" in config_text(application))

            assert "remuestrea" not in config_text(application)

    asyncio.run(scenario())


def test_a_bluetooth_output_says_so_where_it_cannot_be_missed(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        audio_module,
        "sink",
        lambda: audio_module.Sink(
            name="bluez_output.AA", description="Auriculares", rate=48000
        ),
    )
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: (44100, 48000))
    monkeypatch.setattr(audio_module, "hardware_rates", lambda name: ())

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await settle(pilot, lambda: "Auriculares" in config_text(application))

            assert "Bluetooth" in config_text(application)

    asyncio.run(scenario())


def test_a_missing_pillow_is_announced_instead_of_leaving_an_empty_corner(monkeypatch):
    """Without Pillow the cover widget simply never becomes visible.

    That used to be a `log.info` to a file nobody reads, so a fresh clone
    looked broken. The status line now names the extra that fixes it.
    """
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(artwork, "have_decoder", lambda: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert "Pillow" in application.status

    asyncio.run(scenario())


def test_a_present_pillow_says_nothing(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(artwork, "have_decoder", lambda: True)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert "Pillow" not in application.status

    asyncio.run(scenario())


def test_a_terminal_big_enough_shows_nothing_extra(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert application.query_one("#too-small", Static).display is False

    asyncio.run(scenario())


def test_favouriting_nothing_says_so_instead_of_failing(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("f")
            assert application.status == "no hay ninguna pista seleccionada"

    asyncio.run(scenario())
