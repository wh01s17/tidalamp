"""Offline mode: starting without TIDAL, the local library, and the way back."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import typer
from app_helpers import (
    FakeMpv,
    config_row,
    isolate_config,
    isolate_runtime,
    settle,
    wait_for,
)
from test_local import make_flac

from tidalamp import auth, cli, config, levels, links
from tidalamp.app import BrowserScreen, ConfigScreen, RowList, TidalAmp
from tidalamp.queue import Entry
from tidalamp.screens.login import LoginScreen

# ------------------------------------------------------------------ the stand-in


def test_the_offline_session_answers_every_question_with_offline():
    session = auth.OfflineSession()
    with pytest.raises(auth.Offline, match="modo offline"):
        session.track("1")
    # A NotLoggedIn, so the paths that already handle a dead session say it.
    with pytest.raises(auth.NotLoggedIn):
        _ = session.user
    # And an AttributeError, so a getattr with a default reads it as absent.
    assert getattr(session, "config", None) is None
    assert auth.is_offline(session)
    assert not auth.is_offline(object())


def test_restoring_reuses_the_session_kept_in_memory(monkeypatch):
    kept = SimpleNamespace(check_login=lambda: True)
    monkeypatch.setattr(auth, "load_session", lambda: pytest.fail("no hace falta"))
    assert auth.restore(kept) is kept  # type: ignore[arg-type]


def test_restoring_without_one_reads_the_saved_session(monkeypatch):
    saved = object()
    monkeypatch.setattr(auth, "load_session", lambda: saved)
    assert auth.restore(None) is saved


class FakeLinkSession:
    """`tidalapi.Session` as far as the device flow goes."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.saved = []

    def process_link_login(self, link, until_expiry=True):
        assert until_expiry is False, "una comprobación, no el bucle de tidalapi"
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def save_session_to_file(self, path):
        self.saved.append(path)


def test_a_login_check_waits_until_approved_and_then_saves(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "SESSION_FILE", tmp_path / "session.json")
    session = FakeLinkSession([TimeoutError("todavía no"), True])
    assert auth.finish_login(session, object()) is False  # type: ignore[arg-type]
    assert session.saved == []
    assert auth.finish_login(session, object()) is True  # type: ignore[arg-type]
    assert session.saved == [tmp_path / "session.json"]


# ----------------------------------------------------------------- the start


def test_the_setting_starts_offline_without_asking_tidal(monkeypatch):
    monkeypatch.setattr(config, "OFFLINE", True)
    monkeypatch.setattr(cli, "load_session", lambda: pytest.fail("no se pregunta"))
    assert auth.is_offline(cli._session_or_offline())


def no_session():
    raise auth.NotLoggedIn("No hay sesión guardada. Ejecuta: tidalamp login")


def test_without_a_session_the_start_offers_offline(monkeypatch):
    monkeypatch.setattr(cli, "load_session", no_session)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    asked = []
    monkeypatch.setattr(
        cli.typer, "confirm", lambda text, default: asked.append(text) or True
    )
    assert auth.is_offline(cli._session_or_offline())
    assert asked and "offline" in asked[0]


def test_a_tidal_that_does_not_answer_offers_offline_too(monkeypatch):
    def unreachable():
        raise ConnectionError("sin red")

    monkeypatch.setattr(cli, "load_session", unreachable)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.typer, "confirm", lambda text, default: True)
    assert auth.is_offline(cli._session_or_offline())


def test_declining_offline_ends_the_start_as_before(monkeypatch):
    monkeypatch.setattr(cli, "load_session", no_session)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.typer, "confirm", lambda text, default: False)
    with pytest.raises(typer.Exit):
        cli._session_or_offline()


def test_without_a_terminal_to_ask_on_it_fails_as_before(monkeypatch):
    monkeypatch.setattr(cli, "load_session", no_session)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.typer, "confirm", lambda *a, **k: pytest.fail("sin tty"))
    with pytest.raises(typer.Exit):
        cli._session_or_offline()


# ------------------------------------------------------------ the player offline


def offline_app() -> TidalAmp:
    return TidalAmp(auth.OfflineSession(), FakeMpv())  # type: ignore[arg-type]


def test_the_library_opens_straight_onto_local_music(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(config, "LOCAL_FOLDERS", (str(tmp_path),))
    make_flac(tmp_path / "a.flac", title="Schism", album="Lateralus", artist="TOOL")

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            assert "modo offline" in application.status
            await pilot.press("l")
            await settle(
                pilot,
                lambda: (
                    isinstance(application.screen, BrowserScreen)
                    and bool(application.screen.query_one(RowList).rows)
                ),
            )
            screen = application.screen
            assert "MÚSICA LOCAL" in str(screen.query_one("#browser-title").render())
            labels = [row.label for row in screen.query_one(RowList).rows]
            assert labels == [
                "Álbumes",
                "Artistas",
                "Todas las pistas",
                "Carpetas",
                "Playlists",
            ]

    asyncio.run(scenario())


def test_search_says_it_is_tidals_instead_of_failing(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            assert not isinstance(application.screen, BrowserScreen)
            assert "búsqueda es de TIDAL" in application.status

    asyncio.run(scenario())


def test_a_tidal_track_in_the_queue_says_it_does_not_play_offline(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.queue.replace([Entry(id=1, title="Schism", artist="TOOL")])
            application.queue_view.sync()
            application.playback.play_index(0)
            await wait_for(
                pilot, lambda: "no suena en modo offline" in application.status
            )
            assert application.mpv.loaded is None

    asyncio.run(scenario())


# ------------------------------------------------------- switching in settings


def open_settings(application) -> ConfigScreen:
    screen = ConfigScreen(application.setting_changes.apply)
    application.push_screen(screen)
    return screen


def test_the_login_row_only_shows_offline(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())  # type: ignore[arg-type]
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            screen = open_settings(application)
            await pilot.pause()
            config_row(screen, "Modo offline")
            with pytest.raises(AssertionError):
                config_row(screen, "Iniciar sesión en TIDAL")

            application.connection.go_offline()
            await pilot.pause()
            login = screen._rows[config_row(screen, "Iniciar sesión en TIDAL")]
            assert "tidalamp login" in login.note

    asyncio.run(scenario())


def test_going_offline_and_back_keeps_the_session_without_a_login(monkeypatch, tmp_path):
    """The whole promise of the switch: off again, and TIDAL is back with the
    very session it had, no link and no code."""
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)
    real = SimpleNamespace(check_login=lambda: True)
    restored = []

    def restore(kept):
        restored.append(kept)
        return kept

    monkeypatch.setattr(auth, "restore", restore)

    async def scenario() -> None:
        application = TidalAmp(real, FakeMpv())  # type: ignore[arg-type]
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            screen = open_settings(application)
            await pilot.pause()
            screen.cursor = config_row(screen, "Modo offline")
            levels.cached("fav:tracks", list)()

            await pilot.press("enter")
            await pilot.pause()
            assert application.offline
            assert config.read_file(path)["offline"] is True
            # What TIDAL answered is not shown as if it were still there.
            assert "fav:tracks" not in levels._LEVELS
            # The value, not the drawn line: the label column is as wide as the
            # longest label, and Windows has other audio rows than Linux.
            row = screen._rows[config_row(screen, "Modo offline")]
            assert screen._value(row) == "true"

            await pilot.press("enter")
            await wait_for(pilot, lambda: not application.offline)
            assert application.session is real
            assert restored == [real]
            assert config.read_file(path)["offline"] is False
            assert "recuperada" in application.status

    asyncio.run(scenario())


def test_without_a_session_to_go_back_to_it_stays_offline_and_says_why(
    monkeypatch, tmp_path
):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    def nothing(kept):
        raise auth.NotLoggedIn("No hay sesión guardada. Ejecuta: tidalamp login")

    monkeypatch.setattr(auth, "restore", nothing)

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            screen = open_settings(application)
            await pilot.pause()
            screen.cursor = config_row(screen, "Modo offline")
            await pilot.press("enter")
            await wait_for(pilot, lambda: "sigue en modo offline" in application.status)
            assert application.offline
            assert "tidalamp login" in application.status
            # Still offline, so the way to log in is still offered.
            config_row(screen, "Iniciar sesión en TIDAL")

    asyncio.run(scenario())


def test_logging_in_from_the_settings_brings_tidal_back(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)
    config.set_option("offline", True)
    new = SimpleNamespace(name="nueva")
    link = SimpleNamespace(
        verification_uri_complete="link.tidal.com/ABCDE",
        user_code="ABCDE",
        expires_in=300.0,
        interval=0.0,
    )
    answers = iter([False, False, True])
    monkeypatch.setattr(auth, "start_login", lambda: (new, link))
    monkeypatch.setattr(auth, "finish_login", lambda session, link: next(answers))

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            screen = open_settings(application)
            await pilot.pause()
            screen.cursor = config_row(screen, "Iniciar sesión en TIDAL")
            await pilot.press("enter")
            await wait_for(pilot, lambda: not application.offline)
            assert application.session is new
            assert "iniciada" in application.status
            assert config.read_file(path)["offline"] is False
            with pytest.raises(AssertionError):
                config_row(screen, "Iniciar sesión en TIDAL")

    asyncio.run(scenario())


def test_the_login_window_shows_the_link_and_closes_without_waiting(monkeypatch):
    isolate_runtime(monkeypatch)
    link = SimpleNamespace(
        verification_uri_complete="link.tidal.com/ABCDE",
        user_code="ABCDE",
        expires_in=300.0,
        interval=0.0,
    )
    checks = []

    def pending(session, link):
        checks.append(1)
        return False

    monkeypatch.setattr(auth, "start_login", lambda: (object(), link))
    monkeypatch.setattr(auth, "finish_login", pending)

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.push_screen(LoginScreen())
            await wait_for(pilot, lambda: bool(checks))
            message = application.screen.query_one("#choice-message")
            text = "\n".join(
                message.render_line(y).text for y in range(message.size.height)
            )
            assert "https://link.tidal.com/ABCDE" in text
            assert "ABCDE" in text
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(application.screen, LoginScreen)
            assert application.offline

    asyncio.run(scenario())


# ------------------------------------------------- the link, past the mouse


def link_window(monkeypatch):
    link = SimpleNamespace(
        verification_uri_complete="link.tidal.com/ABCDE",
        user_code="ABCDE",
        expires_in=300.0,
        interval=0.0,
    )
    monkeypatch.setattr(auth, "start_login", lambda: (object(), link))
    monkeypatch.setattr(auth, "finish_login", lambda session, link: False)


def window_text(application) -> str:
    """The login window's message, or nothing while it is still mounting."""
    found = application.screen.query("#choice-message")
    if not found:
        return ""
    message = found.first()
    return "\n".join(message.render_line(y).text for y in range(message.size.height))


@pytest.mark.parametrize("how", ["enter", "click"])
def test_enter_or_a_click_opens_the_link_in_the_browser(monkeypatch, how):
    """The player owns the mouse, so the terminal's click on the URL never
    lands: the window opens it itself."""
    isolate_runtime(monkeypatch)
    link_window(monkeypatch)
    opened: list[str] = []
    monkeypatch.setattr(links, "open_url", lambda url: opened.append(url) or True)

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.push_screen(LoginScreen())
            await wait_for(pilot, lambda: "ABCDE" in window_text(application))
            if how == "enter":
                await pilot.press("enter")
            else:
                await pilot.click("#choice-message")
            await pilot.pause()
            assert opened == ["https://link.tidal.com/ABCDE"]
            assert "navegador" in window_text(application)

    asyncio.run(scenario())


def test_c_copies_the_link_and_falls_back_to_the_terminal(monkeypatch):
    isolate_runtime(monkeypatch)
    link_window(monkeypatch)
    monkeypatch.setattr(links, "copy_text", lambda text: False)

    async def scenario() -> None:
        application = offline_app()
        through_terminal: list[str] = []
        application.copy_to_clipboard = through_terminal.append  # type: ignore[method-assign]
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.push_screen(LoginScreen())
            await wait_for(pilot, lambda: "ABCDE" in window_text(application))
            await pilot.press("c")
            await pilot.pause()
            # No clipboard tool on the system: OSC 52, through the terminal.
            assert through_terminal == ["https://link.tidal.com/ABCDE"]
            assert "copiado" in window_text(application)

    asyncio.run(scenario())


def test_the_browser_is_opened_quietly_and_apart(monkeypatch):
    """`xdg-open` and the browser print to the terminal they inherit, which
    is the one the player is drawing on."""
    calls = []
    monkeypatch.setattr(links.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        links.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs))
    )
    assert links.open_url("https://x", platform="linux")
    ((args, kwargs),) = calls
    assert args == ["xdg-open", "https://x"]
    assert kwargs["stdout"] is kwargs["stderr"] is links.subprocess.DEVNULL
    assert kwargs["start_new_session"]


def test_with_nothing_to_open_it_with_it_says_so(monkeypatch):
    monkeypatch.setattr(links.shutil, "which", lambda name: None)
    assert links.open_url("https://x", platform="linux") is False


def test_the_clipboard_tool_follows_the_session(monkeypatch):
    monkeypatch.setattr(links.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert links._copiers("linux") == [["wl-copy"]]
    monkeypatch.delenv("WAYLAND_DISPLAY")
    monkeypatch.setenv("DISPLAY", ":0")
    assert links._copiers("linux")[0][0] == "xclip"
    assert links._copiers("win32") == [["clip"]]


def test_copying_tries_the_next_tool_when_one_fails(monkeypatch):
    monkeypatch.setattr(links, "_copiers", lambda platform: [["roto"], ["bueno"]])
    used = []

    def run(args, **kwargs):
        used.append(args[0])
        if args[0] == "roto":
            raise OSError("no está")

    monkeypatch.setattr(links.subprocess, "run", run)
    assert links.copy_text("https://x", platform="linux")
    assert used == ["roto", "bueno"]


def test_offline_asked_for_again_while_restoring_wins(monkeypatch, tmp_path):
    """Off, then on again before the session is back: the last word was
    offline, so the session that arrives waits in memory instead."""
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)
    real = SimpleNamespace(name="real")

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            connection = application.connection
            connection.restoring = True
            config.set_option("offline", True)
            connection._restored(real)  # type: ignore[arg-type]
            assert application.offline
            assert connection.kept is real
            assert not connection.restoring

    asyncio.run(scenario())


def test_a_click_beside_the_login_window_does_not_open_the_browser(monkeypatch):
    isolate_runtime(monkeypatch)
    link_window(monkeypatch)
    opened: list[str] = []
    monkeypatch.setattr(links, "open_url", lambda url: opened.append(url) or True)

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.push_screen(LoginScreen())
            await wait_for(pilot, lambda: "ABCDE" in window_text(application))
            await pilot.click(offset=(1, 1))
            await pilot.pause()
            assert opened == []

    asyncio.run(scenario())
