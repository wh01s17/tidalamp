"""The command line, driven through typer's runner."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tidalamp import cli, config, i18n
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
        raise MpvNotFound("mpv no está instalado (pacman -S mpv)")

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
