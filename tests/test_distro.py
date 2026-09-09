"""Reading /etc/os-release to name the right package manager."""

from __future__ import annotations

import pytest

from tidalamp import distro


def _os_release(monkeypatch, tmp_path, text: str | None):
    """Point the module at a file with ``text``, or at one that does not exist."""
    path = tmp_path / "os-release"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(distro, "OS_RELEASE", path)


@pytest.mark.parametrize(
    ("os_release", "expected"),
    [
        ("ID=arch\n", "sudo pacman -S mpv"),
        ("ID=debian\n", "sudo apt install mpv"),
        ("ID=fedora\nVERSION_ID=41\n", "sudo dnf install mpv"),
        (
            'ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n',
            "sudo zypper install mpv",
        ),
        ("ID=alpine\n", "sudo apk add mpv"),
    ],
)
def test_the_command_follows_the_distribution(
    monkeypatch, tmp_path, os_release, expected
):
    _os_release(monkeypatch, tmp_path, os_release)
    assert distro.install_command("mpv") == expected


@pytest.mark.parametrize(
    ("os_release", "expected"),
    [
        # A derivative names itself first and its parent in ID_LIKE. Neither
        # Mint nor Pop!_OS is in the table, and both must still say apt.
        ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', "sudo apt install cava"),
        ('ID=pop\nID_LIKE="ubuntu debian"\n', "sudo apt install cava"),
        ('ID=nobara\nID_LIKE="fedora"\n', "sudo dnf install cava"),
    ],
)
def test_a_derivative_falls_back_to_the_family_it_declares(
    monkeypatch, tmp_path, os_release, expected
):
    _os_release(monkeypatch, tmp_path, os_release)
    assert distro.install_command("cava") == expected


def test_ids_are_tried_in_order_of_closeness(monkeypatch, tmp_path):
    """ID wins over ID_LIKE: Ubuntu is apt through its own entry, not Debian's."""
    _os_release(monkeypatch, tmp_path, 'ID=arch\nID_LIKE="debian"\n')
    assert distro.install_command("mpv") == "sudo pacman -S mpv"


@pytest.mark.parametrize("os_release", ["ID=plan9\n", "", "nonsense without an equals\n"])
def test_an_unrecognised_system_gets_no_suggestion(monkeypatch, tmp_path, os_release):
    """Silence beats sending someone to a package manager they do not have."""
    _os_release(monkeypatch, tmp_path, os_release)
    assert distro.install_command("mpv") == ""


def test_a_missing_file_is_not_an_error(monkeypatch, tmp_path):
    _os_release(monkeypatch, tmp_path, None)
    assert distro.install_command("mpv") == ""


def test_the_message_drops_the_parenthetical_when_there_is_no_command(
    monkeypatch, tmp_path
):
    _os_release(monkeypatch, tmp_path, "ID=plan9\n")
    assert distro.missing("mpv") == "mpv no está instalado"


def test_the_message_carries_the_command_when_there_is_one(monkeypatch, tmp_path):
    _os_release(monkeypatch, tmp_path, "ID=fedora\n")
    assert distro.missing("mpv") == "mpv no está instalado (sudo dnf install mpv)"
