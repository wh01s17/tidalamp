"""What the app says about the desktop's media integration when it starts:
nothing when it got the name, which name when another tidalamp had it, and
why when there is none. The backend is a double: the app only reads `start()`
and `shared`, whatever the system."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime, settle

from tidalamp.app import TidalAmp

# Taken before any test can patch it: isolate_runtime switches it off.
START_MEDIA = TidalAmp._start_mpris


class FakeMedia:
    def __init__(self, name: str = "", shared: bool = False, error: str = "") -> None:
        self.name = name
        self.shared = shared
        self.error = error

    @property
    def label(self) -> str:
        return "MPRIS"

    async def start(self) -> str:
        if self.error:
            raise RuntimeError(self.error)
        return self.name

    async def stop(self) -> None:
        return None

    def publish(self) -> None:
        return None

    def publish_tracks(self) -> None:
        return None

    def seeked(self, position: float) -> None:
        return None


def _started(monkeypatch, media: FakeMedia) -> tuple[bool, str]:
    isolate_runtime(monkeypatch)
    seen: list[tuple[bool, str]] = []

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.mpris = media
            application.status = ""
            await START_MEDIA(application)
            seen.append((application._mpris_ready, application.status))

    asyncio.run(scenario())
    return seen[0]


def test_the_plain_name_is_not_worth_a_word(monkeypatch):
    ready, status = _started(monkeypatch, FakeMedia("org.mpris.MediaPlayer2.tidalamp"))
    assert ready is True
    assert status == ""


def test_a_second_instance_says_which_name_it_got(monkeypatch):
    name = "org.mpris.MediaPlayer2.tidalamp.instance4321"
    ready, status = _started(monkeypatch, FakeMedia(name, shared=True))
    assert ready is True
    assert status == f"MPRIS como {name} (ya había otra instancia)"


def test_a_backend_that_names_nothing_is_not_a_second_instance(monkeypatch):
    ready, status = _started(monkeypatch, FakeMedia(""))
    assert ready is True
    assert status == ""


def test_no_integration_is_said_and_not_fatal(monkeypatch):
    ready, status = _started(monkeypatch, FakeMedia(error="sin bus de sesión"))
    assert ready is False
    assert status == "MPRIS no disponible (sin bus de sesión)"


# ------------------------------------------- the audio stack's own rows


def test_windows_offers_the_device_and_exclusive_mode_instead_of_pipewire(
    monkeypatch,
):
    """The device first: exclusive mode takes all of it."""
    from tidalamp.screens import config_window

    monkeypatch.setattr(config_window.audio, "MANAGES_RATES", False)
    rows = config_window.ConfigScreen()._stack_rows("Audio")
    assert [(row.key, row.action) for row in rows] == [
        ("audio_device", ""),
        ("exclusive", ""),
    ]


def test_linux_keeps_its_pipewire_rows(monkeypatch):
    from tidalamp.screens import config_window

    monkeypatch.setattr(config_window.audio, "MANAGES_RATES", True)
    rows = config_window.ConfigScreen()._stack_rows("Audio")
    assert [row.action for row in rows] == ["rates", "restart"]


def test_the_device_row_says_what_auto_stands_for(monkeypatch):
    from tidalamp import config
    from tidalamp.screens import config_window

    monkeypatch.setattr(config, "AUDIO_DEVICE", "auto")
    screen = config_window.ConfigScreen()
    row = config_window.Option("Dispositivo", key="audio_device")
    assert screen._value(row) == "auto"
    screen._devices = [("wasapi/{jbl}", "JBL Charge 3"), ("wasapi/{fiio}", "FiiO")]
    screen._default_device = "wasapi/{jbl}"
    assert screen._value(row) == "auto · JBL Charge 3"
    monkeypatch.setattr(config, "AUDIO_DEVICE", "wasapi/{fiio}")
    assert screen._value(row) == "FiiO"
    monkeypatch.setattr(config, "AUDIO_DEVICE", "wasapi/{gone}")
    assert screen._value(row) == "no conectado; suena por el predeterminado"


def test_the_device_is_picked_from_a_list_and_never_by_an_arrow():
    """An arrow would have moved the sound to another speaker."""
    from tidalamp.screens import config_window

    row = config_window.Option("Dispositivo", key="audio_device")
    assert config_window.ConfigScreen._picked(row)


def test_changing_the_device_moves_the_sound_at_once(monkeypatch):
    from tidalamp import audio, config

    isolate_runtime(monkeypatch)
    monkeypatch.setattr(audio, "connected", lambda name: True)
    seen: list[tuple[list[str], str]] = []

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(config, "AUDIO_DEVICE", "wasapi/{fiio}")
            application._setting_changed("audio_device")
            seen.append((list(mpv.devices), application.status))
            monkeypatch.setattr(config, "AUDIO_DEVICE", "auto")
            application._setting_changed("audio_device")
            seen.append((list(mpv.devices), application.status))

    asyncio.run(scenario())
    assert seen[0] == (["wasapi/{fiio}"], "dispositivo de salida cambiado")
    assert seen[1][0] == ["wasapi/{fiio}", "auto"]
    assert "predeterminado de Windows" in seen[1][1]


def test_exclusive_mode_applies_at_once_and_says_what_it_costs(monkeypatch):
    from tidalamp import config

    isolate_runtime(monkeypatch)
    seen: list[tuple[list[bool], str]] = []

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(config, "EXCLUSIVE", True)
            application._setting_changed("exclusive")
            seen.append((list(mpv.exclusive), application.status))

    asyncio.run(scenario())
    assert seen[0][0] == [True]
    assert "sólo suena tidalamp" in seen[0][1]


def test_choosing_the_same_device_again_applies_it_again(monkeypatch):
    """mpv may be on the default since the device was unplugged; choosing
    it again did nothing, because the setting already said it."""
    from tidalamp import config
    from tidalamp.screens import config_window

    changed: list[str] = []
    monkeypatch.setattr(config, "AUDIO_DEVICE", "wasapi/{fiio}")
    monkeypatch.setattr(config, "DEFAULT_QUALITY", "HI_RES_LOSSLESS")
    screen = config_window.ConfigScreen(on_change=changed.append)
    screen._set(config_window.Option("Dispositivo", key="audio_device"), "wasapi/{fiio}")
    screen._set(config_window.Option("Calidad", key="quality"), "HI_RES_LOSSLESS")
    assert changed == ["audio_device"]


def test_a_device_that_is_not_there_is_not_handed_to_mpv(monkeypatch):
    """mpv asked for it opens nothing and plays in silence."""
    from tidalamp import audio, config

    isolate_runtime(monkeypatch)
    seen: list[tuple[list[str], str]] = []

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(config, "AUDIO_DEVICE", "wasapi/{fiio}")
            monkeypatch.setattr(audio, "connected", lambda name: False)
            application._setting_changed("audio_device")
            seen.append((list(mpv.devices), application.status))

    asyncio.run(scenario())
    assert seen[0][0] == ["auto"]
    assert "no está conectado" in seen[0][1]


def test_the_chosen_device_is_gone_back_to_once_it_is_plugged_in(monkeypatch):
    """The FiiO came back and the sound stayed on the JBL it had fallen to."""
    from tidalamp import audio, config

    isolate_runtime(monkeypatch)
    monkeypatch.setattr(audio, "MANAGES_RATES", False)
    seen: list[tuple[list[str], str]] = []

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(config, "AUDIO_DEVICE", "wasapi/{fiio}")
            monkeypatch.setattr(audio, "connected", lambda name: False)
            application._watch_output()
            await settle(pilot, lambda: True)
            assert mpv.devices == [], "todavía no está"
            monkeypatch.setattr(audio, "connected", lambda name: True)
            application._watch_output()
            await settle(pilot, lambda: mpv.devices)
            seen.append((list(mpv.devices), application.status))
            # Back on it: nothing more to ask Windows.
            application._watch_output()
            await pilot.pause()
            seen.append((list(mpv.devices), application.status))

    asyncio.run(scenario())
    assert seen[0] == (["wasapi/{fiio}"], "volvió el dispositivo de salida; suena por él")
    assert seen[1][0] == ["wasapi/{fiio}"]


def test_linux_never_watches_for_a_device(monkeypatch):
    """No row, no device: the output is PipeWire's default sink."""
    from tidalamp import audio, config

    isolate_runtime(monkeypatch)
    monkeypatch.setattr(audio, "MANAGES_RATES", True)
    asked: list[str] = []

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(config, "AUDIO_DEVICE", "wasapi/{fiio}")
            monkeypatch.setattr(audio, "connected", lambda name: asked.append(name))
            application._watch_output()
            await settle(pilot, lambda: True)

    asyncio.run(scenario())
    assert asked == []


class _Cava:
    """cava, as far as the app asks: it only has to be there."""

    made = 0
    alive = True

    def __init__(self, bars: int) -> None:
        type(self).made += 1

    def frame(self) -> list[float]:
        return [0.5]

    def close(self) -> None:
        pass


def test_exclusive_mode_leaves_the_spectrum_to_the_level_meter(monkeypatch):
    """cava listens to Windows's mixer, and an exclusive stream goes around
    it: the spectrum was a flat line while the music played."""
    from tidalamp import app as app_module
    from tidalamp import audio, config

    start = TidalAmp._start_spectrum
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_start_spectrum", start)
    monkeypatch.setattr(app_module, "Cava", _Cava)
    monkeypatch.setattr(_Cava, "made", 0)
    monkeypatch.setattr(audio, "MANAGES_RATES", False)
    monkeypatch.setattr(config, "EXCLUSIVE", True)
    seen: list[tuple[int, bool]] = []

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            seen.append((_Cava.made, application.cava is None))
            monkeypatch.setattr(config, "EXCLUSIVE", False)
            application._setting_changed("exclusive")
            seen.append((_Cava.made, application.cava is None))
            monkeypatch.setattr(config, "EXCLUSIVE", True)
            application._setting_changed("exclusive")
            seen.append((_Cava.made, application.cava is None))

    asyncio.run(scenario())
    assert seen == [(0, True), (1, False), (1, True)]


def test_linux_keeps_cava_whatever_the_exclusive_setting_says(monkeypatch):
    """The setting does nothing on Linux, where PipeWire's rates are managed."""
    from tidalamp import app as app_module
    from tidalamp import audio, config

    start = TidalAmp._start_spectrum
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_start_spectrum", start)
    monkeypatch.setattr(app_module, "Cava", _Cava)
    monkeypatch.setattr(_Cava, "made", 0)
    monkeypatch.setattr(audio, "MANAGES_RATES", True)
    monkeypatch.setattr(config, "EXCLUSIVE", True)

    async def scenario() -> bool:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            return application.cava is not None

    assert asyncio.run(scenario())


def test_a_muted_output_is_said_on_the_out_line_and_in_the_settings(monkeypatch):
    """Muted in Windows, the track played on in silence and nothing said so."""
    from tidalamp import audio
    from tidalamp.screens import config_window
    from tidalamp.widgets import Glide

    isolate_runtime(monkeypatch)
    muted = audio.Sink(
        name="wasapi/{fiio}", description="FiiO BTR15", rate=48000, muted=True
    )

    async def scenario() -> tuple[str, str]:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            application._set_sink(muted)
            await pilot.pause()
            out = str(application.query_one("#output", Glide).content)
            screen = config_window.ConfigScreen()
            screen._sink = muted
            return out, screen._warning()

    out, warning = asyncio.run(scenario())
    assert "silenciado en Windows" in out
    assert "Silenciada en Windows" in warning


def test_the_spectrum_is_the_level_meter_off_the_default_device(monkeypatch):
    """cava hears the default output's mix only: playing to a FiiO with a
    JBL as the default, the analyser read «FFT» over a flat line."""
    from tidalamp import app as app_module
    from tidalamp import audio, config

    start = TidalAmp._start_spectrum
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_start_spectrum", start)
    monkeypatch.setattr(app_module, "Cava", _Cava)
    monkeypatch.setattr(_Cava, "made", 0)
    monkeypatch.setattr(audio, "MANAGES_RATES", False)
    monkeypatch.setattr(audio, "system_default", lambda: "wasapi/{jbl}")
    monkeypatch.setattr(audio, "connected", lambda name: True)
    monkeypatch.setattr(config, "EXCLUSIVE", False)
    seen: list[bool] = []

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            seen.append(application.cava is not None)  # auto: the default
            for device in ("wasapi/{fiio}", "wasapi/{jbl}"):
                monkeypatch.setattr(config, "AUDIO_DEVICE", device)
                application._setting_changed("audio_device")
                seen.append(application.cava is not None)

    asyncio.run(scenario())
    assert seen == [True, False, True]
