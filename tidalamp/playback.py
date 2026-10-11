"""Playing the queue: from a row to sound, and keeping it going.

A track is resolved in a worker and handed to mpv, and a resolve that comes
back after another was asked for is dropped. A load that fails is retried
and then named and skipped; a device unplugged mid-track moves the sound to
the default one; a dead or stuck mpv is restarted and the track picked up
where it was, as it is after PipeWire is restarted. Past the end of the
queue, the last track's radio can carry on. The second a session quit at is
kept for the next one.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from . import auth, config, library, stream
from .auth import NotLoggedIn
from .i18n import _
from .queue import Entry
from .screens import RowList
from .stream import Playable, StreamUnavailable, gain_for
from .widgets import Marquee, Spinner
from .workers import thread_worker

if TYPE_CHECKING:
    from .app import TidalAmp

# What `Playback.resolving` holds after a stop: an entry no resolve is ever
# for, so whatever comes back late is dropped instead of starting to play.
STOPPED = Entry(id=-1, title="", artist="")

log = logging.getLogger("tidalamp.playback")


class Playback:
    """Turns the queue into sound: what plays, from where, and after what."""

    # How many times a track that will not open is tried again before it is
    # named and skipped. Two, because the failures this exists for are
    # momentary — a CDN answering 500 under load — and a track that is really
    # gone should not hold the queue up for long.
    LOAD_RETRIES = 2
    # How long to wait before trying again after a restart of mpv that failed.
    MPV_RETRY = 5.0

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        # The entry the last resolve was started for. A worker's thread is not
        # cancelled with it: an older resolve can finish after a newer one was
        # asked for, and must not start its track over the newer one.
        self.resolving: Entry | None = None
        self.was_idle = True
        # What is playing, as it was resolved: the badges read it, and a
        # retry or a move to another device loads it again.
        self.playable: Playable | None = None
        # Whether mpv ever got the track that is loaded open. It is what
        # tells an ended track from a load that failed, which look the same
        # from here — both are mpv going idle. See `gave_up`.
        self.opened = False
        # How many times the track that is loaded has been tried again after
        # failing to open, and the second it was asked to start at, so a
        # retry picks up where the first attempt was aimed.
        self.retries = 0
        self.started_at = 0.0
        # Where the track was on the last tick, and the track and second a
        # restarted mpv has to pick up at. A dead or stuck mpv cannot be
        # asked where it was, so the tick's own reading is what is kept.
        self.last_position = 0.0
        self.resume: tuple[Entry, float] | None = None
        # The track, its second and whether it was paused, while PipeWire is
        # restarted under it (`stop_for_pipewire`).
        self.before_pipewire: tuple[Entry, float, bool] | None = None
        # mpv being restarted, or asked whether it is back, from a worker:
        # both wait seconds, and on the UI thread that was a frozen screen.
        self.recovering = False
        self.probing = False
        self.mpv_retry_at = 0.0
        # A radio being fetched to carry on past the end of the queue: one at
        # a time, so an idle mpv waiting for it cannot ask again.
        self.autoplaying = False

    @property
    def node(self) -> TidalAmp:
        return self.app

    def stop_for_pipewire(self) -> None:
        """Stop before PipeWire is restarted, keeping where the track was.

        mpv holds the sink and has to let go of it before the daemon goes.
        Stopping used to be the end of it: the music stayed stopped and the
        track, back at 0:00, was left to be found again (the maintainer
        expected it to go on, 2026-09-24). `back_from_pipewire` goes on.
        """
        current = self.app.queue.current
        self.before_pipewire = None
        if current is not None and not self.app.mpv.idle:
            self.before_pipewire = (current, self.app.mpv.position, self.app.mpv.paused)
        self.stop()

    def back_from_pipewire(self) -> None:
        """PipeWire is back: cava again, and the track from where it was.

        cava was a client of the daemon that went, and died with it: the
        analyser stayed on the RMS meter until tidalamp was opened again
        (seen by the maintainer, 2026-09-24). A track that was playing plays
        on; a paused one waits at its second for play, like a restored queue.
        """
        self.app.spectrum.pick()
        held, self.before_pipewire = self.before_pipewire, None
        if held is None or self.app.queue.playing != -1 or self.resolving is not STOPPED:
            # Nothing was playing, or something else was asked for meanwhile.
            return
        entry, seconds, paused = held
        index = next((i for i, row in enumerate(self.app.queue) if row is entry), -1)
        if index < 0:
            return
        self.resume = (entry, seconds)
        if not paused:
            self.play_index(index)

    def recover_mpv(self) -> None:
        """mpv died under us, or stopped answering for good. Respawn it
        instead of freezing the UI on a dead socket, and put the current
        track back where it was.

        In a worker: killing the old process and waiting for the new one's
        socket take seconds, and on the UI thread that was the whole screen
        frozen for them. The ticks stand still until it is back.
        """
        if self.recovering or time.monotonic() < self.mpv_retry_at:
            return
        self.recovering = True
        # The track goes back where it was, not to 0:00. The second is the
        # last tick's: the one before the stall or the death.
        current = self.app.queue.current
        if current is not None and self.last_position > 1:
            self.resume = (current, self.last_position)
        # A new process starts with an empty playlist: nothing is queued.
        self.app.prefetch.forget()
        self.app.status = _("mpv no responde; reiniciándolo…")
        self.restart_mpv_worker()

    @thread_worker(group="mpv-restart")
    def restart_mpv_worker(self) -> None:
        try:
            self.app.mpv.restart()
        except Exception as exc:
            self.app.call_from_thread(self.mpv_restart_failed, str(exc))
            return
        self.app.call_from_thread(self.mpv_restarted)

    def mpv_restart_failed(self, error: str) -> None:
        self.recovering = False
        self.mpv_retry_at = time.monotonic() + self.MPV_RETRY
        self.app.status = _("mpv murió y no se pudo reiniciar ({error})").format(
            error=error
        )

    def mpv_restarted(self) -> None:
        self.recovering = False
        self.was_idle = True
        self.app.apply_audio()
        index = self.app.queue.playing
        if 0 <= index < len(self.app.queue):
            self.app.status = _("mpv se reinició; recargando la pista")
            self.play_index(index)
        else:
            self.app.status = _("mpv se reinició")

    def probe_mpv(self) -> None:
        """Ask a stalled mpv whether it is back, off the UI thread."""
        if self.probing:
            return
        self.probing = True
        self.probe_mpv_worker()

    @thread_worker(group="mpv-probe")
    def probe_mpv_worker(self) -> None:
        answered = self.app.mpv.probe()
        self.app.call_from_thread(self.mpv_probed, answered)

    def mpv_probed(self, answered: bool) -> None:
        self.probing = False
        if answered:
            self.app.status = _("mpv vuelve a contestar")

    def play(self) -> None:
        """Play, resume or pause: whichever the current state calls for.

        One button, one key, one action. There is no second shortcut that
        pauses: two keys for the same job is the clutter merging the buttons
        was meant to remove.
        """
        if self.app.queue.current is not None and not self.app.mpv.idle:
            self.app.mpv.toggle_pause()
            self.app.status = _("pausa") if self.app.mpv.paused else _("reproduciendo")
            self.app.readout.refresh()
        elif len(self.app.queue):
            self.play_index(self.app.queue_view.cursor_index())

    def toggle_pause(self) -> None:
        """A plain toggle, with no key of its own: MPRIS `PlayPause` uses it.

        Not an `action_`, because nothing on the keyboard reaches it and a
        bindable name that cannot be bound is a lie in the config file.
        """
        self.app.mpv.toggle_pause()
        self.app.status = _("pausa") if self.app.mpv.paused else _("reproduciendo")

    def stop(self) -> None:
        self.autoplaying = False
        if self.resolving is not None and self.resolving is not STOPPED:
            # A resolve on its way: its spinner goes, and so does its track
            # when it comes back.
            self.app.query_one("#busy", Spinner).stop()
        self.resolving = STOPPED
        # `stop` empties mpv's playlist, the track queued after this one too.
        self.app.prefetch.forget()
        self.resume = None
        self.app.mpv.stop()
        self.app.queue.playing = -1
        # The tick reads "mpv went idle" as "the track ended" and moves on.
        # Stopping makes mpv idle on purpose, so say so first, or the next
        # tick restarts the queue from the top — which is what «v» did.
        self.was_idle = True
        self.app.queue_view.sync()
        self.app.query_one(Marquee).text = ""
        self.playable = None
        self.app.readout.refresh()
        self.app.status = _("detenido")

    def next(self) -> None:
        index = self.app.queue.next_index()
        log.debug("siguiente: %s", "fin de la cola" if index is None else index + 1)
        if index is None:
            if config.AUTOPLAY and self.autoplay():
                return
            self.stop()
        else:
            self.play_index(index)

    def autoplay(self) -> bool:
        """Ask TIDAL for the last track's radio to carry on with. False when
        there is nothing to carry on from, and the queue stops as it would."""
        if self.autoplaying:
            return True
        seed = self.app.queue.current
        if seed is None and len(self.app.queue):
            seed = list(self.app.queue)[-1]
        if seed is None:
            return False
        self.autoplaying = True
        self.app.status = _("buscando la radio de «{label}»…").format(label=seed.label)
        self.autoplay_worker(seed)
        return True

    @thread_worker(group="autoplay")
    def autoplay_worker(self, seed: Entry) -> None:
        try:
            entries = library.track_radio(self.app.session, seed)
        except Exception as exc:
            self.app.call_from_thread(self.autoplay_failed, str(exc))
            return
        self.app.call_from_thread(self.autoplay_ready, seed, entries)

    def autoplay_ready(self, seed: Entry, entries: list[Entry]) -> None:
        """Add the station to the end, not over the queue.

        Unlike the track menu's radio, which replaces the queue and starts on
        its seed: the seed is what just finished, and the queue is still the
        user's. Tracks already in it are left out, so the station does not
        loop back over what was just heard.
        """
        # Stopped, or something else started, while the radio was on its way:
        # the user decided, and a late station must not override them.
        if not self.autoplaying:
            return
        self.autoplaying = False
        have = {entry.id for entry in self.app.queue}
        fresh = [entry for entry in entries if entry.id not in have]
        if not fresh:
            self.stop()
            self.app.status = _(
                "reproducción automática: no hay más para «{label}»"
            ).format(label=seed.label)
            return
        start = len(self.app.queue)
        self.app.queue.append(fresh)
        self.app.queue_view.sync()
        self.play_index(start)
        self.app.status = _("reproducción automática: radio de «{label}»").format(
            label=seed.label
        )

    def autoplay_failed(self, message: str) -> None:
        if not self.autoplaying:
            return
        self.autoplaying = False
        self.stop()
        self.app.status = _("reproducción automática: {error}").format(error=message)

    def prev(self) -> None:
        index = self.app.queue.prev_index()
        if index is not None:
            self.play_index(index)

    def play_index(self, index: int) -> None:
        self.autoplaying = False
        if not 0 <= index < len(self.app.queue):
            return
        # Whatever was resolved ahead was for the track after the old one,
        # and the old one goes on playing until this resolves: were it to end
        # meanwhile, mpv would go on to the queued track, not to this.
        self.app.prefetch.drop()
        entry = self.announce(index)
        log.debug("reproducir %s. «%s»", index + 1, entry.title)
        # The spinner carries the message while we wait; repeating it in the
        # status text next to it would just say the same thing twice.
        self.app.status = ""
        self.app.query_one("#busy", Spinner).start(
            _("resolviendo «{title}»…").format(title=entry.title)
        )
        self.resolving = entry
        self.resolve_worker(entry)

    def announce(self, index: int) -> Entry:
        """Show ``index`` as the track playing: the queue's marker and cursor,
        the title, the details and the cover. Not the sound: either a resolve
        brings it, or mpv already went on to it by itself."""
        entry = self.app.queue[index]
        self.app.queue.playing = index
        self.app.prefetch.failed = None
        playlist = self.app.query_one("#playlist", RowList)
        row = self.app.queue_view.row_at(index)
        # A track started from outside the filter — «next», the radio, MPRIS —
        # can be one the filter hides. The cursor stays where the user left it
        # rather than jumping to an unrelated row.
        if row >= 0:
            playlist.cursor = row
        playlist.marked = row
        playlist.refresh()
        self.app.query_one(Marquee).text = f"{index + 1}. {entry.title}"
        self.app.readout.refresh_track_meta()
        self.app.saved(self.app.queue.save())
        self.app.cover.load(entry)
        return entry

    @thread_worker()
    def resolve_worker(self, entry: Entry) -> None:
        try:
            # An access token only lasts a few hours, less than a listening
            # session; refresh it here rather than letting the next call fail.
            # A free row needs neither: it carries its own URL, and
            # refreshing a TIDAL token to play something that is not TIDAL's
            # would be a request per track for nothing.
            if entry.is_tidal and auth.ensure_fresh(self.app.session):
                self.app.call_from_thread(
                    setattr, self.app, "status", _("sesión refrescada")
                )
            # A restored entry has no Track yet; this is where we pay for it.
            playable = stream.playable_for(entry, self.app.session)
        except NotLoggedIn as exc:
            self.app.call_from_thread(self.resolve_failed, str(exc), entry)
            return
        except StreamUnavailable as exc:
            self.app.call_from_thread(self.resolve_failed, str(exc), entry)
            return
        except Exception as exc:
            self.app.call_from_thread(
                self.resolve_failed, _("error: {error}").format(error=exc), entry
            )
            return
        self.app.call_from_thread(self.start, entry, playable)

    def stale(self, entry: Entry | None) -> bool:
        """Whether a resolve that just came back is for a track no longer wanted."""
        return (
            entry is not None
            and self.resolving is not None
            and entry is not self.resolving
        )

    def resolve_failed(self, message: str, entry: Entry | None = None) -> None:
        if self.stale(entry):
            return
        self.resolving = None
        self.app.query_one("#busy", Spinner).stop()
        self.app.status = message

    def start(self, entry: Entry, playable: Playable) -> None:
        if self.stale(entry):
            # «Next» was pressed again while this one resolved; the spinner
            # belongs to the newer resolve, still on its way. Or stop was.
            return
        self.resolving = None
        self.app.query_one("#busy", Spinner).stop()
        # Only the reload after a restart starts part way in, and only for the
        # track it was taken for: «next» meanwhile starts the next at 0:00.
        resume, self.resume = self.resume, None
        start = resume[1] if resume is not None and resume[0] is entry else 0.0
        self.app.mpv.load(playable.url, gain_for(playable), start=start)
        self.was_idle = False
        self.now_playing(entry, playable, start=start)

    def play_on_the_default(self, were_at: float) -> None:
        """Move to the system's default output and go on from where it was.

        For this session only: the setting keeps the device, and the next
        start plays to it again if it is back (`player._device_option`).
        """
        self.app.mpv.set_device("auto")
        self.app.status = _(
            "se desconectó el dispositivo de salida; suena por el predeterminado"
        )
        entry, playable = self.app.queue.current, self.playable
        if entry is None or playable is None:
            return
        start = were_at if self.opened else self.started_at
        # Whatever mpv had queued after it went with the output.
        self.app.prefetch.drop()
        self.app.mpv.load(playable.url, gain_for(playable), start=start)
        self.was_idle = False
        self.opened = False
        self.retries = 0
        self.started_at = start
        self.app.output.follow()
        self.app.spectrum.pick()

    def gave_up(self) -> None:
        """mpv went idle without ever having got the track open.

        That is a load that failed, not a track that ended, and the two used
        to be the same thing here: a URL mpv could not open put «reproduciendo
        X» in the status line and then slid to the next track a second and a
        half later, saying nothing. A queue of them raced past in seconds.

        Worth retrying rather than skipping, because the failure that causes
        this is usually a moment's worth: the Internet Archive answers 500
        under load and the very same URL comes back 206 a second later,
        measured on four of them. TIDAL's CDN does the same. So it is tried
        again, from where it was, and only then given up on and named.
        """
        entry, playable = self.app.queue.current, self.playable
        if entry is None or playable is None:
            return
        log.debug("«%s» no abrió (intento %s)", entry.title, self.retries + 1)
        if self.retries < self.LOAD_RETRIES:
            self.retries += 1
            self.app.status = _("«{title}» no abrió; reintentando…").format(
                title=entry.title
            )
            self.app.mpv.load(playable.url, gain_for(playable), start=self.started_at)
            self.was_idle = False
            return
        # After the skip and not before it: `next` writes its own
        # status on the way past, so saying this first said it to nobody.
        self.next()
        self.app.status = _("no se pudo abrir «{title}»; saltando").format(
            title=entry.title
        )

    def now_playing(self, entry: Entry, playable: Playable, start: float = 0.0) -> None:
        """What changes once a track sounds, whether a resolve started it or
        mpv went on to it by itself.

        Both of those are where a track becomes the one playing, so this is
        where its «has mpv got it open yet» is cleared — including for a
        track mpv slid into with no gap, which never goes through `start`.
        """
        self.playable = playable
        self.opened = False
        self.retries = 0
        self.started_at = start
        self.app.readout.refresh()
        # PipeWire can switch graph rate when playback starts. Query it off
        # the UI thread after handing the URL to mpv.
        self.app.output.follow()
        self.app.status = _("reproduciendo {label}").format(label=entry.label)
        if getattr(playable, "downgraded", False):
            # Say it out loud. The badge shows what arrived, which on its own
            # reads as if it were what we asked for.
            self.app.status = _("{status} · TIDAL entregó {got}, no {asked}").format(
                status=self.app.status, got=playable.quality, asked=playable.requested
            )

    def remember_position(self) -> None:
        """Where the track was, for the next session to pick up at.

        Written once, on the way out: from the tick it would rewrite the
        queue ten times a second. A crash therefore keeps the second of the
        last clean quit, not of the crash. A track restored and never played
        this session keeps the second it was restored with.
        """
        self.app.queue.position = 0.0
        current = self.app.queue.current
        if current is not None:
            seconds = self.last_position
            # Quit while it reloads, after a restart or a play on a restored
            # track: mpv says 0:00 because it has not opened it yet, and the
            # second it is on its way to is the one worth keeping.
            if seconds <= 1 and self.resume is not None and self.resume[0] is current:
                seconds = self.resume[1]
            if seconds > 1:
                self.app.queue.position = seconds
            return
        if self.resume is None:
            return
        entry, seconds = self.resume
        index = next((i for i, row in enumerate(self.app.queue) if row is entry), -1)
        if index >= 0:
            self.app.queue.playing = index
            self.app.queue.position = seconds

    def restore_position(self) -> None:
        """Pick up the second the last session quit at, once that track plays.

        Not at once: a restored queue never starts playing by itself, and an
        idle mpv read as a track that ended would move the queue on. The
        second waits in `resume` for `start`, the same way a restarted mpv
        goes back to its track, and anything else played first drops it.
        """
        index, seconds = self.app.queue.resume_at, self.app.queue.resume_position
        if not 0 <= index < len(self.app.queue) or seconds <= 1:
            return
        entry = self.app.queue[index]
        self.resume = (entry, seconds)
        self.app.status = _(
            "cola restaurada ({count} pistas); «{title}» sigue en {time}"
        ).format(
            count=len(self.app.queue),
            title=entry.title,
            time=f"{int(seconds) // 60}:{int(seconds) % 60:02d}",
        )
