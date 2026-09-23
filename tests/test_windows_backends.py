"""The Windows side that can be checked from any system: where the files go,
how a held file is replaced, which command installs mpv, where mpv.exe is
looked for, the UI language, and the stand-ins for what comes later.

The named pipe itself needs `_winapi` and is tested on Windows."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from conftest import linux_only

from tidalamp import config, i18n, player
from tidalamp.backends.windows import desktop as windows_desktop
from tidalamp.backends.windows import distro as windows_distro
from tidalamp.backends.windows import media as windows_media
from tidalamp.backends.windows import mpv as windows_mpv
from tidalamp.player import MpvNotFound

WINDOWS_ENV = {
    "APPDATA": r"C:\Users\u\AppData\Roaming",
    "LOCALAPPDATA": r"C:\Users\u\AppData\Local",
}


# ---------------------------------------------------------------- paths


def test_windows_keeps_the_config_roaming_and_the_rest_local():
    configured, cache, state = config._dirs(WINDOWS_ENV, "win32")
    assert configured == Path(WINDOWS_ENV["APPDATA"]) / "tidalamp"
    assert cache == Path(WINDOWS_ENV["LOCALAPPDATA"]) / "tidalamp" / "cache"
    assert state == Path(WINDOWS_ENV["LOCALAPPDATA"]) / "tidalamp" / "state"


def test_an_xdg_variable_wins_on_windows_too():
    configured, cache, _ = config._dirs({**WINDOWS_ENV, "XDG_CACHE_HOME": "/x"}, "win32")
    assert cache == Path("/x/tidalamp")
    assert configured == Path(WINDOWS_ENV["APPDATA"]) / "tidalamp"


def test_windows_without_appdata_falls_back_under_the_home():
    configured, _, state = config._dirs({}, "win32")
    assert configured == Path.home() / "AppData/Roaming/tidalamp"
    assert state == Path.home() / "AppData/Local/tidalamp/state"


def test_linux_paths_are_the_xdg_ones_they_always_were():
    assert config._dirs({}, "linux") == (
        Path.home() / ".config/tidalamp",
        Path.home() / ".cache/tidalamp",
        Path.home() / ".local/state/tidalamp",
    )
    assert config._dirs({"XDG_STATE_HOME": "/s"}, "linux")[2] == Path("/s/tidalamp")


# ------------------------------------------------------ replacing a file


def _held_for(monkeypatch, attempts: int) -> list[int]:
    """`os.replace` refuses ``attempts`` times, as while an antivirus scans."""
    calls: list[int] = []

    def replace(source, target):
        calls.append(1)
        if len(calls) <= attempts:
            raise PermissionError("in use")

    monkeypatch.setattr(config.os, "replace", replace)
    monkeypatch.setattr(config, "REPLACE_WAIT", 0)
    return calls


def test_a_file_held_for_a_moment_is_replaced_on_windows(monkeypatch):
    monkeypatch.setattr(config.sys, "platform", "win32")
    calls = _held_for(monkeypatch, 2)
    config._replace("new", Path("old"))
    assert len(calls) == 3


def test_a_file_held_for_good_still_fails_on_windows(monkeypatch):
    monkeypatch.setattr(config.sys, "platform", "win32")
    calls = _held_for(monkeypatch, 99)
    with pytest.raises(PermissionError):
        config._replace("new", Path("old"))
    assert len(calls) == config.REPLACE_TRIES


def test_linux_does_not_retry_a_refused_replace(monkeypatch):
    monkeypatch.setattr(config.sys, "platform", "linux")
    calls = _held_for(monkeypatch, 1)
    with pytest.raises(PermissionError):
        config._replace("new", Path("old"))
    assert len(calls) == 1


# --------------------------------------------------- installing mpv


def _managers(monkeypatch, *installed: str) -> None:
    monkeypatch.setattr(
        windows_distro.shutil,
        "which",
        lambda name: f"C:/bin/{name}.exe" if name in installed else None,
    )


@pytest.mark.parametrize(
    ("installed", "expected"),
    [
        (("winget", "scoop", "choco"), "winget install shinchiro.mpv"),
        (("scoop", "choco"), "scoop bucket add extras; scoop install extras/mpv"),
        (("choco",), "choco install mpv"),
    ],
)
def test_mpv_is_installed_with_the_first_manager_there_is(
    monkeypatch, installed, expected
):
    _managers(monkeypatch, *installed)
    assert windows_distro.install_command("mpv") == expected


def test_no_manager_drops_the_parenthetical(monkeypatch):
    _managers(monkeypatch)
    assert windows_distro.missing("mpv") == "mpv no está instalado"


def test_a_package_no_manager_is_known_for_is_not_guessed(monkeypatch):
    _managers(monkeypatch, "winget")
    assert windows_distro.install_command("cava") == ""


# ------------------------------------------------------- finding mpv.exe


def test_mpv_exe_on_the_path_comes_first(monkeypatch):
    monkeypatch.setattr(windows_mpv.shutil, "which", lambda name: rf"C:\bin\{name}")
    assert windows_mpv.find({}) == r"C:\bin\mpv.exe"


def test_it_asks_the_path_for_mpv_exe_never_the_com_wrapper(monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(windows_mpv.shutil, "which", lambda name: asked.append(name))
    windows_mpv.find({})
    assert asked == ["mpv.exe"]


def test_wingets_mpv_is_found_off_the_path(monkeypatch, tmp_path):
    """shinchiro.mpv installs to Program Files and leaves the PATH alone."""
    monkeypatch.setattr(windows_mpv.shutil, "which", lambda name: None)
    exe = tmp_path / "MPV Player" / "mpv.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    assert windows_mpv.find({"ProgramFiles": str(tmp_path)}) == str(exe)


def test_scoops_shim_is_found_off_the_path(monkeypatch, tmp_path):
    monkeypatch.setattr(windows_mpv.shutil, "which", lambda name: None)
    exe = tmp_path / "scoop" / "shims" / "mpv.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert windows_mpv.find({"USERPROFILE": str(tmp_path)}) == str(exe)


def test_nowhere_is_none(monkeypatch, tmp_path):
    monkeypatch.setattr(windows_mpv.shutil, "which", lambda name: None)
    assert windows_mpv.find({"ProgramFiles": str(tmp_path)}) is None


# ---------------------------------------------------- the mpv_path setting


def test_mpv_path_is_run_as_given(monkeypatch, tmp_path):
    exe = tmp_path / "mpv"
    exe.write_bytes(b"")
    monkeypatch.setattr(config, "MPV_PATH", str(exe))
    assert player._find_mpv() == [str(exe)]


def test_an_mpv_path_to_nothing_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MPV_PATH", str(tmp_path / "missing.exe"))
    with pytest.raises(MpvNotFound, match="mpv_path no apunta a un ejecutable"):
        player._find_mpv()


@linux_only
def test_linux_without_the_setting_runs_plain_mpv(monkeypatch):
    monkeypatch.setattr(config, "MPV_PATH", "")
    monkeypatch.setattr(player.shutil, "which", lambda name: "/usr/bin/mpv")
    assert player._find_mpv() == ["mpv"]


# ------------------------------------------------------------- language


@pytest.mark.parametrize(
    ("lcid", "expected"),
    [(0x0409, "en_US"), (0x0809, "en_GB"), (0x0C0A, "es_ES"), (0x080A, "es_MX")],
)
def test_a_windows_language_id_names_its_locale(lcid, expected):
    assert i18n.from_lcid(lcid) == expected


def test_an_unknown_language_id_is_no_language():
    assert i18n.from_lcid(0) == ""


def test_english_windows_gets_the_english_interface(monkeypatch):
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(i18n, "_system_language", lambda: "en_US")
    assert i18n._language() == "en"


# ------------------------------------------------- what is still to come


def test_the_media_stand_in_starts_names_nothing_and_is_no_second_instance():
    service = windows_media.MprisService(object())
    assert asyncio.run(service.start()) == ""
    assert service.shared is False
    service.publish()
    service.publish_tracks()
    service.seeked(1.0)
    asyncio.run(service.stop())


def test_the_start_menu_is_never_offered_yet():
    assert windows_desktop.offer() is False
    assert windows_desktop.create() is None
    assert windows_desktop.existing([]) is None
    assert windows_desktop.user_launchers() == []
