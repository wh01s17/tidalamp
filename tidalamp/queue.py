"""The play queue: entries, order, repeat/shuffle, and persistence.

``Entry`` deliberately stores plain metadata rather than a ``tidalapi.Track``.
Everything the UI draws comes from those fields, so a saved queue reloads
instantly; the real Track object is fetched from the API only when a song is
about to play (see :meth:`Entry.resolve`).
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import tidalapi

from .config import QUEUE_FILE, ensure_dirs

# Queue rows need an identity of their own: the same song can sit in the queue
# twice, MPRIS TrackList addresses rows by id, and those ids have to survive a
# reorder. A counter is enough — it only has to be unique within one queue.
_next_uid = 0


def _new_uid() -> int:
    global _next_uid
    _next_uid += 1
    return _next_uid


def _claim_uid(value: int) -> int:
    """Take a uid restored from disk, keeping the counter ahead of it."""
    global _next_uid
    _next_uid = max(_next_uid, value)
    return value


class Repeat(StrEnum):
    """Repeat mode. The values match MPRIS ``LoopStatus`` exactly."""

    NONE = "None"
    TRACK = "Track"
    QUEUE = "Playlist"

    def next(self) -> Repeat:
        order = [Repeat.NONE, Repeat.QUEUE, Repeat.TRACK]
        return order[(order.index(self) + 1) % len(order)]


@dataclass(slots=True)
class Entry:
    """One queue row."""

    id: int
    title: str
    artist: str
    album: str = ""
    year: int = 0
    # The record this track belongs to. Kept because the year does not travel
    # in a track listing and has to be asked for once per album; without the
    # id there is nothing to ask about. See `library.album_year`.
    album_id: int = 0
    duration: int = 0
    art_url: str = ""
    # Everything below is only ever drawn in an optional queue column. All of
    # it comes filled in on a plain track listing — checked against the real
    # API — so none of it costs an extra request.
    version: str = ""
    track_num: int = 0
    disc: int = 0
    explicit: bool = False
    popularity: int = 0
    isrc: str = ""
    quality: str = ""
    # Identity of this row, not of the song. Excluded from equality so two
    # rows for the same track still compare equal, as they always have.
    uid: int = field(default_factory=_new_uid, compare=False)
    _track: tidalapi.Track | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_track(cls, track: tidalapi.Track) -> Entry:
        album = getattr(track, "album", None)
        art = ""
        if album is not None:
            try:
                art = album.image(320) or ""
            except Exception:
                # tidalapi raises when the album carries no cover id.
                art = ""
        return cls(
            id=track.id,
            title=track.name,
            artist=getattr(getattr(track, "artist", None), "name", "") or "",
            album=getattr(album, "name", "") or "",
            # tidalapi works the year out of whichever release date it has,
            # and returns None when the album carries neither.
            year=int(getattr(album, "year", 0) or 0),
            album_id=int(getattr(album, "id", 0) or 0),
            duration=int(track.duration or 0),
            art_url=art,
            version=getattr(track, "version", "") or "",
            track_num=int(getattr(track, "track_num", 0) or 0),
            disc=int(getattr(track, "volume_num", 0) or 0),
            explicit=bool(getattr(track, "explicit", False)),
            popularity=int(getattr(track, "popularity", 0) or 0),
            isrc=getattr(track, "isrc", "") or "",
            quality=getattr(track, "audio_quality", "") or "",
            _track=track,
        )

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.title}" if self.artist else self.title

    @property
    def length(self) -> str:
        minutes, secs = divmod(self.duration, 60)
        return f"{minutes}:{secs:02d}"

    def resolve(self, session: tidalapi.Session) -> tidalapi.Track:
        """Fetch the real Track, hitting the API only on a restored entry."""
        if self._track is None:
            # tidalapi types the id as a string; the API takes both and every
            # track id we hold came back from it as an int.
            self._track = session.track(str(self.id))
        return self._track

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "year": self.year,
            "album_id": self.album_id,
            "duration": self.duration,
            "art_url": self.art_url,
            "version": self.version,
            "track_num": self.track_num,
            "disc": self.disc,
            "explicit": self.explicit,
            "popularity": self.popularity,
            "isrc": self.isrc,
            "quality": self.quality,
            "uid": self.uid,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Entry:
        return cls(
            id=int(raw["id"]),
            title=raw.get("title", ""),
            artist=raw.get("artist", ""),
            album=raw.get("album", ""),
            # A queue written before the column existed simply has no year.
            year=int(raw.get("year", 0) or 0),
            # And one written before this field cannot be filled in later:
            # there is no id to ask TIDAL about. It fills on the next reload.
            album_id=int(raw.get("album_id", 0) or 0),
            duration=int(raw.get("duration", 0)),
            art_url=raw.get("art_url", ""),
            version=raw.get("version", "") or "",
            track_num=int(raw.get("track_num", 0) or 0),
            disc=int(raw.get("disc", 0) or 0),
            explicit=bool(raw.get("explicit", False)),
            popularity=int(raw.get("popularity", 0) or 0),
            isrc=raw.get("isrc", "") or "",
            quality=raw.get("quality", "") or "",
            # A queue written before uids existed simply gets fresh ones.
            uid=_claim_uid(int(raw["uid"])) if "uid" in raw else _new_uid(),
        )


class Queue:
    """Ordered entries plus the cursor, shuffle order and repeat mode.

    Shuffle is a permutation held alongside the list rather than a reordering
    of it, so toggling shuffle off restores the original order and the
    displayed numbering never changes under the user.
    """

    def __init__(self) -> None:
        self.entries: list[Entry] = []
        self.playing: int = -1
        self.repeat: Repeat = Repeat.NONE
        self._shuffle: bool = False
        self._order: list[int] = []
        # Where the previous session left off, filled in by load().
        self.resume_at: int = -1

    # ----------------------------------------------------------------- basics

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[Entry]:
        return iter(self.entries)

    def __getitem__(self, index: int) -> Entry:
        return self.entries[index]

    @property
    def current(self) -> Entry | None:
        if 0 <= self.playing < len(self.entries):
            return self.entries[self.playing]
        return None

    # -------------------------------------------------------------- mutation

    def replace(self, entries: list[Entry], start: int = -1) -> None:
        self.entries = list(entries)
        self.playing = start
        self._reshuffle()

    def append(self, entries: list[Entry]) -> int:
        """Add to the end. Returns how many were added."""
        self.entries.extend(entries)
        self._reshuffle()
        return len(entries)

    def insert_next(self, entries: list[Entry]) -> int:
        """Put these right after the current track. Returns how many.

        "Next" has to mean next *in play order*, so shuffle is handled too:
        the indices at or past the insertion point shift along, and the new
        ones go straight after the current track's slot in ``_order`` rather
        than being scattered by a reshuffle. With nothing playing there is no
        "after this", and the end of the queue is the next thing to come.
        """
        if not entries:
            return 0
        if not 0 <= self.playing < len(self.entries):
            return self.append(entries)

        at = self.playing + 1
        self.entries[at:at] = entries
        count = len(entries)
        self._order = [i if i < at else i + count for i in self._order]
        self._order[self._position() + 1 : self._position() + 1] = range(at, at + count)
        return count

    def remove(self, index: int) -> None:
        if not 0 <= index < len(self.entries):
            return
        del self.entries[index]
        if self.playing == index:
            self.playing = -1
        elif self.playing > index:
            self.playing -= 1
        self._reshuffle()

    def move(self, index: int, delta: int) -> int:
        """Move one entry up or down. Returns its new index.

        The shuffled playback order is remapped rather than regenerated: the
        two indices swap inside ``_order``, so each position in the shuffle
        still points at the same song and reordering the visible list does not
        silently reshuffle what plays next.
        """
        target = index + delta
        if not (0 <= index < len(self.entries) and 0 <= target < len(self.entries)):
            return index

        self.entries[index], self.entries[target] = (
            self.entries[target],
            self.entries[index],
        )
        for position, value in enumerate(self._order):
            if value == index:
                self._order[position] = target
            elif value == target:
                self._order[position] = index

        if self.playing == index:
            self.playing = target
        elif self.playing == target:
            self.playing = index
        return target

    def clear(self) -> None:
        self.entries.clear()
        self.playing = -1
        self._order.clear()

    # --------------------------------------------------------------- shuffle

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @shuffle.setter
    def shuffle(self, value: bool) -> None:
        self._shuffle = value
        self._reshuffle()

    def _reshuffle(self) -> None:
        self._order = list(range(len(self.entries)))
        if self._shuffle:
            random.shuffle(self._order)
            # Keep the current track at the front so "next" continues from here.
            if self.playing in self._order:
                self._order.remove(self.playing)
                self._order.insert(0, self.playing)

    # ------------------------------------------------------------- traversal

    def _position(self) -> int:
        """Index of the current track within the playback order."""
        if self.playing in self._order:
            return self._order.index(self.playing)
        return -1

    def next_index(self) -> int | None:
        """The index to play after this one, or None when the queue is done."""
        if not self.entries:
            return None
        if self.repeat is Repeat.TRACK and self.playing >= 0:
            return self.playing
        pos = self._position()
        if pos + 1 < len(self._order):
            return self._order[pos + 1]
        if self.repeat is Repeat.QUEUE:
            return self._order[0] if self._order else None
        return None

    def prev_index(self) -> int | None:
        if not self.entries:
            return None
        pos = self._position()
        if pos > 0:
            return self._order[pos - 1]
        if self.repeat is Repeat.QUEUE and self._order:
            return self._order[-1]
        return None

    def has_next(self) -> bool:
        return self.next_index() is not None

    def has_prev(self) -> bool:
        return self.prev_index() is not None

    # ------------------------------------------------------------ persistence

    def save(self) -> None:
        """Write the queue to disk. Failures are non-fatal by design."""
        try:
            ensure_dirs()
            QUEUE_FILE.write_text(
                json.dumps(
                    {
                        "entries": [e.to_dict() for e in self.entries],
                        "playing": self.playing,
                        "repeat": self.repeat.value,
                        "shuffle": self._shuffle,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def load(self) -> bool:
        """Restore a saved queue. Returns False when there is nothing to load."""
        if not QUEUE_FILE.exists():
            return False
        try:
            raw = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False

        self.entries = [Entry.from_dict(e) for e in raw.get("entries", [])]
        # A restored queue is never mid-playback: mpv starts empty.
        self.playing = -1
        try:
            self.repeat = Repeat(raw.get("repeat", "None"))
        except ValueError:
            self.repeat = Repeat.NONE
        self._shuffle = bool(raw.get("shuffle", False))
        self._reshuffle()

        # Remember where the user left off so the cursor lands there.
        self.resume_at = int(raw.get("playing", -1))
        return bool(self.entries)
