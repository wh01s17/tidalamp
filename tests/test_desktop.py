"""The launcher offered on the first start, so the menu can open tidalamp.

pipx installs a command and nothing else: until someone wrote a `.desktop`
file by hand, tidalamp was missing from the application menu.
"""

from __future__ import annotations

import pytest

from tidalamp import desktop


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A user data dir, an empty system one, and the switch that tests set off."""
    monkeypatch.delenv("TIDALAMP_NO_DESKTOP_ENTRY", raising=False)
    monkeypatch.setattr(desktop.sys, "platform", "linux")
    user, system = tmp_path / "share", tmp_path / "usr-share"
    (system / "applications").mkdir(parents=True)
    return {"dirs": [user, system], "marker": tmp_path / "state" / "desktop-entry"}


def offer(home, executable="/x/tidalamp"):
    return desktop.offer(home["dirs"], home["marker"], executable=executable)


def create(home, executable="/x/tidalamp", on_omarchy=False):
    return desktop.create(
        home["dirs"], home["marker"], executable=executable, on_omarchy=on_omarchy
    )


# ------------------------------------------------------------------ asking


def test_the_first_start_asks(home):
    assert offer(home) is True


def test_a_no_is_not_asked_again(home):
    desktop.decline(home["marker"])

    assert offer(home) is False


def test_a_launcher_deleted_by_hand_is_not_offered_again(home):
    """Deleting it is how someone takes tidalamp out of the menu."""
    create(home).unlink()

    assert offer(home) is False


def test_a_launcher_under_another_name_settles_it_without_asking(home):
    """`omarchy-tui-install` names the file after what was typed: TidalAmp.desktop."""
    own = home["dirs"][0] / "applications" / "TidalAmp.desktop"
    own.parent.mkdir(parents=True)
    own.write_text(
        "[Desktop Entry]\nExec=xdg-terminal-exec --app-id=TUI.tile -e "
        "/home/u/.local/bin/tidalamp tui\n"
    )

    assert offer(home) is False
    assert home["marker"].is_file()
    assert desktop.existing(home["dirs"]) == own


def test_the_packages_own_launcher_settles_it(home):
    (home["dirs"][1] / "applications" / "tidalamp.desktop").write_text(
        "[Desktop Entry]\nExec=tidalamp tui\n"
    )

    assert offer(home) is False


def test_another_app_that_mentions_tidal_does_not(home):
    (home["dirs"][1] / "applications" / "Tidal.desktop").write_text(
        "[Desktop Entry]\nExec=omarchy-launch-webapp https://tidal.com/\n"
    )

    assert offer(home) is True


def test_nothing_is_offered_without_a_command_to_run(home):
    assert offer(home, executable="") is False
    assert not home["marker"].exists()


def test_the_switch_and_other_systems_turn_it_off(home, monkeypatch):
    monkeypatch.setenv("TIDALAMP_NO_DESKTOP_ENTRY", "1")
    assert offer(home) is False
    monkeypatch.delenv("TIDALAMP_NO_DESKTOP_ENTRY")
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    assert offer(home) is False
    assert not home["marker"].exists()


# ---------------------------------------------------------------- creating


def test_creating_writes_the_launcher_its_icon_and_the_answer(home):
    written = create(home, executable="/home/u/.local/bin/tidalamp")

    user = home["dirs"][0]
    assert written == user / "applications" / "tidalamp.desktop"
    text = written.read_text()
    assert "Exec=/home/u/.local/bin/tidalamp tui\n" in text
    assert "Terminal=true\n" in text
    assert "Icon=tidalamp\n" in text
    assert (user / "icons/hicolor/scalable/apps/tidalamp.svg").read_text().startswith("<")
    assert home["marker"].is_file()


def test_on_omarchy_it_opens_in_omarchys_terminal_tiled(home):
    text = create(home, executable="/usr/bin/tidalamp", on_omarchy=True).read_text()

    assert "Exec=xdg-terminal-exec --app-id=TUI.tile -e /usr/bin/tidalamp tui\n" in text
    assert "Terminal=false\n" in text


def test_creating_after_a_no_still_works(home):
    """The settings window can create it later, whatever was answered then."""
    desktop.decline(home["marker"])

    assert create(home) is not None


def test_a_hidden_override_is_never_overwritten(home):
    hidden = home["dirs"][0] / "applications" / "tidalamp.desktop"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("[Desktop Entry]\nHidden=true\n")

    assert offer(home) is False
    assert create(home) is None
    assert hidden.read_text() == "[Desktop Entry]\nHidden=true\n"


def test_a_path_with_spaces_is_quoted_for_exec():
    text = desktop.entry("/home/a b/bin/tidalamp", on_omarchy=False)
    assert 'Exec="/home/a b/bin/tidalamp" tui\n' in text


def test_a_failure_to_write_does_not_stop_the_player(home, monkeypatch):
    def refuse(path, text):
        raise PermissionError("solo lectura")

    monkeypatch.setattr(desktop, "write_atomically", refuse)

    assert create(home) is None
    desktop.decline(home["marker"])


def test_user_launchers_are_every_entry_for_tidalamp_in_the_users_menu(tmp_path):
    """`omarchy-tui-install`'s `TidalAmp.desktop` too: left behind, a logout
    that took the data still found a launcher and never asked again."""
    applications = tmp_path / "applications"
    applications.mkdir()
    omarchy = applications / "TidalAmp.desktop"
    omarchy.write_text("[Desktop Entry]\nExec=xdg-terminal-exec -e /x/tidalamp tui\n")
    hidden = applications / "tidalamp.desktop"
    hidden.write_text("[Desktop Entry]\nHidden=true\n")
    (applications / "tidal.desktop").write_text("[Desktop Entry]\nExec=tidal-hifi\n")
    icon = tmp_path / "icons/hicolor/scalable/apps/tidalamp.svg"
    icon.parent.mkdir(parents=True)
    icon.write_text("<svg/>")

    assert desktop.user_launchers(tmp_path) == [omarchy, hidden, icon]


def test_no_menu_folder_is_no_launchers(tmp_path):
    assert desktop.user_launchers(tmp_path) == []
