"""What the player asks of the TIDAL account, besides the music itself.

Which artist «ir al artista» goes to, adding to a playlist, saving the queue
as one, a track's radio and favourites. Each one asks in a worker of its own
group, says what it is doing on the spinner, and answers on the status line.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from . import auth, levels, library, playlists
from .i18n import _
from .levels import Row
from .queue import Entry
from .screens import ChoiceScreen, RowList, favourite_message
from .widgets import Spinner
from .workers import thread_worker

if TYPE_CHECKING:
    from .app import TidalAmp


class LibraryTasks:
    """The player's errands to the TIDAL account, each in a worker of its own."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        # What is waiting for a destination while the picker is open.
        self.pending_playlist: list[Entry] = []

    @property
    def node(self) -> TidalAmp:
        return self.app

    def choose_artist(
        self, entry: Entry, spinner: Spinner, then: Callable[[int], None]
    ) -> None:
        """Which of the track's artists «ir al artista» goes to, then ``then``.

        One artist goes straight there. Several are listed to pick from: going
        to the main one left the others out of reach. Shared by the queue and
        the browser; ``spinner`` is whichever of the two is on screen.
        """
        spinner.start(_("buscando el artista…"))
        self.artists_worker(entry, spinner, then)

    @thread_worker(group="artists")
    def artists_worker(
        self, entry: Entry, spinner: Spinner, then: Callable[[int], None]
    ) -> None:
        try:
            artists = library.track_artists(self.app.session, entry)
        except Exception as exc:
            self.app.call_from_thread(self.artists_failed, spinner, exc)
            return
        self.app.call_from_thread(self.artists_found, artists, spinner, then)

    def artists_found(
        self,
        artists: list[tuple[int, str]],
        spinner: Spinner,
        then: Callable[[int], None],
    ) -> None:
        spinner.stop()
        if len(artists) == 1:
            then(artists[0][0])
            return
        self.app.push_screen(
            ChoiceScreen(_("¿QUÉ ARTISTA?"), artists, artists[0][0]),
            lambda ident: then(cast(int, ident)) if ident else None,
        )

    def artists_failed(self, spinner: Spinner, exc: Exception) -> None:
        spinner.stop()
        self.app.status = _("no se pudo abrir: {error}").format(error=exc)

    def playlist_chosen(self, key: str | None) -> None:
        entries, self.pending_playlist = self.pending_playlist, []
        if key is None or not entries:
            return
        # The row's cache key is `playlist:<id>`; the write wants the id.
        self.app.query_one("#busy", Spinner).start(_("añadiendo a la playlist…"))
        self.add_worker(key.split(":", 1)[-1], entries)

    @thread_worker(group="playlist-add")
    def add_worker(self, playlist_id: str, entries: list[Entry]) -> None:
        try:
            auth.ensure_fresh(self.app.session)
            added = playlists.add_to_playlist(self.app.session, playlist_id, entries)
        except playlists.PlaylistSaveFailed as exc:
            self.app.call_from_thread(
                self.playlist_added,
                _("«{title}»: entraron {added} de {total}").format(
                    title=exc.title, added=exc.added, total=exc.total
                ),
            )
            return
        except Exception as exc:
            self.app.call_from_thread(
                self.playlist_added, _("error: {error}").format(error=exc)
            )
            return
        self.app.call_from_thread(
            self.playlist_added,
            _("{count} pistas añadidas a la playlist").format(count=added),
        )

    def playlist_added(self, message: str) -> None:
        self.app.query_one("#busy", Spinner).stop()
        self.app.status = message

    def save_named(self, result: str | None) -> None:
        title = (result or "").strip()
        if not title:
            return
        # The queue may keep changing while the network worker runs. Save the
        # exact list that was named, not whichever list happens to exist later.
        entries = list(self.app.queue)
        if not entries:
            self.app.status = _("la cola está vacía; no hay nada que guardar")
            return
        self.app.query_one("#busy", Spinner).start(
            _("guardando la cola como «{title}»…").format(title=title)
        )
        self.save_worker(title, entries)

    @thread_worker(group="save-playlist")
    def save_worker(self, title: str, entries: list[Entry]) -> None:
        try:
            auth.ensure_fresh(self.app.session)
            added = playlists.save_queue_playlist(self.app.session, title, entries)
        except playlists.PlaylistSaveFailed as exc:
            message = _(
                "playlist «{title}» creada con {added} de {total} pistas: {error}"
            ).format(
                title=exc.title,
                added=exc.added,
                total=exc.total,
                error=exc,
            )
        except Exception as exc:
            message = _("no se pudo guardar la cola: {error}").format(error=exc)
        else:
            message = _("playlist «{title}» creada con {count} pistas").format(
                title=title, count=added
            )
        self.app.call_from_thread(self.save_done, message)

    def save_done(self, message: str) -> None:
        self.app.query_one("#busy", Spinner).stop()
        self.app.status = message

    # Its own group, like the other two: an exclusive worker cancels its
    # group, and the resolve worker feeding playback is not this one's to kill.
    @thread_worker(group="radio")
    def radio_worker(self, entry: Entry) -> None:
        try:
            entries = library.track_radio(self.app.session, entry)
        except Exception as exc:
            self.app.call_from_thread(self.radio_failed, str(exc))
            return
        self.app.call_from_thread(self.radio_ready, entry, entries)

    def radio_failed(self, message: str) -> None:
        self.app.query_one("#busy", Spinner).stop()
        self.app.status = message

    def radio_ready(self, entry: Entry, entries: list[Entry]) -> None:
        self.app.query_one("#busy", Spinner).stop()
        # The seed goes first: a station that opens on a different song looks
        # like the wrong thing started.
        self.app.queue.replace([entry, *entries], start=-1)
        self.app.queue_view.sync()
        self.app.playback.play_index(0)
        self.app.status = _("radio de «{label}»: {count} pistas").format(
            label=entry.label, count=len(entries) + 1
        )

    def favourite_selected(self, add: bool) -> None:
        """Favourite the track under the playlist cursor."""
        if self.app.queue_hidden():
            return
        row = self.app.query_one("#playlist", RowList).current
        if row is None or row.entry is None:
            self.app.status = _("no hay ninguna pista seleccionada")
            return
        self.favourite_row(row, add)

    def favourite_entry(self, entry: Entry) -> None:
        """Favourite one entry, for the browser's action menu."""
        self.favourite_row(Row(label=entry.label, entry=entry), True)

    def favourite_row(self, row: Row, add: bool) -> None:
        self.app.query_one("#busy", Spinner).start(
            _("añadiendo a favoritos…") if add else _("quitando de favoritos…")
        )
        self.favourite_worker(row, add)

    @thread_worker(group="favourite")
    def favourite_worker(self, row: Row, add: bool) -> None:
        try:
            message = favourite_message(self.app.session, row, add)
        except Exception as exc:
            self.app.call_from_thread(
                self.favourite_done, _("favoritos: {error}").format(error=exc)
            )
            return
        self.app.call_from_thread(self.favourite_done, message)

    def favourite_done(self, message: str) -> None:
        self.app.query_one("#busy", Spinner).stop()
        self.app.status = message
        # Whatever favourites level is cached is now out of date.
        for level in ("fav:tracks", "fav:albums", "fav:artists"):
            levels.forget(level)
