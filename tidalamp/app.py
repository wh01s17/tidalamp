"""The Winamp-flavoured TUI."""

from __future__ import annotations

from typing import Callable

import tidalapi
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Static

from . import artwork, library
from .auth import NotLoggedIn, ensure_fresh
from .library import Row
from .lyrics import LyricsDocument, load_lyrics
from .mpris import MprisService
from .net import with_retries
from .player import Mpv
from .queue import Entry, Queue, Repeat
from .settings import BAND_LABELS, GAIN_LIMIT, Settings
from .spectrum import Cava, SpectrumUnavailable
from .stream import StreamUnavailable, cleanup_playlists, resolve
from .theme import ThemePalette, load_palette, palette_for
from .widgets import (
    Analyzer,
    Artwork,
    EqualizerBars,
    Marquee,
    SeekBar,
    Slider,
    Spinner,
    TimeDisplay,
)


class RowList(Widget):
    """A scrolling list of rows with a cursor. Used by both panes."""

    cursor = reactive(0)
    marked = reactive(-1)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows: list[Row] = []
        self.empty_text = ""

    def set_rows(self, rows: list[Row]) -> None:
        self.rows = rows
        self.cursor = 0
        self.refresh()

    def extend_at(self, index: int, rows: list[Row]) -> None:
        """Replace the row at ``index`` with ``rows``. This is how a "más…"
        row turns into the page it just fetched, in place, without losing the
        user's scroll position."""
        if not 0 <= index < len(self.rows):
            return
        self.rows[index:index + 1] = rows
        self.cursor = min(index, max(0, len(self.rows) - 1))
        self.refresh()

    def move(self, delta: int) -> None:
        if self.rows:
            self.cursor = max(0, min(len(self.rows) - 1, self.cursor + delta))
            self.refresh()

    @property
    def current(self) -> Row | None:
        if 0 <= self.cursor < len(self.rows):
            return self.rows[self.cursor]
        return None

    def render(self) -> Text:
        palette = palette_for(self)
        if not self.rows:
            return Text(f"  {self.empty_text}", style=palette["empty"])

        height = max(1, self.size.height)
        width = max(20, self.size.width)
        # Keep the cursor in view without a full scrolling container.
        start = max(0, min(self.cursor - height // 2, len(self.rows) - height))
        out = Text()
        for i in range(start, min(len(self.rows), start + height)):
            row = self.rows[i]
            marker = "▶" if i == self.marked else (" " if row.is_playable else "›")
            line = f"{marker}{i + 1:>3}. {row.label}"
            pad = max(1, width - len(line) - len(row.detail) - 1)
            line = f"{line}{' ' * pad}{row.detail}"[:width]
            if i == self.cursor:
                out.append(
                    line,
                    style=(
                        f"bold {palette['active_foreground']} on {palette['accent']}"
                    ),
                )
            elif i == self.marked:
                out.append(line, style=f"bold {palette['accent']}")
            elif not row.is_playable:
                out.append(line, style=palette["container"])
            else:
                out.append(line, style=palette["playable"])
            out.append("\n")
        return out


class SearchScreen(ModalScreen[str]):
    """The search prompt."""

    BINDINGS = [Binding("escape", "dismiss_search", "cancelar")]

    def compose(self) -> ComposeResult:
        with Vertical(id="search-box"):
            yield Static("BUSCAR EN TIDAL", id="search-title")
            yield Input(placeholder="artista, canción o álbum…", id="search-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_dismiss_search(self) -> None:
        self.dismiss("")


class BrowserScreen(ModalScreen[tuple | None]):
    """Drill-down browser over the library and over search results.

    Dismisses with ``("play", entries, index)`` or ``("append", entries, 0)``.
    """

    BINDINGS = [
        Binding("escape", "close", "cerrar"),
        Binding("up", "up", "arriba", show=False),
        Binding("down", "down", "abajo", show=False),
        Binding("pageup", "page_up", "", show=False),
        Binding("pagedown", "page_down", "", show=False),
        Binding("enter", "choose", "abrir/reproducir", show=False),
        Binding("backspace,left", "back", "atrás", show=False),
        Binding("a", "append_one", "añadir", show=False),
        Binding("A", "append_all", "añadir todo", show=False),
        Binding("R", "reload", "recargar", show=False),
    ]

    def __init__(self, title: str, loader, key: str = "") -> None:
        super().__init__()
        self._root_title = title
        self._root_loader = loader
        self._root_key = key
        # Stack of (title, rows, key, loader) so backspace can walk back up and
        # `R` can refetch the level it is looking at.
        self._stack: list[tuple[str, list[Row], str, object]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-box"):
            with Horizontal(id="browser-head"):
                yield Static(self._root_title, id="browser-title")
                yield Spinner(id="browser-spinner")
            yield RowList(id="browser-list")
            yield Static(
                " ↵ abrir/reproducir   a añadir   A añadir todo   ⌫ atrás"
                "   R recargar   esc cerrar",
                id="browser-hint",
            )

    def on_mount(self) -> None:
        self.query_one(RowList).empty_text = "cargando…"
        self._busy(f"cargando {self._root_title.lower()}…")
        self._load(self._root_title, self._root_loader, self._root_key)

    def _busy(self, label: str) -> None:
        self.query_one(Spinner).start(label)

    def _idle(self) -> None:
        self.query_one(Spinner).stop()

    @work(thread=True, exclusive=True)
    def _load(self, title: str, loader, key: str = "") -> None:
        try:
            rows = loader()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self._push, title, rows, key, loader)

    def _failed(self, exc: Exception) -> None:
        self._idle()
        widget = self.query_one(RowList)
        widget.empty_text = f"error: {exc}"
        widget.refresh()

    def _push(self, title: str, rows: list[Row], key: str = "", loader=None) -> None:
        self._idle()
        self._stack.append((title, rows, key, loader))
        widget = self.query_one(RowList)
        widget.empty_text = "vacío"
        widget.set_rows(rows)
        self.query_one("#browser-title", Static).update(title)

    # ------------------------------------------------------------------ keys

    def action_up(self) -> None:
        self.query_one(RowList).move(-1)

    def action_down(self) -> None:
        self.query_one(RowList).move(1)

    def action_page_up(self) -> None:
        self.query_one(RowList).move(-10)

    def action_page_down(self) -> None:
        self.query_one(RowList).move(10)

    def action_back(self) -> None:
        if len(self._stack) <= 1:
            self.dismiss(None)
            return
        # Going back while a level is still loading: the answer, when it
        # lands, is for a level the user has left.
        self._idle()
        self._stack.pop()
        title, rows, _, _ = self._stack[-1]
        widget = self.query_one(RowList)
        widget.set_rows(rows)
        self.query_one("#browser-title", Static).update(title)

    def action_close(self) -> None:
        self.dismiss(None)

    def action_reload(self) -> None:
        """Refetch this level, past the cache.

        Levels are cached for the whole session, which is what makes walking
        the library feel instant — but a playlist created on the phone would
        otherwise never show up until tidalamp restarts. This is the way back.
        """
        if not self._stack:
            return
        title, _, key, loader = self._stack[-1]
        if loader is None:
            return
        library.forget(key)
        self._stack.pop()
        self._busy(f"recargando {title}…")
        self._load(title, loader, key)

    def action_choose(self) -> None:
        widget = self.query_one(RowList)
        row = widget.current
        if row is None:
            return
        if row.more is not None:
            # The title stays put: losing it to say "loading" costs the user
            # the one label that says where they are.
            self._busy("cargando más…")
            self._load_more(widget.cursor, row.more)
            return
        if row.loader is not None:
            self.query_one(RowList).empty_text = "cargando…"
            self._busy(f"abriendo {row.label}…")
            self._load(row.label, row.loader, row.key)
            return
        # Play this track, queueing the whole level so the rest follows.
        entries = [r.entry for r in widget.rows if r.entry is not None]
        index = entries.index(row.entry) if row.entry in entries else 0
        self.dismiss(("play", entries, index))

    @work(thread=True, exclusive=True)
    def _load_more(self, index: int, more) -> None:
        try:
            rows = more()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        self.app.call_from_thread(self._merge, index, rows)

    def _merge(self, index: int, rows: list[Row]) -> None:
        self._idle()
        widget = self.query_one(RowList)
        widget.extend_at(index, rows)
        # The stack holds the level so backspace can restore it; keep it in
        # sync with what is now on screen.
        if self._stack:
            title, _, key, loader = self._stack[-1]
            self._stack[-1] = (title, widget.rows, key, loader)
            self.query_one("#browser-title", Static).update(title)

    def action_append_one(self) -> None:
        row = self.query_one(RowList).current
        if row is None:
            return
        if row.entry is not None:
            self.dismiss(("append", [row.entry], 0))
        elif row.loader is not None:
            # Appending a container means appending everything inside it.
            self._busy(f"añadiendo {row.label}…")
            self._append_container(row.loader)

    @work(thread=True, exclusive=True)
    def _append_container(self, loader) -> None:
        try:
            rows = loader()
        except Exception as exc:
            self.app.call_from_thread(self._failed, exc)
            return
        entries = [r.entry for r in rows if r.entry is not None]
        self.app.call_from_thread(self.dismiss, ("append", entries, 0))

    def action_append_all(self) -> None:
        widget = self.query_one(RowList)
        entries = [r.entry for r in widget.rows if r.entry is not None]
        if entries:
            self.dismiss(("append", entries, 0))
            return
        # A level made only of containers has nothing to append wholesale, so
        # fall back to appending the container under the cursor.
        self.action_append_one()


class EqScreen(ModalScreen[None]):
    """The equaliser window: ten bands and a balance, applied live.

    Every change goes straight to mpv rather than waiting for an OK button —
    an equaliser you cannot hear while you move it is useless.
    """

    BINDINGS = [
        Binding("escape,e", "close", "cerrar"),
        Binding("left", "prev_band", "banda anterior", show=False),
        Binding("right", "next_band", "banda siguiente", show=False),
        Binding("up", "boost", "subir", show=False),
        Binding("down", "cut", "bajar", show=False),
        Binding("0", "reset", "plano", show=False),
        Binding("comma", "balance_left", "balance izq", show=False),
        Binding("full_stop", "balance_right", "balance der", show=False),
        Binding("backslash", "balance_centre", "centrar", show=False),
    ]

    def __init__(self, settings: Settings, apply) -> None:
        super().__init__()
        self.settings = settings
        self._apply = apply

    def compose(self) -> ComposeResult:
        with Vertical(id="eq-box"):
            yield Static("▓ ECUALIZADOR ▓", id="eq-title")
            yield EqualizerBars(id="eq-bars")
            yield Slider(id="eq-balance")
            yield Static(
                " ←→ banda  ↑↓ ±1 dB  0 plano  ,. balance  \\ centro  esc",
                id="eq-hint",
            )

    def on_mount(self) -> None:
        bars = self.query_one(EqualizerBars)
        bars.labels = BAND_LABELS
        bars.limit = GAIN_LIMIT
        balance = self.query_one("#eq-balance", Slider)
        balance.label = "BAL"
        balance.centred = True
        self._redraw()

    def _redraw(self) -> None:
        bars = self.query_one(EqualizerBars)
        bars.gains = list(self.settings.gains)
        self.query_one("#eq-balance", Slider).value = int(self.settings.balance * 100)
        bars.refresh()

    def _band(self) -> int:
        return self.query_one(EqualizerBars).selected

    def _nudge(self, delta: float) -> None:
        band = self._band()
        self.settings.set_gain(band, self.settings.gains[band] + delta)
        self._apply()
        self._redraw()

    def action_prev_band(self) -> None:
        bars = self.query_one(EqualizerBars)
        bars.selected = max(0, bars.selected - 1)
        bars.refresh()

    def action_next_band(self) -> None:
        bars = self.query_one(EqualizerBars)
        bars.selected = min(len(self.settings.gains) - 1, bars.selected + 1)
        bars.refresh()

    def action_boost(self) -> None:
        self._nudge(1.0)

    def action_cut(self) -> None:
        self._nudge(-1.0)

    def action_reset(self) -> None:
        self.settings.reset_eq()
        self._apply()
        self._redraw()

    def _slide(self, delta: float) -> None:
        self.settings.set_balance(self.settings.balance + delta)
        self._apply()
        self._redraw()

    def action_balance_left(self) -> None:
        self._slide(-0.1)

    def action_balance_right(self) -> None:
        self._slide(0.1)

    def action_balance_centre(self) -> None:
        self.settings.set_balance(0.0)
        self._apply()
        self._redraw()

    def action_close(self) -> None:
        self.dismiss(None)


class LyricsScreen(ModalScreen[None]):
    """Lyrics for one track, synchronized to the player when LRC is present."""

    BINDINGS = [
        Binding("escape,y", "close", "cerrar"),
        Binding("up", "up", "arriba", show=False),
        Binding("down", "down", "abajo", show=False),
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
                yield Static(f"▓ LETRA ▓  {self._track_title}", id="lyrics-title")
                yield Spinner(id="lyrics-spinner")
            yield Static("  cargando…", id="lyrics-body")
            yield Static(" ↑↓ desplazar   y/esc cerrar", id="lyrics-hint")

    def on_mount(self) -> None:
        self.query_one(Spinner).start("buscando la letra…")
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
        mode = "sincronizada" if document.synced else "texto"
        provider = f" · {document.provider}" if document.provider else ""
        self.query_one("#lyrics-title", Static).update(
            f"▓ LETRA ▓  {self._track_title} · {mode}{provider}"
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


def _track_path(entry: Entry) -> str:
    """The D-Bus object path for one queue row.

    Keyed on the row's uid, not on the TIDAL track id: the same song can be in
    the queue twice, and MPRIS requires the ids in a TrackList to be distinct.
    """
    return f"/org/mpris/MediaPlayer2/tidalamp/track/{entry.uid}"


def _entry_metadata(entry: Entry) -> dict:
    return {
        "trackid": _track_path(entry),
        "length": float(entry.duration),
        "title": entry.title,
        "artist": entry.artist,
        "album": entry.album,
        "art_url": entry.art_url,
        "url": f"tidal://track/{entry.id}",
    }


class TidalAmp(App):
    """Main application."""

    CSS_PATH = "winamp.tcss"
    TITLE = "TIDAL AMP"

    # Winamp's own transport keys, kept as muscle memory.
    BINDINGS = [
        Binding("z", "prev", "anterior"),
        Binding("x", "play", "play"),
        Binding("c", "pause", "pausa"),
        Binding("v", "stop", "stop"),
        Binding("b", "next", "siguiente"),
        Binding("slash", "search", "buscar"),
        Binding("l", "library", "biblioteca"),
        Binding("y", "lyrics", "letra"),
        Binding("e", "equalizer", "ecualizador"),
        Binding("s", "shuffle", "shuffle"),
        Binding("r", "repeat", "repeat"),
        Binding("up", "cursor_up", "arriba", show=False),
        Binding("down", "cursor_down", "abajo", show=False),
        Binding("pageup", "cursor_page_up", "", show=False),
        Binding("pagedown", "cursor_page_down", "", show=False),
        Binding("enter", "play_selected", "reproducir", show=False),
        Binding("d,delete", "remove", "quitar", show=False),
        Binding("alt+up", "move_up", "subir", show=False),
        Binding("alt+down", "move_down", "bajar", show=False),
        Binding("C", "clear", "vaciar", show=False),
        Binding("left", "seek_back", "-5s", show=False),
        Binding("right", "seek_fwd", "+5s", show=False),
        Binding("plus,equals_sign", "vol_up", "vol+", show=False),
        Binding("minus", "vol_down", "vol-", show=False),
        Binding("comma", "balance_left", "balance izq", show=False),
        Binding("full_stop", "balance_right", "balance der", show=False),
        Binding("backslash", "balance_centre", "centrar balance", show=False),
        Binding("t", "toggle_time", "tiempo", show=False),
        Binding("q,ctrl+c", "quit", "salir"),
    ]

    status = reactive("listo")

    def __init__(self, session: tidalapi.Session, mpv: Mpv) -> None:
        self.tidalamp_palette: ThemePalette = load_palette()
        super().__init__()
        self.session = session
        self.mpv = mpv
        self.queue = Queue()
        self.settings = Settings.load()
        self._lyrics_cache: dict[int, LyricsDocument] = {}
        self._was_idle = True
        self.mpris = MprisService(self)
        self._mpris_ready = False
        # How this terminal can draw a cover, decided once from the environment.
        self.art_protocol = artwork.detect_protocol()
        self._art_url = ""
        self._art_hidden = False
        self._pending_art: artwork.Cover | None = None
        # cava, when it is installed. None means the RMS fallback.
        self.cava: Cava | None = None

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Expose the detected palette to the static TCSS stylesheet."""
        return self.tidalamp_palette.css_variables()

    # ------------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        with Vertical(id="main"):
            yield Static("░▒▓ TIDAL AMP ▓▒░", id="titlebar")
            with Horizontal(id="display"):
                yield Artwork(id="art")
                yield TimeDisplay(id="clock")
                with Vertical(id="readout"):
                    yield Marquee(id="marquee")
                    yield Static("", id="badges")
                    yield Analyzer(id="analyzer")
            yield SeekBar(id="seek")
            yield Slider(id="volume")
            yield Slider(id="balance")
            yield Static(
                "  z ◀◀   x ▶   c ‖   v ■   b ▶▶   / buscar  l lib  y letra  e eq"
                "  s shuf  r rep  q salir",
                id="transport",
            )
            yield Static("", id="modes")
            yield Static("▓ PLAYLIST ▓   d quitar   C vaciar   alt+↑↓ mover", id="pl-title")
            yield RowList(id="playlist")
            with Horizontal(id="statusbar"):
                yield Spinner(id="busy")
                yield Static("", id="status")

    def on_mount(self) -> None:
        playlist = self.query_one("#playlist", RowList)
        playlist.empty_text = "cola vacía — / para buscar, l para tu biblioteca"
        self.query_one("#volume", Slider).value = self.mpv.volume
        balance = self.query_one("#balance", Slider)
        balance.label = "BAL"
        balance.centred = True
        self._apply_audio()
        self._start_spectrum()
        self.set_interval(1 / 10, self._tick_fast)
        self.set_interval(1 / 4, self._tick_slow)
        self.set_interval(2, self._refresh_theme)
        self.run_worker(self._start_mpris(), exclusive=False)

        if self.queue.load():
            self._sync_queue()
            playlist.cursor = max(0, self.queue.resume_at)
            self.status = f"cola restaurada ({len(self.queue)} pistas)"
        self._refresh_modes()

    def _refresh_theme(self) -> None:
        """Follow an Omarchy theme switch without disturbing other state."""
        palette = load_palette()
        if palette.colors == self.tidalamp_palette.colors:
            return
        self.tidalamp_palette = palette
        self.refresh_css(animate=False)
        self._refresh_modes()
        self.screen.refresh()

    def _apply_audio(self) -> None:
        """Push balance and EQ into mpv's filter chain and redraw the slider.

        Also called after mpv is respawned: a fresh process starts with an
        empty chain, so the settings would silently stop applying otherwise.
        """
        self.mpv.set_filter("balance", self.settings.balance_graph())
        self.mpv.set_filter("eq", self.settings.eq_graph())
        self.query_one("#balance", Slider).value = int(self.settings.balance * 100)

    def _start_spectrum(self) -> None:
        """Use cava for a real FFT when it is available. Its absence is not an
        error: the analyser falls back to the RMS meter and says so."""
        analyzer = self.query_one(Analyzer)
        try:
            self.cava = Cava(bars=Analyzer.BARS)
        except SpectrumUnavailable:
            analyzer.spectrum = None
            return
        analyzer.spectrum = self.cava.frame()

    def _stop_spectrum(self) -> None:
        """Drop back to the RMS meter, for good."""
        if self.cava is not None:
            self.cava.close()
            self.cava = None
        self.query_one(Analyzer).spectrum = None

    async def _start_mpris(self) -> None:
        """Claim the MPRIS bus name. A desktop without a session bus is not an
        error: we just run without the integration."""
        try:
            name = await self.mpris.start()
        except Exception as exc:
            self.status = f"MPRIS no disponible ({exc})"
            return
        self._mpris_ready = True
        if name != "org.mpris.MediaPlayer2.tidalamp":
            # Another tidalamp already holds the plain name.
            self.status = f"MPRIS como {name} (ya había otra instancia)"

    # ------------------------------------------------------------------- ticks

    def _tick_fast(self) -> None:
        analyzer = self.query_one(Analyzer)
        if self.cava is not None:
            if self.cava.alive:
                analyzer.spectrum = self.cava.frame()
            else:
                self._stop_spectrum()
        analyzer.level = self.mpv.rms()
        analyzer.active = not self.mpv.paused and not self.mpv.idle
        analyzer.tick()
        self.query_one(Marquee).tick()

    def _tick_slow(self) -> None:
        if not self.mpv.alive:
            self._recover_mpv()
            return

        position, duration = self.mpv.position, self.mpv.duration
        clock = self.query_one(TimeDisplay)
        clock.seconds, clock.total = position, duration

        seek = self.query_one(SeekBar)
        seek.position, seek.total = position, duration
        self.query_one("#volume", Slider).value = self.mpv.volume
        self.query_one("#status", Static).update(f" {self.status}")

        # mpv going idle after having played something means the track ended.
        idle = self.mpv.idle
        if idle and not self._was_idle:
            self.action_next()
        self._was_idle = idle

        if self._art_hidden and len(self.screen_stack) == 1:
            self._restore_art()

        if self._mpris_ready:
            self.mpris.publish()
            self.mpris.publish_tracks()

    def _recover_mpv(self) -> None:
        """mpv died under us. Respawn it instead of freezing the UI on a dead
        socket, and put the current track back where it was."""
        try:
            self.mpv.restart()
        except Exception as exc:
            self.status = f"mpv murió y no se pudo reiniciar ({exc})"
            return
        self._was_idle = True
        self._apply_audio()
        index = self.queue.playing
        if 0 <= index < len(self.queue):
            self.status = "mpv se reinició; recargando la pista"
            self._play_index(index)
        else:
            self.status = "mpv se reinició"

    def _refresh_modes(self) -> None:
        """Render persistent, legible shuffle and repeat state badges."""
        palette = self.tidalamp_palette
        active = f"bold {palette['active_foreground']} on {palette['accent']}"
        inactive = f"bold {palette['inactive']} on {palette['track_background']}"
        repeat = {
            Repeat.NONE: "OFF",
            Repeat.QUEUE: "ALL",
            Repeat.TRACK: "1",
        }[self.queue.repeat]
        modes = Text("  ")
        modes.append(
            f" SHUF {'ON' if self.queue.shuffle else 'OFF'} ",
            style=active if self.queue.shuffle else inactive,
        )
        modes.append("   ")
        modes.append(
            f" REP {repeat} ",
            style=active if self.queue.repeat is not Repeat.NONE else inactive,
        )
        self.query_one("#modes", Static).update(modes, layout=False)

    # ------------------------------------------------------------------ queue

    def _sync_queue(self) -> None:
        """Push the queue into the playlist widget."""
        playlist = self.query_one("#playlist", RowList)
        cursor = playlist.cursor
        playlist.rows = [
            Row(label=e.label, detail=e.length, entry=e) for e in self.queue
        ]
        playlist.cursor = max(0, min(cursor, len(playlist.rows) - 1))
        playlist.marked = self.queue.playing
        playlist.refresh()
        self.queue.save()

    # ------------------------------------------------------------------ search

    def action_search(self) -> None:
        self.push_screen(SearchScreen(), self._run_search)

    def _run_search(self, query: str | None) -> None:
        if not query:
            return
        self.push_screen(
            BrowserScreen(
                f"BUSCAR: {query}",
                lambda: library.search_rows(self.session, query),
            ),
            self._browser_result,
        )

    def action_library(self) -> None:
        self.push_screen(
            BrowserScreen("MI BIBLIOTECA", lambda: library.root(self.session)),
            self._browser_result,
        )

    def _browser_result(self, result: tuple | None) -> None:
        if result is None:
            return
        action, entries, index = result
        if not entries:
            self.status = "nada que añadir"
            return
        if action == "play":
            self.queue.replace(entries, start=-1)
            self._sync_queue()
            self._play_index(index)
        else:
            added = self.queue.append(entries)
            self._sync_queue()
            self.status = f"{added} pistas añadidas a la cola"

    # --------------------------------------------------------------- transport

    def action_cursor_up(self) -> None:
        self.query_one("#playlist", RowList).move(-1)

    def action_cursor_down(self) -> None:
        self.query_one("#playlist", RowList).move(1)

    def action_cursor_page_up(self) -> None:
        self.query_one("#playlist", RowList).move(-10)

    def action_cursor_page_down(self) -> None:
        self.query_one("#playlist", RowList).move(10)

    def action_play_selected(self) -> None:
        if len(self.queue):
            self._play_index(self.query_one("#playlist", RowList).cursor)

    def action_play(self) -> None:
        if self.queue.current is not None and self.mpv.paused:
            self.mpv.toggle_pause()
        elif len(self.queue):
            self._play_index(self.query_one("#playlist", RowList).cursor)

    def action_pause(self) -> None:
        self.mpv.toggle_pause()
        self.status = "pausa" if self.mpv.paused else "reproduciendo"

    def action_stop(self) -> None:
        self.mpv.stop()
        self.queue.playing = -1
        self._sync_queue()
        self.query_one(Marquee).text = ""
        self.status = "detenido"

    def action_next(self) -> None:
        index = self.queue.next_index()
        if index is None:
            self.action_stop()
        else:
            self._play_index(index)

    def action_prev(self) -> None:
        index = self.queue.prev_index()
        if index is not None:
            self._play_index(index)

    def action_remove(self) -> None:
        playlist = self.query_one("#playlist", RowList)
        if len(self.queue):
            self.queue.remove(playlist.cursor)
            self._sync_queue()
            self.status = "pista quitada de la cola"

    def _move_entry(self, delta: int) -> None:
        playlist = self.query_one("#playlist", RowList)
        if not len(self.queue):
            return
        moved = self.queue.move(playlist.cursor, delta)
        if moved == playlist.cursor:
            return
        self._sync_queue()
        playlist.cursor = moved
        playlist.marked = self.queue.playing
        playlist.refresh()

    def action_move_up(self) -> None:
        self._move_entry(-1)

    def action_move_down(self) -> None:
        self._move_entry(1)

    def action_clear(self) -> None:
        self.action_stop()
        self.queue.clear()
        self._sync_queue()
        self._art_url = ""
        self._pending_art = None
        widget = self._artwork()
        if widget is not None:
            widget.show(None)
        self.status = "cola vaciada"

    def action_shuffle(self) -> None:
        self.queue.shuffle = not self.queue.shuffle
        self.queue.save()
        self._refresh_modes()
        self.status = "shuffle activado" if self.queue.shuffle else "shuffle desactivado"

    def action_repeat(self) -> None:
        self.queue.repeat = self.queue.repeat.next()
        self.queue.save()
        self._refresh_modes()
        names = {Repeat.NONE: "sin repetición", Repeat.QUEUE: "repetir cola",
                 Repeat.TRACK: "repetir pista"}
        self.status = names[self.queue.repeat]

    def _play_index(self, index: int) -> None:
        if not 0 <= index < len(self.queue):
            return
        entry = self.queue[index]
        self.queue.playing = index
        playlist = self.query_one("#playlist", RowList)
        playlist.cursor = index
        playlist.marked = index
        playlist.refresh()
        self.query_one(Marquee).text = f"{index + 1}. {entry.label} ({entry.length})"
        # The spinner carries the message while we wait; repeating it in the
        # status text next to it would just say the same thing twice.
        self.status = ""
        self.query_one("#busy", Spinner).start(f"resolviendo «{entry.title}»…")
        self.queue.save()
        self._load_art(entry)
        self._resolve_worker(entry)

    # ----------------------------------------------------------------- artwork

    def _load_art(self, entry: Entry) -> None:
        """Ask for this entry's cover, unless we are already showing it."""
        if self.art_protocol is artwork.Protocol.NONE:
            return
        widget = self._artwork()
        if widget is None:
            return
        if not entry.art_url:
            self._art_url = ""
            widget.show(None)
            return
        if entry.art_url == self._art_url:
            return
        self._art_url = entry.art_url
        self._art_worker(entry.art_url)

    # Its own group: the default one is the resolve worker's, and an exclusive
    # worker cancels the rest of its group — the cover would kill playback.
    @work(thread=True, exclusive=True, group="artwork")
    def _art_worker(self, url: str) -> None:
        widget = self.query_one(Artwork)
        try:
            data = artwork.fetch(url)
            cover = artwork.render(
                data,
                Artwork.COLS,
                Artwork.ROWS,
                self.art_protocol,
                image_id=widget.image_id,
            )
        except Exception as exc:
            # A missing cover is decoration; it never touches the audio path.
            self.call_from_thread(setattr, self, "status", f"sin carátula: {exc}")
            return
        if url == self._art_url:
            self.call_from_thread(widget.show, cover)

    def _artwork(self) -> Artwork | None:
        """The cover widget, or ``None`` before ``compose`` has produced it.

        Textual pushes the default screen on the way up, which reaches
        ``push_screen`` below while there is still nothing to query.
        """
        try:
            return self.query_one(Artwork)
        except Exception:
            return None

    def _hide_art(self) -> None:
        """Take the cover down while another screen is in front.

        kitty and sixel images live above the text, so a modal would open
        underneath the cover instead of over it.
        """
        widget = self._artwork()
        if self._art_hidden or widget is None or widget.cover is None:
            return
        self._art_hidden = True
        self._pending_art = widget.cover
        widget.show(None)

    def _restore_art(self) -> None:
        widget = self._artwork()
        if not self._art_hidden or widget is None:
            return
        self._art_hidden = False
        widget.show(self._pending_art)

    def push_screen(self, screen, callback=None, wait_for_dismiss=False, *, mode=None):  # type: ignore[override]
        self._hide_art()
        return super().push_screen(screen, callback, wait_for_dismiss, mode=mode)

    @work(thread=True, exclusive=True)
    def _resolve_worker(self, entry: Entry) -> None:
        try:
            # An access token only lasts a few hours, less than a listening
            # session; refresh it here rather than letting the next call fail.
            if ensure_fresh(self.session):
                self.call_from_thread(setattr, self, "status", "sesión refrescada")
            # A restored entry has no Track yet; this is where we pay for it.
            track = with_retries(lambda: entry.resolve(self.session))
            playable = resolve(track)
        except NotLoggedIn as exc:
            self.call_from_thread(self._resolve_failed, str(exc))
            return
        except StreamUnavailable as exc:
            self.call_from_thread(self._resolve_failed, str(exc))
            return
        except Exception as exc:
            self.call_from_thread(self._resolve_failed, f"error: {exc}")
            return
        self.call_from_thread(self._start, entry, playable)

    def _resolve_failed(self, message: str) -> None:
        self.query_one("#busy", Spinner).stop()
        self.status = message

    def _start(self, entry: Entry, playable) -> None:
        self.query_one("#busy", Spinner).stop()
        self.mpv.load(playable.url)
        self._was_idle = False
        self.query_one("#badges", Static).update(
            f"{playable.kbps}  {playable.khz}kHz  {playable.quality}"
            f"  {self.query_one(Analyzer).source}"
        )
        self.status = f"reproduciendo {entry.label}"
        if getattr(playable, "downgraded", False):
            # Say it out loud. The badge shows what arrived, which on its own
            # reads as if it were what we asked for.
            self.status = (
                f"{self.status} · TIDAL entregó {playable.quality}, "
                f"no {playable.requested}"
            )

    # ----------------------------------------------------------------- fiddles

    def action_seek_back(self) -> None:
        self.mpv.seek(-5, "relative")

    def action_seek_fwd(self) -> None:
        self.mpv.seek(5, "relative")

    def action_vol_up(self) -> None:
        self.mpv.volume = self.mpv.volume + 5

    def action_vol_down(self) -> None:
        self.mpv.volume = self.mpv.volume - 5

    def _lyrics_for(self, entry: Entry) -> LyricsDocument:
        cached = self._lyrics_cache.get(entry.id)
        if cached is not None:
            return cached
        ensure_fresh(self.session)
        track = with_retries(lambda: entry.resolve(self.session))
        document = load_lyrics(track)
        self._lyrics_cache[entry.id] = document
        return document

    def action_lyrics(self) -> None:
        entry = self.queue.current
        if entry is None:
            self.status = "no hay una pista reproduciéndose"
            return
        self.push_screen(
            LyricsScreen(
                entry.label,
                lambda: self._lyrics_for(entry),
                lambda: self.mpv.position,
            )
        )

    def action_equalizer(self) -> None:
        self.push_screen(EqScreen(self.settings, self._apply_audio), self._eq_closed)

    def _eq_closed(self, _: None) -> None:
        self.settings.save()
        self.status = "ecualizador activo" if self.settings.eq_active else "ecualizador plano"

    def _nudge_balance(self, delta: float) -> None:
        value = self.settings.set_balance(self.settings.balance + delta)
        self._apply_audio()
        self.settings.save()
        side = "centro" if value == 0 else (f"{abs(int(value * 100))}% " + ("izq" if value < 0 else "der"))
        self.status = f"balance: {side}"

    def action_balance_left(self) -> None:
        self._nudge_balance(-0.1)

    def action_balance_right(self) -> None:
        self._nudge_balance(0.1)

    def action_balance_centre(self) -> None:
        self.settings.set_balance(0.0)
        self._apply_audio()
        self.settings.save()
        self.status = "balance: centro"

    def action_toggle_time(self) -> None:
        clock = self.query_one(TimeDisplay)
        clock.countdown = not clock.countdown

    def action_quit(self) -> None:
        self.run_worker(self._shutdown(), exclusive=False)

    async def _shutdown(self) -> None:
        self.queue.save()
        self.settings.save()
        if self._mpris_ready:
            await self.mpris.stop()
        self._stop_spectrum()
        self.mpv.close()
        cleanup_playlists()
        self.exit()

    # ------------------------------------------------------------------ MPRIS

    def mpris_status(self) -> str:
        if self.queue.current is None or self.mpv.idle:
            return "Stopped"
        return "Paused" if self.mpv.paused else "Playing"

    def mpris_metadata(self) -> dict:
        entry = self.queue.current
        return {} if entry is None else _entry_metadata(entry)

    def mpris_track_ids(self) -> list[str]:
        """Just the ids, which is all the TrackList property and the diff need."""
        return [_track_path(entry) for entry in self.queue]

    def mpris_tracks(self) -> list[dict]:
        """The whole queue, in visible order, for ``GetTracksMetadata``."""
        return [_entry_metadata(entry) for entry in self.queue]

    def mpris_go_to(self, track_id: str) -> None:
        for index, entry in enumerate(self.queue):
            if _track_path(entry) == track_id:
                self._play_index(index)
                return

    def mpris_position(self) -> float:
        return self.mpv.position

    def mpris_volume(self) -> float:
        # MPRIS volume is 0.0-1.0; mpv's is a percentage.
        return self.mpv.volume / 100.0

    def mpris_set_volume(self, value: float) -> None:
        self.mpv.volume = int(max(0.0, min(1.3, value)) * 100)

    def mpris_can_go_next(self) -> bool:
        return self.queue.has_next()

    def mpris_can_go_previous(self) -> bool:
        return self.queue.has_prev()

    def mpris_loop_status(self) -> str:
        return self.queue.repeat.value

    def mpris_set_loop_status(self, value: str) -> None:
        try:
            self.queue.repeat = Repeat(value)
        except ValueError:
            return
        self.queue.save()
        self._refresh_modes()

    def mpris_shuffle(self) -> bool:
        return self.queue.shuffle

    def mpris_set_shuffle(self, value: bool) -> None:
        self.queue.shuffle = value
        self.queue.save()
        self._refresh_modes()

    def mpris_play(self) -> None:
        if self.mpv.paused:
            self.mpv.toggle_pause()
        else:
            self.action_play()

    def mpris_pause(self) -> None:
        if not self.mpv.paused:
            self.mpv.toggle_pause()

    def mpris_play_pause(self) -> None:
        self.action_pause()

    def mpris_stop(self) -> None:
        self.action_stop()

    def mpris_next(self) -> None:
        self.action_next()

    def mpris_previous(self) -> None:
        self.action_prev()

    def mpris_seek(self, offset: float) -> None:
        self.mpv.seek(offset, "relative")
        self.mpris.seeked(self.mpv.position)

    def mpris_set_position(self, position: float) -> None:
        self.mpv.seek(position, "absolute")
        self.mpris.seeked(position)

    def mpris_quit(self) -> None:
        self.action_quit()
