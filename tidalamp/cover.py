"""The cover in the player's display band.

Which protocol the terminal draws it with, fetching and cutting it in a
worker, growing its box with the terminal, and taking a pixel cover down
while a window is in front of it, since kitty and sixel pictures paint over
whatever text is drawn on top of them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import artwork, config
from .i18n import _
from .queue import Entry
from .widgets import Artwork
from .workers import thread_worker

if TYPE_CHECKING:
    from .app import TidalAmp

# Fixed pieces of the display band, from styles/player.tcss. `fit` needs them
# to work out how much of the row is left for the cover.
CLOCK_WIDTH = 24
READOUT_WIDTH = 30
DISPLAY_HEIGHT = 9


class CoverView:
    """The cover in the display band: fetched, cut, sized and put away."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        # How this terminal can draw a cover, decided once from the environment.
        self.protocol = artwork.detect_protocol(configured=config.ARTWORK)
        self.url = ""
        # The outline and ground the cover on screen was cut with, so a look
        # that changes either draws it again.
        self.cut_with: tuple[str, tuple[int, int, int]] | None = None
        # A pixel cover taken down while a window is in front, to put back.
        self.hidden = False
        self.pending: artwork.Cover | None = None

    @property
    def node(self) -> TidalAmp:
        return self.app

    def replace_pixel(self) -> None:
        """Take a kitty or sixel cover down and put it straight back.

        Switching the arrangement moves the band the cover sits in without
        necessarily changing its size, and a pixel picture is not text: the
        terminal keeps the old placement where it was drawn until something
        deletes it. Put back through `show`, it is deleted first and drawn
        again where the band now is, whatever the terminal does with a
        placement it was not told to remove.
        """
        widget = self.widget()
        if widget is None or widget.cover is None:
            return
        if widget.cover.protocol is artwork.Protocol.BLOCKS:
            return
        cover = widget.cover
        widget.show(None)
        widget.show(cover)

    def fit(self, compact_changed: bool = False) -> None:
        """Grow the cover box with the terminal, then draw the cover again.

        Two ceilings. Vertically the display band must not eat the playlist,
        so it takes a quarter of the height; horizontally the box shares its
        row with the 24-cell clock and the readout, which needs about 30 cells
        before the marquee stops saying anything useful.
        """
        widget = self.widget()
        if widget is None:
            return
        display = self.app.query_one("#display")
        if self.app.looks.compact:
            if widget.cover is not None:
                widget.show(None)
            if compact_changed:
                display.styles.height = 5
            return
        by_height = self.app.size.height // 4
        # Split, the band shares the player's column with the lyrics above
        # it, and the column is half the panel.
        room = (
            self.app.size.width // 2 - 2 if self.app.looks.split else self.app.size.width
        )
        # Six: the band's two cells of left padding and the four of slack.
        by_width = (room - CLOCK_WIDTH - READOUT_WIDTH - 6) // 2
        resized = widget.resize(min(by_height, by_width))
        # Unconditionally, not only when the cover changed size. The padding
        # is the other half of the sum and it settles on its own schedule: at
        # startup the layout class is set before Textual has recomputed the
        # styles, so the first pass reads no padding, and the second pass —
        # where the real terminal size arrives — resizes nothing and used to
        # skip the correction. Assigning a height that is already right costs
        # nothing; getting here and not assigning it cost a row of cover on
        # top of the seek bar.
        self.fit_band()
        # resize() dropped the cover it had, because it was the old size. A
        # compact layout does the same so graphical protocols cannot float
        # over the queue; expanding fetches it again here.
        if self.url and (resized or widget.cover is None):
            self.worker(self.url)

    def fit_band(self) -> None:
        """Make the band as tall as the cover plus whatever padding it carries.

        `height` is border-box, so padding comes out of the content: a band
        sized for the cover alone leaves it a row short. And a graphical
        protocol does not clip to its widget — it paints over whatever is
        below — so that row lands on the seek bar rather than being cut off.

        Its own function because two things change the sum. The cover resizing
        is the obvious one; switching layout is the other, since each carries
        different padding, and for a while that one went unnoticed: the band
        kept the height worked out under the layout before it.
        """
        widget = self.widget()
        if widget is None:
            return
        display = self.app.query_one("#display")
        padding = display.styles.padding
        display.styles.height = (
            max(DISPLAY_HEIGHT, widget.rows) + padding.top + padding.bottom
        )

    def look(self) -> tuple[str, tuple[int, int, int]]:
        """The outline the look cuts the cover to, and the ground its corners
        take: the band's own, which nova and cuaderno paint as the panel."""
        background = self.app.query_one("#display").styles.background
        if background.a:
            ground = (background.r, background.g, background.b)
        else:
            hex_ = self.app.tidalamp_palette["display_background"].lstrip("#")
            ground = (int(hex_[0:2], 16), int(hex_[2:4], 16), int(hex_[4:6], 16))
        return config.COVER_SHAPE, ground

    def reshape(self) -> None:
        """Draw the cover again if the look now cuts it differently."""
        if self.url and self.cut_with not in (None, self.look()):
            self.worker(self.url)

    def load(self, entry: Entry) -> None:
        """Ask for this entry's cover, unless we are already showing it."""
        if self.protocol is artwork.Protocol.NONE:
            return
        widget = self.widget()
        if widget is None:
            return
        if not entry.art_url:
            self.url = ""
            widget.show(None)
            return
        if entry.art_url == self.url:
            return
        self.url = entry.art_url
        if self.app.looks.compact:
            widget.show(None)
            return
        self.worker(entry.art_url)

    # Its own group: the default one is the resolve worker's, and an exclusive
    # worker cancels the rest of its group — the cover would kill playback.
    @thread_worker(group="artwork")
    def worker(self, url: str) -> None:
        widget = self.app.query_one(Artwork)
        look = self.look()
        try:
            data = artwork.fetch(url)
            cover = artwork.render(
                data,
                widget.cols,
                widget.rows,
                self.protocol,
                image_id=widget.image_id,
                outline=look[0],
                ground=look[1],
            )
        except Exception as exc:
            # A missing cover is decoration; it never touches the audio path.
            self.app.call_from_thread(
                setattr, self.app, "status", _("sin carátula: {error}").format(error=exc)
            )
            cover = None
        if url == self.url:
            self.cut_with = look
            # None too: a cover that could not be had takes the last one
            # down, rather than leaving another record's cover over this one.
            self.app.call_from_thread(self.ready, cover)

    def reload(self) -> None:
        """Draw the cover again with the protocol that is now configured.

        It used to take a restart, which was tolerable while the cover was a
        detail of the display. It stopped being tolerable when transparency
        began moving this setting on the user's behalf: they turned on «let
        the player show through the window» and the hole where the cover had
        been stayed there until they restarted the very thing they were
        configuring.
        """
        self.protocol = artwork.detect_protocol(configured=config.ARTWORK)
        widget = self.widget()
        if widget is None:
            return
        # Down first, and through `show(None)`: a kitty cover is a picture the
        # terminal is holding on our behalf, and it outlives the cells it was
        # drawn over until something deletes it. That is what `show(None)`
        # sends. Then the caches go, so the reload is not mistaken for the
        # cover that is already up.
        self.hidden = False
        self.pending = None
        widget.show(None)
        self.url = ""
        entry = self.app.queue.current
        if entry is not None:
            self.load(entry)
        # The full-screen view keeps a cover of its own, in the old protocol.
        fullscreen = self.app.fullscreen_view()
        if fullscreen is not None:
            fullscreen.reload_cover()

    def ready(self, cover: artwork.Cover | None) -> None:
        """Put a freshly rendered cover up — and take it straight back down if
        there is a window in front of it.

        A cover that lands while a modal is open used to be painted over that
        modal, because a pixel protocol draws above the text no matter when it
        arrived. It happens on any track change made from the browser, not
        only when the protocol is switched. Half blocks are text and stay.
        """
        widget = self.widget()
        if widget is None:
            return
        # Not shown and then hidden: kept for when the window closes. It used
        # to go up and then through `hide`, which returns early when a
        # cover is already hidden, and one always is once a window has opened
        # over a pixel cover. So a cover arriving behind the window (a track
        # changed from the browser, or a theme changed in the settings, which
        # re-measures the box and fetches the cover again) stayed up, painted
        # over the window.
        if (
            cover is not None
            and len(self.app.screen_stack) > 1
            and cover.protocol is not artwork.Protocol.BLOCKS
        ):
            self.hidden = True
            self.pending = cover
            return
        # Up now, so whatever a window hid before is stale. Left set, the next
        # tick saw a hidden cover with no window in front and put it back,
        # over this one: pick another record in the browser, its cover lands
        # from the cache as the browser closes, and the last record's comes
        # back a quarter of a second later (seen on 2026-09-14).
        self.hidden = False
        self.pending = None
        widget.show(cover)

    def widget(self) -> Artwork | None:
        """The cover widget, or ``None`` before ``compose`` has produced it.

        Textual pushes the default screen on the way up, which reaches
        ``push_screen`` below while there is still nothing to query.
        """
        try:
            return self.app.query_one(Artwork)
        except Exception:
            return None

    def hide(self) -> None:
        """Take the cover down while another screen is in front.

        kitty and sixel images live above the text: the terminal paints them
        over the cells, so a modal would open *underneath* the cover instead
        of over it. Half blocks are ordinary characters and stack like any
        other text, so those stay — which is what the scrim behind a modal is
        for, and a cover that blinked out on `l` was the one hole in it.
        """
        widget = self.widget()
        if self.hidden or widget is None or widget.cover is None:
            return
        if widget.cover.protocol is artwork.Protocol.BLOCKS:
            return
        self.hidden = True
        self.pending = widget.cover
        widget.show(None)

    def restore(self) -> None:
        widget = self.widget()
        if not self.hidden or widget is None:
            return
        self.hidden = False
        if self.app.looks.compact:
            return
        widget.show(self.pending)
