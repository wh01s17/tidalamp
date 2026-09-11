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
from ..lyrics import LyricsDocument
from ..theme import palette_for
from ..widgets import Spinner

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    pass


class LyricsScreen(ModalScreen[None]):
    """Lyrics for one track, synchronized to the player when LRC is present."""

    BINDINGS = [
        Binding("escape,y", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("pageup", "page_up", "", show=False),
        Binding("pagedown", "page_down", "", show=False),
    ]

    def __init__(
        self,
        title: str,
        loader: Callable[[], LyricsDocument],
        position: Callable[[], float],
    ) -> None:
        super().__init__()
        self._track_title = title
        self._loader = loader
        self._position = position
        self._document: LyricsDocument | None = None
        self._plain_offset = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="lyrics-box"):
            with Horizontal(id="lyrics-head"):
                yield Static(
                    _("▓ LETRA ▓  {title}").format(title=self._track_title),
                    id="lyrics-title",
                    markup=False,
                )
                yield Spinner(id="lyrics-spinner")
            yield Static("  " + _("cargando…"), id="lyrics-body", markup=False)
            yield Static(_(" ↑↓ desplazar   y/esc cerrar"), id="lyrics-hint")

    def on_mount(self) -> None:
        self.query_one(Spinner).start(_("buscando la letra…"))
        self._load()
        self.set_interval(1 / 4, self._refresh_lyrics)

    @work(thread=True, exclusive=True)
    def _load(self) -> None:
        try:
            document = self._loader()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self._loaded, document)

    def _loaded(self, document: LyricsDocument) -> None:
        self.query_one(Spinner).stop()
        self._document = document
        mode = _("sincronizada") if document.synced else _("texto")
        provider = f" · {document.provider}" if document.provider else ""
        self.query_one("#lyrics-title", Static).update(
            _("▓ LETRA ▓  {title} · {mode}{provider}").format(
                title=self._track_title, mode=mode, provider=provider
            )
        )
        self._refresh_lyrics()

    def _failed(self, exc: Exception) -> None:
        self.query_one(Spinner).stop()
        self.query_one("#lyrics-body", Static).update(f"  {exc}")

    def _refresh_lyrics(self) -> None:
        document = self._document
        if document is None:
            return
        body = self.query_one("#lyrics-body", Static)
        height = max(5, body.size.height)
        if document.synced:
            start, lines, active = document.window(self._position(), height)
        else:
            self._plain_offset = max(
                0, min(self._plain_offset, max(0, len(document.lines) - height))
            )
            start = self._plain_offset
            lines = document.lines[start : start + height]
            active = None

        rendered = Text()
        palette = palette_for(self)
        for offset, line in enumerate(lines):
            index = start + offset
            marker = "▶ " if index == active else "  "
            style = (
                f"bold {palette['active_foreground']} on {palette['accent']}"
                if index == active
                else palette["body"]
            )
            rendered.append(f"{marker}{line.text}\n", style=style)
        body.update(rendered)

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
