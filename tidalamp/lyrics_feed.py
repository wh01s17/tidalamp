"""Where the player's lyrics come from, and the split view's pane.

`y`, the split pane and the full-screen panel all ask `LyricsFeed.for_entry`,
which caches per track; the pane follows the playing track and its line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import auth, lyrics
from .i18n import _
from .lyrics import LyricsDocument, LyricsUnavailable
from .net import with_retries
from .queue import Entry
from .widgets import LyricsPane
from .workers import thread_worker

if TYPE_CHECKING:
    from .app import TidalAmp


class LyricsFeed:
    """Every lyrics view's one door to the words, and the split pane's."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        self.cache: dict[int, LyricsDocument] = {}
        # Which track the split view's lyrics pane was last asked to show, so
        # the tick fetches once per track rather than four times a second.
        self.pane_entry: int | None = None

    @property
    def node(self) -> TidalAmp:
        return self.app

    def for_entry(self, entry: Entry) -> LyricsDocument:
        """The lyrics of a track, cached per entry.

        The single door every lyrics view goes through — `y`, the split
        pane and the full-screen panel — which is why the guard for a row
        that is not TIDAL's lives here and nowhere else. TIDAL is the only
        provider, and it has nothing to say about a track outside its
        catalogue: the views already draw a `LyricsUnavailable` as the
        message under the title.
        """
        cached = self.cache.get(entry.id)
        if cached is not None:
            return cached
        if not entry.is_tidal:
            raise LyricsUnavailable(
                _("«{name}» no viene de TIDAL, que es de donde salen las letras").format(
                    name=entry.title
                )
            )
        auth.ensure_fresh(self.app.session)
        track = with_retries(lambda: entry.resolve(self.app.session))
        document = lyrics.load_lyrics(track)
        self.cache[entry.id] = document
        return document

    def follow(self, position: float) -> None:
        """Keep the split view's lyrics on the playing track and line.

        The fetch happens once per track, in a worker, through the same cache
        `y` uses; everything else is the pane comparing line numbers.
        """
        pane = self.app.query_one(LyricsPane)
        entry = self.app.queue.current
        wanted = entry.id if entry is not None else None
        if wanted != self.pane_entry:
            self.pane_entry = wanted
            if entry is None:
                pane.show(None, _("no hay una pista reproduciéndose"))
            else:
                pane.show(None, _("buscando la letra…"))
                self.pane_worker(entry)
        pane.follow(position, self.app.mpv.duration)

    @thread_worker(group="pane-lyrics")
    def pane_worker(self, entry: Entry) -> None:
        try:
            document = self.for_entry(entry)
        except Exception as exc:
            self.app.call_from_thread(self.pane_loaded, entry.id, None, str(exc))
            return
        self.app.call_from_thread(self.pane_loaded, entry.id, document, "")

    def pane_loaded(
        self, entry_id: int, document: LyricsDocument | None, message: str
    ) -> None:
        # The track moved on while its lyrics were in flight.
        if entry_id != self.pane_entry:
            return
        self.app.query_one(LyricsPane).show(document, message)
