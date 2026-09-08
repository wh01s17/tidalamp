"""The Winamp-flavoured TUI."""

from __future__ import annotations

from dataclasses import dataclass

import tidalapi
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Static

from .mpris import MprisService
from .player import Mpv
from .stream import StreamUnavailable, cleanup_playlists, resolve
from .widgets import Analyzer, Marquee, SeekBar, Slider, TimeDisplay


@dataclass(slots=True)
class Entry:
    """One playlist row."""

    track: tidalapi.Track

    @property
    def title(self) -> str:
        return f"{self.track.artist.name} - {self.track.name}"

    @property
    def duration(self) -> str:
        minutes, secs = divmod(int(self.track.duration or 0), 60)
        return f"{minutes}:{secs:02d}"

    @property
    def album(self) -> str:
        album = getattr(self.track, "album", None)
        return getattr(album, "name", "") or ""

    @property
    def art_url(self) -> str:
        """Cover art URL, or empty when the album has no artwork."""
        album = getattr(self.track, "album", None)
        if album is None:
            return ""
        try:
            return album.image(320) or ""
        except Exception:
            # tidalapi raises when the album carries no cover id.
            return ""


class Playlist(Widget):
    """The playlist editor pane."""

    DEFAULT_CSS = "Playlist { height: 1fr; }"

    cursor = reactive(0)
    playing = reactive(-1)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.entries: list[Entry] = []

    def replace(self, entries: list[Entry]) -> None:
        self.entries = entries
        self.cursor = 0
        self.refresh()

    def move(self, delta: int) -> None:
        if self.entries:
            self.cursor = max(0, min(len(self.entries) - 1, self.cursor + delta))
            self.refresh()

    def render(self):
        from rich.text import Text

        if not self.entries:
            return Text("  playlist vacía — pulsa / para buscar en TIDAL", style="#5f7f67")

        rows = max(1, self.size.height)
        # Keep the cursor in view without a full scrolling container.
        start = max(0, min(self.cursor - rows // 2, len(self.entries) - rows))
        out = Text()
        for i in range(start, min(len(self.entries), start + rows)):
            entry = self.entries[i]
            marker = "▶" if i == self.playing else " "
            line = f"{marker}{i + 1:>3}. {entry.title}"
            width = max(20, self.size.width)
            pad = max(1, width - len(line) - len(entry.duration) - 1)
            line = f"{line}{' ' * pad}{entry.duration}"[:width]
            if i == self.cursor:
                out.append(line, style="bold black on #00ff4c")
            elif i == self.playing:
                out.append(line, style="bold #00ff4c")
            else:
                out.append(line, style="#7fbf8f")
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
        Binding("up", "cursor_up", "arriba", show=False),
        Binding("down", "cursor_down", "abajo", show=False),
        Binding("enter", "play_selected", "reproducir", show=False),
        Binding("left", "seek_back", "-5s", show=False),
        Binding("right", "seek_fwd", "+5s", show=False),
        Binding("plus,equals_sign", "vol_up", "vol+", show=False),
        Binding("minus", "vol_down", "vol-", show=False),
        Binding("t", "toggle_time", "tiempo", show=False),
        Binding("q,ctrl+c", "quit", "salir"),
    ]

    status = reactive("listo")

    def __init__(self, session: tidalapi.Session, mpv: Mpv) -> None:
        super().__init__()
        self.session = session
        self.mpv = mpv
        self._was_idle = True
        self.mpris = MprisService(self)
        self._mpris_ready = False

    # ------------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        with Vertical(id="main"):
            yield Static("░▒▓ TIDAL AMP ▓▒░", id="titlebar")
            with Horizontal(id="display"):
                yield TimeDisplay(id="clock")
                with Vertical(id="readout"):
                    yield Marquee(id="marquee")
                    yield Static("", id="badges")
                    yield Analyzer(id="analyzer")
            yield SeekBar(id="seek")
            yield Slider(id="volume")
            yield Static(
                "  z ◀◀   x ▶   c ‖   v ■   b ▶▶      / buscar   t tiempo   q salir",
                id="transport",
            )
            yield Static("▓ PLAYLIST ▓", id="pl-title")
            yield Playlist(id="playlist")
            yield Static("", id="status")

    def on_mount(self) -> None:
        self.query_one("#volume", Slider).value = self.mpv.volume
        self.set_interval(1 / 10, self._tick_fast)
        self.set_interval(1 / 4, self._tick_slow)
        self.run_worker(self._start_mpris(), exclusive=False)

    async def _start_mpris(self) -> None:
        """Claim the MPRIS bus name. A desktop without a session bus is not an
        error: we just run without the integration."""
        try:
            await self.mpris.start()
        except Exception as exc:
            self.status = f"MPRIS no disponible ({exc})"
            return
        self._mpris_ready = True

    # ------------------------------------------------------------------- ticks

    def _tick_fast(self) -> None:
        analyzer = self.query_one(Analyzer)
        analyzer.level = self.mpv.rms()
        analyzer.active = not self.mpv.paused and not self.mpv.idle
        analyzer.tick()
        self.query_one(Marquee).tick()

    def _tick_slow(self) -> None:
        position, duration = self.mpv.position, self.mpv.duration
        clock = self.query_one(TimeDisplay)
        clock.seconds, clock.total = position, duration

        seek = self.query_one(SeekBar)
        seek.position, seek.total = position, duration
        self.query_one("#volume", Slider).value = self.mpv.volume
        self.query_one("#status", Static).update(f" {self.status}")

        if self._mpris_ready:
            self.mpris.publish()

        # mpv going idle after having played something means the track ended.
        idle = self.mpv.idle
        if idle and not self._was_idle:
            self.action_next()
        self._was_idle = idle

    # ------------------------------------------------------------------ search

    def action_search(self) -> None:
        self.push_screen(SearchScreen(), self._run_search)

    def _run_search(self, query: str | None) -> None:
        if query:
            self.status = f"buscando «{query}»…"
            self._search_worker(query)

    @work(thread=True, exclusive=True)
    def _search_worker(self, query: str) -> None:
        try:
            results = self.session.search(query, models=[tidalapi.Track], limit=50)
            tracks = results.get("tracks", [])
        except Exception as exc:
            self.call_from_thread(setattr, self, "status", f"error de búsqueda: {exc}")
            return
        entries = [Entry(track) for track in tracks]
        self.call_from_thread(self._apply_results, query, entries)

    def _apply_results(self, query: str, entries: list[Entry]) -> None:
        self.query_one(Playlist).replace(entries)
        self.status = f"{len(entries)} resultados para «{query}»"

    # --------------------------------------------------------------- transport

    def action_cursor_up(self) -> None:
        self.query_one(Playlist).move(-1)

    def action_cursor_down(self) -> None:
        self.query_one(Playlist).move(1)

    def action_play_selected(self) -> None:
        playlist = self.query_one(Playlist)
        if playlist.entries:
            self._play_index(playlist.cursor)

    def action_play(self) -> None:
        playlist = self.query_one(Playlist)
        if playlist.playing >= 0 and self.mpv.paused:
            self.mpv.toggle_pause()
        elif playlist.entries:
            self._play_index(playlist.cursor)

    def action_pause(self) -> None:
        self.mpv.toggle_pause()
        self.status = "pausa" if self.mpv.paused else "reproduciendo"

    def action_stop(self) -> None:
        self.mpv.stop()
        self.query_one(Playlist).playing = -1
        self.query_one(Marquee).text = ""
        self.status = "detenido"

    def action_next(self) -> None:
        playlist = self.query_one(Playlist)
        if playlist.playing + 1 < len(playlist.entries):
            self._play_index(playlist.playing + 1)
        else:
            self.action_stop()

    def action_prev(self) -> None:
        playlist = self.query_one(Playlist)
        if playlist.playing > 0:
            self._play_index(playlist.playing - 1)

    def _play_index(self, index: int) -> None:
        playlist = self.query_one(Playlist)
        entry = playlist.entries[index]
        playlist.playing = index
        playlist.cursor = index
        playlist.refresh()
        self.query_one(Marquee).text = f"{index + 1}. {entry.title} ({entry.duration})"
        self.status = f"resolviendo «{entry.track.name}»…"
        self._resolve_worker(entry)

    @work(thread=True, exclusive=True)
    def _resolve_worker(self, entry: Entry) -> None:
        try:
            playable = resolve(entry.track)
        except StreamUnavailable as exc:
            self.call_from_thread(setattr, self, "status", str(exc))
            return
        self.call_from_thread(self._start, entry, playable)

    def _start(self, entry: Entry, playable) -> None:
        self.mpv.load(playable.url)
        self._was_idle = False
        badges = f"{playable.kbps}  {playable.khz}kHz  {playable.quality}"
        self.query_one("#badges", Static).update(badges)
        self.status = f"reproduciendo {entry.title}"

    # ----------------------------------------------------------------- fiddles

    def action_seek_back(self) -> None:
        self.mpv.seek(-5, "relative")

    def action_seek_fwd(self) -> None:
        self.mpv.seek(5, "relative")

    def action_vol_up(self) -> None:
        self.mpv.volume = self.mpv.volume + 5

    def action_vol_down(self) -> None:
        self.mpv.volume = self.mpv.volume - 5

    def action_toggle_time(self) -> None:
        clock = self.query_one(TimeDisplay)
        clock.countdown = not clock.countdown

    def action_quit(self) -> None:
        self.run_worker(self._shutdown(), exclusive=False)

    async def _shutdown(self) -> None:
        if self._mpris_ready:
            await self.mpris.stop()
        self.mpv.close()
        cleanup_playlists()
        self.exit()

    # ------------------------------------------------------------------ MPRIS

    def _current_entry(self) -> Entry | None:
        playlist = self.query_one(Playlist)
        if 0 <= playlist.playing < len(playlist.entries):
            return playlist.entries[playlist.playing]
        return None

    def mpris_status(self) -> str:
        if self._current_entry() is None or self.mpv.idle:
            return "Stopped"
        return "Paused" if self.mpv.paused else "Playing"

    def mpris_metadata(self) -> dict:
        entry = self._current_entry()
        if entry is None:
            return {}
        return {
            "trackid": f"/org/mpris/MediaPlayer2/tidalamp/track/{entry.track.id}",
            "length": float(entry.track.duration or 0),
            "title": entry.track.name,
            "artist": entry.track.artist.name,
            "album": entry.album,
            "art_url": entry.art_url,
            "url": f"tidal://track/{entry.track.id}",
        }

    def mpris_position(self) -> float:
        return self.mpv.position

    def mpris_volume(self) -> float:
        # MPRIS volume is 0.0-1.0; mpv's is a percentage.
        return self.mpv.volume / 100.0

    def mpris_set_volume(self, value: float) -> None:
        self.mpv.volume = int(max(0.0, min(1.3, value)) * 100)

    def mpris_can_go_next(self) -> bool:
        playlist = self.query_one(Playlist)
        return playlist.playing + 1 < len(playlist.entries)

    def mpris_can_go_previous(self) -> bool:
        return self.query_one(Playlist).playing > 0

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
