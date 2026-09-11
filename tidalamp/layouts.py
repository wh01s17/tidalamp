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
    # What `_transport_keycaps` draws either side of each key's face.
    keycaps: tuple[str, str] = ("[", "]")
    # The themed looks' emblem: a small PNG in `tidalamp/emblems`, drawn behind
    # the queue the way a cover is drawn in its box (`artwork.emblem_cells`).
    # Traced from the maintainer's reference pictures (the neon city is drawn
    # by hand), reduced to 192 px and 48 colours; the references are not kept.
    emblem: str = ""
    # Where it sits and how large: `middle` of the right edge, or `bottom`,
    # tucked into the lower right corner; `emblem_scale` stretches the share
    # of the queue it may take (most look right at 1).
    emblem_anchor: str = "middle"
    emblem_scale: float = 1.0
    # And the line that goes with it: under the large emblem, and in the
    # title's place while nothing is playing.
    tagline: Callable[[], str] | None = None


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
            transport="keycaps",
            ascii_only=True,
        ),
        # The themed looks. Each is paired with a built-in palette of the same
        # name (`theme.PAIRED`), and the names evoke rather than name: a colour
        # scheme belongs to nobody, a registered title does.
        #
        # A purple giant with a lime trim and orange warning stripes.
        Layout(
            "unidad-morada",
            title=lambda width: ruled("UNIDAD-01  //  TIDAL AMP", width, "▚"),
            queue_heading=lambda width, hints: spread(
                f"▰▰ {_('COLA')} ▰▰", hints, width, " "
            ),
            transport="keycaps",
            keycaps=("⟦", "⟧"),
            emblem="unidad-morada.png",
            tagline=lambda: _("sincronía al 400 %"),
        ),
        # Straw-yellow on open sea, a flag at the masthead.
        Layout(
            "pirata",
            title=lambda width: ruled("☠  TIDAL AMP  ☠", width, "~"),
            queue_heading=lambda width, hints: spread(
                f"⎈ {_('BITÁCORA')} ", hints, width, "~"
            ),
            transport="keycaps",
            keycaps=("(", ")"),
            emblem="pirata.png",
            emblem_anchor="bottom",
            emblem_scale=1.0,
            tagline=lambda: _("rumbo a la gran ruta"),
        ),
        # A black notebook, ruled lines, one red that matters.
        Layout(
            "cuaderno",
            title=lambda width: "✎ tidal amp",
            queue_heading=lambda width, hints: spread(
                f"✎ {_('páginas')} ", hints, width, "_"
            ),
            transport="nova",
            emblem="cuaderno.png",
            tagline=lambda: _("trae manzanas"),
        ),
        # Night city: yellow and cyan neon, hard edges.
        Layout(
            "neon-noir",
            title=lambda width: ruled("▌NEON//NOIR▐  tidalamp", width, "━"),
            queue_heading=lambda width, hints: spread(
                f"▌{_('COLA')}▐ ", hints, width, "━"
            ),
            transport="keycaps",
            keycaps=("▐", "▌"),
            emblem="neon-noir.png",
            emblem_anchor="bottom",
            tagline=lambda: _("despierta: la ciudad no duerme"),
        ),
        # Old gold on a dark forest, a chronicle rather than a list.
        Layout(
            "runas",
            title=lambda width: ruled("◆  T I D A L   A M P  ◆", width, "·"),
            queue_heading=lambda width, hints: ruled(_("CRÓNICA"), width, "·"),
            transport="retro",
            emblem="runas.png",
            tagline=lambda: _("un anillo para oírlas a todas"),
        ),
        # Red, gold and green on black.
        Layout(
            "reggae",
            title=lambda width: ruled("♫  tidal amp  ♫", width, "≈"),
            queue_heading=lambda width, hints: spread(
                f"♫ {_('cola')} ", hints, width, "≈"
            ),
            transport="quattro",
            emblem="reggae.png",
            tagline=lambda: _("un solo amor, un solo corazón"),
        ),
        # The wild card: a purple suit, green hair, the four suits.
        Layout(
            "comodin",
            title=lambda width: ruled("♠ ♥  TIDAL AMP  ♦ ♣", width, "─"),
            queue_heading=lambda width, hints: spread(
                f"♠ {_('baraja')} ", hints, width, "─"
            ),
            transport="keycaps",
            keycaps=("{", "}"),
            emblem="comodin.png",
            emblem_anchor="bottom",
            emblem_scale=1.15,
            tagline=lambda: _("¿por qué tan serio?"),
        ),
        # Crimson and violet under a pointed arch.
        Layout(
            "gotico",
            title=lambda width: ruled("✠  TIDAL AMP  ✠", width, "━"),
            queue_heading=lambda width, hints: ruled(
                _("LISTA DE REPRODUCCIÓN"), width, "━"
            ),
            transport="retro",
            emblem="gotico.png",
            tagline=lambda: _("nunca más, dijo el cuervo"),
        ),
        # Bone on black, blood red, and noise at the edges.
        Layout(
            "death-metal",
            title=lambda width: ruled("▓▒░  T I D A L   A M P  ░▒▓", width, "░"),
            queue_heading=lambda width, hints: spread(
                f"░▒▓ {_('COLA')} ▓▒░", hints, width, " "
            ),
            transport="keycaps",
            keycaps=("╣", "╠"),
            emblem="death-metal.png",
            tagline=lambda: _("hasta el once"),
        ),
    )
}

DEFAULT_LAYOUT = LAYOUT_TABLE["quattro"]

# What the `backdrop` setting takes: the theme's own picture, none, or any
# themed look's, by the look's name.
BACKDROPS = (
    "auto",
    "none",
    *(name for name, layout in LAYOUT_TABLE.items() if layout.emblem),
)


def backdrop_for(setting: str, layout: Layout) -> Layout | None:
    """The look whose picture goes behind the queue, or None for none."""
    if setting == "none":
        return None
    if setting == "auto":
        return layout if layout.emblem else None
    chosen = LAYOUT_TABLE.get(setting)
    return chosen if chosen is not None and chosen.emblem else None


def layout_for(name: str) -> Layout:
    """The layout called `name`, or the default for a name nobody knows."""
    return LAYOUT_TABLE.get(name, DEFAULT_LAYOUT)
