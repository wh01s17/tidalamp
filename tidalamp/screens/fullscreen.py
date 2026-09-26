"""The full-screen view: the cover as large as the terminal allows."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rich.cells import cell_len
from rich.text import Text
from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from .. import artwork, config
from ..columns import QUALITY_LABELS
from ..i18n import _
from ..lyrics import LyricsDocument
from ..queue import Entry, Repeat
from ..theme import palette_for
from ..widgets import Artwork, Glide, LyricsBoard, SeekBar
from .rowlist import RowChosen, RowList, RowMenu

if TYPE_CHECKING:
    from ..app import TidalAmp


def _clock(seconds: float) -> str:
    minutes, rest = divmod(int(max(0.0, seconds)), 60)
    return f"{minutes}:{rest:02d}"


class FullArtwork(Artwork):
    """The cover with no ceiling but the room it is given.

    Its own kitty image id, so it neither replaces nor is replaced by the
    player's cover, which is taken down while this view is in front.
    """

    MAX_ROWS = 400

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.image_id = 2


# sixel is drawn at its own size in pixels, and TIDAL serves 1280 at most:
# past this many rows (at the 20 px a cell is taken to be) the cover would
# only be stretched, and a 4K-sized one was 6 MB and seconds of encoding.
SIXEL_ROWS = 1280 // artwork.CELL[1]


class TrackCard(Glide):
    """The title, the artists and the album at the foot of the view.

    One row each, gliding when a line does not fit. It was a `Static`, and a
    track with seven artists wrapped them onto the album's row and pushed the
    album out of the bar for good.
    """

    def _line_styles(self) -> list[str]:
        palette = palette_for(self)
        return [f"bold {palette['accent']}", palette["body"], palette["muted"]]


class FullscreenScreen(Screen[None]):
    """The cover centred and large, a bar at the foot, the words and the
    queue on demand.

    Not a window over the player but the player's other face: the cover is
    drawn here, not hidden, and windows opened over this view (help, speed)
    hide it the way they hide the player's. Opened with `w`, left with esc.

    `y` and `tab` open two panels to the right of the cover, which shrinks to
    make room: the lyrics first and the queue against the edge, so opening
    the queue over open lyrics docks it on the right rather than pushing the
    words out of the way.
    """

    BINDINGS = [
        Binding("escape", "close", _("volver"), show=False),
        Binding("tab", "toggle_queue", _("cola"), show=False, priority=True),
        Binding("up", "queue_up", "", show=False),
        Binding("down", "queue_down", "", show=False),
        Binding("enter", "queue_play", "", show=False),
        Binding("question_mark", "help", _("ayuda"), show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        # The cover this view asked for, so a track change is noticed on the
        # tick and a late answer for the last track is dropped.
        self._url = ""
        self._pending: artwork.Cover | None = None
        self._suspended = False
        self._panel = False
        # The lyrics panel: whether it is open, and which track it is on, so
        # a track change is noticed on the tick and asked for once.
        self._words = False
        self._words_entry: int | None = None
        # The clickable glyphs on the controls line, as (start, end, action).
        self._hits: list[tuple[int, int, str]] = []
        # The buttons on the right of the bar, as (start, end, action) in
        # cells counted back from the right edge: that line is right-aligned,
        # so where each word sits depends on the width of the bar.
        self._side_hits: list[tuple[int, int, str]] = []
        # What the queue panel last mirrored, to redraw it only when it changed.
        self._queue_shape: tuple = ()
        # Set once a kitty cover has been shown here: closing the view deletes
        # the image then, whatever the cover and the protocol are by that time.
        self._sent_kitty = False
        # False until on_mount, which runs once the widgets exist. The player's
        # tick sees this screen in front the moment it is pushed, before its
        # widgets are mounted, and a slow machine got there first.
        self._ready = False

    @property
    def player(self) -> TidalAmp:
        return cast("TidalAmp", self.app)

    def compose(self) -> ComposeResult:
        with Horizontal(id="fs-body"):
            with Vertical(id="fs-stage"):
                yield FullArtwork(id="fs-art")
            with Vertical(id="fs-lyrics"):
                # The words alone, with no heading over them: beside the
                # cover it is plain what they are, and the button on the bar
                # says so. Centred in their column, like the cover in its
                # stage, and drifting because the arrows here belong to the
                # queue: plain lyrics are carried by the song, not scrolled.
                yield LyricsBoard(id="fs-lyrics-body", drift=True, centre=True)
            with Vertical(id="fs-queue"):
                yield Static(_("COLA"), id="fs-queue-title", markup=False)
                yield RowList(id="fs-queue-list")
        with Horizontal(id="fs-bar"):
            yield TrackCard(id="fs-track")
            with Vertical(id="fs-centre"):
                yield Static("", id="fs-controls")
                yield SeekBar(id="fs-seek")
                yield Static("", id="fs-times", markup=False)
            yield Static("", id="fs-side")

    def on_mount(self) -> None:
        self._ready = True
        # The frame is the look's own: whatever border the player wears, this
        # view wears too, so a theme changes both.
        self.styles.border = self.player.query_one("#main").styles.border
        self.query_one("#fs-queue").display = False
        self.query_one("#fs-lyrics").display = False
        # Here, and only here, the names too long for the column slide to show
        # their end. This queue is a wall of thirty names read at a glance,
        # and the ones worth reading are exactly the ones that do not fit;
        # the player's own queue is read a row at a time with the cursor, and
        # there only the artist column moves.
        self.query_one("#fs-queue-list", RowList).set_glide()
        # The panel is the player's queue, not a copy with a cursor of its own:
        # every queue key (`g`, `d`, `alt+↑↓`, `m`, `f`) acts on the player's
        # cursor, so the panel follows that cursor the moment it moves.
        self.watch(self._main_list(), "cursor", self._cursor_moved, init=False)
        # And the other way: a click on the panel moves the player's cursor,
        # which is the one every queue key acts on.
        self.watch(
            self.query_one("#fs-queue-list", RowList),
            "cursor",
            self._panel_clicked,
            init=False,
        )
        self.follow(self.player.mpv.position, self.player.mpv.duration)
        self.call_after_refresh(self._laid_out)

    def on_resize(self, event) -> None:
        self.call_after_refresh(self._laid_out)

    def _laid_out(self) -> None:
        """What depends on the widgets' real sizes: the cover's box, and the
        controls, which are centred by hand and were drawn at width 0 on mount."""
        self._fit()
        self._render_controls()

    # ---------------------------------------------------------------- cover

    def _current_url(self) -> str:
        """The playing track's cover at 1280 px: the queue keeps the 320 that
        suits the player, and stretched to fill a 4K screen it is a blur."""
        entry = self.player.queue.current
        url = (entry.art_url or "") if entry is not None else ""
        return artwork.sized(url, 1280) if url else ""

    def _fit(self) -> None:
        """As large as the stage, square on screen, with a row of air."""
        stage = self.query_one("#fs-stage")
        width, height = stage.size.width, stage.size.height
        if not width or not height:
            return
        art = self.query_one(FullArtwork)
        rows = max(Artwork.MIN_ROWS, min(height - 2, (width - 4) // 2))
        if self.player.art_protocol is artwork.Protocol.SIXEL:
            rows = min(rows, SIXEL_ROWS)
        resized = art.resize(rows)
        if resized or art.cover is None or self._url != self._current_url():
            self._request()

    def _ground(self) -> tuple[int, int, int]:
        background = self.query_one("#fs-stage").styles.background
        if background.a:
            return (background.r, background.g, background.b)
        hex_ = palette_for(self)["display_background"].lstrip("#")
        return (int(hex_[0:2], 16), int(hex_[2:4], 16), int(hex_[4:6], 16))

    def _request(self) -> None:
        art = self.query_one(FullArtwork)
        url = self._current_url()
        protocol = self.player.art_protocol
        self._url = url
        if not url or protocol is artwork.Protocol.NONE:
            art.show(None)
            return
        self._cover_worker(
            url, art.cols, art.rows, protocol, config.COVER_SHAPE, self._ground()
        )

    @work(thread=True, exclusive=True, group="fs-art")
    def _cover_worker(
        self,
        url: str,
        cols: int,
        rows: int,
        protocol: artwork.Protocol,
        outline: str,
        ground: tuple[int, int, int],
    ) -> None:
        try:
            data = artwork.fetch(url)
            cover = artwork.render(
                data, cols, rows, protocol, image_id=2, outline=outline, ground=ground
            )
        except Exception:
            # A missing cover is decoration, here as in the player.
            return
        if cover is not None:
            self.app.call_from_thread(self._cover_ready, url, cover)

    def _cover_ready(self, url: str, cover: artwork.Cover) -> None:
        if url != self._url:
            return
        if self._suspended and cover.protocol is not artwork.Protocol.BLOCKS:
            self._pending = cover
            return
        self._show(cover)

    def _show(self, cover: artwork.Cover) -> None:
        if cover.protocol is artwork.Protocol.KITTY:
            self._sent_kitty = True
        self.query_one(FullArtwork).show(cover)

    def reload_cover(self) -> None:
        """The cover protocol changed (a window over this view turned
        transparency on, which moves it to blocks): drop the cover kept for
        after the window and fetch one in the protocol in use now."""
        self._pending = None
        self.query_one(FullArtwork).show(None)
        self._url = ""
        if not self._suspended:
            self._request()

    def on_screen_suspend(self, event: events.ScreenSuspend) -> None:
        """A window opened over this view: a pixel cover would float over it."""
        self._suspended = True
        art = self.query_one(FullArtwork)
        if art.cover is not None and art.cover.protocol is not artwork.Protocol.BLOCKS:
            self._pending = art.cover
            art.show(None)

    def on_screen_resume(self, event: events.ScreenResume) -> None:
        self._suspended = False
        pending, self._pending = self._pending, None
        # A cover kept from before the window, in a protocol that is no longer
        # the one in use, is not put back: it was a kitty image sent again
        # after transparency had moved the cover to blocks.
        if pending is not None and pending.protocol is self.player.art_protocol:
            self._show(pending)
        elif self._url != self._current_url() or pending is not None:
            self._url = ""
            self._request()

    # ------------------------------------------------------------- the bar

    def follow(self, position: float, duration: float) -> None:
        """The player's tick, while this view is in front."""
        if not self._ready:
            return
        seek = self.query_one("#fs-seek", SeekBar)
        seek.position, seek.total = position, duration
        self.query_one("#fs-times", Static).update(
            f"{_clock(position)}  /  {_clock(duration)}"
        )
        self._render_track()
        self._render_controls()
        self._render_side()
        if self._words:
            self._sync_lyrics(position, duration)
        if self._panel:
            self.mirror_queue()
        if self._current_url() != self._url:
            self._request()

    def _render_track(self) -> None:
        entry = self.player.queue.current
        if entry is None:
            lines = ["TIDAL AMP"]
        else:
            lines = [entry.title, entry.artist]
            if entry.album:
                lines.append(entry.album)
        self.query_one("#fs-track", TrackCard).update("\n".join(lines))

    def _render_controls(self) -> None:
        """Shuffle, previous, play, next and repeat, centred and clickable."""
        player = self.player
        palette = palette_for(self)
        plain = player.layout.ascii_only
        playing = not player.mpv.paused and not player.mpv.idle
        queue = player.queue
        # Heavier glyphs than the player's own, and a space between a mode's
        # sign and the mark that says which mode: at the foot of a screen
        # given over to one cover, the thin ones read as specks beside the
        # track's name, and «⟳A» read as one glyph nobody could name.
        if plain:
            shuffle = "SH *" if queue.shuffle else "SH -"
            repeat = "RP " + player.REPEAT_MARKS_ASCII[queue.repeat]
            prev, play, nxt = "<<", "||" if playing else "> ", ">>"
        else:
            # The heavy cut of each glyph, not the light one: at the foot of a
            # screen given over to one cover the thin marks read as specks
            # beside the track's name. «⬤ ◯» for the mode lamps, «❚❚» for the
            # pause, and the mode's sign apart from its mark.
            shuffle = "⇄ ⬤" if queue.shuffle else "⇄ ◯"
            repeat = f"{player.REPEAT_SIGN} {player.REPEAT_TAGS[queue.repeat]}"
            # Play is padded to the two cells the pause takes, the way the
            # ASCII row pads «> » to «||»: a button that changes width shifts
            # every button to its right each time it is pressed.
            prev, play, nxt = "◀◀", "❚❚" if playing else "▶ ", "▶▶"
        buttons = [
            ("shuffle", shuffle, queue.shuffle),
            ("prev", prev, False),
            ("play", play, True),
            ("next", nxt, False),
            ("repeat", repeat, queue.repeat is not Repeat.NONE),
        ]
        gap = "      "
        width = self.query_one("#fs-controls").size.width
        total = sum(cell_len(label) for _a, label, _l in buttons) + cell_len(gap) * (
            len(buttons) - 1
        )
        offset = max(0, (width - total) // 2)
        text = Text(" " * offset)
        self._hits = []
        cursor = offset
        for index, (action, label, lit) in enumerate(buttons):
            if index:
                text.append(gap)
                cursor += cell_len(gap)
            # Bold whether it is lit or not: unlit they are the same weight
            # as the times under them and disappeared into the bar.
            colour = palette["accent"] if lit else palette["body"]
            text.append(label, style=f"bold {colour}")
            self._hits.append((cursor, cursor + cell_len(label), action))
            cursor += cell_len(label)
        self.query_one("#fs-controls", Static).update(text)

    def _render_side(self) -> None:
        palette = palette_for(self)
        playable = self.player._playable
        text = Text(justify="right", no_wrap=True, overflow="ellipsis")
        if playable is not None:
            quality = QUALITY_LABELS.get(playable.quality, playable.quality)
            text.append(f"{quality} · {playable.khz} kHz", style=palette["muted"])
        # The two panels as buttons, lit while they are open. Each carries the
        # key that opens it, so the line under them is left for the way out.
        gap = "   "
        buttons = [
            ("toggle_lyrics", f"{self.player.lyrics_key} ♪ " + _("letra"), self._words),
            ("toggle_queue", "tab ≡ " + _("cola"), self._panel),
        ]
        text.append("\n")
        self._side_hits = []
        # Counted back from the right edge, the end of the line: the whole
        # line is right-aligned, so the last button ends where the bar does.
        back = 0
        for index, (action, label, _lit) in enumerate(reversed(buttons)):
            if index:
                back += cell_len(gap)
            self._side_hits.append((back, back + cell_len(label), action))
            back += cell_len(label)
        for index, (_action, label, lit) in enumerate(buttons):
            if index:
                text.append(gap, style=palette["muted"])
            text.append(
                label, style=f"bold {palette['accent']}" if lit else palette["body"]
            )
        text.append(
            f"\n? {_('ayuda')}   w/esc {_('volver')}",
            style=palette["muted"],
        )
        self.query_one("#fs-side", Static).update(text)

    @on(events.Click, "#fs-controls")
    def _controls_clicked(self, event: events.Click) -> None:
        # From the screen's coordinates, not `event.x`: which widget the
        # offset is counted from depends on who is handling the event.
        x = event.screen_x - self.query_one("#fs-controls").region.x
        for start, end, action in self._hits:
            if start <= x < end:
                getattr(self.player, f"action_{action}")()
                self._render_controls()
                break
        event.stop()

    @on(events.Click, "#fs-seek")
    def _seek_clicked(self, event: events.Click) -> None:
        seek = self.query_one("#fs-seek", SeekBar)
        position = seek.value_at(event.screen_x - seek.region.x)
        if position is not None:
            self.player.mpv.seek(position)
        event.stop()

    @on(events.Click, "#fs-side")
    def _side_clicked(self, event: events.Click) -> None:
        """The buttons sit on the second row of the side, against its right
        edge: which one was hit is counted back from that edge."""
        region = self.query_one("#fs-side").content_region
        event.stop()
        if event.screen_y != region.y + 1:
            return
        back = region.right - 1 - event.screen_x
        for start, end, action in self._side_hits:
            if start <= back < end:
                getattr(self, f"action_{action}")()
                break

    # ------------------------------------------------------------ the words

    @property
    def lyrics_open(self) -> bool:
        return self._words

    def action_toggle_lyrics(self) -> None:
        """Show or hide the words beside the cover, which shrinks to make room.

        With the queue open too the words go between the two, so the queue
        stays against the right edge where `tab` put it.
        """
        self._words = not self._words
        self.query_one("#fs-lyrics").display = self._words
        if self._words:
            # From scratch: the panel may have been closed for several tracks.
            self._words_entry = None
            self._sync_lyrics(self.player.mpv.position, self.player.mpv.duration)
        self._render_side()
        self.call_after_refresh(self._fit)

    def _sync_lyrics(self, position: float, duration: float) -> None:
        """Keep the panel on the playing track and on the line it is singing.

        One fetch per track, in a worker, through the same cache `y` uses in
        the player; everything else is the board comparing line numbers.
        """
        board = self.query_one("#fs-lyrics-body", LyricsBoard)
        entry = self.player.queue.current
        wanted = entry.id if entry is not None else None
        if wanted != self._words_entry:
            self._words_entry = wanted
            if entry is None:
                board.show(None, _("no hay una pista reproduciéndose"))
            else:
                board.show(None, _("buscando la letra…"))
                self._lyrics_worker(entry)
        board.follow(position, duration)

    @work(thread=True, exclusive=True, group="fs-lyrics")
    def _lyrics_worker(self, entry: Entry) -> None:
        try:
            document = self.player._lyrics_for(entry)
        except Exception as exc:
            self.app.call_from_thread(self._lyrics_failed, entry.id, str(exc))
            return
        self.app.call_from_thread(self._lyrics_ready, entry.id, document)

    def _lyrics_ready(self, entry_id: int, document: LyricsDocument) -> None:
        # The track moved on, or the view was closed, while the lyrics were
        # in flight: a thread worker is not stopped in the middle, and what
        # it answers to is gone.
        if entry_id != self._words_entry or not self.is_mounted:
            return
        self.query_one("#fs-lyrics-body", LyricsBoard).show(document)

    def _lyrics_failed(self, entry_id: int, message: str) -> None:
        if entry_id != self._words_entry or not self.is_mounted:
            return
        self.query_one("#fs-lyrics-body", LyricsBoard).show(None, message)

    # ------------------------------------------------------------ the queue

    @property
    def queue_open(self) -> bool:
        return self._panel

    def _main_list(self) -> RowList:
        return self.player.query_one("#playlist", RowList)

    def mirror_queue(self, force: bool = False) -> None:
        """Show the player's queue as it is: its rows, its mark, its cursor.

        The same rows as the player's list, filter and all, so a row here is
        the same row there and every queue action lands where it is aimed.
        """
        if not self._ready:
            return
        main = self._main_list()
        shape = (id(main.rows), len(main.rows), main.marked, main.cursor)
        if shape == self._queue_shape and not force:
            return
        self._queue_shape = shape
        listing = self.query_one("#fs-queue-list", RowList)
        listing.rows = main.rows
        listing.marked = main.marked
        listing.cursor = main.cursor
        listing.refresh()

    def _cursor_moved(self) -> None:
        if self._panel:
            self.mirror_queue()

    def _panel_clicked(self, cursor: int) -> None:
        main = self._main_list()
        if self._panel and main.cursor != cursor:
            main.cursor = cursor

    @on(RowChosen, "#fs-queue-list")
    def _panel_row_chosen(self, message: RowChosen) -> None:
        message.stop()
        self.action_queue_play()

    @on(RowMenu, "#fs-queue-list")
    def _panel_row_menu(self, message: RowMenu) -> None:
        message.stop()
        self.player.action_track_menu()

    def open_queue(self) -> None:
        if not self._panel:
            self.action_toggle_queue()

    def action_toggle_queue(self) -> None:
        """Show or hide the queue beside the cover, which shrinks to make room."""
        self._panel = not self._panel
        self.query_one("#fs-queue").display = self._panel
        if self._panel:
            self.mirror_queue(force=True)
        self._render_side()
        self.call_after_refresh(self._fit)

    def action_queue_up(self) -> None:
        if self._panel:
            self._main_list().move(-1)

    def action_queue_down(self) -> None:
        if self._panel:
            self._main_list().move(1)

    def action_queue_play(self) -> None:
        if self._panel:
            self.player.action_play_selected()
            self.mirror_queue(force=True)

    def action_help(self) -> None:
        """The help window, with this view's keys and nothing else."""
        # Here and not at the top: `app` imports this module.
        from ..app import keys_for
        from .help import HelpScreen

        self.app.push_screen(HelpScreen(keys_for, only="fullscreen"))

    def action_close(self) -> None:
        # Down first: a kitty image outlives the cells it was drawn over.
        art = self.query_one(FullArtwork)
        art.show(None)
        # And deleted by id whenever one was ever shown here, whatever the
        # cover is now: a view closed after its protocol changed left one
        # stuck on the player.
        driver = getattr(self.app, "_driver", None)
        if self._sent_kitty and driver is not None:
            driver.write(artwork.kitty_delete(art.image_id))
        self.dismiss(None)
