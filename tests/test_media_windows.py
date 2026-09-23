"""The SMTC service against a stand-in for WinRT: what it tells Windows and
what it does with what Windows tells it. The real controls need Windows and
a person to press the keys (windows.md, checklist); the logic does not."""

from __future__ import annotations

import asyncio
import threading
from datetime import timedelta
from enum import Enum
from types import SimpleNamespace

import pytest

from tidalamp.backends.windows.media import MprisService, WinRT


class Button(Enum):
    PLAY = 0
    PAUSE = 1
    STOP = 2
    NEXT = 7
    PREVIOUS = 8


class Status(Enum):
    STOPPED = 2
    PLAYING = 3
    PAUSED = 4


class Controls:
    """SystemMediaTransportControls, as far as the service touches them."""

    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.removed: list[str] = []
        self.timelines: list[SimpleNamespace] = []
        self.updates = 0
        self.cleared = 0
        self.display_updater = SimpleNamespace(
            type=None,
            thumbnail=None,
            music_properties=SimpleNamespace(title="", artist="", album_title=""),
            update=self._update,
            clear_all=self._clear,
        )

    def _update(self) -> None:
        self.updates += 1

    def _clear(self) -> None:
        self.cleared += 1

    def add_button_pressed(self, handler):
        self.handlers["button"] = handler
        return "token-button"

    def add_playback_position_change_requested(self, handler):
        self.handlers["position"] = handler
        return "token-position"

    def remove_button_pressed(self, token):
        self.removed.append(token)

    def remove_playback_position_change_requested(self, token):
        self.removed.append(token)

    def update_timeline_properties(self, timeline):
        self.timelines.append(timeline)


class App:
    """The `mpris_*` adapter, recording what it is asked to do."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.status = "Playing"
        self.metadata = {
            "title": "Schism",
            "artist": "Tool",
            "album": "Lateralus",
            "length": 403.0,
            "art_url": "https://resources.tidal.com/c.jpg",
        }

    def mpris_status(self):
        return self.status

    def mpris_metadata(self):
        return self.metadata

    def mpris_can_go_next(self):
        return True

    def mpris_can_go_previous(self):
        return False

    def mpris_position(self):
        return 12.5

    def __getattr__(self, name):
        if name.startswith("mpris_"):
            return lambda *args: self.calls.append((name, args))
        raise AttributeError(name)


def _winrt(controls: Controls) -> WinRT:
    return WinRT(
        player=object(),
        controls=controls,
        button=Button,
        status=Status,
        music="MUSIC",
        timeline=SimpleNamespace,
        picture=lambda url: f"picture:{url}",
    )


def _started(app: App) -> tuple[MprisService, Controls]:
    controls = Controls()
    service = MprisService(app, winrt=lambda: _winrt(controls))
    return service, controls


def test_starting_turns_the_controls_on_and_listens():
    async def scenario():
        service, controls = _started(App())
        assert await service.start() == ""
        return service, controls

    service, controls = asyncio.run(scenario())
    assert controls.is_enabled and controls.is_play_enabled and controls.is_next_enabled
    assert controls.playback_status is Status.STOPPED
    assert set(controls.handlers) == {"button", "position"}
    assert service.shared is False


def test_the_panel_shows_the_track_and_its_place_in_it():
    async def scenario():
        service, controls = _started(App())
        await service.start()
        service.publish()
        return controls

    controls = asyncio.run(scenario())
    music = controls.display_updater.music_properties
    assert (music.title, music.artist, music.album_title) == (
        "Schism",
        "Tool",
        "Lateralus",
    )
    assert (
        controls.display_updater.thumbnail == "picture:https://resources.tidal.com/c.jpg"
    )
    assert controls.playback_status is Status.PLAYING
    assert controls.is_previous_enabled is False
    timeline = controls.timelines[-1]
    assert timeline.end_time == timedelta(seconds=403)
    assert timeline.position == timedelta(seconds=12.5)


def test_nothing_changed_is_nothing_sent():
    async def scenario():
        service, controls = _started(App())
        await service.start()
        service.publish()
        service.publish()
        service.publish()
        return controls

    controls = asyncio.run(scenario())
    assert controls.updates == 1
    assert len(controls.timelines) == 1


def test_pausing_changes_the_status_not_the_track():
    async def scenario():
        app = App()
        service, controls = _started(app)
        await service.start()
        service.publish()
        app.status = "Paused"
        service.publish()
        return controls

    controls = asyncio.run(scenario())
    assert controls.playback_status is Status.PAUSED
    assert controls.updates == 1


def test_no_track_clears_the_panel():
    async def scenario():
        app = App()
        service, controls = _started(app)
        await service.start()
        service.publish()
        app.metadata, app.status = {}, "Stopped"
        service.publish()
        return controls

    controls = asyncio.run(scenario())
    assert controls.cleared == 1
    assert controls.playback_status is Status.STOPPED


@pytest.mark.parametrize(
    ("button", "called"),
    [
        (Button.PLAY, "mpris_play"),
        (Button.PAUSE, "mpris_pause"),
        (Button.NEXT, "mpris_next"),
        (Button.PREVIOUS, "mpris_previous"),
        (Button.STOP, "mpris_stop"),
    ],
)
def test_a_media_key_from_a_winrt_thread_runs_on_the_apps_loop(button, called):
    """The press arrives on another thread; the app is only touched from its own."""

    async def scenario():
        app = App()
        service, controls = _started(app)
        await service.start()
        loop_thread = threading.get_ident()
        ran_on: list[int] = []
        original = app.__getattr__(called)
        setattr(
            app,
            called,
            lambda *args: (ran_on.append(threading.get_ident()), original(*args)),
        )
        press = threading.Thread(
            target=controls.handlers["button"],
            args=(controls, SimpleNamespace(button=button)),
        )
        press.start()
        press.join()
        await asyncio.sleep(0.05)
        return app, ran_on, loop_thread

    app, ran_on, loop_thread = asyncio.run(scenario())
    assert app.calls == [(called, ())]
    assert ran_on == [loop_thread]


def test_dragging_the_panels_bar_seeks_in_seconds():
    async def scenario():
        app = App()
        service, controls = _started(app)
        await service.start()
        wanted = SimpleNamespace(requested_playback_position=timedelta(minutes=2))
        controls.handlers["position"](controls, wanted)
        await asyncio.sleep(0.01)
        return app

    assert asyncio.run(scenario()).calls == [("mpris_set_position", (120.0,))]


def test_a_seek_moves_the_panels_bar():
    async def scenario():
        service, controls = _started(App())
        await service.start()
        service.publish()
        service.seeked(300.0)
        return controls

    assert asyncio.run(scenario()).timelines[-1].position == timedelta(seconds=300)


def test_no_winrt_is_an_error_the_app_can_report():
    def missing():
        raise ImportError("No module named 'winrt'")

    service = MprisService(App(), winrt=missing)
    with pytest.raises(ImportError):
        asyncio.run(service.start())


def test_winrt_failing_later_switches_the_controls_off_not_the_player():
    async def scenario():
        service, controls = _started(App())
        await service.start()

        def broken():
            raise OSError("RPC server unavailable")

        controls.display_updater.update = broken
        service.publish()  # must not raise
        service.publish()
        service.seeked(1.0)
        return service

    assert asyncio.run(scenario())._winrt is None


def test_stopping_lets_go_of_the_handlers():
    async def scenario():
        service, controls = _started(App())
        await service.start()
        await service.stop()
        return controls

    controls = asyncio.run(scenario())
    assert controls.removed == ["token-button", "token-position"]
    assert controls.is_enabled is False
