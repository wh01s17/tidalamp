"""The menu launcher from inside the app: asked on the first start, and a row
in the settings window for later."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app_helpers import FakeMpv, config_text, isolate_config, isolate_runtime, settle

from tidalamp import desktop
from tidalamp.app import ConfigScreen, TidalAmp
from tidalamp.screens import ChoiceScreen


def _first_start(monkeypatch, tmp_path, keys: list[str]) -> tuple[TidalAmp, list[str]]:
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        desktop, "create", lambda: calls.append("create") or tmp_path / "t.desktop"
    )
    monkeypatch.setattr(desktop, "decline", lambda: calls.append("decline"))
    application = TidalAmp(object(), FakeMpv())
    application.offer_launcher = True

    async def scenario() -> None:
        async with application.run_test(size=(100, 34)) as pilot:
            await settle(pilot, lambda: isinstance(application.screen, ChoiceScreen))
            for key in keys:
                await pilot.press(key)
            await settle(pilot, lambda: not isinstance(application.screen, ChoiceScreen))

    asyncio.run(scenario())
    return application, calls


def test_the_first_start_asks_and_yes_creates_the_launcher(monkeypatch, tmp_path):
    application, calls = _first_start(monkeypatch, tmp_path, ["enter"])

    assert calls == ["create"]
    assert "menú de aplicaciones" in application.status


def test_no_is_remembered(monkeypatch, tmp_path):
    application, calls = _first_start(monkeypatch, tmp_path, ["down", "enter"])

    assert calls == ["decline"]
    assert "no se volverá a preguntar" in application.status


def test_esc_leaves_the_question_for_next_time(monkeypatch, tmp_path):
    _application, calls = _first_start(monkeypatch, tmp_path, ["escape"])

    assert calls == []


def test_without_the_flag_nothing_is_asked(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            assert not isinstance(application.screen, ChoiceScreen)

    asyncio.run(scenario())


def _launcher_row(screen: ConfigScreen) -> int:
    return next(i for i, row in enumerate(screen._rows) if row.action == "launcher")


def test_the_settings_row_says_where_an_existing_launcher_is(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    found = Path("/home/u/.local/share/applications/TidalAmp.desktop")
    monkeypatch.setattr(desktop, "existing", lambda dirs: found)
    monkeypatch.setattr(desktop, "create", lambda: _fail("creó otro lanzador"))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            screen = ConfigScreen()
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = _launcher_row(screen)
            await pilot.press("enter")
            await settle(pilot, lambda: "ya existe" in config_text(application))
            drawn = config_text(application)
            assert "El acceso directo ya existe" in drawn
            assert str(found) in drawn
            assert not isinstance(application.screen, ChoiceScreen)

    asyncio.run(scenario())


def test_the_settings_row_creates_the_launcher_when_there_is_none(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    created = tmp_path / "tidalamp.desktop"
    calls: list[str] = []
    monkeypatch.setattr(desktop, "existing", lambda dirs: None)
    monkeypatch.setattr(desktop, "create", lambda: calls.append("create") or created)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            screen = ConfigScreen()
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = _launcher_row(screen)
            assert "sin crear" in config_text(application)
            await pilot.press("enter")
            await settle(pilot, lambda: isinstance(application.screen, ChoiceScreen))
            await pilot.press("enter")
            await settle(pilot, lambda: application.screen is screen)
            assert calls == ["create"]
            assert "menú de aplicaciones" in application.status
            await settle(pilot, lambda: "creado" in config_text(application))

    asyncio.run(scenario())


def _fail(message: str):
    raise AssertionError(message)


def test_a_footer_line_too_wide_glides_instead_of_ending_in_an_ellipsis(
    monkeypatch, tmp_path
):
    """A path cropped to «…» lost the part worth reading: the file name."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    found = Path(
        "/srv/a/very/long/folder/that/does/not/fit/applications/TidalAmp.desktop"
    )
    monkeypatch.setattr(desktop, "existing", lambda dirs: found)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(70, 40)) as pilot:
            await pilot.pause()
            screen = ConfigScreen()
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = _launcher_row(screen)
            screen._launcher_probed(found)
            await pilot.pause()
            assert "…" not in config_text(application).splitlines()[-1]
            assert screen._glide_overflow > 0
            for _step in range(screen._glide_overflow * 3 + 200):
                screen._glide_tick()
                if screen._glide_offset == screen._glide_overflow:
                    break
            await pilot.pause()
            assert "TidalAmp.desktop" in config_text(application)

    asyncio.run(scenario())
