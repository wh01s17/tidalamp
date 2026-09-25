"""The Windows side that can be checked from any system: where the files go,
how a held file is replaced, which command installs mpv, where mpv.exe is
looked for, the UI language, and the stand-ins for what comes later.

The named pipe itself needs `_winapi` and is tested on Windows."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import linux_only, windows_only

from tidalamp import config, i18n, player
from tidalamp.backends.windows import desktop as windows_desktop
from tidalamp.backends.windows import distro as windows_distro
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
    _managers(monkeypatch, "scoop")
    assert windows_distro.install_command("cava") == ""


def test_cava_comes_from_winget(monkeypatch):
    _managers(monkeypatch, "winget", "scoop")
    assert windows_distro.install_command("cava") == "winget install karlstav.cava"


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


# ------------------------------------------------------ the terminal (F3)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        # Windows Terminal sets no TERM. Half blocks until sixel has been seen
        # working there: sixel sent to a terminal that cannot read it fills
        # the screen with garbage, and half blocks never fail.
        ({"WT_SESSION": "c0ffee"}, "blocks"),
        # conhost sets nothing at all.
        ({}, "blocks"),
        # WezTerm says who it is on Windows too, and speaks kitty graphics.
        ({"TERM_PROGRAM": "WezTerm"}, "kitty"),
        # Asked for, sixel is honoured anywhere.
        ({"WT_SESSION": "c0ffee", "TIDALAMP_ART": "sixel"}, "sixel"),
    ],
)
def test_the_cover_on_windows_terminals(env, expected):
    from tidalamp import artwork

    assert artwork.detect_protocol(env=env) == artwork.Protocol(expected)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        # Cascadia may or may not carry the sextants: a box of tofu per cell
        # is worse than the quadrants every font has.
        ({"WT_SESSION": "c0ffee"}, False),
        ({"WT_SESSION": "c0ffee", "TIDALAMP_SEXTANTS": "1"}, True),
        # WezTerm draws them itself, whatever the font.
        ({"TERM_PROGRAM": "WezTerm"}, True),
    ],
)
def test_sextants_on_windows_terminals(env, expected):
    from tidalamp import artwork

    assert artwork.draws_sextants(env=env) is expected


def test_cava_listens_through_wasapi_loopback_on_windows():
    from tidalamp import spectrum

    assert spectrum.input_method("win32") == ""
    assert spectrum.input_method("linux") == "pulse"


def test_cava_on_windows_is_not_told_which_input_to_use(monkeypatch, tmp_path):
    """cava 1.0.0 refuses a config that names one («on windows changing input
    method is not supported») and exits: the spectrum never ran on Windows,
    and the analyser stayed on the RMS meter (2026-09-24)."""
    from tidalamp import spectrum

    monkeypatch.setattr(spectrum, "CACHE_DIR", tmp_path)
    windows = spectrum.Cava._write_config(8, 30, "", "auto").read_text(encoding="utf-8")
    assert "method = raw" in windows, "the output keeps its own"
    assert "[input]\nsource = auto\n" in windows
    linux = spectrum.Cava._write_config(8, 30, "pulse", "auto").read_text(
        encoding="utf-8"
    )
    assert "[input]\nmethod = pulse\nsource = auto\n" in linux


def test_the_palette_note_does_not_promise_omarchy_on_windows(monkeypatch):
    from tidalamp.screens import config_window

    monkeypatch.setattr(config_window.sys, "platform", "win32")
    assert "Omarchy sólo existe en Linux" in config_window._palette_note()


# --------------------------------------------------- audio and launcher (F4)


class ReportingMpv:
    """What the Windows audio backend asks mpv, answered from a table."""

    def __init__(self, **properties) -> None:
        self.properties = properties

    def get(self, name: str):
        return self.properties.get(name)


def test_the_output_is_what_mpv_opened(monkeypatch):
    from tidalamp.backends.windows import audio as windows_audio

    monkeypatch.setattr(windows_audio, "_player", None)
    windows_audio.use_player(
        ReportingMpv(
            **{
                "audio-device": "wasapi/{d3b}",
                "audio-out-params": {"samplerate": 96000, "format": "s32"},
                "audio-device-list": [
                    {"name": "auto", "description": "Autoselect device"},
                    {"name": "wasapi/{d3b}", "description": "FiiO BTR15"},
                ],
            }
        )
    )
    found = windows_audio.sink()
    assert (found.name, found.description, found.rate, found.sample_format) == (
        "wasapi/{d3b}",
        "FiiO BTR15",
        96000,
        "s32",
    )


def test_before_mpv_opens_an_output_there_is_nothing_to_say(monkeypatch):
    from tidalamp.backends.windows import audio as windows_audio

    monkeypatch.setattr(windows_audio, "_player", None)
    assert windows_audio.sink() == windows_audio.Sink()
    windows_audio.use_player(ReportingMpv())
    assert windows_audio.sink().rate == 0


def test_there_is_never_a_rate_to_force_on_windows():
    from tidalamp.backends.windows import audio as windows_audio

    output = windows_audio.Sink(name="wasapi/{d3b}", rate=48000)
    assert windows_audio.MANAGES_RATES is False
    assert windows_audio.rate_to_force(output, 96000, (96000,), (96000,), 1) == 0
    assert windows_audio.force_rate(96000) is False
    assert windows_audio.allowed_rates() == ()


def test_exclusive_mode_is_asked_of_mpv_on_windows_only(monkeypatch):
    monkeypatch.setattr(config, "EXCLUSIVE", True)
    monkeypatch.setattr(player.sys, "platform", "win32")
    assert player._exclusive_option() == ["--audio-exclusive=yes"]
    monkeypatch.setattr(player.sys, "platform", "linux")
    assert player._exclusive_option() == []


def test_exclusive_mode_is_off_until_asked_for(monkeypatch):
    monkeypatch.setattr(player.sys, "platform", "win32")
    monkeypatch.setattr(config, "EXCLUSIVE", False)
    assert player._exclusive_option() == []


# ------------------------------------------------------- the output device

_OUTPUTS = [
    {"name": "auto", "description": "Autoselect device"},
    {"name": "wasapi/{jbl}", "description": "Altavoces (JBL Charge 3 Stereo)"},
    {"name": "wasapi/{fiio}", "description": "FiiO BTR15"},
    {"name": "openal", "description": "Default (openal)"},
]


def test_auto_says_which_device_it_is_playing_to(monkeypatch):
    """mpv only says «Autoselect device»; with exclusive mode on, the user
    has to know which output tidalamp is taking whole."""
    from tidalamp.backends.windows import audio as windows_audio

    monkeypatch.setattr(
        windows_audio, "_endpoints", lambda: windows_audio.Endpoints("{jbl}", ["{jbl}"])
    )
    windows_audio.use_player(
        ReportingMpv(**{"audio-device": "auto", "audio-device-list": _OUTPUTS})
    )
    found = windows_audio.sink()
    assert (found.name, found.description) == (
        "auto",
        "Altavoces (JBL Charge 3 Stereo)",
    )


def test_a_device_muted_in_windows_is_said_in_shared_mode_only(monkeypatch):
    """A FiiO muted in Windows played in silence with the clock running, and
    loud in exclusive mode, which goes around the mixer and its mute."""
    from tidalamp.backends.windows import audio as windows_audio

    monkeypatch.setattr(
        windows_audio,
        "_endpoints",
        lambda: windows_audio.Endpoints(
            "{jbl}", ["{jbl}", "{fiio}"], frozenset({"{fiio}"})
        ),
    )
    shown = {"audio-device": "wasapi/{fiio}", "audio-device-list": _OUTPUTS}
    windows_audio.use_player(ReportingMpv(**shown, **{"audio-exclusive": False}))
    assert windows_audio.sink().muted
    windows_audio.use_player(ReportingMpv(**shown, **{"audio-exclusive": True}))
    assert not windows_audio.sink().muted
    on_auto = {"audio-device": "auto", "audio-device-list": _OUTPUTS}
    windows_audio.use_player(ReportingMpv(**on_auto, **{"audio-exclusive": False}))
    assert not windows_audio.sink().muted, "the default, the JBL, is not muted"


def test_only_wasapi_outputs_are_offered(monkeypatch):
    """Exclusive mode is WASAPI's; openal is another road to the same devices."""
    from tidalamp.backends.windows import audio as windows_audio

    monkeypatch.setattr(windows_audio, "_player", None)
    assert windows_audio.devices() == []
    windows_audio.use_player(ReportingMpv(**{"audio-device-list": _OUTPUTS}))
    assert windows_audio.devices() == [
        ("wasapi/{jbl}", "Altavoces (JBL Charge 3 Stereo)"),
        ("wasapi/{fiio}", "FiiO BTR15"),
    ]


def test_a_device_is_connected_when_windows_lists_it_active(monkeypatch):
    from tidalamp.backends.windows import audio as windows_audio

    monkeypatch.setattr(
        windows_audio, "_endpoints", lambda: windows_audio.Endpoints("{jbl}", ["{jbl}"])
    )
    assert windows_audio.system_default() == "wasapi/{jbl}"
    assert windows_audio.connected("wasapi/{JBL}")
    assert not windows_audio.connected("wasapi/{fiio}")


def test_a_windows_that_cannot_be_asked_takes_no_choice_away(monkeypatch):
    from tidalamp.backends.windows import audio as windows_audio

    monkeypatch.setattr(windows_audio, "_endpoints", lambda: None)
    assert windows_audio.system_default() == ""
    assert windows_audio.connected("wasapi/{fiio}")


def test_the_device_is_asked_of_mpv_on_windows_only(monkeypatch):
    from tidalamp.backends.windows import audio as windows_audio

    monkeypatch.setattr(windows_audio, "connected", lambda name: True)
    monkeypatch.setattr(config, "AUDIO_DEVICE", "wasapi/{fiio}")
    monkeypatch.setattr(player.sys, "platform", "win32")
    assert player._device_option() == ["--audio-device=wasapi/{fiio}"]
    monkeypatch.setattr(player.sys, "platform", "linux")
    assert player._device_option() == []


def test_auto_leaves_the_device_to_mpv(monkeypatch):
    monkeypatch.setattr(player.sys, "platform", "win32")
    monkeypatch.setattr(config, "AUDIO_DEVICE", "auto")
    assert player._device_option() == []


def test_a_device_switched_off_plays_through_the_default(monkeypatch):
    """Asked for a device that is not there, mpv opens nothing and plays in
    silence («Could not open/initialize audio device -> no sound»)."""
    from tidalamp.backends.windows import audio as windows_audio

    monkeypatch.setattr(windows_audio, "connected", lambda name: False)
    monkeypatch.setattr(config, "AUDIO_DEVICE", "wasapi/{jbl}")
    monkeypatch.setattr(player.sys, "platform", "win32")
    assert player._device_option() == []


@windows_only
def test_windows_names_its_default_output_the_way_mpv_does():
    from tidalamp.backends.windows import audio as windows_audio

    found = windows_audio._endpoints()
    assert found is not None
    default, active, silent = found
    assert silent <= set(active)
    if not active:
        pytest.skip("no audio output on this machine")
    assert all(guid.startswith("{") and guid.endswith("}") for guid in active)
    assert default in active


def test_the_session_is_left_to_the_acl_on_windows(monkeypatch, tmp_path):
    from tidalamp import auth

    monkeypatch.setattr(auth.sys, "platform", "win32")
    monkeypatch.setattr(auth.os, "chmod", lambda *a: pytest.fail("chmod en Windows"))
    auth._tighten(tmp_path / "session.json")


@pytest.fixture
def start_menu(monkeypatch, tmp_path):
    """A Start menu of the test's own, with the launcher allowed to be offered."""
    monkeypatch.setattr(windows_desktop.sys, "platform", "win32")
    monkeypatch.delenv("TIDALAMP_NO_DESKTOP_ENTRY", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))
    # No Windows Terminal unless a test says so; and never the real `which`,
    # which takes its Windows path once sys.platform says win32.
    monkeypatch.setattr(windows_desktop.shutil, "which", lambda name: None)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.setattr(windows_desktop, "_desktop_folder", lambda: desktop)
    runs: list[dict] = []

    def run(argv, **kwargs):
        runs.append({"argv": argv, "env": kwargs["env"]})
        Path(kwargs["env"]["TIDALAMP_LNK"]).write_bytes(b"L\x00\x00\x00")

    monkeypatch.setattr(windows_desktop.subprocess, "run", run)
    return {
        "marker": tmp_path / "state" / "desktop-entry",
        "runs": runs,
        "desktop": desktop,
    }


def test_the_shortcut_is_offered_once(start_menu):
    marker = start_menu["marker"]
    assert windows_desktop.offer(marker=marker, executable=r"C:\bin\tidalamp.exe")
    windows_desktop.decline(marker)
    assert not windows_desktop.offer(marker=marker, executable=r"C:\bin\tidalamp.exe")


def test_a_shortcut_already_there_settles_it(start_menu):
    menu = windows_desktop.data_dirs()[1]
    menu.mkdir(parents=True)
    (menu / "tidalamp.LNK").write_bytes(b"")
    marker = start_menu["marker"]
    assert not windows_desktop.offer(marker=marker, executable=r"C:\bin\tidalamp.exe")
    assert marker.exists()


def test_the_shortcut_opens_windows_terminal_when_there_is_one(start_menu, monkeypatch):
    monkeypatch.setattr(
        windows_desktop.shutil, "which", lambda name: r"C:\WindowsApps\wt.exe"
    )
    made = windows_desktop.create(
        marker=start_menu["marker"], executable=r"C:\Program Files\tidalamp.exe"
    )
    env = start_menu["runs"][0]["env"]
    assert made == windows_desktop.data_dirs()[0] / "TidalAmp.lnk"
    assert env["TIDALAMP_LNK_TARGET"] == r"C:\WindowsApps\wt.exe"
    assert env["TIDALAMP_LNK_ARGUMENTS"] == r'"C:\Program Files\tidalamp.exe" tui'
    assert env["TIDALAMP_LNK_ICON"].endswith("tidalamp.ico")


def test_without_windows_terminal_the_shortcut_runs_tidalamp_itself(
    start_menu, monkeypatch
):
    monkeypatch.setattr(windows_desktop.shutil, "which", lambda name: None)
    windows_desktop.create(marker=start_menu["marker"], executable=r"C:\t\tidalamp.exe")
    env = start_menu["runs"][0]["env"]
    assert (env["TIDALAMP_LNK_TARGET"], env["TIDALAMP_LNK_ARGUMENTS"]) == (
        r"C:\t\tidalamp.exe",
        "tui",
    )


def test_no_value_ever_reaches_powershell_as_code(start_menu, monkeypatch):
    """The script is fixed text; paths arrive through the environment."""
    monkeypatch.setattr(windows_desktop.shutil, "which", lambda name: None)
    sneaky = r"C:\it's\$(evil)\tidalamp.exe"
    windows_desktop.create(marker=start_menu["marker"], executable=sneaky)
    argv = start_menu["runs"][0]["argv"]
    assert argv[-1] == windows_desktop._SCRIPT
    assert not any(sneaky in part for part in argv)


def test_a_shortcut_that_cannot_be_made_does_not_stop_the_player(start_menu, monkeypatch):
    def fails(argv, **kwargs):
        raise windows_desktop.subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(windows_desktop.subprocess, "run", fails)
    marker = start_menu["marker"]
    assert windows_desktop.create(marker=marker, executable=r"C:\t\tidalamp.exe") is None
    assert not marker.exists()


def test_a_logout_that_takes_the_data_takes_both_shortcuts(start_menu, monkeypatch):
    monkeypatch.setattr(windows_desktop.shutil, "which", lambda name: None)
    made = windows_desktop.create(
        marker=start_menu["marker"], executable=r"C:\t\tidalamp.exe"
    )
    assert windows_desktop.user_launchers() == [
        made,
        start_menu["desktop"] / "TidalAmp.lnk",
    ]


def test_a_yes_puts_the_same_shortcut_on_the_desktop_too(start_menu, monkeypatch):
    """Where a Windows user looks for what they just installed."""
    monkeypatch.setattr(
        windows_desktop.shutil, "which", lambda name: r"C:\WindowsApps\wt.exe"
    )
    made = windows_desktop.create(
        marker=start_menu["marker"], executable=r"C:\t\tidalamp.exe"
    )
    menu, desktop = (run["env"] for run in start_menu["runs"])
    assert made == windows_desktop.data_dirs()[0] / "TidalAmp.lnk"
    assert desktop["TIDALAMP_LNK"] == str(start_menu["desktop"] / "TidalAmp.lnk")
    for key in ("TIDALAMP_LNK_TARGET", "TIDALAMP_LNK_ARGUMENTS", "TIDALAMP_LNK_ICON"):
        assert desktop[key] == menu[key]


def test_a_shortcut_already_on_the_desktop_is_left_alone(start_menu):
    (start_menu["desktop"] / "tidalamp.LNK").write_bytes(b"mine")
    windows_desktop.create(marker=start_menu["marker"], executable=r"C:\t\tidalamp.exe")
    assert len(start_menu["runs"]) == 1
    assert (start_menu["desktop"] / "tidalamp.LNK").read_bytes() == b"mine"


def test_a_desktop_that_refuses_the_shortcut_keeps_the_menus(start_menu, monkeypatch):
    """The Start menu's is the one that counts: a yes is still a yes."""
    desktop_link = str(start_menu["desktop"] / "TidalAmp.lnk")

    def run(argv, **kwargs):
        if kwargs["env"]["TIDALAMP_LNK"] == desktop_link:
            raise windows_desktop.subprocess.CalledProcessError(1, argv)
        Path(kwargs["env"]["TIDALAMP_LNK"]).write_bytes(b"L\x00\x00\x00")

    monkeypatch.setattr(windows_desktop.subprocess, "run", run)
    marker = start_menu["marker"]
    made = windows_desktop.create(marker=marker, executable=r"C:\t\tidalamp.exe")
    assert made == windows_desktop.data_dirs()[0] / "TidalAmp.lnk"
    assert marker.exists()


def test_without_a_desktop_to_find_only_the_menu_gets_one(start_menu, monkeypatch):
    monkeypatch.setattr(windows_desktop, "_desktop_folder", lambda: None)
    made = windows_desktop.create(
        marker=start_menu["marker"], executable=r"C:\t\tidalamp.exe"
    )
    assert made is not None
    assert len(start_menu["runs"]) == 1


def test_only_windows_speaks_of_the_desktop():
    from tidalamp.backends.linux import desktop as linux_desktop

    assert "ESCRITORIO" in windows_desktop.question()
    assert "escritorio" in windows_desktop.created()
    assert linux_desktop.question() == "¿AÑADIR TIDALAMP AL MENÚ DE APLICACIONES?"
    assert linux_desktop.created() == "tidalamp ya está en el menú de aplicaciones"
    assert windows_desktop.setting() == (
        "Accesos directos",
        "añade tidalamp al menú Inicio y al escritorio",
    )
    assert linux_desktop.setting() == (
        "Acceso directo en el menú",
        "añade tidalamp al menú de aplicaciones",
    )
    # The logout's «borrar también los datos» takes both, and says so.
    assert "del menú Inicio y del escritorio" in windows_desktop.data_note()
    assert linux_desktop.data_note().endswith("y el acceso directo del menú.")


@windows_only
def test_the_desktop_is_asked_of_the_shell():
    """OneDrive can move it out of the profile, so it is not guessed."""
    found = windows_desktop._desktop_folder()
    assert found is not None
    assert found.is_dir()


# ---------------------------------------------------------------- winget


def test_winget_installs_the_exact_ids_distro_names():
    from tidalamp.backends.windows import winget

    for package, identifier in winget.IDS.items():
        call = winget.command(package)
        assert call[:4] == ["winget", "install", "--id", identifier]
        assert "--exact" in call
        assert identifier in windows_distro._COMMANDS["winget"][package]


def test_winget_install_answers_by_exit_code_and_survives_no_winget():
    import subprocess

    from tidalamp.backends.windows import winget

    def ran(code):
        return lambda args: subprocess.CompletedProcess(args, code)

    def gone(args):
        raise FileNotFoundError(args[0])

    assert winget.install("mpv", run=ran(0))
    assert not winget.install("mpv", run=ran(1))
    assert not winget.install("mpv", run=gone)


def test_cava_is_found_where_its_installer_put_it_although_the_path_is_stale(
    tmp_path,
):
    """winget's cava installs to %LOCALAPPDATA%\\cava and adds it to the PATH of
    processes started later. Looked for only in WinGet\\Links, it was never
    found, and the offer to install it came back on every start."""
    from tidalamp.backends.windows import cava

    env = {"LOCALAPPDATA": str(tmp_path)}
    assert cava.find(env) is None
    (tmp_path / "cava").mkdir()
    (tmp_path / "cava" / "cava.exe").write_bytes(b"")
    assert cava.find(env) == str(tmp_path / "cava" / "cava.exe")
    assert cava.find({}) is None


def test_a_portable_cava_in_winget_links_is_found_too(tmp_path):
    from tidalamp.backends.windows import cava

    links = tmp_path / "Microsoft/WinGet/Links"
    links.mkdir(parents=True)
    (links / "cava.exe").write_bytes(b"")
    assert cava.find({"LOCALAPPDATA": str(tmp_path)}) == str(links / "cava.exe")


def test_an_offered_package_is_remembered_alone(tmp_path):
    from tidalamp.backends.windows import winget

    marker = tmp_path / "state" / "offered"
    assert not winget.offered("cava", marker)
    winget.mark_offered("cava", marker)
    winget.mark_offered("cava", marker)
    assert winget.offered("cava", marker)
    assert not winget.offered("mpv", marker)
    assert marker.read_text(encoding="utf-8") == "cava\n"


# --------------------------------------------------- mpv's own media controls


def test_mpv_is_asked_to_leave_the_media_keys_to_tidalamp(monkeypatch):
    """mpv registered a media session of its own and took the keys: next
    and previous went to its playlist, which holds one track, and did
    nothing (mpv 0.41, 2026-09-24)."""
    monkeypatch.setattr(windows_mpv, "_knows", lambda executable, option: True)
    monkeypatch.setattr(player.sys, "platform", "win32")
    assert player._media_controls_option([r"C:\mpv\mpv.exe"]) == ["--media-controls=no"]
    monkeypatch.setattr(player.sys, "platform", "linux")
    assert player._media_controls_option(["mpv"]) == []


def test_an_mpv_without_the_option_is_not_handed_it(monkeypatch):
    """An option mpv does not know is fatal: it would not start at all."""
    monkeypatch.setattr(windows_mpv, "_knows", lambda executable, option: False)
    assert windows_mpv.media_controls_off((r"C:\mpv\mpv.exe",)) == []


@pytest.mark.parametrize(
    ("listed", "known"),
    [
        (" --media-controls                 Flag (default: yes)\n", True),
        (" --media-controls-extra           Flag\n --mute  Flag\n", False),
        ("", False),
    ],
)
def test_the_option_is_read_off_mpvs_own_list(monkeypatch, listed, known):
    class Done:
        stdout = listed

    windows_mpv._knows.cache_clear()
    monkeypatch.setattr(windows_mpv.subprocess, "run", lambda *a, **k: Done())
    assert windows_mpv._knows(("mpv.exe",), "--media-controls") is known
    windows_mpv._knows.cache_clear()


def test_an_mpv_that_cannot_be_asked_gets_no_extra_option(monkeypatch):
    def fails(*args, **kwargs):
        raise OSError("no such file")

    windows_mpv._knows.cache_clear()
    monkeypatch.setattr(windows_mpv.subprocess, "run", fails)
    assert windows_mpv._knows(("mpv.exe",), "--media-controls") is False
    windows_mpv._knows.cache_clear()
