"""The queue as the player shows it.

The rows the widget holds are the ones the filter lets through, so a row on
screen is no longer the same number as a position in the queue: `shown` is
the map between the two, and every action that acts on a track goes through
it. The album years, which a track listing does not carry, are fetched here
too, out of the way.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from textual.containers import Horizontal
from textual.widgets import Input, Static

from . import config, levels, library
from .i18n import _
from .levels import Row
from .queue import Entry, Repeat
from .screens import (
    BrowserScreen,
    CreditsScreen,
    FullscreenScreen,
    PlaylistPickerScreen,
    RowList,
    TrackActionsScreen,
    actions_for,
)
from .widgets import Spinner
from .workers import thread_worker

if TYPE_CHECKING:
    from .app import TidalAmp


class QueueView:
    """The queue on screen: its rows, its filter, and the map between them."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        # What `C` threw away, kept for one undo. In memory only: the file is
        # already overwritten by the time anyone can press the key.
        self.cleared: tuple[list[Entry], int] | None = None
        # What the queue is narrowed to, and which queue positions that
        # leaves on screen. Empty filter means every position, in order.
        self.filter = ""
        self.shown: list[int] = []

    @property
    def node(self) -> TidalAmp:
        return self.app

    def refresh_title(self) -> None:
        widget = self.app.query_one("#pl-title", Static)
        hints = (
            _("↵ reproducir · ↑↓ navegar")
            if self.app.looks.compact
            else _("↵ reproducir · ↑↓ navegar · d quitar · alt+↑↓ mover")
        )
        widget.update(self.app.looks.layout.queue_heading(widget.size.width, hints))

    def sync(self) -> None:
        """Push the queue into the playlist widget, through the filter.

        The widget only ever holds the rows the filter lets through, so a row
        on screen is no longer the same number as a position in the queue.
        `shown` is the map between the two, and every action that acts on a
        track goes through it.
        """
        playlist = self.app.query_one("#playlist", RowList)
        # Where the cursor was, in queue terms, so a queue that changed under
        # it — or a filter that just narrowed — leaves it on the same track.
        was = self.index_at(playlist.cursor)
        rows = [
            Row(label=entry.label, detail=entry.length, entry=entry, number=position + 1)
            for position, entry in enumerate(self.app.queue)
        ]
        self.shown = [
            position
            for position, row in enumerate(rows)
            if not self.filter or levels.matches(self.filter, row)
        ]
        playlist.rows = [rows[position] for position in self.shown]
        playlist.cursor = max(0, self.row_at(was))
        playlist.marked = self.row_at(self.app.queue.playing)
        playlist.refresh()
        self.render_filter()
        # Every edit to the queue comes through here, and any of them can
        # change which track is next.
        self.app.prefetch.check()
        self.app.saved(self.app.queue.save())
        self.fill_years()
        fullscreen = self.app.fullscreen_view()
        if fullscreen is not None:
            fullscreen.mirror_queue()

    def fill_years(self) -> None:
        """Ask TIDAL for the years the queue is missing, out of the way.

        The year is the one column a track listing does not carry, so it costs
        a request per album. That happens here rather than while the level
        loads: the rows go up straight away and the years arrive a moment
        later, instead of every level taking a second per record it holds.

        Nobody pays for a column they turned off.
        """
        if "year" not in config.COLUMNS:
            return
        wanted = {
            entry.album_id
            for entry in self.app.queue
            if entry.year == 0 and entry.album_id > 0
        }
        if wanted:
            self.years_worker(sorted(wanted))

    @thread_worker(group="years")
    def years_worker(self, album_ids: list[int]) -> None:
        found = {
            album: library.album_year(self.app.session, album) for album in album_ids
        }
        if any(found.values()):
            self.app.call_from_thread(self.years_ready, found)

    def years_ready(self, found: dict[int, int]) -> None:
        """Write what came back onto the queue and redraw it.

        Straight onto the entries rather than through a setter: the year is a
        detail of the record, not a change to the queue, and nothing about the
        order or the playing track has moved.
        """
        for entry in self.app.queue:
            if entry.year == 0:
                entry.year = found.get(entry.album_id, 0)
        self.app.saved(self.app.queue.save())
        self.app.query_one("#playlist", RowList).refresh()
        self.app.readout.refresh_track_meta()

    def index_at(self, cursor: int) -> int:
        """Which track in the queue the row at ``cursor`` is. -1 when none."""
        if 0 <= cursor < len(self.shown):
            return self.shown[cursor]
        return -1

    def cursor_index(self) -> int:
        """The queue position under the cursor. -1 when the queue is empty."""
        return self.index_at(self.app.query_one("#playlist", RowList).cursor)

    def row_at(self, position: int) -> int:
        """Where queue position ``position`` sits on screen.

        -1 when the filter is hiding it, which is a real answer: the track
        playing right now may well not be one of the ones being searched for.
        """
        try:
            return self.shown.index(position)
        except ValueError:
            return -1

    def render_filter(self) -> None:
        """The count next to the search box: how much of the queue is left."""
        if not self.app.query("#queue-filter-bar"):
            return
        if not self.app.query_one("#queue-filter-bar", Horizontal).display:
            return
        self.app.query_one("#queue-filter-count", Static).update(
            _("{shown} de {total}").format(
                shown=len(self.shown), total=len(self.app.queue)
            )
            if self.filter
            else _("{total} en la cola").format(total=len(self.app.queue))
        )

    def clear_filter(self) -> None:
        """Drop the filter and close its bar, leaving the cursor on the track
        it was on: narrowing the queue is how you reach a track in it."""
        self.filter = ""
        self.app.query_one("#queue-filter", Input).value = ""
        self.app.query_one("#queue-filter-bar", Horizontal).display = False
        self.app.set_focus(None)
        self.sync()

    def track_menu(self) -> None:
        """Open the track menu on the queue row under the cursor.

        The same menu the browser opens with ↵. There it had to be asked for
        because ↵ already queued the whole level; here ↵ plays the row, and
        the menu is what carries everything else it can do.
        """
        if self.app.queue_hidden():
            return
        row = self.app.query_one("#playlist", RowList).current
        if row is None or row.entry is None:
            self.app.status = _("no hay ninguna pista seleccionada")
            return
        self.app.push_screen(
            TrackActionsScreen(row.entry.label, actions_for(row.entry)),
            self.menu_chosen,
        )

    def menu_chosen(self, action: str | None) -> None:
        """Act on a queue row the way the browser acts on one of its own.

        `play` is the one that differs: in the browser it queues the level and
        starts there, and here the level *is* the queue, so it only has to
        start. Everything else is the same call the browser's answer makes.
        """
        if action is None:
            return
        index = self.cursor_index()
        if index < 0:
            return
        if action == "play":
            self.app.playback.play_index(index)
            return
        entry = self.app.queue[index]
        if action == "artist":
            self.app.tasks.choose_artist(
                entry,
                self.app.query_one("#busy", Spinner),
                functools.partial(self.open_browser_at, entry, "artist"),
            )
            return
        if action == "album":
            self.open_browser_at(entry, "album")
            return
        if action == "credits":
            self.app.push_screen(CreditsScreen(entry))
            return
        self.browser_answered((action, [entry], 0))

    def open_browser_at(self, entry: Entry, kind: str, artist_id: int = 0) -> None:
        """The browser is not open from the queue: it opens at the library's
        root with that level already on top, so ⌫ goes back to the root."""
        self.app.push_screen(
            BrowserScreen(
                _("MI BIBLIOTECA"),
                lambda: library.root(self.app.session),
                goto=functools.partial(
                    library.go_to, self.app.session, entry, kind, artist_id
                ),
                busy=(
                    _("buscando el artista…")
                    if kind == "artist"
                    else _("buscando el álbum…")
                ),
            ),
            self.browser_answered,
        )

    def open_filter(self) -> None:
        """Open the search bar under the queue and start typing into it."""
        if isinstance(self.app.screen, FullscreenScreen):
            # The bar lives under the player's queue, behind this view.
            self.app.status = _("la búsqueda de la cola está en el reproductor")
            return
        self.app.query_one("#queue-filter-bar", Horizontal).display = True
        self.render_filter()
        self.app.query_one("#queue-filter", Input).focus()

    def close_filter(self) -> None:
        """esc undoes the last thing that happened, and nothing else."""
        if self.app.query_one("#queue-filter-bar", Horizontal).display:
            self.clear_filter()

    def to_playing(self) -> None:
        """Put the queue cursor back on the track that is playing."""
        if isinstance(self.app.screen, FullscreenScreen):
            # In the full-screen view, `g` is a way to the queue: it opens.
            self.app.screen.open_queue()
        if self.app.queue.playing < 0:
            self.app.status = _("no hay una pista reproduciéndose")
            return
        row = self.row_at(self.app.queue.playing)
        if row < 0:
            self.clear_filter()
            row = self.row_at(self.app.queue.playing)
        if row < 0:
            return
        playlist = self.app.query_one("#playlist", RowList)
        playlist.cursor = row
        playlist.marked = row
        playlist.refresh()

    def browser_answered(self, result: tuple | None) -> None:
        if result is None:
            return
        action, entries, index = result
        if not entries:
            self.app.status = _("nada que añadir")
            return
        if action == "play":
            self.app.queue.replace(entries, start=-1)
            self.sync()
            self.app.playback.play_index(index)
        elif action == "next":
            self.app.queue.insert_next(entries)
            self.sync()
            self.app.status = (
                _("«{label}» sonará a continuación").format(label=entries[0].label)
                if len(entries) == 1
                else _("{count} pistas sonarán a continuación").format(count=len(entries))
            )
        elif action == "playlist":
            self.app.tasks.pending_playlist = list(entries)
            self.app.push_screen(
                PlaylistPickerScreen(self.app.session), self.app.tasks.playlist_chosen
            )
        elif action == "radio":
            self.app.query_one("#busy", Spinner).start(
                _("buscando la radio de «{label}»…").format(label=entries[0].label)
            )
            self.app.tasks.radio_worker(entries[0])
        elif action == "favourite":
            self.app.tasks.favourite_entry(entries[0])
        else:
            added = self.app.queue.append(entries)
            self.sync()
            self.app.status = _("{count} pistas añadidas a la cola").format(count=added)

    def remove(self) -> None:
        if self.app.queue_hidden():
            return
        index = self.cursor_index()
        if index >= 0:
            self.app.queue.remove(index)
            self.sync()
            self.app.status = _("pista quitada de la cola")

    def move_entry(self, delta: int) -> None:
        """Move the track under the cursor one place along the queue.

        Under a filter the rows on screen may not visibly reorder — the track
        it swapped with can be one the filter is hiding — but the number at
        the head of the line is the queue position, and that does change.
        """
        if self.app.queue_hidden():
            return
        index = self.cursor_index()
        if index < 0:
            return
        moved = self.app.queue.move(index, delta)
        if moved == index:
            return
        self.sync()
        playlist = self.app.query_one("#playlist", RowList)
        playlist.cursor = max(0, self.row_at(moved))
        playlist.refresh()

    def clear(self) -> None:
        # One key away from `c`, which stops. A slipped shift used to be the
        # end of a queue that took half an hour to build, and since a queue
        # can be saved to TIDAL it is worth more than it was.
        cursor = self.cursor_index()
        self.cleared = (
            (list(self.app.queue), max(0, cursor)) if len(self.app.queue) else None
        )
        self.app.playback.stop()
        self.app.queue.clear()
        self.sync()
        self.app.cover.url = ""
        self.app.cover.pending = None
        widget = self.app.cover.widget()
        if widget is not None:
            widget.show(None)
        self.app.status = _("cola vaciada")

    def undo_clear(self) -> None:
        """Put back what `C` threw away, once.

        It does not start playing again. Clearing stopped the music, and
        undoing gives back the list, not the sound: a song starting on its own
        because someone undid a mistake is a worse surprise than the mistake.
        """
        if self.cleared is None:
            self.app.status = _("no hay ningún vaciado que deshacer")
            return
        entries, cursor = self.cleared
        # One level. A second would be a history nobody asked for, and this
        # exists for the slip of two seconds ago.
        self.cleared = None
        self.app.queue.replace(entries, start=-1)
        self.sync()
        playlist = self.app.query_one("#playlist", RowList)
        playlist.cursor = max(0, self.row_at(cursor))
        playlist.refresh()
        self.app.status = _("cola restaurada ({count} pistas)").format(count=len(entries))

    def shuffle(self) -> None:
        self.app.queue.shuffle = not self.app.queue.shuffle
        self.app.saved(self.app.queue.save())
        self.app.prefetch.check()
        self.app.transport.refresh()
        self.app.status = (
            _("shuffle activado") if self.app.queue.shuffle else _("shuffle desactivado")
        )

    def repeat(self) -> None:
        self.app.queue.repeat = self.app.queue.repeat.next()
        self.app.saved(self.app.queue.save())
        self.app.prefetch.check()
        self.app.transport.refresh()
        names = {
            Repeat.NONE: _("sin repetición"),
            Repeat.QUEUE: _("repetir cola"),
            Repeat.TRACK: _("repetir pista"),
        }
        self.app.status = names[self.app.queue.repeat]
