"""MPRIS2 D-Bus interface.

Publishing ``org.mpris.MediaPlayer2.tidalamp`` is what lets the rest of the
desktop talk to us: ``playerctl``, the Waybar media module, Hyprland's media
keys, and any external frontend (a Quickshell widget consumes MPRIS natively,
so it needs no IPC of our own).

dbus-next is asyncio-based and Textual already runs an asyncio loop, so the
service lives on that same loop rather than in a thread.
"""

from __future__ import annotations

from typing import Any, Protocol

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method, signal

BUS_NAME = "org.mpris.MediaPlayer2.tidalamp"
OBJECT_PATH = "/org/mpris/MediaPlayer2"

# MPRIS expresses every time value in microseconds.
USEC = 1_000_000


class PlayerBackend(Protocol):
    """What the MPRIS service needs from the application.

    Keeping this a Protocol means ``mpris.py`` stays independent of Textual and
    of tidalapi, the same way ``widgets.py`` does.
    """

    def mpris_status(self) -> str: ...
    def mpris_metadata(self) -> dict[str, Any]: ...
    def mpris_position(self) -> float: ...
    def mpris_volume(self) -> float: ...
    def mpris_set_volume(self, value: float) -> None: ...
    def mpris_can_go_next(self) -> bool: ...
    def mpris_can_go_previous(self) -> bool: ...
    def mpris_play(self) -> None: ...
    def mpris_pause(self) -> None: ...
    def mpris_play_pause(self) -> None: ...
    def mpris_stop(self) -> None: ...
    def mpris_next(self) -> None: ...
    def mpris_previous(self) -> None: ...
    def mpris_seek(self, offset: float) -> None: ...
    def mpris_set_position(self, position: float) -> None: ...
    def mpris_quit(self) -> None: ...


class _Root(ServiceInterface):
    """``org.mpris.MediaPlayer2`` — the application-level interface."""

    def __init__(self, backend: PlayerBackend) -> None:
        super().__init__("org.mpris.MediaPlayer2")
        self._backend = backend

    @method()
    def Raise(self):  # noqa: N802 - D-Bus method name
        # We are a TUI; there is no window to raise. CanRaise reports False.
        pass

    @method()
    def Quit(self):  # noqa: N802
        self._backend.mpris_quit()

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> "b":  # noqa: N802, F821
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> "b":  # noqa: N802, F821
        return False

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> "b":  # noqa: N802, F821
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> "s":  # noqa: N802, F821
        return "tidalamp"

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> "s":  # noqa: N802, F821
        return "tidalamp"

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> "as":  # noqa: N802, F821
        return []

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> "as":  # noqa: N802, F821
        return []


class _Player(ServiceInterface):
    """``org.mpris.MediaPlayer2.Player`` — transport and metadata."""

    def __init__(self, backend: PlayerBackend) -> None:
        super().__init__("org.mpris.MediaPlayer2.Player")
        self._backend = backend

    # ---------------------------------------------------------------- methods

    @method()
    def Next(self):  # noqa: N802
        self._backend.mpris_next()

    @method()
    def Previous(self):  # noqa: N802
        self._backend.mpris_previous()

    @method()
    def Pause(self):  # noqa: N802
        self._backend.mpris_pause()

    @method()
    def PlayPause(self):  # noqa: N802
        self._backend.mpris_play_pause()

    @method()
    def Stop(self):  # noqa: N802
        self._backend.mpris_stop()

    @method()
    def Play(self):  # noqa: N802
        self._backend.mpris_play()

    @method()
    def Seek(self, offset: "x"):  # noqa: N802, F821
        self._backend.mpris_seek(offset / USEC)

    @method()
    def SetPosition(self, track_id: "o", position: "x"):  # noqa: N802, F821
        self._backend.mpris_set_position(position / USEC)

    @method()
    def OpenUri(self, uri: "s"):  # noqa: N802, F821
        # Opening arbitrary URIs is not supported; SupportedUriSchemes is empty.
        pass

    @signal()
    def Seeked(self, position: "x") -> "x":  # noqa: N802, F821
        return position

    # ------------------------------------------------------------- properties

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":  # noqa: N802, F821
        return self._backend.mpris_status()

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":  # noqa: N802, F821
        return _pack_metadata(self._backend.mpris_metadata())

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":  # noqa: N802, F821
        return int(self._backend.mpris_position() * USEC)

    @dbus_property()
    def Volume(self) -> "d":  # noqa: N802, F821
        return self._backend.mpris_volume()

    @Volume.setter
    def Volume(self, value: "d"):  # noqa: N802, F821
        self._backend.mpris_set_volume(value)

    @dbus_property(access=PropertyAccess.READ)
    def Rate(self) -> "d":  # noqa: N802, F821
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> "d":  # noqa: N802, F821
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> "d":  # noqa: N802, F821
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":  # noqa: N802, F821
        return self._backend.mpris_can_go_next()

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":  # noqa: N802, F821
        return self._backend.mpris_can_go_previous()

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":  # noqa: N802, F821
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":  # noqa: N802, F821
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> "b":  # noqa: N802, F821
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":  # noqa: N802, F821
        return True


def _pack_metadata(raw: dict[str, Any]) -> dict[str, Variant]:
    """Turn a plain dict into the Variant-typed map MPRIS expects."""
    packed: dict[str, Variant] = {
        "mpris:trackid": Variant("o", raw.get("trackid", "/org/mpris/MediaPlayer2/TrackList/NoTrack")),
        "mpris:length": Variant("x", int(raw.get("length", 0) * USEC)),
    }
    if title := raw.get("title"):
        packed["xesam:title"] = Variant("s", title)
    if artist := raw.get("artist"):
        packed["xesam:artist"] = Variant("as", [artist])
    if album := raw.get("album"):
        packed["xesam:album"] = Variant("s", album)
    if art := raw.get("art_url"):
        packed["mpris:artUrl"] = Variant("s", art)
    if url := raw.get("url"):
        packed["xesam:url"] = Variant("s", url)
    return packed


class MprisService:
    """Owns the bus connection and pushes change notifications."""

    def __init__(self, backend: PlayerBackend) -> None:
        self._backend = backend
        self._bus: MessageBus | None = None
        self._player: _Player | None = None
        self._last: dict[str, Any] = {}

    async def start(self) -> None:
        """Connect and claim the well-known name. Raises on failure."""
        self._bus = await MessageBus().connect()
        self._player = _Player(self._backend)
        self._bus.export(OBJECT_PATH, _Root(self._backend))
        self._bus.export(OBJECT_PATH, self._player)
        await self._bus.request_name(BUS_NAME)

    def publish(self) -> None:
        """Emit PropertiesChanged for whatever actually changed.

        Called from the UI tick. MPRIS clients redraw on every signal, so we
        diff against the last emission instead of emitting unconditionally.
        """
        if self._player is None:
            return

        current = {
            "PlaybackStatus": self._backend.mpris_status(),
            "Metadata": self._backend.mpris_metadata(),
            "Volume": round(self._backend.mpris_volume(), 3),
            "CanGoNext": self._backend.mpris_can_go_next(),
            "CanGoPrevious": self._backend.mpris_can_go_previous(),
        }
        changed = {k: v for k, v in current.items() if self._last.get(k) != v}
        if not changed:
            return
        self._last = current

        if "Metadata" in changed:
            changed["Metadata"] = _pack_metadata(changed["Metadata"])
        self._player.emit_properties_changed(changed)

    def seeked(self, position: float) -> None:
        """Announce a discontinuous position jump, as the spec requires."""
        if self._player is not None:
            self._player.Seeked(int(position * USEC))

    async def stop(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
