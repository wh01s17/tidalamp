"""MPRIS adapter contract without using the desktop session bus."""

from __future__ import annotations

import asyncio
import shutil
import subprocess

import pytest
from dbus_fast.aio import MessageBus

from tidalamp import mpris


class FakeBackend:
    def __init__(self) -> None:
        self.status = "Playing"
        self.metadata = {
            "trackid": "/org/mpris/MediaPlayer2/track/42",
            "length": 245.25,
            "title": "Schism",
            "artist": "TOOL",
            "album": "Lateralus",
            "art_url": "https://example.test/cover.jpg",
            "url": "tidal:track:42",
        }
        self.position = 12.5
        self.volume = 0.8
        self.loop_status = "None"
        self.shuffle = False
        self.can_go_next = True
        self.can_go_previous = False
        self.calls: list[tuple[str, object | None]] = []

    def mpris_status(self) -> str:
        return self.status

    def mpris_metadata(self) -> dict[str, object]:
        return self.metadata

    def mpris_position(self) -> float:
        return self.position

    def mpris_volume(self) -> float:
        return self.volume

    def mpris_set_volume(self, value: float) -> None:
        self.calls.append(("volume", value))

    def mpris_loop_status(self) -> str:
        return self.loop_status

    def mpris_set_loop_status(self, value: str) -> None:
        self.calls.append(("loop", value))

    def mpris_shuffle(self) -> bool:
        return self.shuffle

    def mpris_set_shuffle(self, value: bool) -> None:
        self.calls.append(("shuffle", value))

    def mpris_can_go_next(self) -> bool:
        return self.can_go_next

    def mpris_can_go_previous(self) -> bool:
        return self.can_go_previous

    def mpris_play(self) -> None:
        self.calls.append(("play", None))

    def mpris_pause(self) -> None:
        self.calls.append(("pause", None))

    def mpris_play_pause(self) -> None:
        self.calls.append(("play_pause", None))

    def mpris_stop(self) -> None:
        self.calls.append(("stop", None))

    def mpris_next(self) -> None:
        self.calls.append(("next", None))

    def mpris_previous(self) -> None:
        self.calls.append(("previous", None))

    def mpris_seek(self, offset: float) -> None:
        self.calls.append(("seek", offset))

    def mpris_set_position(self, position: float) -> None:
        self.calls.append(("position", position))

    def mpris_quit(self) -> None:
        self.calls.append(("quit", None))


class RecordingPlayer:
    def __init__(self) -> None:
        self.changes: list[dict[str, object]] = []
        self.seeked: list[int] = []

    def emit_properties_changed(self, changed: dict[str, object]) -> None:
        self.changes.append(changed)

    def Seeked(self, position: int) -> None:  # noqa: N802
        self.seeked.append(position)


def test_metadata_is_packed_into_typed_variants():
    packed = mpris._pack_metadata(FakeBackend().metadata)

    assert packed["mpris:trackid"].signature == "o"
    assert packed["mpris:trackid"].value.endswith("/42")
    assert packed["mpris:length"].value == 245_250_000
    assert packed["xesam:title"].value == "Schism"
    assert packed["xesam:artist"].value == ["TOOL"]
    assert packed["mpris:artUrl"].value == "https://example.test/cover.jpg"


def test_player_converts_dbus_time_units_to_seconds():
    backend = FakeBackend()
    player = mpris._Player(backend)

    assert player.Position == 12_500_000
    player.Seek(1_500_000)
    player.SetPosition("/org/mpris/MediaPlayer2/track/42", 2_250_000)

    assert backend.calls == [("seek", 1.5), ("position", 2.25)]


def test_player_delegates_transport_and_writable_properties():
    backend = FakeBackend()
    player = mpris._Player(backend)

    player.Play()
    player.Pause()
    player.PlayPause()
    player.Stop()
    player.Next()
    player.Previous()
    player.Volume = 0.45
    player.LoopStatus = "Playlist"
    player.Shuffle = True

    assert backend.calls == [
        ("play", None),
        ("pause", None),
        ("play_pause", None),
        ("stop", None),
        ("next", None),
        ("previous", None),
        ("volume", 0.45),
        ("loop", "Playlist"),
        ("shuffle", True),
    ]


def test_publish_emits_only_changed_properties():
    backend = FakeBackend()
    player = RecordingPlayer()
    service = mpris.MprisService(backend)
    service._player = player

    service.publish()
    service.publish()
    backend.status = "Paused"
    service.publish()

    assert len(player.changes) == 2
    assert set(player.changes[0]) == {
        "PlaybackStatus",
        "Metadata",
        "Volume",
        "CanGoNext",
        "CanGoPrevious",
        "LoopStatus",
        "Shuffle",
    }
    assert player.changes[0]["Metadata"]["xesam:title"].value == "Schism"
    assert player.changes[1] == {"PlaybackStatus": "Paused"}


def test_seeked_signal_uses_microseconds():
    player = RecordingPlayer()
    service = mpris.MprisService(FakeBackend())
    service._player = player

    service.seeked(3.75)

    assert player.seeked == [3_750_000]


def test_name_collision_claims_a_reachable_instance_name(monkeypatch):
    class FakeBus:
        def __init__(self) -> None:
            self.requested: list[str] = []
            self.exports: list[tuple[str, object]] = []

        async def connect(self):
            return self

        def export(self, path: str, interface: object) -> None:
            self.exports.append((path, interface))

        async def request_name(self, name: str):
            self.requested.append(name)
            if len(self.requested) == 1:
                return mpris.RequestNameReply.EXISTS
            return mpris.RequestNameReply.PRIMARY_OWNER

    bus = FakeBus()
    monkeypatch.setattr(mpris, "MessageBus", lambda: bus)
    monkeypatch.setattr(mpris.os, "getpid", lambda: 4321)
    service = mpris.MprisService(FakeBackend())

    claimed = asyncio.run(service.start())

    assert claimed == "org.mpris.MediaPlayer2.tidalamp.instance4321"
    assert bus.requested == [
        "org.mpris.MediaPlayer2.tidalamp",
        "org.mpris.MediaPlayer2.tidalamp.instance4321",
    ]
    assert [path for path, _ in bus.exports] == [mpris.OBJECT_PATH, mpris.OBJECT_PATH]


@pytest.fixture
def isolated_session_bus(monkeypatch):
    if shutil.which("dbus-daemon") is None:
        pytest.skip("dbus-daemon no está instalado")
    process = subprocess.Popen(
        ["dbus-daemon", "--session", "--nofork", "--print-address=1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    address = process.stdout.readline().strip()
    if not address:
        stderr = process.stderr.read() if process.stderr is not None else ""
        process.terminate()
        pytest.fail(f"dbus-daemon no entregó una dirección: {stderr}")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
    yield address
    process.terminate()
    process.wait(timeout=2)


def test_real_bus_exposes_properties_controls_signals_and_collision(
    isolated_session_bus,
):
    async def scenario() -> None:
        backend = FakeBackend()
        primary = mpris.MprisService(backend)
        secondary = mpris.MprisService(FakeBackend())
        client = None
        try:
            assert await primary.start() == mpris.BUS_NAME
            instance_name = await secondary.start()
            assert instance_name.startswith(f"{mpris.BUS_NAME}.instance")

            client = await MessageBus(bus_address=isolated_session_bus).connect()
            introspection = await client.introspect(mpris.BUS_NAME, mpris.OBJECT_PATH)
            proxy = client.get_proxy_object(
                mpris.BUS_NAME, mpris.OBJECT_PATH, introspection
            )
            root = proxy.get_interface("org.mpris.MediaPlayer2")
            player = proxy.get_interface("org.mpris.MediaPlayer2.Player")
            properties = proxy.get_interface("org.freedesktop.DBus.Properties")

            assert await root.get_identity() == "tidalamp"
            assert await player.get_playback_status() == "Playing"
            assert await player.get_position() == 12_500_000
            metadata = await player.get_metadata()
            assert metadata["xesam:title"].value == "Schism"

            await player.call_play()
            await player.set_volume(0.35)
            assert backend.calls == [("play", None), ("volume", 0.35)]

            changes: list[dict[str, object]] = []
            seeked: list[int] = []
            properties.on_properties_changed(
                lambda interface, changed, invalidated: changes.append(changed)
            )
            player.on_seeked(seeked.append)

            primary.publish()
            await asyncio.sleep(0.02)
            primary.publish()
            await asyncio.sleep(0.02)
            assert len(changes) == 1

            backend.status = "Paused"
            primary.publish()
            primary.seeked(7.25)
            await asyncio.sleep(0.02)
            assert changes[-1]["PlaybackStatus"].value == "Paused"
            assert seeked == [7_250_000]
        finally:
            if client is not None:
                client.disconnect()
            await secondary.stop()
            await primary.stop()

    asyncio.run(scenario())
