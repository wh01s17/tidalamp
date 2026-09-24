"""The command line, driven through typer's runner."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tidalamp import about, cli, config, i18n
from tidalamp.auth import NotLoggedIn
from tidalamp.player import MpvNotFound

runner = CliRunner()


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.toml")
    return tmp_path / "config.toml"


def test_config_creates_the_template_and_prints_the_settings(xdg):
    result = runner.invoke(cli.app, ["config"])

    assert result.exit_code == 0
    assert str(xdg) in result.output
    assert "quality" in result.output and config.DEFAULT_QUALITY in result.output
    assert "Teclas: todas por defecto." in result.output
    assert xdg.exists()


def test_config_reports_changed_keys(xdg, monkeypatch):
    monkeypatch.setitem(config.KEYS, "play", "p")

    result = runner.invoke(cli.app, ["config"])

    assert "Teclas cambiadas:" in result.output
    assert "play" in result.output and "por defecto x" in result.output


def test_config_warns_about_actions_that_do_not_exist(xdg, monkeypatch):
    """Otherwise a typo in [keys] binds nothing and says nothing."""
    monkeypatch.setitem(config.KEYS, "reproducir", "p")

    result = runner.invoke(cli.app, ["config"])

    assert "no existen y se ignoran: reproducir" in result.output


def test_config_output_and_new_template_follow_the_selected_language(xdg):
    i18n.use("en")

    result = runner.invoke(cli.app, ["config"])

    assert result.exit_code == 0
    assert "Settings in use:" in result.output
    assert "Keys: all defaults." in result.output
    assert xdg.read_text(encoding="utf-8").startswith("# tidalamp configuration.")


def test_tui_without_a_session_says_to_log_in(monkeypatch):
    def no_session():
        raise NotLoggedIn("No hay sesión guardada. Ejecuta: tidalamp login")

    monkeypatch.setattr(cli, "load_session", no_session)

    result = runner.invoke(cli.app, ["tui"])

    assert result.exit_code == 1
    assert "No hay sesión guardada" in result.output


def test_tui_without_mpv_says_so_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(cli, "load_session", lambda: object())

    def no_mpv():
        raise MpvNotFound("mpv no está instalado (sudo dnf install mpv)")

    monkeypatch.setattr(cli, "Mpv", no_mpv)

    result = runner.invoke(cli.app, ["tui"])

    assert result.exit_code == 1
    assert "mpv no está instalado" in result.output


def test_the_bare_command_launches_the_tui(monkeypatch):
    launched = []
    monkeypatch.setattr(cli, "tui", lambda: launched.append(True))

    result = runner.invoke(cli.app, [])

    assert result.exit_code == 0
    assert launched == [True]


def test_help_does_not_launch_the_tui(monkeypatch):
    monkeypatch.setattr(cli, "tui", lambda: pytest.fail("abrió la TUI"))

    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "Commands" in result.output


@pytest.mark.parametrize("flag", ["--version", "-v"])
def test_the_version_flag_prints_the_version_without_opening_the_tui(flag, monkeypatch):
    """It is what a bug report is asked to quote, so it must not need a
    session, mpv, or a terminal the player would fit in."""
    monkeypatch.setattr(cli, "tui", lambda: pytest.fail("abrió la TUI"))
    monkeypatch.setattr(cli, "load_session", lambda: pytest.fail("pidió sesión"))

    result = runner.invoke(cli.app, [flag])

    assert result.exit_code == 0
    assert result.output.strip() == f"tidalamp {about.version()}"


def test_search_prints_ids_for_scripts(monkeypatch):
    class FakeSession:
        def search(self, query, limit=10):
            artist = type("A", (), {"name": "TOOL"})()
            track = type("T", (), {"id": 42, "name": "Schism", "artist": artist})()
            return {"tracks": [track]}

    monkeypatch.setattr(cli, "load_session", lambda: FakeSession())

    result = runner.invoke(cli.app, ["search", "schism"])

    assert result.exit_code == 0
    assert "42  TOOL - Schism" in result.output


def test_tui_offers_the_launcher_once_it_can_play(monkeypatch):
    """Only after the session and mpv are there: a launcher that opens straight
    into «log in first» is not worth offering."""
    from tidalamp import desktop

    offered = []
    monkeypatch.setattr(cli, "load_session", lambda: object())
    monkeypatch.setattr(cli, "Mpv", lambda: type("M", (), {"close": lambda self: None})())
    monkeypatch.setattr(desktop, "offer", lambda: True)
    monkeypatch.setattr("tidalamp.app.TidalAmp.__init__", lambda self, s, m: None)
    monkeypatch.setattr(
        "tidalamp.app.TidalAmp.run", lambda self: offered.append(self.offer_launcher)
    )

    result = runner.invoke(cli.app, ["tui"])

    assert result.exit_code == 0, result.output
    assert offered == [True]


def test_tui_without_a_session_offers_no_launcher(monkeypatch):
    from tidalamp import desktop

    def no_session():
        raise NotLoggedIn("No hay sesión guardada. Ejecuta: tidalamp login")

    monkeypatch.setattr(cli, "load_session", no_session)
    monkeypatch.setattr(desktop, "offer", lambda: pytest.fail("ofreció el lanzador"))

    assert runner.invoke(cli.app, ["tui"]).exit_code == 1


# ------------------------------------------------ installing with winget


class _Console:
    """A stdin that is a terminal, as it is when someone runs the .exe."""

    def isatty(self) -> bool:
        return True


@pytest.fixture
def winget(tmp_path, monkeypatch):
    """winget present, nothing installed, every answer yes: what ran is
    recorded instead of running."""
    from tidalamp import spectrum
    from tidalamp.backends.windows import mpv as windows_mpv
    from tidalamp.backends.windows import winget as winget_module

    installed: list[str] = []
    monkeypatch.setattr(cli.sys, "stdin", _Console())
    monkeypatch.setattr(winget_module, "available", lambda: True)
    monkeypatch.setattr(winget_module, "install", installed.append)
    monkeypatch.setattr(winget_module, "OFFERED", tmp_path / "offered")
    monkeypatch.setattr(windows_mpv, "find", lambda: None)
    monkeypatch.setattr(spectrum, "available", lambda: False)
    monkeypatch.setattr(config, "MPV_PATH", "")
    monkeypatch.setattr(cli.typer, "confirm", lambda *a, **k: True)
    return installed


def test_a_missing_mpv_is_installed_on_a_yes_instead_of_ending_in_an_error(winget):
    """The .exe used to stop at «mpv is not installed (winget install …)» and
    leave the typing to the user."""
    cli._offer_installs("win32")
    assert winget == ["mpv", "cava"]


def test_mpv_already_there_is_not_offered(winget, monkeypatch):
    from tidalamp.backends.windows import mpv as windows_mpv

    monkeypatch.setattr(windows_mpv, "find", lambda: r"C:\mpv\mpv.exe")
    cli._offer_installs("win32")
    assert winget == ["cava"]


def test_a_no_to_cava_is_not_asked_again(winget, monkeypatch):
    asked: list[str] = []

    def no(text, **_kwargs):
        asked.append(text)
        return False

    monkeypatch.setattr(cli.typer, "confirm", no)
    cli._offer_installs("win32")
    cli._offer_installs("win32")
    assert winget == []
    assert len(asked) == 3, "mpv twice, since nothing plays without it; cava once"


def test_cava_is_offered_once_even_when_the_yes_did_not_install_it(winget):
    """A yes whose cava was then not found (it was looked for in the wrong
    folder) brought the question back on every start."""
    cli._offer_installs("win32")
    cli._offer_installs("win32")
    assert winget == ["mpv", "cava", "mpv"]


def test_nothing_is_asked_without_a_console_or_off_windows(winget, monkeypatch):
    cli._offer_installs("linux")
    monkeypatch.setattr(cli.sys, "stdin", None)
    cli._offer_installs("win32")
    assert winget == []
