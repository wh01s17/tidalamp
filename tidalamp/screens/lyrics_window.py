"""The lyrics window that `y` opens."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..i18n import _
from ..lyrics import LyricsDocument, fit, last_start
from ..queue import Entry
from ..theme import palette_for
from ..widgets import Glide, Spinner

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    pass


class LyricsScreen(ModalScreen[None]):
    """Lyrics for the playing track, synchronized to the player when LRC is present.

    It follows the track rather than keeping the one it opened on: while it
    is in front the app's keys do not reach the player, but the media keys
    (MPRIS) and the end of a song still move the queue on.
    """

    BINDINGS = [
        Binding("escape,y", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("pageup", "page_up", "", show=False),
        Binding("pagedown", "page_down", "", show=False),
    ]

    def __init__(
        self,
        current: Callable[[], Entry | None],
        loader: Callable[[Entry], LyricsDocument],
        position: Callable[[], float],
    ) -> None:
        super().__init__()
        self._current = current
        self._loader = loader
        self._position = position
        entry = current()
        self._entry_id = entry.id if entry is not None else None
        self._track_title = entry.label if entry is not None else ""
        self._document: LyricsDocument | None = None
        self._plain_offset = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="lyrics-box"):
            with Horizontal(id="lyrics-head"):
                # A Glide, not a Static: a Static wrapped the title on words
                # and a head one row tall hid everything after the first break.
                yield Glide(
                    _("▓ LETRA ▓  {title}").format(title=self._track_title),
                    id="lyrics-title",
                )
                yield Spinner(id="lyrics-spinner")
            yield Static("  " + _("cargando…"), id="lyrics-body", markup=False)
            yield Static(_(" ↑↓ desplazar   y/esc cerrar"), id="lyrics-hint")

    def on_mount(self) -> None:
        self._start()
        self.set_interval(1 / 4, self._tick)

    def _start(self) -> None:
        """Ask for the lyrics of the track the window is on, from scratch."""
        self._document = None
        self._plain_offset = 0
        self.query_one("#lyrics-title", Glide).update(
            _("▓ LETRA ▓  {title}").format(title=self._track_title)
        )
        entry = self._current()
        if entry is None or entry.id != self._entry_id:
            self.query_one("#lyrics-body", Static).update(
                "  " + _("no hay una pista reproduciéndose")
            )
            return
        self.query_one("#lyrics-body", Static).update("  " + _("cargando…"))
        self.query_one(Spinner).start(_("buscando la letra…"))
        self._load(entry)

    def _tick(self) -> None:
        entry = self._current()
        wanted = entry.id if entry is not None else None
        if wanted != self._entry_id:
            self._entry_id = wanted
            self._track_title = entry.label if entry is not None else ""
            self.query_one(Spinner).stop()
            self._start()
            return
        self._refresh_lyrics()

    @work(thread=True, exclusive=True)
    def _load(self, entry: Entry) -> None:
        try:
            document = self._loader(entry)
        except Exception as exc:
            self.app.call_from_thread(self._failed, entry.id, exc)
            return
        self.app.call_from_thread(self._loaded, entry.id, document)

    def _loaded(self, entry_id: int, document: LyricsDocument) -> None:
        # The track moved on while its lyrics were in flight.
        if entry_id != self._entry_id:
            return
        self.query_one(Spinner).stop()
        self._document = document
        mode = _("sincronizada") if document.synced else _("texto")
        provider = f" · {document.provider}" if document.provider else ""
        self.query_one("#lyrics-title", Glide).update(
            _("▓ LETRA ▓  {title} · {mode}{provider}").format(
                title=self._track_title, mode=mode, provider=provider
            )
        )
        self._refresh_lyrics()

    def _failed(self, entry_id: int, exc: Exception) -> None:
        if entry_id != self._entry_id:
            return
        self.query_one(Spinner).stop()
        self.query_one("#lyrics-body", Static).update(f"  {exc}")

    def _refresh_lyrics(self) -> None:
        document = self._document
        if document is None:
            return
        body = self.query_one("#lyrics-body", Static)
        height = max(5, body.content_size.height)
        # Wrapped here, not by the Static: it counted as one line what it
        # drew on two or three rows, and brought the second row back under
        # the marker instead of under the text.
        width = max(10, body.content_size.width - self.MARKER)
        wrapped = [self._wrap(line.text, width) for line in document.lines]
        rows = [len(parts) for parts in wrapped]
        if document.synced:
            active = document.active_index(self._position())
            start, end = fit(rows, active or 0, height)
        else:
            active = None
            self._plain_offset = max(0, min(self._plain_offset, last_start(rows, height)))
            start = self._plain_offset
            end = fit(rows[start:], 0, height)[1] + start

        rendered = Text(no_wrap=True, overflow="crop")
        palette = palette_for(self)
        for index in range(start, end):
            style = (
                f"bold {palette['active_foreground']} on {palette['accent']}"
                if index == active
                else palette["body"]
            )
            for row, part in enumerate(wrapped[index]):
                marker = "▶ " if index == active and row == 0 else "  "
                rendered.append(f"{marker}{part}\n", style=style)
        body.update(rendered)

    # The cells the marker, «▶ » or two spaces, takes at the start of a row.
    MARKER = 2

    def _wrap(self, text: str, width: int) -> list[str]:
        """``text`` in rows of at most ``width`` cells, split between words."""
        if not text:
            return [""]
        return [part.plain.rstrip() for part in Text(text).wrap(self.app.console, width)]

    def _scroll_plain(self, amount: int) -> None:
        if self._document is None or self._document.synced:
            return
        self._plain_offset += amount
        self._refresh_lyrics()

    def action_up(self) -> None:
        self._scroll_plain(-1)

    def action_down(self) -> None:
        self._scroll_plain(1)

    def action_page_up(self) -> None:
        self._scroll_plain(-8)

    def action_page_down(self) -> None:
        self._scroll_plain(8)

    def action_close(self) -> None:
        self.dismiss(None)
