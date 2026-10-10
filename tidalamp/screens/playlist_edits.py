"""What the browser does to the favourites and to the playlists you made.

`d` takes a row out of the favourites or of the playlist open, `alt+↑↓`
moves a track inside a playlist of yours, and the menu over one of your
playlists renames it, describes it or deletes it. Each one asks TIDAL in a
worker and then changes the level on screen in place, rather than fetching it
again: TIDAL has it that way now, and asking again would only cost a request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import levels, library, playlists
from ..auth import ensure_fresh
from ..i18n import _
from ..levels import Row
from ..workers import thread_worker
from .choice import ChoiceScreen
from .prompts import PlaylistNameScreen

if TYPE_CHECKING:
    from ..app import TidalAmp
    from .browser import BrowserScreen


def favourite_message(session, row: Row, add: bool) -> str:
    """Do the favourite and phrase the result. Shared by the browser
    and the player."""
    ensure_fresh(session)
    label = library.favourite(session, row, add)
    if add:
        return _("«{label}» añadido a favoritos").format(label=label)
    return _("«{label}» quitado de favoritos").format(label=label)


class PlaylistEdits:
    """The browser's writes to favourites and playlists, and their answers."""

    def __init__(self, screen: BrowserScreen) -> None:
        self.screen = screen
        # A move in a playlist on its way to TIDAL. A second one sent before
        # the first lands would go by a position that is about to change.
        self.moving = False

    @property
    def node(self) -> BrowserScreen:
        return self.screen

    @property
    def player(self) -> TidalAmp:
        return self.screen.player

    def _source(self) -> Row | None:
        """The row that opened the level on screen."""
        stack = self.screen._stack
        return stack[-1][4] if stack else None

    # ------------------------------------------------------------- remove

    def ask_remove(self) -> None:
        """Take the row out of where it is: favourites, or the playlist open.

        Asked first, with the cursor on «cancel», like restarting PipeWire:
        adding a track back to a playlist does not put it back where it was.
        """
        row = self.screen._list().current
        source = self._source()
        where = ""
        if row is not None and row.more is None and source is not None:
            kind, _sep, ident = source.key.partition(":")
            if source.key.startswith("fav:"):
                where = _("favoritos")
            elif kind == "playlist" and ident and row.entry is not None:
                where = f"«{source.label}»"
        if not where or row is None or source is None:
            self.player.status = _("aquí no hay de dónde quitar")
            return
        self.screen.app.push_screen(
            ChoiceScreen(
                _("QUITAR"),
                [
                    (
                        "remove",
                        _("quitar «{label}» de {where}").format(
                            label=row.label, where=where
                        ),
                    ),
                    ("cancel", _("cancelar")),
                ],
                cursor=1,
            ),
            lambda answer: self._remove(row, source) if answer == "remove" else None,
        )

    def _remove(self, row: Row, source: Row) -> None:
        self.screen._busy(_("quitando…"))
        self._remove_worker(row, source)

    @thread_worker(group="remove")
    def _remove_worker(self, row: Row, source: Row) -> None:
        session = self.player.session
        gone: Row | None = row
        try:
            if source.key.startswith("fav:"):
                message = favourite_message(session, row, False)
            else:
                assert row.entry is not None
                ensure_fresh(session)
                playlist = playlists.remove_from_playlist(
                    session, source.key.partition(":")[2], row.entry
                )
                message = _("«{label}» quitada de «{playlist}»").format(
                    label=row.label, playlist=playlist
                )
        except playlists.TrackNotInPlaylist:
            message = _("«{label}» ya no está en la playlist").format(label=row.label)
        except playlists.PlaylistNotWritable as exc:
            title = exc.args[0] if exc.args else ""
            message = _("«{title}» es de otra cuenta: no se puede quitar nada").format(
                title=title
            )
            gone = None
        except Exception as exc:
            message = _("quitar: {error}").format(error=exc)
            gone = None
        self.screen.app.call_from_thread(self._removed, message, gone)

    def _removed(self, message: str, row: Row | None) -> None:
        self.screen._idle()
        self.player.status = message
        if row is not None:
            self.screen._drop(row)

    # ------------------------------------------------- rename and describe

    def ask_edit(self, row: Row, *, rename: bool) -> None:
        """A new name, or a new description, typed over the one it has."""
        self.screen.app.push_screen(
            PlaylistNameScreen(
                title=_("RENOMBRAR PLAYLIST")
                if rename
                else _("DESCRIPCIÓN DE LA PLAYLIST"),
                value=row.label if rename else row.description,
                placeholder=_("nombre de la playlist…") if rename else _("descripción…"),
            ),
            lambda text: self._edit(row, rename, text),
        )

    def _edit(self, row: Row, rename: bool, text: str | None) -> None:
        if text is None:
            return
        text = text.strip()
        # A name cannot be empty; a description can, and that clears it.
        if (rename and (not text or text == row.label)) or (
            not rename and text == row.description
        ):
            return
        self.screen._busy(_("guardando…"))
        self._edit_worker(row, rename, text)

    @thread_worker(group="playlist-edit")
    def _edit_worker(self, row: Row, rename: bool, text: str) -> None:
        session = self.player.session
        ident = row.key.partition(":")[2]
        done: str | None = None
        try:
            ensure_fresh(session)
            if rename:
                playlists.edit_playlist(session, ident, title=text)
                message = _("«{old}» ahora se llama «{new}»").format(
                    old=row.label, new=text
                )
            else:
                playlists.edit_playlist(session, ident, description=text)
                message = _("descripción de «{title}» cambiada").format(title=row.label)
            done = text
        except playlists.PlaylistNotWritable:
            message = _("«{title}» es de otra cuenta: no se puede cambiar").format(
                title=row.label
            )
        except Exception as exc:
            message = _("playlist: {error}").format(error=exc)
        self.screen.app.call_from_thread(self._edited, message, row, rename, done)

    def _edited(self, message: str, row: Row, rename: bool, text: str | None) -> None:
        self.player.status = message
        if not self.screen.is_mounted:
            return
        self.screen._idle()
        if text is None:
            return
        # The row on screen, in place: the cached listing is already dropped,
        # and the next visit asks TIDAL again.
        if rename:
            row.label = text
        else:
            row.description = text
        self.screen._list().refresh()

    # ------------------------------------------------------------- delete

    def ask_delete(self, row: Row) -> None:
        """Asked first, with the cursor on «cancelar»: a deleted playlist
        does not come back."""
        self.screen.app.push_screen(
            ChoiceScreen(
                _("BORRAR PLAYLIST"),
                [
                    ("delete", _("borrar «{title}» de TIDAL").format(title=row.label)),
                    ("cancel", _("cancelar")),
                ],
                cursor=1,
            ),
            lambda answer: self._delete(row) if answer == "delete" else None,
        )

    def _delete(self, row: Row) -> None:
        self.screen._busy(_("borrando…"))
        self._delete_worker(row)

    @thread_worker(group="playlist-edit")
    def _delete_worker(self, row: Row) -> None:
        session = self.player.session
        gone: Row | None = None
        try:
            ensure_fresh(session)
            playlists.delete_playlist(session, row.key.partition(":")[2])
            message = _("«{title}» borrada").format(title=row.label)
            gone = row
        except playlists.PlaylistNotWritable:
            message = _("«{title}» es de otra cuenta: no se puede cambiar").format(
                title=row.label
            )
        except Exception as exc:
            message = _("playlist: {error}").format(error=exc)
        self.screen.app.call_from_thread(self._removed, message, gone)

    # --------------------------------------------------------------- move

    def move(self, delta: int) -> None:
        """`alt+↑` `alt+↓`: move a track inside a playlist of yours.

        Only in the playlist's own order and with no filter: sorted or
        narrowed, the row's place on screen is not its place in TIDAL, and
        the move would land somewhere nobody asked for.
        """
        screen = self.screen
        row = screen._list().current
        source = self._source()
        if (
            row is None
            or row.entry is None
            or source is None
            or not source.editable
            or not source.key.startswith("playlist:")
        ):
            self.player.status = _("solo se reordenan las pistas de tus playlists")
            return
        if levels.chosen(source) is not None or screen._filter:
            self.player.status = _(
                "para mover una pista, la playlist tiene que estar en su orden "
                "y sin filtro"
            )
            return
        if self.moving:
            return
        level = screen._level()
        index = next((i for i, candidate in enumerate(level) if candidate is row), -1)
        other = index + delta
        if index < 0 or other < 0 or other >= len(level):
            return
        if level[other].entry is None:
            # The next row is «más…»: the track that follows is not loaded.
            self.player.status = _(
                "carga la página siguiente con «más…» antes de bajarla"
            )
            return
        self.moving = True
        screen._busy(_("moviendo…"))
        self._move_worker(row, source, index, delta)

    @thread_worker(group="playlist-move")
    def _move_worker(self, row: Row, source: Row, index: int, delta: int) -> None:
        session = self.player.session
        assert row.entry is not None
        moved = 0
        try:
            ensure_fresh(session)
            playlists.move_in_playlist(
                session, source.key.partition(":")[2], row.entry, index, delta
            )
            message = _("«{label}» movida").format(label=row.label)
            moved = delta
        except playlists.MoveNotConfirmed:
            message = _(
                "TIDAL no dejó «{label}» donde se pidió; R recarga la playlist"
            ).format(label=row.label)
        except playlists.TrackNotInPlaylist:
            message = _("«{label}» ya no está en la playlist").format(label=row.label)
        except playlists.PlaylistNotWritable:
            message = _("«{title}» es de otra cuenta: no se puede cambiar").format(
                title=source.label
            )
        except Exception as exc:
            message = _("mover: {error}").format(error=exc)
        self.screen.app.call_from_thread(self._moved, message, row, moved)

    def _moved(self, message: str, row: Row, delta: int) -> None:
        self.moving = False
        self.player.status = message
        screen = self.screen
        if not screen.is_mounted:
            return
        screen._idle()
        if not delta:
            return
        # The two rows swap on screen, in the list the level is: TIDAL has
        # them that way now, and asking again would only cost a request.
        level = screen._level()
        index = next((i for i, candidate in enumerate(level) if candidate is row), -1)
        other = index + delta
        if index < 0 or not 0 <= other < len(level):
            return
        level[index], level[other] = level[other], level[index]
        screen._show(other)
