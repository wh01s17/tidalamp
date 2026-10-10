"""The next track, ahead of time.

The next track is resolved while this one plays and queued in mpv, so the
two songs meet without the silence a request to TIDAL would put between them.
Its cover and, if something on screen shows them, its lyrics are fetched into
their caches on the way. Only the entry the queue says is next is ever kept.
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, NamedTuple

from . import artwork, auth, lyrics, stream
from .queue import Entry
from .screens import LyricsScreen
from .stream import Playable, gain_for
from .workers import thread_worker

if TYPE_CHECKING:
    from .app import TidalAmp


class Prepared(NamedTuple):
    """The next track, resolved ahead and already queued in mpv."""

    entry: Entry
    playable: Playable
    # When it was resolved: its URL expires, so it is not kept forever.
    at: float


class Prefetcher:
    """Resolves the next track ahead and queues it in mpv, for no gap."""

    # How long before the end the next track is resolved. The URL TIDAL hands
    # out expires, so not as soon as a track starts; twenty seconds is room
    # for a slow answer and a retry, and for mpv to open it ahead.
    PREFETCH_LEAD = 20.0
    # How long a resolved track may wait, queued, before it is resolved
    # again: a track paused near its end would otherwise go on to a URL that
    # expired while nobody listened.
    PREPARED_TTL = 300.0

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        # The next track, while it resolves ahead and once it is queued in
        # mpv; and the one whose resolve ahead failed, so the tick does not
        # ask again four times a second. Only the entry the queue says is
        # next is ever kept: `check` drops anything else.
        self.prefetching: Entry | None = None
        self.prepared: Prepared | None = None
        self.failed: Entry | None = None

    @property
    def node(self) -> TidalAmp:
        return self.app

    def next_entry(self) -> Entry | None:
        index = self.app.queue.next_index()
        return None if index is None else self.app.queue[index]

    def start(self, position: float, duration: float) -> None:
        """Resolve the next track while this one plays, and queue it in mpv.

        Without it, the next track was only asked of TIDAL once this one had
        ended, and the silence between the two songs was that request: on a
        live album or a concept record, a gap where the record has none.
        """
        if (
            self.prefetching is not None
            or self.app.playback.resolving is not None
            or self.app.queue.playing < 0
            or duration <= 0
            or duration - position > self.PREFETCH_LEAD
        ):
            return
        entry = self.next_entry()
        if entry is None or entry is self.failed:
            return
        prepared = self.prepared
        if prepared is not None:
            if (
                prepared.entry is entry
                and time.monotonic() - prepared.at < self.PREPARED_TTL
            ):
                return
            self.drop()
        self.prefetching = entry
        # The lyrics only when something on screen follows the playing track
        # with them: otherwise it is a request per track nobody reads.
        view = self.app.fullscreen_view()
        with_lyrics = (
            self.app.looks.split
            or (view is not None and view.lyrics_open)
            or any(isinstance(screen, LyricsScreen) for screen in self.app.screen_stack)
        )
        self.worker(entry, with_lyrics)

    @thread_worker(group="prefetch")
    def worker(self, entry: Entry, with_lyrics: bool = False) -> None:
        try:
            if entry.is_tidal:
                auth.ensure_fresh(self.app.session)
            playable = stream.playable_for(entry, self.app.session)
        except Exception:
            # Quietly: the track after this one is not what the user is
            # listening to. When its turn comes it is resolved as ever, and
            # a failure then says why.
            self.app.call_from_thread(self.gave_up, entry)
            return
        self.app.call_from_thread(self.landed, entry, playable)
        self.warm(entry, with_lyrics)

    def warm(self, entry: Entry, with_lyrics: bool) -> None:
        """Fetch the next track's cover, and its lyrics if asked, into their
        caches. The sound starts with no gap, and without this the cover and
        the lyrics then came in a moment after it, off the network.

        After the audio is queued, never before: this is decoration. Only the
        download is done ahead; drawing depends on the box and the look at
        the time, and from the disk cache it is quick. Failures are silent,
        and the track's own turn fetches again and says why.

        A free row has a cover and no lyrics: TIDAL is the only provider
        here, and it knows nothing about a track that is not in its
        catalogue.
        """
        if entry.art_url and self.app.cover.protocol is not artwork.Protocol.NONE:
            with contextlib.suppress(Exception):
                artwork.fetch(entry.art_url)
        if with_lyrics and entry.is_tidal and entry.id not in self.app.lyrics.cache:
            with contextlib.suppress(Exception):
                # Free: `playable_for` already resolved it a moment ago and
                # the Track is cached on the entry.
                self.app.lyrics.cache[entry.id] = lyrics.load_lyrics(
                    entry.resolve(self.app.session)
                )

    def landed(self, entry: Entry, playable: Playable) -> None:
        """Queue what came back, if it is still the track that comes next.

        The same care as `Playback.resolving`: a result for a track the queue no
        longer puts next (shuffle, repeat or an edit moved it meanwhile)
        must not play.
        """
        if entry is not self.prefetching:
            return
        self.prefetching = None
        if (
            self.app.queue.playing < 0
            or self.app.playback.resolving is not None
            or self.next_entry() is not entry
        ):
            return
        self.app.mpv.append(playable.url, gain_for(playable))
        self.prepared = Prepared(entry, playable, time.monotonic())

    def gave_up(self, entry: Entry) -> None:
        if entry is self.prefetching:
            self.prefetching = None
            self.failed = entry

    def advance(self) -> None:
        """mpv went on to the track `landed` queued: follow it."""
        prepared = self.prepared
        assert prepared is not None
        self.prepared = None
        # Keep only what plays now, back at position 0, so that the next one
        # queued is position 1 again.
        self.app.mpv.drop_queued()
        index = self.app.queue.next_index()
        if index is None or self.app.queue[index] is not prepared.entry:
            # Every change to the queue checks what is prepared, so this is
            # not expected; if it happens, the queue is what gets played.
            if index is None:
                self.app.playback.stop()
            else:
                self.app.playback.play_index(index)
            return
        self.app.playback.announce(index)
        self.app.playback.now_playing(prepared.entry, prepared.playable)

    def forget(self) -> None:
        """Forget the track resolved ahead, and one on its way, without
        telling mpv: for callers whose next command to it empties its
        playlist anyway (`load`, `stop`, a restart)."""
        self.prefetching = None
        self.prepared = None

    def drop(self) -> None:
        """Forget the track resolved ahead, and take it out of mpv's playlist."""
        queued = self.prepared is not None
        self.forget()
        if queued:
            self.app.mpv.drop_queued()

    def check(self) -> None:
        """After the queue changed: keep what was prepared only if it is
        still the track that comes next."""
        wanted = self.next_entry() if self.app.queue.playing >= 0 else None
        self.failed = None
        if self.prefetching is not None and self.prefetching is not wanted:
            # Its result is dropped when it lands.
            self.prefetching = None
        if self.prepared is not None and self.prepared.entry is not wanted:
            self.drop()
