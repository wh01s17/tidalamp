"""How the player looks: its size, its arrangement, its look and its palette.

The terminal's size decides between the full player, the compact one and the
notice that it is too small, and whether the queue goes beside the player
(split). The look puts its classes on the panel, tints its glyphs, puts its
emblem behind the queue and draws its titles; the palette follows an Omarchy
theme switch. In Windows Terminal the margin around the cells is painted in
the panel's colour, and the terminal is asked to take whole frames.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import TYPE_CHECKING

from rich.text import Text
from textual.color import Color
from textual.widgets import Static

from . import artwork, config, theme
from .i18n import _
from .layouts import Layout, backdrop_for, layout_for
from .screens import RowList
from .theme import LAYOUTS
from .widgets import LyricsPane, Marquee
from .workers import quiet_after_teardown

if TYPE_CHECKING:
    from .app import TidalAmp


class Looks:
    """How the player is laid out and dressed, as the terminal and the settings change."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        # Below 80x26 the cover and the balance row go.
        self.compact = False
        # The OSC 11 last sent to Windows Terminal, None while it keeps its own.
        self.terminal_margin: str | None = None
        # The look and palette the frame's flourish was drawn for.
        self.flourish: tuple[str, int] | None = None

    @quiet_after_teardown
    def check_size(self) -> None:
        """Cover the UI with an explanation when the terminal is too small."""
        width, height = self.app.size.width, self.app.size.height
        compact = width < 80 or height < 26
        compact_changed = compact != self.compact
        self.compact = compact
        main = self.app.query_one("#main")
        if main.has_class("compact") != compact:
            main.set_class(compact, "compact")
        split = self.split_fits(width, height)
        split_changed = main.has_class("split") != split
        if split_changed:
            main.set_class(split, "split")
            self.place_transport(main, split)
        self.layout_classes(main)
        if split_changed:
            self.app.cover.replace_pixel()
        self.app.cover.fit(compact_changed or split_changed)
        self.apply_emblem()
        # These are all cropped or ruled to their own widget's width, which
        # only exists after layout. `check_size` also runs from the resize
        # that precedes compose, hence the guard.
        if self.app.query("#transport-menu"):
            self.refresh_widths()
            if split_changed:
                # The panel kept its size, so no resize is coming to report
                # the halves' new widths: wait for the layout pass instead.
                self.app.call_after_refresh(self.refresh_widths)
        too_small = width < self.app.MIN_WIDTH or height < self.app.MIN_HEIGHT
        notice = self.app.query_one("#too-small", Static)
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
                        min_width=self.app.MIN_WIDTH,
                        min_height=self.app.MIN_HEIGHT,
                    ),
                    style=f"bold {self.app.tidalamp_palette['accent']}",
                )
            )

    def split_fits(self, width: int, height: int) -> bool:
        """Whether the queue goes beside the player: asked for, and room for it.

        Falling back on its own is the point. Asked for on an ordinary
        terminal, two columns would be two broken halves, and nothing on
        screen would say why.
        """
        return (
            config.ARRANGEMENT == "split"
            and width >= self.app.SPLIT_MIN_WIDTH
            and height >= self.app.SPLIT_MIN_HEIGHT
        )

    def place_transport(self, main, split: bool) -> None:
        """Under both columns in split, between the halves when stacked.

        The grid places its cells in the order of the children, so the row
        that spans the two columns has to come after the second one.
        """
        if not self.app.query("#transport"):
            return
        transport = self.app.query_one("#transport")
        queue = self.app.query_one("#queue-half")
        if split:
            main.move_child(transport, after=queue)
        else:
            main.move_child(transport, before=queue)

    @property
    def split(self) -> bool:
        """Whether the halves are side by side right now."""
        return self.app.query_one("#main").has_class("split")

    def refresh_widths(self) -> None:
        """Redraw everything that is cropped or ruled to its widget's width.

        A resize is one moment those widths change and switching the
        arrangement is the other. Both are rare; the ticks are the hot path.
        """
        self.app.spectrum.apply_shape()
        self.app.transport.refresh(relayout=True)
        self.app.queue_view.refresh_title()
        titlebar = self.app.query_one("#titlebar", Static)
        titlebar.update(self.title_text(titlebar.size.width))

    def ask_for_synchronized_output(self, platform: str = sys.platform) -> None:
        """Ask the terminal whether it can take a frame all at once.

        Textual asks on Linux and never on Windows, so there every frame went
        out piece by piece. Windows Terminal erases a sixel under any text
        written over it, and a repaint of the cover box is blank lines first
        and the image after (`artwork.sixel_from_below`): shown mid-frame, the
        cover blinked at every key. The answer comes back through Textual's
        own parser, which turns synchronized output on when it is yes; a
        terminal that does not know the question says no or nothing.
        """
        if platform != "win32" or self.app._driver is None or self.app.is_headless:
            return
        self.app._driver.write("\033[?2026$p")
        self.app._driver.flush()

    def paint_terminal_margin(
        self, platform: str = sys.platform, environ: Mapping[str, str] = os.environ
    ) -> None:
        """Give Windows Terminal the player's ground as its own background.

        Windows Terminal keeps a margin no program can draw in: its padding,
        the gutter of the scrollbar, which it reserves even on the alternate
        screen, and the part of a cell the window's width leaves over. It
        paints that margin in the profile's background, so the player stood
        in a dark frame with a band on the right as wide as three columns.
        OSC 11 changes that background; `#main` is on the panel colour in
        every look, so that is the one it gets. Only in Windows Terminal
        (``WT_SESSION``): it resets the colour on the way out, and the conhost
        of Windows 10 is not known to, which would leave the prompt purple.
        """
        if (
            platform != "win32"
            or "WT_SESSION" not in environ
            or self.app._driver is None
            or self.app.is_headless
        ):
            return
        ground = Color.parse(self.app.tidalamp_palette["panel"])
        code = f"\033]11;rgb:{ground.r:02x}/{ground.g:02x}/{ground.b:02x}\033\\"
        if code == self.terminal_margin:
            return
        self.terminal_margin = code
        self.app._driver.write(code)
        self.app._driver.flush()

    @staticmethod
    def layout_classes(main) -> None:
        """Put exactly one layout class on the panel, for the stylesheet.

        Set rather than toggled blindly: `set_class` on an unchanged class
        still invalidates the styles, and this runs on every resize.
        """
        for name in LAYOUTS:
            wanted = name == config.THEME
            if main.has_class(name) != wanted:
                main.set_class(wanted, name)

    @property
    def layout(self) -> Layout:
        """The layout in force, read fresh: the settings screen swaps it live."""
        return layout_for(config.THEME)

    def title_text(self, width: int = 0) -> str | Text:
        return self.tinted(self.layout.title(width))

    def tinted(self, line: str, roles: tuple[str, ...] = ()) -> str | Text:
        """The line with the look's tinted glyphs in their colours, in turn;
        the rest keeps whatever colour its widget gives it."""
        layout = self.layout
        roles = roles or layout.tint_colors
        if not layout.tint or not roles:
            return line
        colours = [self.app.tidalamp_palette[role] for role in roles]
        text = Text(line)
        found = 0
        for index, glyph in enumerate(line):
            if glyph in layout.tint:
                text.stylize(colours[found % len(colours)], index, index + 1)
                found += 1
        return text

    def apply_emblem(self) -> None:
        """Put the look's emblem behind the queue, and its line where the
        words are not.

        Behind the queue rather than in the cover's box, so it is there the
        whole time and not only while nothing plays; it has the room there
        to carry some detail.
        """
        if not self.app.query("#playlist"):
            return
        layout = self.layout
        # The flourish in the frame's foot. Set only when it changes: this
        # runs on every resize, and each assignment repaints the frame.
        flourish = (layout.name, id(self.app.tidalamp_palette))
        if self.flourish != flourish:
            self.flourish = flourish
            self.app.query_one("#main").border_subtitle = self.tinted(
                layout.frame_subtitle, layout.flourish_colors
            )
        tagline = layout.tagline() if layout.tagline else ""
        # The picture is its own setting: the theme's by default, any other
        # look's when the user mixes them, and it keeps the place and size
        # that look gives it.
        source = backdrop_for(config.BACKDROP, layout)
        playlist = self.app.query_one("#playlist", RowList)
        if source is None:
            playlist.set_backdrop(None)
        else:
            playlist.set_backdrop(
                artwork.emblem_path(source.emblem),
                source.emblem_anchor,
                source.emblem_scale,
            )
        pane = self.app.query_one(LyricsPane)
        if pane.tagline != tagline:
            pane.tagline = tagline
            pane.refresh()
        marquee = self.app.query_one(Marquee)
        idle = tagline or "TIDAL AMP"
        if marquee.idle_text != idle:
            marquee.idle_text = idle
            marquee.refresh()

    def apply_appearance(self) -> None:
        """Apply structure and palette without restarting playback."""
        self.layout_classes(self.app.query_one("#main"))
        self.apply_emblem()
        # After the refresh: the band's ground is only the new look's once
        # Textual has restyled it.
        self.app.call_after_refresh(self.app.cover.reshape)
        # Each layout pads the display band differently, so the height worked
        # out under the last one is wrong under this one.
        if not self.compact:
            self.app.cover.fit_band()
        titlebar = self.app.query_one("#titlebar", Static)
        titlebar.update(self.title_text(titlebar.size.width))
        self.app.transport.refresh(relayout=True)
        self.app.queue_view.refresh_title()
        self.app.screen.refresh()

    @quiet_after_teardown
    def refresh_theme(self) -> None:
        """Follow an Omarchy theme switch without disturbing other state."""
        palette = theme.load_palette(name=config.PALETTE)
        if palette.colors == self.app.tidalamp_palette.colors:
            return
        self.app.tidalamp_palette = palette
        self.app.refresh_css(animate=False)
        self.paint_terminal_margin()
        self.app.transport.refresh()
        self.app.screen.refresh()
