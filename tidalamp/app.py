"""The Winamp-flavoured TUI."""

from __future__ import annotations

from typing import cast

import tidalapi
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static

from . import artwork, config, library
from .auth import NotLoggedIn, ensure_fresh
from .i18n import _
from .library import Row
from .lyrics import LyricsDocument, load_lyrics
from .mpris import MprisService
from .net import with_retries
from .player import Mpv
from .queue import Entry, Queue, Repeat
from .screens import (
    BrowserScreen,
    EqScreen,
    HelpScreen,
    LyricsScreen,
    RowList,
    SearchScreen,
    favourite_message,
)
from .settings import Settings
from .spectrum import Cava, SpectrumUnavailable
from .stream import StreamUnavailable, cleanup_playlists, resolve
from .theme import ThemePalette, load_palette
from .widgets import (
    Analyzer,
    Artwork,
    Marquee,
    SeekBar,
    Slider,
    Spinner,
    TimeDisplay,
)


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


# Every action a user may rebind, with the key Winamp used. Navigation keys
# (arrows, page up/down, Enter, Escape) are deliberately not here: they are
# what makes the browser navigable, and a typo there locks you out of it.
DEFAULT_KEYS: dict[str, str] = {
    "prev": "z",
    "play": "x",
    "stop": "v",
    "next": "b",
    "search": "slash",
    "library": "l",
    "lyrics": "y",
    "equalizer": "e",
    "shuffle": "s",
    "repeat": "r",
    "favourite": "f",
    "unfavourite": "F",
    "remove": "d,delete",
    "move_up": "alt+up",
    "move_down": "alt+down",
    "clear": "C",
    "seek_back": "left",
    "seek_fwd": "right",
    "vol_up": "plus,equals_sign",
    "vol_down": "minus",
    "balance_left": "comma",
    "balance_right": "full_stop",
    "balance_centre": "backslash",
    "toggle_time": "t",
    "help": "question_mark,h",
    "quit": "q,ctrl+c",
}


def keys_for(action: str) -> str:
    """The key bound to ``action``, from the config file or the default."""
    override = config.KEYS.get(action)
    if override:
        return override
    if action not in DEFAULT_KEYS:
        raise KeyError(_("acción desconocida: {action}").format(action=action))
    return DEFAULT_KEYS[action]


def _bind(action: str, description: str, show: bool = False) -> Binding:
    return Binding(keys_for(action), action, description, show=show)


def unknown_key_actions() -> list[str]:
    """Actions named in the config file that do not exist. For the CLI to warn."""
    return sorted(set(config.KEYS) - set(DEFAULT_KEYS))


# Fixed pieces of the display band, from winamp.tcss. `_fit_artwork` needs
# them to work out how much of the row is left for the cover.
CLOCK_WIDTH = 24
READOUT_WIDTH = 30
DISPLAY_HEIGHT = 9


class MainPanel(Vertical):
    """The whole UI, in one container that watches its own size.

    ``Resize`` does not bubble and never reaches the App, so the check for a
    terminal too small to draw has to hang off something that is laid out.
    This panel is width and height 100%, which makes it the screen's stand-in.
    """

    def on_resize(self, event) -> None:
        cast("TidalAmp", self.app)._check_size()


class TidalAmp(App):
    """Main application."""

    CSS_PATH = "winamp.tcss"
    TITLE = "TIDAL AMP"

    # The display alone needs 18 columns of cover, 24 of clock and room for the
    # readout; below this the layout does not shrink, it overlaps. Saying so is
    # better than drawing something broken and letting the user guess.
    MIN_WIDTH = 76
    MIN_HEIGHT = 20

    # Winamp's own transport keys, kept as muscle memory. Rebindable ones come
    # from DEFAULT_KEYS through the config file; navigation stays fixed.
    BINDINGS = [
        _bind("prev", _("anterior"), show=True),
        _bind("play", "play", show=True),
        _bind("stop", "stop", show=True),
        _bind("next", _("siguiente"), show=True),
        _bind("search", _("buscar"), show=True),
        _bind("library", _("biblioteca"), show=True),
        _bind("lyrics", _("letra"), show=True),
        _bind("equalizer", _("ecualizador"), show=True),
        _bind("shuffle", "shuffle", show=True),
        _bind("repeat", "repeat", show=True),
        Binding("up", "cursor_up", _("arriba"), show=False),
        Binding("down", "cursor_down", _("abajo"), show=False),
        Binding("pageup", "cursor_page_up", "", show=False),
        Binding("pagedown", "cursor_page_down", "", show=False),
        Binding("enter", "play_selected", _("reproducir"), show=False),
        _bind("remove", _("quitar")),
        _bind("move_up", _("subir")),
        _bind("move_down", _("bajar")),
        _bind("clear", _("vaciar")),
        _bind("seek_back", "-5s"),
        _bind("seek_fwd", "+5s"),
        _bind("vol_up", "vol+"),
        _bind("vol_down", "vol-"),
        _bind("balance_left", _("balance izq")),
        _bind("balance_right", _("balance der")),
        _bind("balance_centre", _("centrar balance")),
        _bind("toggle_time", _("tiempo")),
        _bind("favourite", _("favorito")),
        _bind("unfavourite", _("quitar favorito")),
        _bind("help", _("ayuda"), show=True),
        _bind("quit", _("salir"), show=True),
    ]

    status = reactive(_("listo"))

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
        self.art_protocol = artwork.detect_protocol(configured=config.ARTWORK)
        self._art_url = ""
        self._art_hidden = False
        self._pending_art: artwork.Cover | None = None
        # cava, when it is installed. None means the RMS fallback.
        self.cava: Cava | None = None
        # What the play/pause button is currently drawn as.
        self._transport_playing = False

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Expose the detected palette to the static TCSS stylesheet."""
        return self.tidalamp_palette.css_variables()

    # ------------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        with MainPanel(id="main"):
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
            # Two halves, not one string: the transport keys belong with the
            # sliders above them, and the windows read as a menu, which they
            # only do once there is air between the two. Shuffle and repeat
            # sit on the left with the transport: they are buttons that hold
            # a state, not places to go. Both halves are filled in by
            # `_refresh_modes`, which dims the separators and lights the state.
            with Horizontal(id="transport"):
                yield Static("", id="transport-play")
                yield Static("", id="transport-menu")
            yield Static(
                _("▓ PLAYLIST ▓   d quitar   C vaciar   alt+↑↓ mover"), id="pl-title"
            )
            yield RowList(id="playlist")
            with Horizontal(id="statusbar"):
                yield Spinner(id="busy")
                yield Static("", id="status", markup=False)
        yield Static("", id="too-small")

    def _check_size(self) -> None:
        """Cover the UI with an explanation when the terminal is too small."""
        self._fit_artwork()
        width, height = self.size.width, self.size.height
        too_small = width < self.MIN_WIDTH or height < self.MIN_HEIGHT
        notice = self.query_one("#too-small", Static)
        notice.display = too_small
        if too_small:
            notice.update(
                Text(
                    _(
                        "\n  La ventana es de {width}×{height}.\n"
                        "  TIDAL AMP necesita al menos {min_width}×{min_height}.\n\n"
                        "  Agranda el terminal o reduce el tamaño de letra.\n"
                    ).format(
                        width=width,
                        height=height,
                        min_width=self.MIN_WIDTH,
                        min_height=self.MIN_HEIGHT,
                    ),
                    style=f"bold {self.tidalamp_palette['accent']}",
                )
            )

    def _fit_artwork(self) -> None:
        """Grow the cover box with the terminal, then draw the cover again.

        Two ceilings. Vertically the display band must not eat the playlist,
        so it takes a quarter of the height; horizontally the box shares its
        row with the 24-cell clock and the readout, which needs about 30 cells
        before the marquee stops saying anything useful.
        """
        widget = self._artwork()
        if widget is None:
            return
        by_height = self.size.height // 4
        by_width = (self.size.width - CLOCK_WIDTH - READOUT_WIDTH - 4) // 2
        if not widget.resize(min(by_height, by_width)):
            return
        self.query_one("#display").styles.height = max(DISPLAY_HEIGHT, widget.rows)
        # resize() dropped the cover it had, because it was the old size.
        if self._art_url:
            self._art_worker(self._art_url)

    def on_mount(self) -> None:
        self._check_size()
        playlist = self.query_one("#playlist", RowList)
        playlist.empty_text = _("cola vacía — / para buscar, l para tu biblioteca")
        volume = self.query_one("#volume", Slider)
        # Tied to the player's own ceiling rather than left on the widget
        # default: when the two drifted apart, the bar drew past its track.
        volume.maximum = Mpv.VOLUME_MAX
        volume.value = self.mpv.volume
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
            self.status = _("cola restaurada ({count} pistas)").format(
                count=len(self.queue)
            )
        self._refresh_modes()
        # Last, so it wins over the queue-restore message: without Pillow the
        # cover never appears and nothing else would ever say why.
        if self.art_protocol is not artwork.Protocol.NONE and not artwork.have_decoder():
            self.status = _('sin carátula: falta Pillow (pip install "tidalamp[art]")')

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
            self.status = _("MPRIS no disponible ({error})").format(error=exc)
            return
        self._mpris_ready = True
        if name != "org.mpris.MediaPlayer2.tidalamp":
            # Another tidalamp already holds the plain name.
            self.status = _("MPRIS como {name} (ya había otra instancia)").format(
                name=name
            )

    # ------------------------------------------------------------------- ticks

    def _tick_fast(self) -> None:
        analyzer = self.query_one(Analyzer)
        if self.cava is not None:
            if self.cava.alive:
                analyzer.spectrum = self.cava.frame()
            else:
                self._stop_spectrum()
        analyzer.level = self.mpv.rms()
        playing = not self.mpv.paused and not self.mpv.idle
        analyzer.active = playing
        analyzer.tick()
        self.query_one(Marquee).tick()
        # The play/pause button follows the state, but only redraw it when the
        # state actually turns over: this runs ten times a second.
        if playing != self._transport_playing:
            self._transport_playing = playing
            self._refresh_modes()

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
            self.status = _("mpv murió y no se pudo reiniciar ({error})").format(
                error=exc
            )
            return
        self._was_idle = True
        self._apply_audio()
        index = self.queue.playing
        if 0 <= index < len(self.queue):
            self.status = _("mpv se reinició; recargando la pista")
            self._play_index(index)
        else:
            self.status = _("mpv se reinició")

    # A middle dot in the muted colour, not a full box-drawing bar: the row
    # is a list of small things, and a solid rule between each one shouts
    # louder than the labels it is separating.
    SEPARATOR = " · "

    # One play/pause button, not two. The glyph is the action it will do:
    # «▶» while stopped or paused, «‖» while something is playing, which is
    # what every transport in the world does. `c` still pauses on its own —
    # it is in the config file and in muscle memory — it just has no button
    # of its own any more.
    TRANSPORT_HEAD = "  z ◀◀ · x "
    TRANSPORT_TAIL = " · v ■ · b ▶▶"

    # "↻ " and "↻1" are the same width, so toggling repeat does not shove the
    # rest of the row sideways.
    REPEAT_GLYPHS = {Repeat.NONE: "↻ ", Repeat.QUEUE: "↻ ", Repeat.TRACK: "↻1"}

    def _separated(self, text: str, body: str, dim: str) -> Text:
        """Render a `·`-joined run with the separators dimmed."""
        out = Text()
        for index, part in enumerate(text.split(self.SEPARATOR)):
            if index:
                out.append(self.SEPARATOR, style=dim)
            out.append(part, style=body)
        return out

    def _refresh_modes(self) -> None:
        """Draw the transport row, with shuffle and repeat lit by their state."""
        palette = self.tidalamp_palette
        ground = palette["transport_background"]
        body = f"{palette['transport_foreground']} on {ground}"
        dim = f"{palette['inactive']} on {ground}"
        active = f"bold {palette['active_foreground']} on {palette['accent']}"
        inactive = f"bold {palette['inactive']} on {ground}"

        playing = not self.mpv.paused and not self.mpv.idle
        row = self._separated(self.TRANSPORT_HEAD, body, dim)
        row.append("‖" if playing else "▶", style=body)
        row.append_text(self._separated(self.TRANSPORT_TAIL, body, dim))
        row.append(self.SEPARATOR, style=dim)
        row.append(" s ⇄ ", style=active if self.queue.shuffle else inactive)
        row.append(self.SEPARATOR, style=dim)
        row.append(
            f" r {self.REPEAT_GLYPHS[self.queue.repeat]} ",
            style=active if self.queue.repeat is not Repeat.NONE else inactive,
        )
        row.append("  ", style=body)
        self.query_one("#transport-play", Static).update(row, layout=False)

        menu = _("? ayuda · / buscar · l lib · y letra · e eq · f/F favorito · q salir")
        self.query_one("#transport-menu", Static).update(
            self._separated(f"{menu}  ", body, dim), layout=False
        )

    # ------------------------------------------------------------------ queue

    def _sync_queue(self) -> None:
        """Push the queue into the playlist widget."""
        playlist = self.query_one("#playlist", RowList)
        cursor = playlist.cursor
        playlist.rows = [Row(label=e.label, detail=e.length, entry=e) for e in self.queue]
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
                _("BUSCAR: {query}").format(query=query),
                lambda: library.search_rows(self.session, query),
            ),
            self._browser_result,
        )

    def action_library(self) -> None:
        self.push_screen(
            BrowserScreen(_("MI BIBLIOTECA"), lambda: library.root(self.session)),
            self._browser_result,
        )

    def _browser_result(self, result: tuple | None) -> None:
        if result is None:
            return
        action, entries, index = result
        if not entries:
            self.status = _("nada que añadir")
            return
        if action == "play":
            self.queue.replace(entries, start=-1)
            self._sync_queue()
            self._play_index(index)
        elif action == "next":
            self.queue.insert_next(entries)
            self._sync_queue()
            self.status = _("«{label}» sonará a continuación").format(
                label=entries[0].label
            )
        elif action == "radio":
            self.query_one("#busy", Spinner).start(
                _("buscando la radio de «{label}»…").format(label=entries[0].label)
            )
            self._radio_worker(entries[0])
        elif action == "favourite":
            self._favourite_entry(entries[0])
        else:
            added = self.queue.append(entries)
            self._sync_queue()
            self.status = _("{count} pistas añadidas a la cola").format(count=added)

    # Its own group, like the other two: an exclusive worker cancels its
    # group, and the resolve worker feeding playback is not this one's to kill.
    @work(thread=True, exclusive=True, group="radio")
    def _radio_worker(self, entry: Entry) -> None:
        try:
            entries = library.track_radio(self.session, entry)
        except Exception as exc:
            self.call_from_thread(self._radio_failed, str(exc))
            return
        self.call_from_thread(self._radio_ready, entry, entries)

    def _radio_failed(self, message: str) -> None:
        self.query_one("#busy", Spinner).stop()
        self.status = message

    def _radio_ready(self, entry: Entry, entries: list[Entry]) -> None:
        self.query_one("#busy", Spinner).stop()
        # The seed goes first: a station that opens on a different song looks
        # like the wrong thing started.
        self.queue.replace([entry, *entries], start=-1)
        self._sync_queue()
        self._play_index(0)
        self.status = _("radio de «{label}»: {count} pistas").format(
            label=entry.label, count=len(entries) + 1
        )

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
        """Play, resume or pause: whichever the current state calls for.

        One button, one key, one action. There is no second shortcut that
        pauses: two keys for the same job is the clutter merging the buttons
        was meant to remove.
        """
        if self.queue.current is not None and not self.mpv.idle:
            self.mpv.toggle_pause()
            self.status = _("pausa") if self.mpv.paused else _("reproduciendo")
        elif len(self.queue):
            self._play_index(self.query_one("#playlist", RowList).cursor)

    def _toggle_pause(self) -> None:
        """A plain toggle, with no key of its own: MPRIS `PlayPause` uses it.

        Not an `action_`, because nothing on the keyboard reaches it and a
        bindable name that cannot be bound is a lie in the config file.
        """
        self.mpv.toggle_pause()
        self.status = _("pausa") if self.mpv.paused else _("reproduciendo")

    def action_stop(self) -> None:
        self.mpv.stop()
        self.queue.playing = -1
        self._sync_queue()
        self.query_one(Marquee).text = ""
        self.status = _("detenido")

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
            self.status = _("pista quitada de la cola")

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
        self.status = _("cola vaciada")

    def action_shuffle(self) -> None:
        self.queue.shuffle = not self.queue.shuffle
        self.queue.save()
        self._refresh_modes()
        self.status = (
            _("shuffle activado") if self.queue.shuffle else _("shuffle desactivado")
        )

    def action_repeat(self) -> None:
        self.queue.repeat = self.queue.repeat.next()
        self.queue.save()
        self._refresh_modes()
        names = {
            Repeat.NONE: _("sin repetición"),
            Repeat.QUEUE: _("repetir cola"),
            Repeat.TRACK: _("repetir pista"),
        }
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
        self.query_one("#busy", Spinner).start(
            _("resolviendo «{title}»…").format(title=entry.title)
        )
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
                widget.cols,
                widget.rows,
                self.art_protocol,
                image_id=widget.image_id,
            )
        except Exception as exc:
            # A missing cover is decoration; it never touches the audio path.
            self.call_from_thread(
                setattr, self, "status", _("sin carátula: {error}").format(error=exc)
            )
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

    def push_screen(self, screen, callback=None, wait_for_dismiss=False, *, mode=None):
        self._hide_art()
        return super().push_screen(screen, callback, wait_for_dismiss, mode=mode)

    @work(thread=True, exclusive=True)
    def _resolve_worker(self, entry: Entry) -> None:
        try:
            # An access token only lasts a few hours, less than a listening
            # session; refresh it here rather than letting the next call fail.
            if ensure_fresh(self.session):
                self.call_from_thread(setattr, self, "status", _("sesión refrescada"))
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
            self.call_from_thread(
                self._resolve_failed, _("error: {error}").format(error=exc)
            )
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
        self.status = _("reproduciendo {label}").format(label=entry.label)
        if getattr(playable, "downgraded", False):
            # Say it out loud. The badge shows what arrived, which on its own
            # reads as if it were what we asked for.
            self.status = _("{status} · TIDAL entregó {got}, no {asked}").format(
                status=self.status, got=playable.quality, asked=playable.requested
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
            self.status = _("no hay una pista reproduciéndose")
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

    def action_help(self) -> None:
        # keys_for, not DEFAULT_KEYS: the screen has to show what the user's
        # own config file rebound, not what shipped.
        self.push_screen(HelpScreen(keys_for))

    def _eq_closed(self, _result: None) -> None:
        self.settings.save()
        self.status = (
            _("ecualizador activo") if self.settings.eq_active else _("ecualizador plano")
        )

    def _nudge_balance(self, delta: float) -> None:
        value = self.settings.set_balance(self.settings.balance + delta)
        self._apply_audio()
        self.settings.save()
        side = (
            _("centro")
            if value == 0
            else (
                f"{abs(int(value * 100))}% "
                + (_("izquierda") if value < 0 else _("derecha"))
            )
        )
        self.status = _("balance: {value}").format(value=side)

    def action_balance_left(self) -> None:
        self._nudge_balance(-0.1)

    def action_balance_right(self) -> None:
        self._nudge_balance(0.1)

    def action_balance_centre(self) -> None:
        self.settings.set_balance(0.0)
        self._apply_audio()
        self.settings.save()
        self.status = _("balance: {value}").format(value=_("centro"))

    def action_favourite(self) -> None:
        self._favourite_selected(True)

    def action_unfavourite(self) -> None:
        self._favourite_selected(False)

    def _favourite_selected(self, add: bool) -> None:
        """Favourite the track under the playlist cursor."""
        row = self.query_one("#playlist", RowList).current
        if row is None or row.entry is None:
            self.status = _("no hay ninguna pista seleccionada")
            return
        self._favourite_row(row, add)

    def _favourite_entry(self, entry: Entry) -> None:
        """Favourite one entry, for the browser's action menu."""
        self._favourite_row(Row(label=entry.label, entry=entry), True)

    def _favourite_row(self, row: Row, add: bool) -> None:
        self.query_one("#busy", Spinner).start(
            _("añadiendo a favoritos…") if add else _("quitando de favoritos…")
        )
        self._favourite_worker(row, add)

    @work(thread=True, exclusive=True, group="favourite")
    def _favourite_worker(self, row: Row, add: bool) -> None:
        try:
            message = favourite_message(self.session, row, add)
        except Exception as exc:
            self.call_from_thread(
                self._favourite_done, _("favoritos: {error}").format(error=exc)
            )
            return
        self.call_from_thread(self._favourite_done, message)

    def _favourite_done(self, message: str) -> None:
        self.query_one("#busy", Spinner).stop()
        self.status = message
        # Whatever favourites level is cached is now out of date.
        for level in ("fav:tracks", "fav:albums", "fav:artists"):
            library.forget(level)

    def action_toggle_time(self) -> None:
        clock = self.query_one(TimeDisplay)
        clock.countdown = not clock.countdown

    async def action_quit(self) -> None:
        # Async because Textual's own action_quit is: saving the queue, closing
        # mpv and dropping off the bus are things to finish, not to fire off.
        await self._shutdown()

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
        ceiling = Mpv.VOLUME_MAX / 100.0
        self.mpv.volume = int(max(0.0, min(ceiling, value)) * 100)

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
        self._toggle_pause()

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
        # Comes in on the bus, not from the keyboard: hand the shutdown to the
        # loop rather than awaiting it inside a D-Bus method call.
        self.run_worker(self._shutdown(), exclusive=False)
