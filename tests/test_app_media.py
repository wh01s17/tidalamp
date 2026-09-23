"""What the app says about the desktop's media integration when it starts:
nothing when it got the name, which name when another tidalamp had it, and
why when there is none. The backend is a double: the app only reads `start()`
and `shared`, whatever the system."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime

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


def test_windows_offers_exclusive_mode_instead_of_pipewire(monkeypatch):
    from tidalamp.screens import config_window

    monkeypatch.setattr(config_window.audio, "MANAGES_RATES", False)
    rows = config_window.ConfigScreen()._stack_rows("Audio")
    assert [(row.key, row.action) for row in rows] == [("exclusive", "")]


def test_linux_keeps_its_pipewire_rows(monkeypatch):
    from tidalamp.screens import config_window

    monkeypatch.setattr(config_window.audio, "MANAGES_RATES", True)
    rows = config_window.ConfigScreen()._stack_rows("Audio")
    assert [row.action for row in rows] == ["rates", "restart"]


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
