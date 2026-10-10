"""The retro-player TUI.

`TidalAmp` is the root that holds the player together: it composes the
widgets, owns the session, mpv, the queue and the settings, binds the keys,
runs the two ticks and opens the windows. What each part of the player does
lives in an object of its own, which the app creates and every other part
reaches through it:

- `looks.Looks`: size, arrangement, look, palette and the terminal's frame.
- `transport.Transport`: the row of buttons and the menu beside it.
- `cover.CoverView`: the cover in the display band.
- `readout.Readout`: the lines that say what plays and how.
- `spectrum_feed.SpectrumFeed`: what the analyser draws.
- `output.Output`: the sink, its rate and the device chosen.
- `playback.Playback`: from a row to sound, and keeping it going.
- `prefetch.Prefetcher`: the next track, queued in mpv ahead of time.
- `queue_view.QueueView`: the queue on screen, its filter and its edits.
- `lyrics_feed.LyricsFeed`: the lyrics every view asks for.
- `library_tasks.LibraryTasks`: errands to the TIDAL account.
- `setting_changes.SettingChanges`: a setting changed while running.
- `media_bridge.MediaBridge`: what MPRIS and the media keys may ask.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import tidalapi
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Input, Static

from . import artwork, audio, auth, config, desktop, library, theme, workers
from .cover import CoverView
from .i18n import _
from .keys import bind, keys_for
from .library_tasks import LibraryTasks
from .looks import Looks
from .lyrics_feed import LyricsFeed
from .media_bridge import MediaBridge
from .mpris import MediaService, MprisService
from .output import Output
from .playback import Playback
from .player import Mpv
from .prefetch import Prefetcher
from .queue import Queue
from .queue_view import QueueView
from .readout import Readout
from .screens import (
    BrowserScreen,
    ChoiceScreen,
    ConfigScreen,
    CreditsScreen,
    EqScreen,
    FullscreenScreen,
    HelpScreen,
    LyricsScreen,
    PlaylistNameScreen,
    RowChosen,
    RowList,
    RowMenu,
    SearchScreen,
    SpeedScreen,
    speed_text,
)
from .setting_changes import SettingChanges
from .settings import Settings
from .spectrum_feed import SpectrumFeed
from .stream import cleanup_playlists
from .theme import ThemePalette
from .transport import Transport
from .widgets import (
    Analyzer,
    Artwork,
    Glide,
    LyricsPane,
    Marquee,
    SeekBar,
    Slider,
    Spinner,
    TimeDisplay,
)
from .workers import quiet_after_teardown

log = logging.getLogger("tidalamp.app")


class MainPanel(Vertical):
    """The whole UI, in one container that watches its own size.

    ``Resize`` does not bubble and never reaches the App, so the check for a
    terminal too small to draw has to hang off something that is laid out.
    This panel is width and height 100%, which makes it the screen's stand-in.
    """

    def on_resize(self, event) -> None:
        cast("TidalAmp", self.app).looks.check_size()


class Measured(Static):
    """A line drawn to its own width: a ruled title, a heading with the hints
    pushed to the right edge, a menu cropped to fit.

    It redraws itself when its size changes. The app used to guess when that
    happened (a resize, a change of layout, one refresh after switching the
    arrangement) and switching back from split beat the guess: the queue's
    heading kept the half width it had and its hints stopped in the middle.
    """

    def on_resize(self, event) -> None:
        app = self.app
        if isinstance(app, TidalAmp) and app.query("#transport-menu"):
            app.looks.refresh_widths()


class TidalAmp(App):
    """Main application."""

    # Read in this order; later rules win at equal specificity.
    CSS_PATH = [
        "styles/base.tcss",
        "styles/player.tcss",
        "styles/compact.tcss",
        "styles/looks.tcss",
        "styles/themed.tcss",
    ]
    TITLE = "TIDAL AMP"

    # Nothing takes focus on its own. The player is driven by bindings, which
    # only fire while no widget is eating the keys, and the queue's search box
    # is a widget that would otherwise grab them at startup and swallow `x`.
    # Every screen that wants a cursor in a box focuses it itself.
    AUTO_FOCUS = None

    # At 60×18 the compact layout drops the cover and balance row. Below that
    # even the transport, a useful queue and the status line cannot coexist.
    MIN_WIDTH = 60
    MIN_HEIGHT = 18

    # Where `split` is allowed to put the queue beside the player. The clock
    # and the readout alone are 54 columns, so the player's half needs close
    # to the 80 the stacked panel needs whole. The transport is not in the
    # sum: split runs it under both columns. The height is the compact
    # threshold, because a player half without its cover is not worth a
    # column of its own.
    SPLIT_MIN_WIDTH = 160
    SPLIT_MIN_HEIGHT = 26

    # Winamp's own transport keys, kept as muscle memory. Rebindable ones come
    # from DEFAULT_KEYS through the config file; navigation stays fixed.
    BINDINGS = [
        bind("prev", _("anterior"), show=True),
        bind("play", "play", show=True),
        bind("stop", "stop", show=True),
        bind("next", _("siguiente"), show=True),
        bind("search", _("buscar"), show=True),
        bind("filter_queue", _("buscar en la cola")),
        bind("track_menu", _("menú de la pista")),
        bind("to_playing", _("volver a la pista que suena")),
        bind("save_playlist", _("guardar la cola como playlist")),
        bind("library", _("biblioteca"), show=True),
        bind("lyrics", _("letra"), show=True),
        bind("credits", _("créditos")),
        bind("equalizer", _("ecualizador"), show=True),
        bind("shuffle", "shuffle", show=True),
        bind("repeat", "repeat", show=True),
        Binding("up", "cursor_up", _("arriba"), show=False),
        Binding("down", "cursor_down", _("abajo"), show=False),
        Binding("pageup", "cursor_page_up", "", show=False),
        Binding("pagedown", "cursor_page_down", "", show=False),
        Binding("enter", "play_selected", _("reproducir"), show=False),
        Binding("escape", "close_queue_filter", "", show=False),
        bind("remove", _("quitar")),
        bind("move_up", _("subir")),
        bind("move_down", _("bajar")),
        bind("clear", _("vaciar")),
        bind("undo_clear", _("deshacer el vaciado")),
        bind("seek_back", "-5s"),
        bind("seek_fwd", "+5s"),
        bind("vol_up", "vol+"),
        bind("vol_down", "vol-"),
        bind("balance_left", _("balance izq")),
        bind("balance_right", _("balance der")),
        bind("balance_centre", _("centrar balance")),
        bind("toggle_time", _("tiempo")),
        bind("speed", _("velocidad")),
        bind("fullscreen", _("pantalla completa")),
        bind("favourite", _("favorito")),
        bind("unfavourite", _("quitar favorito")),
        bind("config", _("config"), show=True),
        bind("help", _("ayuda"), show=True),
        bind("quit", _("salir"), show=True),
        # Priority, so it is checked before any window: the way out that does
        # not ask has to work whatever is open. `q` is not, or typing a «q»
        # into a search box would quit.
        Binding(
            keys_for("force_quit"),
            "force_quit",
            _("salir sin preguntar"),
            show=False,
            priority=True,
        ),
    ]

    status = reactive(_("listo"))

    def __init__(self, session: tidalapi.Session, mpv: Mpv) -> None:
        self.tidalamp_palette: ThemePalette = theme.load_palette(name=config.PALETTE)
        super().__init__()
        self.session = session
        self.mpv = mpv
        # Windows asks mpv what the output is; Linux asks PipeWire and ignores it.
        audio.use_player(mpv)
        self.queue = Queue()
        self.settings = Settings.load()
        # The parts of the player, each in an object of its own (see the
        # module's docstring). Every one of them reaches the others through
        # the app, so the order they are made in does not matter.
        self.looks = Looks(self)
        self.transport = Transport(self)
        self.cover = CoverView(self)
        self.readout = Readout(self)
        self.spectrum = SpectrumFeed(self)
        self.output = Output(self)
        self.playback = Playback(self)
        self.prefetch = Prefetcher(self)
        self.queue_view = QueueView(self)
        self.lyrics = LyricsFeed(self)
        self.tasks = LibraryTasks(self)
        self.setting_changes = SettingChanges(self)
        # What the media keys and the desktop's panel reach.
        self.media = MediaBridge(self)
        self.mpris: MediaService = MprisService(self.media)
        self._mpris_ready = False
        # The question `q` asks, while it is open.
        self._quit_question: ChoiceScreen | None = None
        # What the play/pause button is currently drawn as.
        self._transport_playing = False
        # What the status line already says, so writing it again is free.
        self._status_line = ""
        # Whether a failed save has been reported already. Once a session:
        # the queue is saved on every track change, and a full disk would
        # otherwise take the status line over.
        self._save_warned = False
        # Set by the CLI when this is the first start that can offer a menu
        # launcher. Off by default, so tests and embedders never see it.
        self.offer_launcher = False
        # Set by a logout that takes the app's data: on the way out nothing is
        # saved, and these are deleted again once mpv has let go, since the
        # queue, the settings and the covers were being written until then.
        self.forget_on_exit: tuple[Path, ...] = ()

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Expose the detected palette to the static TCSS stylesheet."""
        return self.tidalamp_palette.css_variables()

    # ---------------------------------------------------------------- the panel

    def compose(self) -> ComposeResult:
        with MainPanel(id="main"):
            # markup=False on both headings: a layout that rules them with
            # «[ TIDAL AMP ]» hands Static a string that Rich would read as a
            # tag, and the brackets and everything between them disappeared.
            yield Measured(self.looks.title_text(), id="titlebar", markup=False)
            # The player and the queue, each in a container of its own even
            # while they are stacked, and the transport between them as a
            # sibling of both. `split` lays the three out on a grid with a
            # class and the stylesheet, and moves the transport under both
            # columns with `move_child`, which reorders without remounting.
            # Moving widgets between containers would be remove() and
            # mount(), which throws away the queue's cursor, the decoded
            # cover and the marquee's phase.
            with Vertical(id="player-half"):
                # Hidden while stacked; `split` gives it the rows of the
                # column the band does not use.
                yield LyricsPane(id="lyrics-pane")
                with Horizontal(id="display"):
                    yield Artwork(id="art")
                    with Vertical(id="clockbox"):
                        yield TimeDisplay(id="clock")
                        # The rest of the track's identity, under the time:
                        # the marquee above only has room for one line and it
                        # spends it on the title.
                        yield Glide(id="trackmeta")
                    with Vertical(id="readout"):
                        yield Marquee(id="marquee")
                        yield Glide(id="badges")
                        yield Glide("OUT  —", id="output")
                        yield Analyzer(id="analyzer")
                yield SeekBar(id="seek")
                yield Slider(id="volume")
                yield Slider(id="balance")
            # Two halves, not one string: the transport keys belong with the
            # sliders above them, and the windows read as a menu, which they
            # only do once there is air between the two. Shuffle and repeat
            # sit on the left with the transport: they are buttons that hold
            # a state, not places to go. Both halves are filled in by
            # `Transport.refresh`, which dims the separators and lights the state.
            with Horizontal(id="transport"):
                yield Static("", id="transport-play")
                yield Measured("", id="transport-menu")
            with Vertical(id="queue-half"):
                yield Measured("", id="pl-title", markup=False)
                yield RowList(id="playlist")
                # The queue's own search bar, the same shape as the browser's:
                # it opens under the list without covering it, so the queue
                # narrows under the eyes of whoever is typing. Hidden until
                # ctrl+f.
                with Horizontal(id="queue-filter-bar"):
                    yield Input(placeholder=_("buscar en la cola…"), id="queue-filter")
                    # markup=False: it counts rows for text the user typed,
                    # and a «[» in it would be read as a tag.
                    yield Static("", id="queue-filter-count", markup=False)
            with Horizontal(id="statusbar"):
                yield Spinner(id="busy")
                yield Static("", id="status", markup=False)
        yield Static("", id="too-small")

    def on_terminal_supports_synchronized_output(self, _message: object) -> None:
        # Textual's own handler turns it on; this only leaves a trace, which is
        # the first thing to look for if the cover blinks again.
        log.info("el terminal acepta frames enteros (modo 2026)")

    def on_unmount(self) -> None:
        # Before Textual leaves the alternate screen, while the driver still
        # writes: the shell gets its own background back.
        if self.looks.terminal_margin is not None and self._driver is not None:
            self._driver.write("\033]111\033\\")
            self._driver.flush()
            self.looks.terminal_margin = None

    def call_from_thread(
        self, callback: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Textual's, for a thread worker that finishes after the app has:
        see `workers.call_from_thread`."""
        return workers.call_from_thread(self, callback, *args, **kwargs)

    def on_mount(self) -> None:
        self.looks.ask_for_synchronized_output()
        self.looks.paint_terminal_margin()
        self.looks.check_size()
        self.query_one("#queue-filter-bar", Horizontal).display = False
        playlist = self.query_one("#playlist", RowList)
        playlist.empty_text = _("cola vacía — / para buscar, l para tu biblioteca")
        # Only the artist column slides here, when a track's artists do not
        # fit it; the titles are read a row at a time with the cursor and
        # keep their crop (the full-screen queue slides those too).
        playlist.set_glide(names=False)
        volume = self.query_one("#volume", Slider)
        # Tied to the player's own ceiling rather than left on the widget
        # default: when the two drifted apart, the bar drew past its track.
        volume.maximum = Mpv.VOLUME_MAX
        volume.label = "VOL/mpv"
        volume.value = self.mpv.volume
        balance = self.query_one("#balance", Slider)
        balance.label = "BAL"
        balance.centred = True
        self.apply_audio()
        self.spectrum.start()
        self.readout.refresh()
        self.output.follow()
        self.set_interval(1 / 10, self._tick_fast)
        self.set_interval(1 / 4, self._tick_slow)
        self.set_interval(2, self.looks.refresh_theme)
        self.set_interval(2, self.output.watch)
        self.run_worker(self._start_mpris(), exclusive=False)

        if self.queue.load():
            self.queue_view.sync()
            playlist.cursor = max(0, self.queue_view.row_at(self.queue.resume_at))
            self.status = _("cola restaurada ({count} pistas)").format(
                count=len(self.queue)
            )
            self.playback.restore_position()
        self.transport.refresh()
        self.queue_view.refresh_title()
        # Last, so it wins over the queue-restore message: without Pillow the
        # cover never appears and nothing else would ever say why.
        if (
            self.cover.protocol is not artwork.Protocol.NONE
            and not artwork.have_decoder()
        ):
            self.status = _('sin carátula: falta Pillow (pip install "tidalamp[art]")')
        if self.offer_launcher:
            self._ask_launcher()

    def _ask_launcher(self) -> None:
        """First start: ask whether tidalamp should appear in the menu."""
        self.push_screen(
            ChoiceScreen(
                desktop.question(),
                [
                    ("create", _("sí, crear el acceso directo")),
                    ("decline", _("no, y no volver a preguntar")),
                ],
                hint=_(" ↑↓ elegir  ↵ aplicar  esc preguntar la próxima vez"),
            ),
            self._launcher_answered,
        )

    def _launcher_answered(self, value: object) -> None:
        if value == "create":
            if desktop.create() is not None:
                self.status = desktop.created()
            else:
                self.status = _("no se pudo crear el acceso directo; mira el log")
        elif value == "decline":
            desktop.decline()
            self.status = _("sin acceso directo; no se volverá a preguntar")

    def apply_audio(self) -> None:
        """Push balance and EQ into mpv's filter chain and redraw the slider.

        Also called after mpv is respawned: a fresh process starts with an
        empty chain, so the settings would silently stop applying otherwise.
        """
        self.mpv.set_filter("balance", self.settings.balance_graph())
        self.mpv.set_filter("eq", self.settings.eq_graph())
        self.query_one("#balance", Slider).value = int(self.settings.balance * 100)

    async def _start_mpris(self) -> None:
        """Claim the MPRIS bus name. A desktop without a session bus is not an
        error: we just run without the integration."""
        try:
            name = await self.mpris.start()
        except Exception as exc:
            self.status = _("{name} no disponible ({error})").format(
                name=self.mpris.label, error=exc
            )
            return
        self._mpris_ready = True
        if self.mpris.shared:
            # Another tidalamp already holds the plain name.
            self.status = _("MPRIS como {name} (ya había otra instancia)").format(
                name=name
            )

    # ------------------------------------------------------------------- ticks

    @quiet_after_teardown
    def _tick_fast(self) -> None:
        # Nothing to read off an mpv being restarted or not answering; the
        # slow tick says so on the status line.
        if self.playback.recovering or self.mpv.stalled:
            return
        playing = not self.mpv.paused and not self.mpv.idle
        # The play/pause button follows the state, but only redraw it when the
        # state actually turns over: this runs ten times a second. It happens
        # behind a modal too, so closing one never shows a stale glyph.
        if playing != self._transport_playing:
            self._transport_playing = playing
            self.transport.refresh()
            self.readout.refresh()

        # Nothing behind a modal is worth animating. The scrim leaves the
        # player visible on purpose, and a translucent screen is what makes
        # that expensive: every analyzer frame repaints the player *and*
        # blends the whole terminal again, ten times a second. Measured on a
        # 4K terminal with the library open, 240x62: 8.8% of a core with the
        # backdrop still against 37.7% with it dancing behind a window nobody
        # is looking at. cava keeps only its latest frame, so the analyzer
        # picks up where the music is — not where it was — on the way back.
        if len(self.screen_stack) > 1:
            return

        if self.spectrum.cava is not None:
            if self.spectrum.cava.alive:
                self.spectrum.feed(self.spectrum.cava.frame())
            else:
                self.spectrum.stop()
        analyzer = self.spectrum.analyzer()
        analyzer.level = self.mpv.rms()
        analyzer.active = playing
        analyzer.tick()
        self.query_one(Marquee).tick()

    @quiet_after_teardown
    def _tick_slow(self) -> None:
        if self.playback.recovering:
            return
        if not self.mpv.alive or self.mpv.stalled_for() > Mpv.STALL_LIMIT:
            self.playback.recover_mpv()
            return
        if self.mpv.stalled:
            # Alive but not answering. Every command gives up at once while
            # it is like this, so the screen keeps moving; a worker asks it
            # whether it is back, and past STALL_LIMIT it is restarted.
            self.status = _("mpv no contesta; esperando a que vuelva…")
            self._refresh_status()
            self.playback.probe_mpv()
            return

        position, duration = self.mpv.position, self.mpv.duration
        # Idle reads as 0:00, and a track cut short by its output going away
        # is picked up where it was, so the reading before this one is kept.
        were_at = self.playback.last_position
        self.playback.last_position = position
        # The same rule as the fast tick: a player nobody is looking at does
        # not redraw itself. Four times a second, a moving clock behind a
        # modal costs a repaint of the player *and* a blend of the whole
        # terminal, for a second hand under a scrim.
        if len(self.screen_stack) == 1:
            clock = self.query_one(TimeDisplay)
            clock.seconds, clock.total = position, duration

            seek = self.query_one(SeekBar)
            seek.position, seek.total = position, duration
            self.query_one("#volume", Slider).value = self.mpv.volume
        elif isinstance(self.screen, FullscreenScreen):
            # The full-screen view draws the same clock and bar in its own
            # widgets; the player behind it is not looked at.
            self.screen.follow(position, duration)
        # The status line is the exception. A favourite added from the browser
        # reports there, and through the scrim it is legible, so it is written
        # even behind a modal — and it costs nothing when the words are the
        # same, which four times a second they almost always are.
        self._refresh_status()

        # mpv went on by itself to the track queued after this one: the gap
        # that is not there. It never goes idle in between, so it has to be
        # looked for here.
        if self.prefetch.prepared is not None and self.mpv.playlist_pos > 0:
            self.prefetch.advance()

        # A track mpv got open is a track that can end. Until then, idle
        # means the load failed rather than the track finishing
        # (`Playback.gave_up`).
        # The duration and not only the position, because mpv publishes it as
        # soon as the file opens: a track two seconds long can begin and end
        # between two of these ticks without a position ever being read, and
        # judging it by the position alone called it a failure and retried a
        # track that had played perfectly well.
        if position > 0 or duration > 0:
            self.playback.opened = True

        # mpv going idle after having played something means the track ended.
        idle = self.mpv.idle
        if idle and not self.playback.was_idle:
            if self.output.gone():
                self.playback.play_on_the_default(were_at)
            elif self.playback.opened:
                self.playback.next()
            else:
                self.playback.gave_up()
        self.playback.was_idle = idle
        if not idle:
            self.prefetch.start(position, duration)

        if self.cover.hidden and len(self.screen_stack) == 1:
            self.cover.restore()

        if self.looks.split and len(self.screen_stack) == 1:
            self.lyrics.follow(position)

        if self._mpris_ready:
            self.mpris.publish()
            self.mpris.publish_tracks()

    def _refresh_status(self) -> None:
        """Write the status line, and only when it changed: `Static.update()`
        repaints whether or not the words moved."""
        line = f" {self.status}"
        # A failed save is said once in full, and the very next message (the
        # track that starts, the repeat mode) wrote over it before anyone
        # could read it. The mark stays for the session: nothing is being
        # saved, and that stays true until the app is restarted.
        if self._save_warned:
            line += "  " + _("· sin guardar en disco")
        if line == self._status_line:
            return
        self._status_line = line
        self.query_one("#status", Static).update(line)

    def saved(self, error: OSError | None) -> None:
        """Say that a save failed, once a session.

        The queue, the settings and the library's orders are written by
        modules that know nothing of Textual; they hand the error back and
        this is where it is shown. Not fatal, but not silent either: with a
        full disk the queue used to be lost without a trace.
        """
        if error is None or self._save_warned:
            return
        self._save_warned = True
        log.warning("no se pudo guardar: %s", error)
        self.status = _("no se pudo guardar en disco ({error})").format(error=error)

    # ---------------------------------------------------------------- the mouse

    @on(events.Click, "#transport-play")
    def _transport_clicked(self, event: events.Click) -> None:
        """Give the framed transport the mouse behaviour its shape promises."""
        action = self.transport.action_at(event.x)
        if action is not None:
            getattr(self, f"action_{action}")()
            event.stop()

    @on(events.Click, "#seek")
    def _seek_clicked(self, event: events.Click) -> None:
        position = self.query_one("#seek", SeekBar).value_at(event.x)
        if position is not None:
            self.mpv.seek(position)
        event.stop()

    @on(events.Click, "#volume")
    def _volume_clicked(self, event: events.Click) -> None:
        slider = self.query_one("#volume", Slider)
        self.mpv.volume = slider.value_at(event.x)
        slider.value = self.mpv.volume
        self.status = _("volumen: {value}").format(value=self.mpv.volume)
        event.stop()

    @on(events.Click, "#balance")
    def _balance_clicked(self, event: events.Click) -> None:
        slider = self.query_one("#balance", Slider)
        self._set_balance(slider.value_at(event.x) / 100)
        event.stop()

    # ------------------------------------------------------------------ queue

    @on(RowChosen, "#playlist")
    def _queue_row_chosen(self, message: RowChosen) -> None:
        """A double click on a queue row plays it, as ↵ does."""
        message.stop()
        self.action_play_selected()

    @on(RowMenu, "#playlist")
    def _queue_row_menu(self, message: RowMenu) -> None:
        """A right click on a queue row opens its menu, as `m` does."""
        message.stop()
        self.queue_view.track_menu()

    # ---------------------------------------------------------- queue filter

    @on(Input.Changed, "#queue-filter")
    def _queue_filter_changed(self, event: Input.Changed) -> None:
        value = event.value.strip()
        if value == self.queue_view.filter:
            return
        self.queue_view.filter = value
        self.queue_view.sync()

    @on(Input.Submitted, "#queue-filter")
    def _queue_filter_submitted(self, event: Input.Submitted) -> None:
        """↵ hands the keys back to the queue and leaves the filter applied."""
        self.query_one("#queue-filter", Input).blur()
        self.set_focus(None)

    # ------------------------------------------------- the library and search

    def action_search(self) -> None:
        self.push_screen(SearchScreen(), self._run_search)

    def _run_search(self, query: str | None) -> None:
        if not query:
            return
        self.push_screen(
            BrowserScreen(
                _("BUSCAR: {query}").format(query=query),
                lambda: library.search_rows(self.session, query),
                search=True,
            ),
            self.queue_view.browser_answered,
        )

    def action_save_playlist(self) -> None:
        if not len(self.queue):
            self.status = _("la cola está vacía; no hay nada que guardar")
            return
        self.push_screen(PlaylistNameScreen(), self.tasks.save_named)

    def action_library(self) -> None:
        self.push_screen(
            BrowserScreen(_("MI BIBLIOTECA"), lambda: library.root(self.session)),
            self.queue_view.browser_answered,
        )

    # --------------------------------------------------------- the queue's keys

    def action_cursor_up(self) -> None:
        self.query_one("#playlist", RowList).move(-1)

    def action_cursor_down(self) -> None:
        self.query_one("#playlist", RowList).move(1)

    def action_cursor_page_up(self) -> None:
        self.query_one("#playlist", RowList).move(-10)

    def action_cursor_page_down(self) -> None:
        self.query_one("#playlist", RowList).move(10)

    def action_play(self) -> None:
        self.playback.play()

    def action_stop(self) -> None:
        self.playback.stop()

    def action_next(self) -> None:
        self.playback.next()

    def action_prev(self) -> None:
        self.playback.prev()

    def action_track_menu(self) -> None:
        self.queue_view.track_menu()

    def action_filter_queue(self) -> None:
        self.queue_view.open_filter()

    def action_close_queue_filter(self) -> None:
        self.queue_view.close_filter()

    def action_to_playing(self) -> None:
        self.queue_view.to_playing()

    def action_remove(self) -> None:
        self.queue_view.remove()

    def action_clear(self) -> None:
        self.queue_view.clear()

    def action_undo_clear(self) -> None:
        self.queue_view.undo_clear()

    def action_shuffle(self) -> None:
        self.queue_view.shuffle()

    def action_repeat(self) -> None:
        self.queue_view.repeat()

    def action_play_selected(self) -> None:
        if len(self.queue):
            self.playback.play_index(self.queue_view.cursor_index())

    def action_move_up(self) -> None:
        self.queue_view.move_entry(-1)

    def action_move_down(self) -> None:
        self.queue_view.move_entry(1)

    # ------------------------------------------------------------------ windows

    def push_screen(self, screen, callback=None, wait_for_dismiss=False, *, mode=None):
        self.cover.hide()
        # The `transparency` setting travels as a class rather than as two
        # copies of the stylesheet: the CSS says what transparent looks like,
        # this says whether this window is.
        screen.set_class(self.see_through(below=self.screen), "transparent")
        return super().push_screen(screen, callback, wait_for_dismiss, mode=mode)

    @staticmethod
    def see_through(below) -> bool:
        """Whether a window opened over ``below`` lets it show through.

        Never over the full-screen view. What lies under a window there is a
        cover as large as the terminal, and every change inside the window
        sends its rows again with that cover blended in at the sides. Measured
        in a pty at 480x130 with the cover in blocks: opening the help cost
        0.86 MB and twenty lines of scroll 1.21 MB with the window see-through,
        0.22 and 0.35 without. The player behind the other windows keeps it.
        """
        return config.TRANSPARENCY and not isinstance(below, FullscreenScreen)

    # ----------------------------------------------------------------- fiddles

    def action_seek_back(self) -> None:
        self.mpv.seek(-5, "relative")

    def action_seek_fwd(self) -> None:
        self.mpv.seek(5, "relative")

    def action_vol_up(self) -> None:
        self.mpv.volume = self.mpv.volume + 5

    def action_vol_down(self) -> None:
        self.mpv.volume = self.mpv.volume - 5

    def action_credits(self) -> None:
        """The credit of the row under the cursor, or of the track playing.

        The cursor first, because that is what the eye is on: in the queue
        `k` reads about the row you are looking at, the way `m` acts on it.
        With the queue hidden, or nothing selected, it falls back to what is
        sounding, which is the only thing there is to ask about then.
        """
        row = None
        if not self.queue_hidden() and self.query("#playlist"):
            row = self.query_one("#playlist", RowList).current
        entry = row.entry if row is not None and row.entry is not None else None
        if entry is None:
            entry = self.queue.current
        if entry is None:
            self.status = _("no hay una pista reproduciéndose")
            return
        if entry.is_tidal:
            # Not a failure worth a red line: TIDAL's catalogue has no licence
            # that asks anything of the listener and no page to point at.
            self.status = _("los créditos son de «Lofi sin copyright»")
            return
        self.push_screen(CreditsScreen(entry))

    def action_lyrics(self) -> None:
        # In the full-screen view the words are a panel beside the cover, not
        # a window over it: a window there hides the very cover they belong
        # to, and its own panel can sit next to the queue.
        if isinstance(self.screen, FullscreenScreen):
            self.screen.action_toggle_lyrics()
            return
        if self.queue.current is None:
            self.status = _("no hay una pista reproduciéndose")
            return
        self.push_screen(
            LyricsScreen(
                lambda: self.queue.current,
                self.lyrics.for_entry,
                lambda: self.mpv.position,
            )
        )

    def action_equalizer(self) -> None:
        self.push_screen(EqScreen(self.settings, self.apply_audio), self._eq_closed)

    def action_fullscreen(self) -> None:
        """The cover as large as the terminal allows, a bar under it, and the
        queue beside it on demand. Only from the player itself; pressed again
        in the view, it closes it, as esc does."""
        if isinstance(self.screen, FullscreenScreen):
            self.screen.action_close()
            return
        if len(self.screen_stack) > 1:
            return
        if self.size.width < self.MIN_WIDTH or self.size.height < self.MIN_HEIGHT:
            self.status = _(
                "la pantalla completa necesita al menos {width}×{height}"
            ).format(width=self.MIN_WIDTH, height=self.MIN_HEIGHT)
            return
        self.push_screen(FullscreenScreen())

    @property
    def lyrics_key(self) -> str:
        """The key that opens the lyrics, for the full-screen view's button:
        `y`, or whatever the config file rebound it to."""
        return keys_for("lyrics").split(",")[0]

    def fullscreen_view(self) -> FullscreenScreen | None:
        """The full-screen view, if it is anywhere on the stack."""
        return next(
            (
                screen
                for screen in self.screen_stack
                if isinstance(screen, FullscreenScreen)
            ),
            None,
        )

    def queue_hidden(self) -> bool:
        """True while the full-screen view is in front with its queue closed.

        The queue keys act on the player's cursor, which that view shows in
        its panel. With the panel closed they would act on a row nobody can
        see, so they ask for it instead.
        """
        screen = self.screen
        if isinstance(screen, FullscreenScreen) and not screen.queue_open:
            self.status = _("abre la cola con tab para eso")
            return True
        return False

    def action_speed(self) -> None:
        self.push_screen(SpeedScreen(self.mpv.speed), self.speed_chosen)

    def speed_chosen(self, speed: float | None) -> None:
        if speed is None or speed == self.mpv.speed:
            return
        self.mpv.speed = speed
        self.status = _("velocidad: {value}").format(value=speed_text(speed))
        self.transport.refresh()

    def action_config(self) -> None:
        self.push_screen(ConfigScreen(self.setting_changes.apply))

    def action_help(self) -> None:
        # keys_for, not DEFAULT_KEYS: the screen has to show what the user's
        # own config file rebound, not what shipped.
        self.push_screen(HelpScreen(keys_for))

    def _eq_closed(self, _result: None) -> None:
        self.saved(self.settings.save())
        self.status = (
            _("ecualizador activo") if self.settings.eq_active else _("ecualizador plano")
        )

    def _nudge_balance(self, delta: float) -> None:
        self._set_balance(self.settings.balance + delta)

    def _set_balance(self, requested: float) -> None:
        value = self.settings.set_balance(requested)
        self.apply_audio()
        self.saved(self.settings.save())
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
        self._set_balance(0.0)

    def action_favourite(self) -> None:
        self.tasks.favourite_selected(True)

    def action_unfavourite(self) -> None:
        self.tasks.favourite_selected(False)

    def action_toggle_time(self) -> None:
        clock = self.query_one(TimeDisplay)
        clock.countdown = not clock.countdown

    async def action_quit(self) -> None:
        """Ask before closing: `q` sits right next to `w`, and a slip from
        the full-screen key closed the player. The cursor starts on «cancel»;
        `q` again with the question open means yes."""
        if self._quit_question is not None and self.screen is self._quit_question:
            self._quit_question.dismiss("quit")
            return
        self._quit_question = ChoiceScreen(
            _("¿SALIR DE TIDALAMP?"),
            [("quit", _("salir")), ("cancel", _("cancelar"))],
            cursor=1,
            # The quit key again means yes; the app's binding cannot hear it
            # with this window in front.
            keys=tuple(key.strip() for key in keys_for("quit").split(",")),
            key_value="quit",
        )
        self.push_screen(self._quit_question, self._quit_answered)

    def _quit_answered(self, answer: object) -> None:
        self._quit_question = None
        if answer == "quit":
            self.quit_now()

    def quit_now(self) -> None:
        """Close the player without asking, the way «salir» does once asked."""
        self.run_worker(self.close_player(), exclusive=False)

    async def action_force_quit(self) -> None:
        # Async because Textual's own action_quit is: saving the queue, closing
        # mpv and dropping off the bus are things to finish, not to fire off.
        await self.close_player()

    async def close_player(self) -> None:
        """Save, let go of mpv and the bus, and exit.

        Not `_shutdown`: that is Textual's own, the one that closes the screens
        and the driver once the app exits, and a method of that name here
        replaced it rather than running before it.
        """
        if not self.forget_on_exit:
            self.playback.remember_position()
            self.saved(self.queue.save())
            self.saved(self.settings.save())
        if self._mpris_ready:
            await self.mpris.stop()
        self.spectrum.stop()
        self.mpv.close()
        cleanup_playlists()
        if self.forget_on_exit:
            auth.logout(self.forget_on_exit)
        self.exit()
