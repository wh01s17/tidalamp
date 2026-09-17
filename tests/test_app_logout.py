"""Logging out from the settings window: the session goes, the app's data only
when its box is ticked, the window says how to come back, and the app
closes."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, config_text, isolate_config, isolate_runtime, settle

from tidalamp import auth
from tidalamp.app import ConfigScreen, TidalAmp
from tidalamp.queue import Queue
from tidalamp.screens import ChoiceScreen, LogoutScreen
from tidalamp.settings import Settings


def _logout_row(screen: ConfigScreen) -> int:
    return next(i for i, row in enumerate(screen._rows) if row.action == "logout")


def _run(monkeypatch, tmp_path, keys: list[str], stuck: bool = False):
    """Open the logout question, press ``keys`` in it, accept whatever follows."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    session = locked / "session.json"
    session.write_text("x")
    settings = tmp_path / "state"
    settings.mkdir()
    (settings / "queue.json").write_text("[]")
    if stuck:
        # A folder that cannot be written to: a session that stays put.
        locked.chmod(0o500)
    asked: list[bool] = []

    def forgotten(data_too: bool = False):
        asked.append(data_too)
        return (session, settings) if data_too else (session,)

    monkeypatch.setattr(auth, "forgotten", forgotten)
    closed: list[bool] = []
    monkeypatch.setattr(TidalAmp, "quit_now", lambda self: closed.append(True))
    seen: dict[str, str] = {}

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            screen = ConfigScreen()
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = _logout_row(screen)
            await pilot.press("enter")
            await settle(pilot, lambda: isinstance(application.screen, LogoutScreen))
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            if isinstance(application.screen, ChoiceScreen):
                seen["message"] = str(
                    application.screen.query_one("#choice-message").render()
                )
                await pilot.press("enter")
                await pilot.pause()
            elif application.screen is screen:
                seen["config"] = config_text(application)

    try:
        asyncio.run(scenario())
    finally:
        locked.chmod(0o700)
    return session, settings, asked, closed, seen


def test_the_question_opens_on_cancel(monkeypatch, tmp_path):
    """↵ twice by reflex on the row must not log anybody out."""
    session, settings, asked, closed, _seen = _run(monkeypatch, tmp_path, ["enter"])

    assert session.exists() and settings.exists()
    assert asked == [] and closed == []


def test_logging_out_keeps_the_settings_unless_the_box_is_ticked(monkeypatch, tmp_path):
    session, settings, asked, closed, seen = _run(monkeypatch, tmp_path, ["up", "enter"])

    assert not session.exists()
    assert settings.exists()
    assert asked == [False]
    assert "tidalamp login" in seen["message"]
    assert "Se borró la sesión." in seen["message"]
    assert closed == [True]


def test_the_ticked_box_takes_the_settings_with_the_session(monkeypatch, tmp_path):
    # Up to the box, tick it, down to «cerrar sesión», apply.
    session, settings, asked, closed, seen = _run(
        monkeypatch, tmp_path, ["up", "up", "enter", "down", "enter"]
    )

    assert not session.exists() and not settings.exists()
    assert asked == [True]
    assert "los datos de tidalamp" in seen["message"]
    assert closed == [True]


def test_logging_out_without_the_box_still_saves_the_queue_on_the_way_out(
    monkeypatch, tmp_path
):
    isolate_runtime(monkeypatch)
    saved: list[str] = []
    monkeypatch.setattr(Queue, "save", lambda self: saved.append("queue"))
    monkeypatch.setattr(auth, "logout", lambda paths: saved.append("deleted"))

    asyncio.run(_close(TidalAmp(object(), FakeMpv())))

    assert saved == ["queue"]


def test_with_the_box_nothing_is_saved_and_the_data_goes_again_after_mpv(
    monkeypatch, tmp_path
):
    """The queue came back: quitting saved it after the logout had deleted it."""
    isolate_runtime(monkeypatch)
    events: list[object] = []
    monkeypatch.setattr(Queue, "save", lambda self: events.append("queue"))
    monkeypatch.setattr(Settings, "save", lambda self: events.append("settings"))
    monkeypatch.setattr(auth, "logout", lambda paths: events.append(paths))
    application = TidalAmp(object(), FakeMpv())
    application.forget_on_exit = (tmp_path / "state",)

    asyncio.run(_close(application))

    assert events == [(tmp_path / "state",)]


async def _close(application: TidalAmp) -> None:
    async with application.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await application._close_player()


def test_ticking_the_box_alone_deletes_nothing(monkeypatch, tmp_path):
    session, settings, asked, closed, _seen = _run(
        monkeypatch, tmp_path, ["up", "up", "enter", "escape"]
    )

    assert session.exists() and settings.exists()
    assert asked == [] and closed == []


def test_a_logout_that_failed_does_not_close_the_app(monkeypatch, tmp_path):
    _session, _settings, _asked, closed, seen = _run(
        monkeypatch, tmp_path, ["up", "enter"], stuck=True
    )

    assert closed == []
    assert "No se pudo cerrar la sesión" in seen["config"]
