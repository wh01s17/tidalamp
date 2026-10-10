"""What the desktop's media integration may ask of the player.

`MediaBridge` is the app's side of `media.PlayerBackend`: MPRIS over D-Bus on
Linux and the media controls on Windows hold one and ask it for the state and
for the transport, and it answers from the app. The `mpris_` prefix is the
contract's name, whatever the system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .player import Mpv
from .queue import Entry, Repeat

if TYPE_CHECKING:
    from .app import TidalAmp


def track_path(entry: Entry) -> str:
    """The D-Bus object path for one queue row.

    Keyed on the row's uid, not on the TIDAL track id: the same song can be in
    the queue twice, and MPRIS requires the ids in a TrackList to be distinct.
    """
    return f"/org/mpris/MediaPlayer2/tidalamp/track/{entry.uid}"


def entry_metadata(entry: Entry) -> dict:
    return {
        "trackid": track_path(entry),
        "length": float(entry.duration),
        "title": entry.title,
        "artist": entry.artist,
        "album": entry.album,
        "art_url": entry.art_url,
        # A free row's audio is a real URL; a TIDAL one has none that
        # outlives the play, so it gets the scheme its own clients use.
        "url": entry.url or f"tidal://track/{entry.id}",
    }


class MediaBridge:
    """The player, as `media.PlayerBackend` sees it."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app

    def mpris_status(self) -> str:
        if self.app.queue.current is None or self.app.mpv.idle:
            return "Stopped"
        return "Paused" if self.app.mpv.paused else "Playing"

    def mpris_metadata(self) -> dict:
        entry = self.app.queue.current
        return {} if entry is None else entry_metadata(entry)

    def mpris_track_ids(self) -> list[str]:
        """Just the ids, which is all the TrackList property and the diff need."""
        return [track_path(entry) for entry in self.app.queue]

    def mpris_tracks(self) -> list[dict]:
        """The whole queue, in visible order, for ``GetTracksMetadata``."""
        return [entry_metadata(entry) for entry in self.app.queue]

    def mpris_go_to(self, track_id: str) -> None:
        for index, entry in enumerate(self.app.queue):
            if track_path(entry) == track_id:
                self.app.playback.play_index(index)
                return

    def mpris_position(self) -> float:
        return self.app.mpv.position

    def mpris_volume(self) -> float:
        # MPRIS volume is 0.0-1.0; mpv's is a percentage.
        return self.app.mpv.volume / 100.0

    def mpris_set_volume(self, value: float) -> None:
        ceiling = Mpv.VOLUME_MAX / 100.0
        self.app.mpv.volume = int(max(0.0, min(ceiling, value)) * 100)

    def mpris_rate(self) -> float:
        return self.app.mpv.speed

    def mpris_set_rate(self, value: float) -> None:
        """A desktop's speed, rounded to the nearest of the window's quarters.

        MPRIS says a rate of 0 must not be set (a client should pause
        instead), and mpv takes nothing at or below 0, so those are ignored.
        """
        if value <= 0:
            return
        speed = min(Mpv.SPEEDS, key=lambda candidate: abs(candidate - value))
        self.app.speed_chosen(speed)

    def mpris_can_go_next(self) -> bool:
        return self.app.queue.has_next()

    def mpris_can_go_previous(self) -> bool:
        return self.app.queue.has_prev()

    def mpris_loop_status(self) -> str:
        return self.app.queue.repeat.value

    def mpris_set_loop_status(self, value: str) -> None:
        try:
            self.app.queue.repeat = Repeat(value)
        except ValueError:
            return
        self.app.saved(self.app.queue.save())
        self.app.transport.refresh()

    def mpris_shuffle(self) -> bool:
        return self.app.queue.shuffle

    def mpris_set_shuffle(self, value: bool) -> None:
        self.app.queue.shuffle = value
        self.app.saved(self.app.queue.save())
        self.app.transport.refresh()

    def mpris_play(self) -> None:
        if self.app.mpv.paused:
            self.app.mpv.toggle_pause()
        else:
            self.app.playback.play()

    def mpris_pause(self) -> None:
        if not self.app.mpv.paused:
            self.app.mpv.toggle_pause()

    def mpris_play_pause(self) -> None:
        self.app.playback.toggle_pause()

    def mpris_stop(self) -> None:
        self.app.playback.stop()

    def mpris_next(self) -> None:
        self.app.playback.next()

    def mpris_previous(self) -> None:
        self.app.playback.prev()

    def mpris_seek(self, offset: float) -> None:
        self.app.mpv.seek(offset, "relative")
        self.app.mpris.seeked(self.app.mpv.position)

    def mpris_set_position(self, position: float) -> None:
        self.app.mpv.seek(position, "absolute")
        self.app.mpris.seeked(position)

    def mpris_quit(self) -> None:
        # Comes in on the bus, not from the keyboard: hand the shutdown to the
        # loop rather than awaiting it inside a D-Bus method call.
        self.app.run_worker(self.app.close_player(), exclusive=False)
