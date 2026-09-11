"""What tells one layout from another, written as data.

A layout is the structure half of a look; the palette in `theme.py` is the
colour half. Everything the app used to ask with `if config.THEME == ...` is a
field here instead, so a new layout is one entry in `LAYOUT_TABLE` plus its
block of TCSS, and nothing in `app.py` has to learn its name.

The transport is the one part that stays code: each look draws its buttons
differently enough that a table of glyphs would be a program in disguise.
`transport` names the builder, `_transport_<name>` on the app.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rich.cells import cell_len

from .i18n import _


def ruled(title: str, width: int, rule: str) -> str:
    """A centred title on a rule that fills the row, Winamp's title bars.

    The original draws its heading over a band of thin horizontal lines,
    which is what tells its two windows apart from everything else on the
    desktop. One row of `═` is as close as a terminal gets.
    """
    label = f" {title} "
    if width <= cell_len(label):
        return label.strip()[:width]
    slack = width - cell_len(label)
    left = slack // 2
    return rule * left + label + rule * (slack - left)


def spread(heading: str, hints: str, width: int, fill: str) -> str:
    """Heading left, hints hard against the right edge, `fill` between."""
    room = width - cell_len(heading) - cell_len(hints) - 2
    return f"{heading}{fill * max(1, room)}  {hints}"


@dataclass(frozen=True)
class Layout:
    name: str
    # The title bar at a given width. Width, because the ruled ones fill it.
    title: Callable[[int], str]
    # The queue's heading at a given width, with the key hints the app picked
    # for its size. A layout is free to leave the hints out.
    queue_heading: Callable[[int, str], str]
    # Which `_transport_<name>` builder draws the buttons.
    transport: str
    # The glyph budget: a layout for terminals without box drawing keeps its
    # own chrome to ASCII, and the transport swaps every glyph for a stand-in.
    ascii_only: bool = False


# Each heading is a function rather than a string so the words go through
# `_()` when they are drawn, not when this module is imported: the language
# can change under a running app. And each `_()` keeps a literal argument,
# which the catalogue test needs to find it.
LAYOUT_TABLE: dict[str, Layout] = {
    layout.name: layout
    for layout in (
        # A flat, modern TUI treatment; the default.
        Layout(
            "quattro",
            title=lambda width: "TIDAL AMP  //  PLAYER",
            queue_heading=lambda width, hints: spread("▓ PLAYLIST ▓", hints, width, " "),
            transport="quattro",
        ),
        # The 1997 skin, as far as a terminal can go: square keys, ruled
        # title bars and a centred playlist window heading. The original's
        # playlist is its own window with its own title bar, and the keys are
        # not written on it: they are one `?` away, and the transport menu
        # still leads with «? ayuda» in every look.
        Layout(
            "retro",
            title=lambda width: ruled("T I D A L   A M P", width, "═"),
            queue_heading=lambda width, hints: ruled(
                _("LISTA DE REPRODUCCIÓN"), width, "═"
            ),
            transport="retro",
        ),
        # No frames at all, one flat ground, state carried by colour.
        Layout(
            "nova",
            title=lambda width: "▍ tidalamp",
            queue_heading=lambda width, hints: spread(
                f"▍ {_('cola')} ", hints, width, "─"
            ),
            transport="nova",
        ),
        # A terminal before it had box drawing: `[ z << ]` keys, rules made of
        # `=` and `-`, and no glyph the chrome cannot type.
        Layout(
            "ascii",
            title=lambda width: ruled("[ TIDAL AMP ]", width, "="),
            queue_heading=lambda width, hints: spread(
                f"--[ {_('COLA')} ]", hints, width, "-"
            ),
            transport="ascii",
            ascii_only=True,
        ),
    )
}

DEFAULT_LAYOUT = LAYOUT_TABLE["quattro"]


def layout_for(name: str) -> Layout:
    """The layout called `name`, or the default for a name nobody knows."""
    return LAYOUT_TABLE.get(name, DEFAULT_LAYOUT)
