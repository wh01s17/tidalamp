"""The settings window, the config file behind it, and transparency."""

from __future__ import annotations

import asyncio

from app_helpers import (
    FakeMpv,
    config_row,
    config_text,
    isolate_config,
    isolate_runtime,
    settle,
    transport,
)
from textual.widgets import Static

from tidalamp import app as app_module
from tidalamp import audio as audio_module
from tidalamp import columns as columns_module
from tidalamp import library
from tidalamp.app import ConfigScreen, RowList, TidalAmp
from tidalamp.queue import Entry
from tidalamp.screens import (
    ColumnsScreen,
)
from tidalamp.widgets import (
    Analyzer,
    Artwork,
)


def test_the_menu_announces_the_settings_window(monkeypatch):
    """It was reachable only from the help screen, which you have to know to
    open in the first place."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 26)) as pilot:
            await pilot.pause()
            assert "o config" in transport(application, "menu")

    asyncio.run(scenario())


def test_the_setting_changes_the_shape_without_moving_the_analyser(monkeypatch):
    """Every shape is drawn in the same place — beside the cover, under the
    track details — and all of them use the whole column."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            analyzer = application.query_one("#analyzer", Analyzer)
            assert analyzer.mode == "bars"
            where = analyzer.region

            monkeypatch.setattr(app_module.config, "VISUALIZER", "curve")
            application._setting_changed("visualizer")
            await pilot.pause()

            assert analyzer.mode == "curve"
            assert analyzer.region == where, "no se mueve de sitio"

    asyncio.run(scenario())


def test_the_config_screen_offers_every_shape_and_writes_the_one_chosen(
    monkeypatch, tmp_path
):
    isolate_runtime(monkeypatch)
    path = tmp_path / "config.toml"
    monkeypatch.setattr(app_module.config, "CONFIG_FILE", path)
    changed: list[str] = []

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()

            def applied(name: str) -> None:
                changed.append(name)
                application._setting_changed(name)

            screen = ConfigScreen(applied)
            application.push_screen(screen)
            await pilot.pause()
            row = next(o for o in screen._rows if o.key == "visualizer")
            assert row.choices == Analyzer.MODES

            # One step along the row, the way ↵ moves it.
            screen._cycle(row, 1)
            await pilot.pause()

            assert app_module.config.VISUALIZER == "mirror"
            assert 'visualizer = "mirror"' in path.read_text(encoding="utf-8")
            assert changed == ["visualizer"]
            assert application.query_one("#analyzer", Analyzer).mode == "mirror"

    asyncio.run(scenario())


def test_nobody_pays_for_the_year_column_they_turned_off(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(app_module.config, "COLUMNS", ("artist", "duration"))
    asked: list[int] = []
    monkeypatch.setattr(library, "album_year", lambda s, a: asked.append(a) or 0)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=1, title="a", artist="x", album="y", album_id=7)], start=-1
            )
            application._sync_queue()
            await pilot.pause()

            assert asked == []

    asyncio.run(scenario())


def test_o_opens_the_settings_and_esc_closes_them(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
            assert isinstance(application.screen, ConfigScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert len(application.screen_stack) == 1

    asyncio.run(scenario())


def test_changing_a_setting_writes_the_file_and_takes_effect(monkeypatch, tmp_path):
    """The whole point: a change made once stays made. It used to need an
    editor, or a variable exported before launching."""
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen(application._setting_changed))
            await pilot.pause()

            assert app_module.config.DEFAULT_QUALITY == "HI_RES_LOSSLESS"
            await pilot.press("enter")  # cursor starts on Quality
            await pilot.pause()

            assert app_module.config.DEFAULT_QUALITY == "LOW"
            assert app_module.config.read_file(path)["quality"] == "LOW"
            assert "LOW" in application.status

    asyncio.run(scenario())


def test_the_settings_cycle_both_ways(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await pilot.pause()

            await pilot.press("left")
            await pilot.pause()
            assert app_module.config.DEFAULT_QUALITY == "LOSSLESS"

            await pilot.press("right")
            await pilot.pause()
            assert app_module.config.DEFAULT_QUALITY == "HI_RES_LOSSLESS"

    asyncio.run(scenario())


def test_the_settings_are_grouped_by_what_they_are_about(monkeypatch, tmp_path):
    """Ten switches in one column read as ten unrelated switches: the quality
    of the stream sat next to the colour of the borders."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen(application._setting_changed))
            await pilot.pause()
            drawn = application.screen.query_one("#config-list").render_line
            lines = [drawn(y).text for y in range(30)]
            at = {
                name: next(i for i, line in enumerate(lines) if line.strip() == name)
                for name in ("Audio", "Apariencia", "General")
            }
            assert at["Audio"] < at["Apariencia"] < at["General"]

            def row(label: str) -> int:
                return next(i for i, line in enumerate(lines) if label in line)

            assert at["Audio"] < row("Calidad") < at["Apariencia"]
            assert at["Apariencia"] < row("Transparencia") < at["General"]
            assert at["General"] < row("Idioma")

    asyncio.run(scenario())


def test_the_settings_list_scrolls_instead_of_hiding_the_cursor(monkeypatch, tmp_path):
    """The window grows to its text and stops at the terminal. On a small one
    the rows past the fold used to be selectable and invisible at once."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()
            last = len(screen._rows) - 1
            for _ in range(last):
                await pilot.press("down")
            await pilot.pause()

            widget = application.screen.query_one("#config-list")
            lines = [widget.render_line(y).text for y in range(widget.size.height)]
            assert any(screen._rows[last].label in line for line in lines)
            # And its heading came with it, so the row is not orphaned.
            assert any(line.strip() == screen._rows[last].group for line in lines)

    asyncio.run(scenario())


def test_a_modal_is_solid_until_transparency_is_turned_on(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()
            assert not screen.has_class("transparent")

            screen.cursor = config_row(screen, "Transparencia")
            await pilot.press("enter")
            await pilot.pause()

            assert app_module.config.TRANSPARENCY is True
            # On the window that is already open, not only on the next one:
            # the answer belongs under the cursor that asked for it.
            assert screen.has_class("transparent")

    asyncio.run(scenario())


def test_choosing_columns_redraws_the_queue_that_is_already_there(monkeypatch, tmp_path):
    """It has to land on the queue on screen, not on the next one loaded."""
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(160, 34)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [
                    Entry(
                        id=1,
                        title="Virgen",
                        artist="Adolescent's",
                        album="Ahora",
                        year=1993,
                        popularity=64,
                        duration=272,
                    )
                ],
                start=0,
            )
            application._sync_queue()
            await pilot.pause()
            playlist = application.query_one("#playlist", RowList)
            assert "64" not in playlist.render_line(0).text

            screen = ConfigScreen(application._setting_changed)
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = config_row(screen, "Columnas de la cola")
            await pilot.press("enter")
            await settle(pilot, lambda: isinstance(application.screen, ColumnsScreen))

            picker = application.screen
            picker.cursor = [c.name for c in columns_module.ALL].index("popularity")
            await pilot.press("enter")
            await pilot.pause()

            # Same queue, no reload: the row on screen has the column now.
            assert "popularity" in app_module.config.COLUMNS
            assert "64" in playlist.render_line(0).text
            assert "popularity" in app_module.config.read_file(path)["columns"]

    asyncio.run(scenario())


def test_a_setting_the_environment_overrides_is_labelled(monkeypatch, tmp_path):
    """Showing a value the app is not using would be a lie."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setenv("TIDALAMP_QUALITY", "HIGH")
    app_module.config.reload()

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await pilot.pause()
            assert "TIDALAMP_QUALITY" in config_text(application)

    asyncio.run(scenario())


def test_the_way_out_of_the_settings_survives_a_short_terminal(monkeypatch, tmp_path):
    """The footer grew a line; the hint is docked so it is never the one cut."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        audio_module,
        "sink",
        lambda: audio_module.Sink(name="s", description="Mi DAC", rate=48000),
    )
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: (48000,))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            application.push_screen(ConfigScreen())
            await settle(pilot, lambda: "Mi DAC" in config_text(application))
            box = application.screen.query_one("#config-box")
            hint = application.screen.query_one("#config-hint")

            assert box.region.bottom <= 18
            assert hint.region.bottom <= box.region.bottom
            assert "cerrar" in hint.render_line(0).text

    asyncio.run(scenario())


def test_the_rates_row_writes_and_removes_the_drop_in(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    dropin = tmp_path / "pipewire.conf.d" / "rates.conf"
    monkeypatch.setattr(audio_module, "CONF_DIR", dropin.parent)
    monkeypatch.setattr(audio_module, "RATES_FILE", dropin)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen()
            application.push_screen(screen)
            await pilot.pause()

            screen.cursor = config_row(screen, "Ritmos hi-res en PipeWire")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert dropin.is_file()

            await pilot.press("enter")
            await pilot.pause()
            assert not dropin.exists()

    asyncio.run(scenario())


def test_sixty_columns_use_the_compact_player_instead_of_a_warning(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(60, 18)) as pilot:
            await pilot.pause()

            assert application.query_one("#too-small", Static).display is False
            assert application.query_one("#main").has_class("compact")
            assert application.query_one(Artwork).region.width == 0
            assert application.query_one("#balance").display is False
            assert application.query_one("#playlist").size.height >= 3
            assert "↵ reproducir" in str(
                application.query_one("#pl-title", Static).content
            )
            assert "? ayuda" in str(application.query_one("#transport-menu").content)

    asyncio.run(scenario())


def test_the_output_rate_is_followed_until_pipewire_settles(monkeypatch):
    """The badge used to read the sink a quarter second after `loadfile`.

    PipeWire only switches the graph rate once mpv opens the device, which is
    after the stream has been fetched and decoded: that early read reported
    the *previous* track's rate, so the badge said 44.1 kHz while the DAC's
    own screen read 96K. The worker has to keep looking.
    """
    from tidalamp import app as app_module

    rates = iter([44100, 44100, 96000, 96000, 96000, 96000, 96000, 96000])
    seen: list[int] = []

    def fake_sink() -> audio_module.Sink:
        return audio_module.Sink(
            name="alsa_output.usb",
            description="FIIO BTR15",
            rate=next(rates, 96000),
            sample_format="s16le",
        )

    monkeypatch.setattr(audio_module, "sink", fake_sink)
    monkeypatch.setattr(app_module, "SINK_SETTLE", 0.3)
    monkeypatch.setattr(app_module, "SINK_POLL", 0.0)
    monkeypatch.setattr(
        app_module, "get_current_worker", lambda: type("W", (), {"is_cancelled": False})
    )

    class Recorder:
        def _set_sink(self, sink):
            seen.append(sink.rate)

        def call_from_thread(self, fn, sink):
            fn(sink)

    recorder = Recorder()
    # The worker body, called straight rather than through Textual's runner.
    TidalAmp._refresh_sink_worker.__wrapped__(recorder)

    # It published the stale rate first, then corrected itself, and it did not
    # repeat a rate that had not moved.
    assert seen == [44100, 96000]
