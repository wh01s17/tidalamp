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
from ..queue import Repeat
from ..theme import palette_for
from ..widgets import Artwork, SeekBar
from .rowlist import RowList

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


class FullscreenScreen(Screen[None]):
    """The cover centred and large, a bar at the foot, the queue on demand.

    Not a window over the player but the player's other face: the cover is
    drawn here, not hidden, and windows opened over this view (help, speed)
    hide it the way they hide the player's. Opened with `w`, left with esc.
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
        # The clickable glyphs on the controls line, as (start, end, action).
        self._hits: list[tuple[int, int, str]] = []
        # What the queue panel last mirrored, to redraw it only when it changed.
        self._queue_shape: tuple = ()

    @property
    def player(self) -> TidalAmp:
        return cast("TidalAmp", self.app)

    def compose(self) -> ComposeResult:
        with Horizontal(id="fs-body"):
            with Vertical(id="fs-stage"):
                yield FullArtwork(id="fs-art")
            with Vertical(id="fs-queue"):
                yield Static(_("COLA"), id="fs-queue-title", markup=False)
                yield RowList(id="fs-queue-list")
        with Horizontal(id="fs-bar"):
            yield Static("", id="fs-track", markup=False)
            with Vertical(id="fs-centre"):
                yield Static("", id="fs-controls")
                yield SeekBar(id="fs-seek")
                yield Static("", id="fs-times", markup=False)
            yield Static("", id="fs-side")

    def on_mount(self) -> None:
        # The frame is the look's own: whatever border the player wears, this
        # view wears too, so a theme changes both.
        self.styles.border = self.player.query_one("#main").styles.border
        self.query_one("#fs-queue").display = False
        # The panel is the player's queue, not a copy with a cursor of its own:
        # every queue key (`g`, `d`, `alt+↑↓`, `m`, `f`) acts on the player's
        # cursor, so the panel follows that cursor the moment it moves.
        self.watch(self._main_list(), "cursor", self._cursor_moved, init=False)
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
        self.query_one(FullArtwork).show(cover)

    def on_screen_suspend(self, event: events.ScreenSuspend) -> None:
        """A window opened over this view: a pixel cover would float over it."""
        self._suspended = True
        art = self.query_one(FullArtwork)
        if art.cover is not None and art.cover.protocol is not artwork.Protocol.BLOCKS:
            self._pending = art.cover
            art.show(None)

    def on_screen_resume(self, event: events.ScreenResume) -> None:
        self._suspended = False
        if self._pending is not None:
            self.query_one(FullArtwork).show(self._pending)
            self._pending = None

    # ------------------------------------------------------------- the bar

    def follow(self, position: float, duration: float) -> None:
        """The player's tick, while this view is in front."""
        seek = self.query_one("#fs-seek", SeekBar)
        seek.position, seek.total = position, duration
        self.query_one("#fs-times", Static).update(
            f"{_clock(position)}  /  {_clock(duration)}"
        )
        self._render_track()
        self._render_controls()
        self._render_side()
        if self._panel:
            self.mirror_queue()
        if self._current_url() != self._url:
            self._request()

    def _render_track(self) -> None:
        palette = palette_for(self)
        entry = self.player.queue.current
        text = Text(no_wrap=True, overflow="ellipsis")
        if entry is None:
            text.append("TIDAL AMP", style=f"bold {palette['accent']}")
        else:
            text.append(entry.title, style=f"bold {palette['accent']}")
            text.append(f"\n{entry.artist}", style=palette["body"])
            if entry.album:
                text.append(f"\n{entry.album}", style=palette["muted"])
        self.query_one("#fs-track", Static).update(text)

    def _render_controls(self) -> None:
        """Shuffle, previous, play, next and repeat, centred and clickable."""
        player = self.player
        palette = palette_for(self)
        plain = player.layout.ascii_only
        playing = not player.mpv.paused and not player.mpv.idle
        queue = player.queue
        if plain:
            shuffle = "SH*" if queue.shuffle else "SH-"
            repeat = "RP" + player.REPEAT_MARKS_ASCII[queue.repeat]
            prev, play, nxt = "<<", "||" if playing else "> ", ">>"
        else:
            shuffle = "⇄●" if queue.shuffle else "⇄○"
            repeat = player.REPEAT_GLYPHS[queue.repeat]
            prev, play, nxt = "◀◀", "‖" if playing else "▶", "▶▶"
        buttons = [
            ("shuffle", shuffle, queue.shuffle),
            ("prev", prev, False),
            ("play", play, True),
            ("next", nxt, False),
            ("repeat", repeat, queue.repeat is not Repeat.NONE),
        ]
        gap = "     "
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
            style = f"bold {palette['accent']}" if lit else palette["body"]
            text.append(label, style=style)
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
        text.append(
            "\n≡ " + _("cola"),
            style=f"bold {palette['accent']}" if self._panel else palette["body"],
        )
        text.append(
            f"\n? {_('ayuda')}   tab {_('cola')}   w/esc {_('volver')}",
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
        self.action_toggle_queue()
        event.stop()

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
        if not self.is_mounted:
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
        self.query_one(FullArtwork).show(None)
        self.dismiss(None)
