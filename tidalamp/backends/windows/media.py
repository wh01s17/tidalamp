"""The media integration on Windows: SMTC, the panel and the media keys.

System Media Transport Controls is what Windows shows over the volume flyout
and what the keyboard's media keys drive. It is MPRIS's counterpart, and this
is the same service the Linux backend is, behind `tidalamp.media`'s contract.

**No window of our own.** SMTC belongs to a window, which a TUI does not
have. A `MediaPlayer` carries a set of controls of its own; switching its
command manager off leaves them for us to drive. It is the way out for desktop
programs without a window, and whether it holds for one started from a
terminal and not packaged is what windows.md's checklist asks to see.

**Threads.** A button press arrives on a WinRT thread-pool thread. It is
handed to the app's event loop with `call_soon_threadsafe` and nothing more:
the queue and the player are only ever touched from the UI's own loop.

**Units.** The app works in seconds; WinRT's `TimeSpan` reaches Python as a
`datetime.timedelta`, which is where the conversion is made.

**Never fatal.** No packages, no WinRT, or a call that fails: `start` raises,
and the app says the controls are unavailable and plays on. A failure after
that is logged once and switches the integration off, not the player.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from ...i18n import _
from ...media import PlayerBackend

log = logging.getLogger("tidalamp.media")


@dataclass
class WinRT:
    """What this module takes from WinRT, in one place so tests can stand in."""

    player: Any  # Windows.Media.Playback.MediaPlayer, kept alive with the controls
    controls: Any  # its SystemMediaTransportControls
    button: Any  # SystemMediaTransportControlsButton
    status: Any  # MediaPlaybackStatus
    music: Any  # MediaPlaybackType.MUSIC
    timeline: Callable[[], Any]  # SystemMediaTransportControlsTimelineProperties
    picture: Callable[[str], Any]  # a thumbnail from a URL


def _system() -> WinRT:
    """The real thing. Imported here: the packages exist only on Windows."""
    from winrt.windows.foundation import Uri
    from winrt.windows.media import (
        MediaPlaybackStatus,
        MediaPlaybackType,
        SystemMediaTransportControlsButton,
        SystemMediaTransportControlsTimelineProperties,
    )
    from winrt.windows.media.playback import MediaPlayer
    from winrt.windows.storage.streams import RandomAccessStreamReference

    player = MediaPlayer()
    player.command_manager.is_enabled = False
    return WinRT(
        player=player,
        controls=player.system_media_transport_controls,
        button=SystemMediaTransportControlsButton,
        status=MediaPlaybackStatus,
        music=MediaPlaybackType.MUSIC,
        timeline=SystemMediaTransportControlsTimelineProperties,
        picture=lambda url: RandomAccessStreamReference.create_from_uri(Uri(url)),
    )


class MprisService:
    """SMTC, driven from the app's `mpris_*` adapter like the D-Bus service."""

    def __init__(
        self,
        backend: PlayerBackend,
        winrt: Callable[[], WinRT] | None = None,
    ) -> None:
        self._backend = backend
        self._make = winrt or _system
        self._winrt: WinRT | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tokens: list[tuple[str, Any]] = []
        self._last: dict[str, Any] = {}

    @property
    def label(self) -> str:
        return _("controles multimedia")

    @property
    def shared(self) -> bool:
        """Every program has controls of its own: there is no name to share."""
        return False

    async def start(self) -> str:
        self._loop = asyncio.get_running_loop()
        winrt = self._make()
        controls = winrt.controls
        controls.is_enabled = True
        controls.is_play_enabled = True
        controls.is_pause_enabled = True
        controls.is_stop_enabled = True
        controls.is_next_enabled = True
        controls.is_previous_enabled = True
        controls.playback_status = winrt.status.STOPPED
        self._tokens = [
            ("button_pressed", controls.add_button_pressed(self._pressed)),
            (
                "playback_position_change_requested",
                controls.add_playback_position_change_requested(self._position_asked),
            ),
        ]
        self._winrt = winrt
        return ""

    async def stop(self) -> None:
        winrt, self._winrt = self._winrt, None
        if winrt is None:
            return
        try:
            for event, token in self._tokens:
                getattr(winrt.controls, f"remove_{event}")(token)
            winrt.controls.is_enabled = False
        except Exception as exc:  # WinRT raises its own; closing must not
            log.debug("SMTC no se cerró limpio: %s", exc)
        self._tokens = []

    # -------------------------------------------------- from Windows to us

    def _pressed(self, sender: Any, args: Any) -> None:
        """A media key or a button on the panel. On a WinRT thread."""
        winrt, loop = self._winrt, self._loop
        if winrt is None or loop is None:
            return
        actions = {
            winrt.button.PLAY: self._backend.mpris_play,
            winrt.button.PAUSE: self._backend.mpris_pause,
            winrt.button.STOP: self._backend.mpris_stop,
            winrt.button.NEXT: self._backend.mpris_next,
            winrt.button.PREVIOUS: self._backend.mpris_previous,
        }
        action = actions.get(args.button)
        if action is not None:
            loop.call_soon_threadsafe(action)

    def _position_asked(self, sender: Any, args: Any) -> None:
        """The panel's position bar was dragged. On a WinRT thread."""
        loop = self._loop
        wanted = args.requested_playback_position
        if loop is not None and isinstance(wanted, timedelta):
            loop.call_soon_threadsafe(
                self._backend.mpris_set_position, wanted.total_seconds()
            )

    # -------------------------------------------------- from us to Windows

    def publish(self) -> None:
        """Tell Windows what changed, and only that: this runs on the UI tick,
        and redrawing the panel every time makes it flicker on some systems."""
        winrt = self._winrt
        if winrt is None:
            return
        current: dict[str, Any] = {
            "status": self._backend.mpris_status(),
            "metadata": self._backend.mpris_metadata(),
            "next": self._backend.mpris_can_go_next(),
            "previous": self._backend.mpris_can_go_previous(),
        }
        changed = {key for key, value in current.items() if self._last.get(key) != value}
        if not changed:
            return
        self._last = current
        try:
            controls = winrt.controls
            if "status" in changed:
                controls.playback_status = {
                    "Playing": winrt.status.PLAYING,
                    "Paused": winrt.status.PAUSED,
                }.get(current["status"], winrt.status.STOPPED)
            controls.is_next_enabled = current["next"]
            controls.is_previous_enabled = current["previous"]
            if "metadata" in changed:
                self._show(winrt, current["metadata"])
            if changed & {"metadata", "status"}:
                self._timeline(winrt, self._backend.mpris_position())
        except Exception as exc:
            self._give_up(exc)

    def publish_tracks(self) -> None:
        """SMTC has no track list: next and previous are all it shows."""

    def seeked(self, position: float) -> None:
        """A jump in the track: the panel's position bar follows it."""
        winrt = self._winrt
        if winrt is None:
            return
        try:
            self._timeline(winrt, position)
        except Exception as exc:
            self._give_up(exc)

    def _show(self, winrt: WinRT, metadata: dict[str, Any]) -> None:
        updater = winrt.controls.display_updater
        if not metadata:
            updater.clear_all()
            updater.update()
            return
        updater.type = winrt.music
        music = updater.music_properties
        music.title = str(metadata.get("title") or "")
        music.artist = str(metadata.get("artist") or "")
        music.album_title = str(metadata.get("album") or "")
        art = metadata.get("art_url")
        if art:
            updater.thumbnail = winrt.picture(str(art))
        updater.update()

    def _timeline(self, winrt: WinRT, position: float) -> None:
        length = float(self._last.get("metadata", {}).get("length") or 0.0)
        timeline = winrt.timeline()
        timeline.start_time = timedelta(0)
        timeline.min_seek_time = timedelta(0)
        timeline.end_time = timedelta(seconds=length)
        timeline.max_seek_time = timedelta(seconds=length)
        timeline.position = timedelta(seconds=max(0.0, min(position, length or position)))
        winrt.controls.update_timeline_properties(timeline)

    def _give_up(self, exc: Exception) -> None:
        log.warning("SMTC falló; sin controles multimedia desde ahora: %s", exc)
        self._winrt = None
