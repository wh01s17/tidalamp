"""MPRIS2 D-Bus interface.

Publishing ``org.mpris.MediaPlayer2.tidalamp`` is what lets the rest of the
desktop talk to us: ``playerctl``, the Waybar media module, Hyprland's media
keys, and any external frontend (a Quickshell widget consumes MPRIS natively,
so it needs no IPC of our own).

dbus-fast is asyncio-based and Textual already runs an asyncio loop, so the
service lives on that same loop rather than in a thread.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from dbus_fast import Variant
from dbus_fast.aio import MessageBus
from dbus_fast.constants import PropertyAccess, RequestNameReply
from dbus_fast.service import ServiceInterface, dbus_property, method, signal

from .i18n import _
from .player import Mpv

BUS_NAME = "org.mpris.MediaPlayer2.tidalamp"
OBJECT_PATH = "/org/mpris/MediaPlayer2"

# The path the spec reserves for "there is no track here".
NO_TRACK = "/org/mpris/MediaPlayer2/TrackList/NoTrack"

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
    def mpris_rate(self) -> float: ...
    def mpris_set_rate(self, value: float) -> None: ...
    def mpris_loop_status(self) -> str: ...
    def mpris_set_loop_status(self, value: str) -> None: ...
    def mpris_shuffle(self) -> bool: ...
    def mpris_set_shuffle(self, value: bool) -> None: ...
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
    def mpris_track_ids(self) -> list[str]: ...
    def mpris_tracks(self) -> list[dict[str, Any]]: ...
    def mpris_go_to(self, track_id: str) -> None: ...


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
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> "s":  # noqa: N802, F821
        return "tidalamp"

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> "s":  # noqa: N802, F821
        return "tidalamp"

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> "as":  # noqa: N802
        return []

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> "as":  # noqa: N802
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
    def Metadata(self) -> "a{sv}":  # noqa: N802
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

    @dbus_property()
    def LoopStatus(self) -> "s":  # noqa: N802, F821
        return self._backend.mpris_loop_status()

    @LoopStatus.setter
    def LoopStatus(self, value: "s"):  # noqa: N802, F821
        self._backend.mpris_set_loop_status(value)

    @dbus_property()
    def Shuffle(self) -> "b":  # noqa: N802, F821
        return self._backend.mpris_shuffle()

    @Shuffle.setter
    def Shuffle(self, value: "b"):  # noqa: N802, F821
        self._backend.mpris_set_shuffle(value)

    # The speed window's range: a quarter to double. A desktop may ask for any
    # number in between; the backend rounds it to the nearest quarter.
    @dbus_property()
    def Rate(self) -> "d":  # noqa: N802, F821
        return self._backend.mpris_rate()

    @Rate.setter
    def Rate(self, value: "d"):  # noqa: N802, F821
        self._backend.mpris_set_rate(value)

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> "d":  # noqa: N802, F821
        return Mpv.SPEEDS[0]

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> "d":  # noqa: N802, F821
        return Mpv.SPEEDS[-1]

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


class _TrackList(ServiceInterface):
    """``org.mpris.MediaPlayer2.TrackList`` — the queue, as the desktop sees it.

    Read-only on purpose. ``CanEditTracks`` is False because ``AddTrack`` takes
    a URI and we publish no supported URI schemes: there is nothing a client
    could hand us that we could play. The spec ties both editing methods to
    that one flag, so claiming True would promise an ``AddTrack`` we cannot
    honour. ``GoTo`` is not gated by it, and that is the half worth having:
    a client can jump to any row of the queue.
    """

    def __init__(self, backend: PlayerBackend) -> None:
        super().__init__("org.mpris.MediaPlayer2.TrackList")
        self._backend = backend

    @method()
    def GetTracksMetadata(self, track_ids: "ao") -> "aa{sv}":  # noqa: N802, F821
        return _metadata_for(self._backend.mpris_tracks(), track_ids)

    @method()
    def AddTrack(self, uri: "s", after_track: "o", set_as_current: "b"):  # noqa: N802, F821
        # CanEditTracks is False, so the spec says this has no effect.
        pass

    @method()
    def RemoveTrack(self, track_id: "o"):  # noqa: N802, F821
        pass

    @method()
    def GoTo(self, track_id: "o"):  # noqa: N802, F821
        self._backend.mpris_go_to(track_id)

    @signal()
    def TrackListReplaced(self, tracks: "ao", current: "o") -> "aoo":  # noqa: N802, F821
        return [tracks, current]

    @dbus_property(access=PropertyAccess.READ)
    def Tracks(self) -> "ao":  # noqa: N802, F821
        return self._backend.mpris_track_ids()

    @dbus_property(access=PropertyAccess.READ)
    def CanEditTracks(self) -> "b":  # noqa: N802, F821
        return False


def _metadata_for(
    tracks: list[dict[str, Any]], track_ids: list[str]
) -> list[dict[str, Variant]]:
    """Metadata for the ids asked for, in the order asked.

    Ids that are no longer in the queue are skipped rather than failing the
    whole call: a client's list is always a little behind ours.
    """
    known = {t.get("trackid"): t for t in tracks}
    return [_pack_metadata(known[i]) for i in track_ids if i in known]


def _pack_metadata(raw: dict[str, Any]) -> dict[str, Variant]:
    """Turn a plain dict into the Variant-typed map MPRIS expects."""
    packed: dict[str, Variant] = {
        "mpris:trackid": Variant("o", raw.get("trackid", NO_TRACK)),
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
        self._tracklist: _TrackList | None = None
        self._last: dict[str, Any] = {}
        self._last_tracks: list[str] | None = None
        self.bus_name: str = BUS_NAME

    async def start(self) -> str:
        """Connect and claim a bus name. Returns the name actually claimed.

        If another tidalamp already owns the well-known name we must not
        pretend we got it: every client would keep talking to that first
        instance while we sat there silently believing we were exported. MPRIS
        allows a per-instance suffix exactly for this case.
        """
        self._bus = await MessageBus().connect()
        self._player = _Player(self._backend)
        self._tracklist = _TrackList(self._backend)
        self._bus.export(OBJECT_PATH, _Root(self._backend))
        self._bus.export(OBJECT_PATH, self._player)
        self._bus.export(OBJECT_PATH, self._tracklist)

        reply = await self._bus.request_name(BUS_NAME)
        if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):
            self.bus_name = f"{BUS_NAME}.instance{os.getpid()}"
            reply = await self._bus.request_name(self.bus_name)
            if reply not in (
                RequestNameReply.PRIMARY_OWNER,
                RequestNameReply.ALREADY_OWNER,
            ):
                raise RuntimeError(
                    _("no se pudo reclamar un nombre MPRIS ({reply})").format(
                        reply=reply.name
                    )
                )
        return self.bus_name

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
            "Rate": self._backend.mpris_rate(),
            "CanGoNext": self._backend.mpris_can_go_next(),
            "CanGoPrevious": self._backend.mpris_can_go_previous(),
            "LoopStatus": self._backend.mpris_loop_status(),
            "Shuffle": self._backend.mpris_shuffle(),
        }
        changed = {k: v for k, v in current.items() if self._last.get(k) != v}
        if not changed:
            return
        self._last = current

        if "Metadata" in changed:
            changed["Metadata"] = _pack_metadata(changed["Metadata"])
        self._player.emit_properties_changed(changed)

    def publish_tracks(self) -> None:
        """Announce a changed queue, again only when it really changed.

        ``Tracks`` is the one property the spec tells implementations *not* to
        announce through ``PropertiesChanged``: ``TrackListReplaced`` is how a
        client learns the list moved. Our queue changes wholesale often enough
        — shuffle, reorder, clear — that a single replace is both simpler and
        more truthful than a stream of added/removed events.
        """
        if self._tracklist is None:
            return
        # Ids only: this runs on the UI tick, and building metadata for a long
        # queue four times a second to find out nothing moved would be silly.
        ids = self._backend.mpris_track_ids()
        if ids == self._last_tracks:
            return
        self._last_tracks = ids
        current = self._backend.mpris_metadata().get("trackid", NO_TRACK)
        self._tracklist.TrackListReplaced(ids, current)

    def seeked(self, position: float) -> None:
        """Announce a discontinuous position jump, as the spec requires."""
        if self._player is not None:
            self._player.Seeked(int(position * USEC))

    async def stop(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
