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
    # The themed looks' 8-bit emblem, one string per pixel row, drawn behind
    # the queue (`widgets.backdrop_runs`). Each letter is a palette role
    # rather than a colour (see `widgets.EMBLEM_ROLES`), so the drawing
    # follows whatever palette the user moves to; `.` is see-through. Up to
    # 48 pixels a side, scaled to the queue it sits behind.
    #
    # The ones with a reference picture were read from it: pixel art at its
    # own grid, the rest reduced by area, then each colour given a role by
    # hand. The four without one are drawn with primitives.
    emblem: tuple[str, ...] = ()
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
            emblem=(
                "MC...............................",
                ".CC..............................",
                ".MC..............................",
                "..CM.............................",
                "..CC.............................",
                "...CM............................",
                "...CC............................",
                "....CC...........................",
                "....CC...........................",
                ".....CC..........................",
                ".....CC..........................",
                "......CC........MCCCCCM..MCM.....",
                "......CCC.....MMMCCCCMMMCCCCCCCM.",
                ".......CBR.CCCCMMMCCMMMMMCCCCCM..",
                ".......GGCCCCCCCCCCCCBMMMCCCCM...",
                "........CCCCCCCCCCCMBCMCCCMMMMMM.",
                "........CCCCCMMMMCCCCCCCCCMMMMMMM",
                "........CCCMMBMMMCCCCCCCCCMMMMMMC",
                "........MMMMMMCCCMMMCCCCCMMMCCCCC",
                "........MCCCCCCCMMCCCCCCMMRMMCCC.",
                "........CCCCCCCMMCCCCCMMMMRRMMMM.",
                ".........CBMBMBMCCCMMMCMRRRYRMMM.",
                "..........C.C.MRCCRMMCBMRYRRYYRR.",
                "...............RRGMCMMMMRYRMYYYYY",
                "..............M.BCCMMMMRYYYRYYYYY",
                "...........B..BMCCCMBMRYYYYYRYRRR",
                "...........BCMBCMBCCMRYYYYYRMYYR.",
                "..........CCCBBBMBM..RRYYYYRRYYR.",
                "..........BBBBBBMM.....RRYYRRYYR.",
                "..........BBBBCM.......RYYYYRYYR.",
                "..........BBBB..........RYYYRYY..",
                ".........GGBBC...........YYYRYY..",
                ".........GGCBC...........RYYRYR..",
                ".........GGBB............RYYRYR..",
                ".........GGBC.............YYRRR..",
                ".........GG..............RRRMY...",
                "............................RY...",
                ".............................R...",
            ),
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
            emblem=(
                "..BB..................BB...",
                ".BBBB......YYYY......BBBB..",
                "BBBB.....YYYYYYYYY....BBBB.",
                "BBBBB...Y.YYYYYYY.Y...BBBBB",
                "BB.BBB.Y...YYYYYY.Y..BBBBB.",
                "....BB...............B.....",
                "......RRRRRRRRRRRRRR.......",
                "......RRRRRRRRRRRRRR.......",
                "...........................",
                ".......B...B.....B.........",
                "......BBB...BBB...BB.......",
                "......BB....BB....BB.......",
                ".......B....BB....B........",
                "........B..BBBB..BB........",
                ".........BBBB.BBBB.........",
                ".........BBBBBBBB..........",
                ".........BBBBBBBB..........",
                ".......BBB.BBBB.BBBB.......",
                "......BB.BBBBBBBB.BB.......",
                ".BBBBBB.BB.BBBB.BB.BBBBB...",
                ".BBBBB..BBBBBBBBBB.BBBBB...",
                "..BBBB..BBBBBBBBB..BBBBB...",
                "...BBBB..BBBBBBBB..BBB.....",
                "...BBB....BBBBB.....BB.....",
            ),
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
            emblem=(
                ".............C...............",
                "............CCC..............",
                "...M.MM...CCCCCC......M..M...",
                "....M.MMM.CCCCCCC....MM.M.M..",
                "..M.MMMMMMBBBCCC...MMMMMM....",
                "CMCCMCCMMMRBRCBCCCMMMMCMMCMMC",
                "MCCCCCMMMMBBBBBMMMMMMMMCCCCCM",
                ".....MM..MBBBCBMMMMMM.M......",
                "....M...MMCBBBBMMMM.M...M....",
                ".........MMBBBMMMMM..........",
                "........MCMMBCMMMM...........",
                ".........CCCCCC.C............",
                ".........CCCCCC.C............",
                ".........CC.CCC.C............",
                ".........CCMBBMMCC...........",
                ".........BBMCMMCB............",
                ".........CC.CMCCCC...........",
                "........C.CCCC..RC...........",
                "..........CCC...RCC..........",
                "...........CC....CC..........",
                "............CC...CC..........",
                ".............C...C...........",
                ".................C...........",
            ),
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
            emblem=(
                "...............M............................",
                "...............M.................RRRR.......",
                "...............M................RRRRRR......",
                "...............M...............RRRRRRRR.....",
                ".............MMMM.............RRRRRRRRRR....",
                ".............MMMM.............RRRRRRRRRR....",
                ".............MYMM.............RRRRRRRRRR....",
                ".............MMMM........MMMMMRRRRRRRRRR....",
                ".............MMMM........MMMMM.RRRRRRRR.....",
                ".......MMMMM.MYMM........MRRRM..RRRRRR......",
                ".......MMMMM.MMMM........MRRRM...RRRRMMMMMMM",
                ".......MMMMM.MMMM........MMMMM.......MMMMMMM",
                ".......MMMMM.MMMM.MMMMMM.MMMMM.......MMMYMCM",
                ".......MMMMM.MMMM.MMMMMM.MMMMM.......MMMMMMM",
                "MMMMMM.MMMMM.MMMM.MCCCMM.MMMMM.......MMMMMMM",
                "MMMMMM.MMMMM.MMMM.MMCCMM.MMMYM.MMMMM.MYMYMMM",
                "MYMMMM.MMMMM.MMMM.MMCCMM.MMMMM.MMMMM.MMMMMMM",
                "MMMMMM.MMMCM.MMMM.MMCCMM.MMMMM.MYMMM.MMMMMMM",
                "MMMMMM.MMMMM.MMMM.MMCCMM.MYMYM.MMMMM.MYMMMMM",
                "MMMMMM.MMMMM.MMMM.MMCCMM.MMMMM.MMMMM.MMMMMMM",
                "MMMMMM.MYMCM.MMMM.MMCCMM.MMMMM.MMMMM.MMMMMMM",
                "MMMMMM.MMMMM.MYMM.MMCCMM.MYMMM.MMMMM.MMMMMMM",
                "MMMMMM.MMMMM.MMMM.MMCCMM.MMMMM.MMMMM.MMMMMMM",
                "MMMMMM.MMMMM.MMMM.MMMMMM.MMMMM.MMMMM.MMMMMMM",
                "MMMMMM.MMMMM.MMMM.MMMMMM.MMMMM.MMMMM.MMMMMMM",
                "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                "............................................",
                "C..C..C..C..C..C..C..C..C..C..C..C..C..C..C.",
                ".Y..Y..Y..Y..Y..Y..Y..Y..Y..Y..Y..Y..Y..Y..Y",
            ),
            tagline=lambda: _("despierta: la ciudad no duerme"),
        ),
        # Old gold on a dark forest, a chronicle rather than a list.
        Layout(
            "runas",
            title=lambda width: ruled("◆  T I D A L   A M P  ◆", width, "·"),
            queue_heading=lambda width, hints: ruled(_("CRÓNICA"), width, "·"),
            transport="retro",
            emblem=(
                ".......................R.................",
                "......................RRR................",
                ".................RRR..RAARR..............",
                "...............RRAAARRRAAAAR.............",
                "..............RAAAYAAAAAAAAARRR..........",
                "............RAAAAAAAYRAAAAAAAAA..........",
                "..........RRAAAAAAAAAAAAAAAAAYAR.........",
                "..R......RRRAAAAARRAARRAAAAAAAAAAA.......",
                ".RA.....RRRRRAAAAA.R.A.RAAAAAAAAAR.......",
                "RAA.RAAARRARRAAAARR..A.RAAARAAAARR.......",
                "RA.RAAAARRARRAR...A..R..RARARRRAAAR......",
                "A..AAAAAAARAAARR..R.....RAAR..RAAAR......",
                "....AAAAAAAAAA.......R..RRRRRARAAAAARRAR.",
                "....AAAAAAARRAR...R..R...RRAAAAAYA.YAA.A.",
                "AA..ARRRRRRRRR.R..R..R..RRAAAAYAA.YYAAAAR",
                "RAA.AAAARRAAAR.RR....RRAAAAAARAAAAAARYAR.",
                "RRA..AAYAAAAAAAARRR..RRAAAARAARAAAAARAAR.",
                ".RAA.AAAAYYAAAAAAARARRAAAARRAAAAAAARRR...",
                ".RRA.AAAAAYYAAAAAAAAAAAYAAAAAAAYAAR.RR...",
                ".RRA..RAYYYYYAAAAAARAAAAAAARRRAAAR..R....",
                ".RRA..RRAAAAAAAAAAAAAAAAAAARAR.R.........",
                ".RRAA..RRRRAAAAAAAARAAYAAAAR.......R.....",
                ".RRAA......AAAAAAAARAAYYARAR.......R.....",
                ".RRAAA.R....RAAAARRRAAAAAR........RR.....",
                ".RRAAA.......RR.....RRRAAR........AR.....",
                ".RRAAAA................AAR........RR.....",
                ".RRRAAA................RAR.......RR......",
                ".RRRAAAA........................RRR......",
                ".RRRAAAAA.......................ARR......",
                ".RRRRAAAAA.....................RRR.......",
                "....RAAAAAA...................RARR.......",
                "....RARAAAA...................ARRR.......",
                "....RARAAAAA..................ARRR.......",
                "...RRRRAAAAA.................ARRRR.......",
                "..R.RRRAAAAAA...............AARR.........",
            ),
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
            emblem=(
                "..............MMMMMMMM..............",
                "...........MMMMMMMMMMMMMM...........",
                ".........MMMMMMMMMMMMMMMMMM.........",
                "........MMMMMMKKKKKKKKMMMMMM........",
                "......MMMMMMKKMMMMMMMMKKMMMMMM......",
                ".....MMMMMKKMMMMMMMMMMMMKKMMMMM.....",
                "....MMBMMKMMMMMKKKKKKMMMMMKMMMMM....",
                "....MBMMKMMMKKKMMMMMMKKKMMMKMMMM....",
                "...MMMMKMMMKMMMMMMMMMMMMKMMMKMMMM...",
                "..MMMMKMMMKMMMMKKKKKKMMMMKMMMKMMMM..",
                "..MMMKMMMKMMMKKYYYYYYKKMMMKMMMKMMM..",
                ".MMMMKMMKMMMKMYRRRRRRYMKMMMKMMKMMMM.",
                ".MMMKMMKMMMKYYRRRRRRRRYYKMMMKMMKMMM.",
                ".MMMKMMKMMKMYRRRRRRRRRRYMKMMKMMKMMM.",
                "MMMKMMMKMMKYRRRRRRRRRRRRYKMMKMMMKMMM",
                "MMMKMMKMMKYRRRRRRRRRRRRRRYKMMKMMKMMM",
                "MMMKMMKMMKYYYYYYYKKYYYYYYYKMMKMMKMMM",
                "MMMKMMKMMKYYYYYYKKKKYYYYYYKMMKMMKMMM",
                "MMMKMMKMMKYYYYYYKKKKYYYYYYKMMKMMKMMM",
                "MMMKMMKMMKYYYYYYYKKYYYYYYYKMMKMMKMMM",
                "MMMKMMKMMKYGGGGGGGGGGGGGGYKMMKMMKMMM",
                "MMMKMMMKMMKYGGGGGGGGGGGGYKMMKMMMKMMM",
                ".MMMKMMKMMKMYGGGGGGGGGGYMKMMKMMKMMM.",
                ".MMMKMMKMMMKYYGGGGGGGGYYKMMMKMMKMMM.",
                ".MMMMKMMKMMMKMYGGGGGGYMKMMMKMMKMMMM.",
                "..MMMKMMMKMMMKKYYYYYYKKMMMKMMMKMMM..",
                "..MMMMKMMMKMMMMKKKKKKMMMMKMMMKMMMM..",
                "...MMMMKMMMKMMMMMMMMMMMMKMMMKBMMM...",
                "....MMMMKMMMKKKMMMMMMKKKMMMKMMMM....",
                "....MMMMMKMMMMMKKKKKKMMMMMKMBMMM....",
                ".....MMMMMKKMMMMMMMMMMMMKKMMMMM.....",
                "......MMMMMMKKMMMMMMMMKKMMMMMM......",
                "........MMMMMMKKKKKKKKMMMMMM........",
                ".........MMMMMMMMMMMMMMMMMM.........",
                "...........MMMMMMMMMMMMMM...........",
                "..............MMMMMMMM..............",
            ),
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
            emblem=(
                "...G.G.MMM..B....BB..BBBBBBBBMMMMMMMM........G.G",
                ".GG.G.MBBBBB.BBBB.BBBBBBBBBBBBBBBBBB..........G.",
                "G...G.BMBBBBBBBBBB.BBBB....BBBBBBBBBMM........GG",
                ".G..G.M.BBMBBBBBBBB..BBBBBBBBBBBBBBBBBMMM......G",
                ".GG..M...MMBBBBBBBBB...BBBBBBBBBBBBBBB..BM....GG",
                ".G...M.....MBBBBBBBBBB...BBBBBBBBBBBBBBMMBM...GG",
                ".G...BM.....MBBBBBBBBBB....BBBBBBBBBBMBMMBBG...G",
                "G..G.MM.....MBBBBBBBBBBBBBB..BBBBBBBBBBMMBB....G",
                ".....MM......MBBBBB.BBBBBBBBBBBBBBBBBBBMMBBM...G",
                "G....M.......MBBBBBBBBBBBBBBB.BBBBBBBMBMMBBG...G",
                "....MM....M...MBBBBBBB..BBBBB.....BBBBB.MBBGG.GG",
                "G...BBM..MBMMM.MBBB.BB.BBBBB..MBBBBMBBMGMBB...GG",
                "MMG.MBBM..MB.M..MB.BBBBBBBBBBB..BBBBBB.MMBM...GG",
                "....BMMM....BMMM...BBBBBBBBBBBBBBM.BBBMMBBB...GG",
                "....MM......M.MM...BBBBBBBBBBBBBBBB.MMM.MB..G.GG",
                ".AA.MBBMM.........MBBBMMBBBBBBBBBBBBBBBM.MG...GG",
                ".AA.BBBB........M.MBBB..MMMMMBBBBBBBBBBBM.M...GG",
                "AAA.BBBBMMMM.....MMBBB...............BM.MM.GG.GG",
                "AAA.BBBBM......MMMBBBBM..MBM..........M.MB..G.GG",
                "AAA.BBBBBM..MM..MMBBBMM..MMBB.G.M....MBBBBB..G.G",
                "AAA.BBBBBBBBBBMMMBBBBBB....MBBBBBM....MBBBBB.GG.",
                "AAA.BBBBBBBBBBBMBBBBBB...............MMBBBBB..G.",
                "AAA.BBMBBBBBBBBBBBBBBM.M...........MM.MBBB.MB.GG",
                "AAA.BBBBBBBBMBBMBBBBBBM.M..........MBMMBBM.M..GG",
                "AAAA.MBBBBBM.MBMBBBBBBBBBBM....MM..MBBBBB..M..GG",
                "A.A..M.MMBMMBBBBBBBBBBBBBBM.M.MMBMMBBBBBB.....GG",
                "A.A.RMMM.B.MBBBBBBBBBMBBBBBMMM.MBBBBBBBBM..G....",
                "A.A..MMMBBMMBBBBBBBBB.BBBBBBBBBBBBBBBBBB.G..G...",
                "AAAA...BBBB.MBBBBBBBMB.BBBBBBBBBBBBBBMMM.G...G..",
                "AAAA..M.BBBM.BBBBBBBBB.MBBBBBBBBBBBBM.....GG....",
                "AAAAA...MBBMMMBBBBBMBBMBBBBBBBBBBBBMR.B.G.GGGG..",
                "AAAAA.RM.BBM.MMBBB.MMMBBBBBBBBBMBBM...M.......G.",
                "AAAAA....BBBM.MMMMMMMMBBBBBBBBBBMM.MBM..........",
                "AAAAAA..R....M..M..MMBBBBBBBBBB..RMBM......MAA..",
                "AAAAAA...RRR.BBBBBMMBBMMBBBM...R.MBM.A.....AAAA.",
                "AAAAAAA...RRR....MBM.M...BB.RRRMBBM..A.....AAAAA",
                "AAAAAAA...RRRRRRR..........RRRMBBM...A.....AAAAA",
                "AAAAAA.....RRRRRRRRRRRRRRRRRRMBMM..........AAAAA",
                "A.AAAA...MBM.RRRRRR.MMMMRRR.BM.....A.......AAAAA",
                "AAAAAA...MBBBM.RR.MMBBBBM.BBM...A.AA.......AAAAA",
                "AAAAAA....BBBBBMMMBBBMBBBBM...A.AAAA.......AAAAA",
                "AAAAA.......BBBBBBBBBBBB....A.AAAA.........AAAAA",
                "AAAAA........BBBBBBBBA......AAAAAAA........AAAAA",
                "AAAA...........BBBBBB.....AAAAAAA............AAA",
                "AAAA.......A...............AAAAAAA..........AA.A",
                "AAAA.......AAA.............AAAAAAA............AA",
            ),
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
            emblem=(
                "............B.........B...........",
                "............BB.......BB...........",
                ".........MMMMBBB.B.BBBMMM.........",
                ".........MMMMBBBBBBBBBMMM.........",
                ".........MMMMMBBBBBBBMMMM.........",
                ".........AAAAABMMMMMBAAAA.........",
                ".........AAAAAAAAAAAAAAAA.........",
                ".........AAAAAAAAAAAAAAAA.........",
                "........MAAAAAAAMAAAAAAAAM........",
                ".......MMAAAAAMMMMMMAAAAAMM.......",
                "......MMMAAAMMCCMCCCMMAAAMMM......",
                ".....MMMMMAMCCCCMCCCCCMMAMMMM.....",
                ".....MMMAAMCCCCCMCCCCCMMAAMMM.....",
                "....MMMMAMCMCCCCMCCCCMCCMAMMMM....",
                "...MMMMAMCCCMCCYYYYCMCCCCMAMMMM...",
                "...MMMAAMCCCCMYYYYYYCCCCCMAAMMM...",
                "..MMMMAMCCCCCYYYAAYYYCCCCCMAMMMM..",
                "..MMMAAMCCCCYYYAAAAYYYCCCCMAAMMM..",
                ".MMMMAMMMMMMYYAAAAAAYYMMMMMAAMMMM.",
                ".MMMAAAMCCCCYYAAAAAAYYCCCCMAAAMMM.",
                ".MMMAAAMCCCCYYYAAAAYYYCCCCMAAAMMM.",
                ".MMMAAAMCCCCCYYYAAYYYCCCCCMAAAMMM.",
                "MMMAAAAAMCCCMCYYYYYYMCCCCMAAAAAMMM",
                "MMMAAAAAMCCMCCCYYYYCCMCCCMAAAAAMMM",
                "MMMAAAAAAMMCCCCCMCCCCCMCMAAAAAAMMM",
                "MMMAAAAAAMMCCCCCMCCCCCCMAAAAAAAMMM",
                "MMMAAAAAAAAMCCCCMCCCCCMAAAAAAAAMMM",
                ".MMMAAAAAAAAMMCCMCCCMMAAAAAAAAMMM.",
                ".MMMAAAAAAAAAAMMMMMMAAAAAAAAAAMMM.",
                ".MMMAAAAAAAAAAAAAAAAAAAAAAAAAAMMM.",
                ".MMMAAAACCMCCAAAAAAAACCMCCAAAAMMM.",
                ".MMMAAAACCMCCAAAAAAAACCMCCAAAAMMM.",
                ".MMMAAAACCMCCAAAAAAAACCMCCAAAAMMM.",
                ".MMMAAAACCMCCAAAAAAAACCMCCAAAAMMM.",
                ".MMMAAAACCMCCAAAAAAAACCMCCAAAAMMM.",
                ".MMMAAAACCMCCAAAAAAAACCMCCAAAAMMM.",
                ".MMMAAAACCMCCAAAAAAAACCMCCAAAAMMM.",
                ".MMMAAAACCMCCAAAAAAAACCMCCAAAAMMM.",
                ".MMMAAAACCMCCAAAAAAAACCMCCAAAAMMM.",
                ".MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM.",
                ".MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM.",
            ),
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
            emblem=(
                "..........BBBBBBBBB.........",
                ".......BBBBBBBBBBBBBBB......",
                ".....BBBBBBBBBBBBBBBB.......",
                "....BBBBBB.........BB.......",
                "...BBBBB...................Y",
                "..BBBB......MMMMMMM.....YYYY",
                ".BBBB......MMMMMMMMM....YY..",
                ".BBB......MMMMMMMMMMM...YY..",
                "BBB......MMMMMMMMMMMMM..YY..",
                "BBB.....MMMMMKKKKKMMMMM.YY..",
                "BBB.....MMMMKKBBBKKMMMM.YY..",
                ".......MMMMKBBBBBBBKMMMMYY..",
                ".......MMMKKRRBBRRBKKMMMYY..",
                "......MMMMKBRRBBRRBBKMMMYY..",
                "......MMMMKBBBBBBBBBKMMMYY..",
                "......MMMMKBBBKKBBBBKMMMYY..",
                ".....MMMMMKKBBBBBBBKKMMMYY..",
                ".....MMMMMMKKBKBKBKKMMMMYY..",
                ".....MMMMMMMKKBBBKKMMMMMMY..",
                ".....MMMMMMMMKKKKKMMMMMMMY..",
                ".....MMMMMMMMMMMMMMMMMMMMY..",
                "....MMMMMMMMMMMMMMMMMMBBBB..",
                "....MMMMMMMMMMMMMMMMMMBBBB..",
                "....MMMMMMMMMMMMMMMMMMBBBB..",
                "....MMMMKMMMMKMMMMKMMMMMMY..",
                "....MMMMKMMMMKMMMMKMMMMMMY..",
                "...MMMMMKMMMMKMMMMKMMMMMMM..",
                "...MMMMMKMMMMKMMMMKMMMMMMM..",
                "...MMMMKMMMMKMMMMKMMMMMMMM..",
                "...MMMMKMMMMKMMMMKMMMMMMMM..",
                "...MMMMKMMMMKMMMMKMMMMMMMM..",
                "..MMMMMKMMMMKMMMMKMMMMMMMM..",
                "..MMMMMKMMMMKMMMMKMMMMMMMM..",
                "..MMMMMKMMMMKMMMMKMMMMMMMM..",
                "..MMMMKMMMMKMMMMKMMMMMMMMMM.",
                "..MMMMKMMMMKMMMMKMMMMMMMMMM.",
                ".MMMMMKMMMMKMMMMKMMMMMMMMMM.",
                ".MMMMMKMMMMKMMMMKMMMMMMMMMM.",
                ".MMMMMMMMMMMMMMMMMMMMMMMMMM.",
            ),
            tagline=lambda: _("hasta el once"),
        ),
    )
}

DEFAULT_LAYOUT = LAYOUT_TABLE["quattro"]


def layout_for(name: str) -> Layout:
    """The layout called `name`, or the default for a name nobody knows."""
    return LAYOUT_TABLE.get(name, DEFAULT_LAYOUT)
