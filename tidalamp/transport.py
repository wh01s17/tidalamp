"""The transport: the row of buttons under the player and the menu beside it.

Drawn for the look in force, with shuffle, repeat and the speed lit by their
state. Each look has a builder that fills `Transport.hits` with the clickable
faces on the middle row and returns the three rows to draw. Adding a look
means adding one of these and one block of TCSS; nothing else in the app asks
which layout is on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.cells import cell_len
from rich.text import Text
from textual.widgets import Static

from . import about
from .i18n import _
from .keys import keys_for
from .queue import Repeat
from .screens.speed import speed_text

if TYPE_CHECKING:
    from .app import TidalAmp

# A middle dot in the muted colour, not a full box-drawing bar: the menu is a
# list of small things, and a solid rule between each one shouts louder than
# the labels it is separating.
SEPARATOR = " · "

# The transport is drawn as boxed buttons three rows tall. The play/pause
# glyph is the action it will do: "▶" while stopped or paused, "Ⅱ" while
# something is playing, which is what every transport in the world does.
# Every state remains legible without colour and keeps a fixed width.
# The sign and the mark it carries, kept apart so a view with room to spare
# can put air between them: run together they read as one glyph nobody can
# name, and the full-screen bar draws them «⟳ A».
REPEAT_SIGN = "⟳"
REPEAT_TAGS = {Repeat.NONE: "–", Repeat.QUEUE: "A", Repeat.TRACK: "1"}
REPEAT_GLYPHS = {mode: "⟳" + tag for mode, tag in REPEAT_TAGS.items()}

# The same three states behind a spelled-out label. One cell each, so the
# word keeps its width whichever mode is on, and in the heavy cut: the light
# «○ ●» were specks beside the letters they belong to.
REPEAT_MARKS = {Repeat.NONE: "◯", Repeat.QUEUE: "⬤", Repeat.TRACK: "1"}

# The same three again, for the layout that spends no Unicode at all.
REPEAT_MARKS_ASCII = {Repeat.NONE: "-", Repeat.QUEUE: "*", Repeat.TRACK: "1"}

# Between the transport proper and the two buttons that hold a state.
BUTTON_GAP = "   "

Hits = list[tuple[int, int, str]]


def separated(text: str, body: str, dim: str, room: int = 0) -> Text:
    """Render a `·`-joined run with the separators dimmed.

    `room` drops whole entries off the tail instead of cutting through one:
    half a word behind a separator reads as a rendering fault, while a
    shorter list reads as a shorter list. The first entry is cropped rather
    than dropped, so a very narrow terminal still shows something.
    """
    parts = text.split(SEPARATOR)
    if room:
        kept: list[str] = []
        used = 0
        for part in parts:
            width = cell_len(part) + (len(SEPARATOR) if kept else 0)
            if kept and used + width > room:
                break
            kept.append(part)
            used += width
        parts = kept or [parts[0]]
    out = Text()
    for index, part in enumerate(parts):
        if index:
            out.append(SEPARATOR, style=dim)
        out.append(part, style=body)
    if room and out.cell_len > room:
        out.truncate(room, overflow="crop")
    return out


def button_key(action: str) -> str:
    """The key on a button's face: the first one bound, as you type it.

    Read from `keys_for`, not from `DEFAULT_KEYS`, so a button rebound in
    `config.toml` shows the key that actually works — a button with the
    wrong letter on it is worse than one with no letter at all.
    """
    return about.pretty_keys(keys_for(action).split(",")[0])


class Transport:
    """Draws the transport for the app, and knows where its buttons are."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        # The (start, end, action) spans of the clickable faces on the middle
        # row, as the last drawing left them.
        self.hits: Hits = []

    def action_at(self, x: int) -> str | None:
        """The action of the button at column ``x`` of the middle row."""
        for start, end, action in self.hits:
            if start <= x < end:
                return action
        return None

    def buttons(
        self, words: bool = False, lower: bool = False, plain: bool = False
    ) -> list[list[tuple[str, str, bool]]]:
        """(action, label, lit) per button, in two groups.

        Two groups, because they are two kinds of thing: the transport does
        something and springs back, while shuffle and repeat stay pressed.

        `words` spells the two toggles out — SHUFFLE and REPEAT, the way the
        original does — instead of using the `⇄ ⟳` glyphs. It costs about a
        dozen columns, so a compact terminal keeps the glyphs whatever the
        layout asks for, and the glyphs still say the state on their own.

        `plain` swaps every glyph for its ASCII stand-in. Each one is padded
        to the width of the widest in its slot (`> ` against `||`), because a
        button that changes width shifts everything to its right when you
        press it.
        """
        app = self.app
        mpv, queue, compact = app.mpv, app.queue, app.looks.compact
        playing = not mpv.paused and not mpv.idle
        key = button_key
        separator = "" if compact else " "
        spelled = words and not compact

        def word(text: str) -> str:
            return text.lower() if lower else text.upper()

        if plain:
            prev, play, stop, nxt = "<<", "||" if playing else "> ", "[]", ">>"
            on, off = "*", "-"
            marks = REPEAT_MARKS_ASCII
        else:
            prev = "◀" if compact else "◀◀"
            # Both text glyphs occupy one cell, including in compact mode.
            play = about.PAUSE if playing else "▶"
            stop = "■"
            nxt = "▶" if compact else "▶▶"
            on, off = "⬤", "◯"
            marks = REPEAT_MARKS

        if spelled:
            # The trailing mark, not the colour, is what says the state: the
            # three repeat modes have to be told apart on a mono terminal, and
            # all four labels have to keep one width so the row never shifts.
            shuffle = f"{key('shuffle')} {word('shuffle')} {on if queue.shuffle else off}"
            repeat = f"{key('repeat')} {word('repeat')} {marks[queue.repeat]}"
        elif plain:
            shuffle = f"{key('shuffle')}{separator}SH{on if queue.shuffle else off}"
            repeat = f"{key('repeat')}{separator}RP{marks[queue.repeat]}"
        else:
            # `separator` is the air between the key and its glyph; the same
            # cell goes between the glyph and its mark, which used to be
            # stuck to it. The compact player pays for neither.
            sign = "⬤" if queue.shuffle else "◯"
            shuffle = f"{key('shuffle')}{separator}⇄{separator}{sign}"
            tag = REPEAT_TAGS[queue.repeat]
            repeat = f"{key('repeat')}{separator}{REPEAT_SIGN}{separator}{tag}"
        rate = speed_text(mpv.speed)
        rate = (rate.replace("×", "x") if plain else rate).ljust(5)
        modes: list[tuple[str, str, bool]] = [
            ("shuffle", shuffle, queue.shuffle),
            ("repeat", repeat, queue.repeat is not Repeat.NONE),
        ]
        # Lit off 1×, like a toggle left on, and padded to its widest,
        # `0.25×`, so choosing a speed never shifts the row. Not in the
        # compact player, which has no columns to spare; `b` still opens it.
        if not compact:
            modes.append(("speed", f"{key('speed')}{separator}{rate}", mpv.speed != 1.0))
        return [
            [
                ("prev", f"{key('prev')}{separator}{prev}", False),
                ("play", f"{key('play')}{separator}{play}", False),
                ("stop", f"{key('stop')}{separator}{stop}", False),
                ("next", f"{key('next')}{separator}{nxt}", False),
            ],
            modes,
        ]

    def _quattro(self, hits: Hits, body: str, dim: str, lit: str) -> list[Text]:
        """Flat: one divider between the two groups, no frames."""
        rows = [Text("", style=body) for _row in range(3)]
        row = rows[1]
        row.append("  ", style=body)
        for group_index, group in enumerate(self.buttons()):
            if group_index:
                row.append("  │  ", style=dim)
            for button_index, (action, label, enabled) in enumerate(group):
                if button_index:
                    row.append("  ", style=body)
                width = cell_len(label) + 2
                hits.append((row.cell_len, row.cell_len + width, action))
                row.append(f" {label} ", style=lit if enabled else body)
        return rows

    def _retro(self, hits: Hits, body: str, dim: str, lit: str) -> list[Text]:
        """The 1997 transport: one square button each, packed shoulder to
        shoulder, and the two toggles spelled SHUFFLE and REPEAT.

        The original's buttons are not one segmented frame; they are separate
        square keys in a row, which is what `┐┌` between two of them says.
        Square corners, not the rounded ones the flat layout uses.

        Half blocks were tried first, to fake the raised bevel of the real
        thing. In a terminal they are not an outline: `▀` fills its cell, so a
        row of them came out as a solid grey slab across the panel. A drawn
        line is the only edge a terminal actually has.
        """
        rows = [Text("  ", style=body) for _row in range(3)]
        edges = ("┌─┐", "│ │", "└─┘")
        for group_index, group in enumerate(self.buttons(words=True)):
            if group_index:
                for row in rows:
                    row.append(" " if self.app.looks.compact else BUTTON_GAP, style=body)
            for action, label, enabled in group:
                width = cell_len(label) + 2
                for row, edge in zip(rows, edges, strict=True):
                    face_row = edge[1] == " "
                    row.append(edge[0], style=body)
                    if face_row:
                        hits.append((row.cell_len, row.cell_len + width, action))
                    # Only the face lights up: an accent block on all three
                    # rows swallowed the frame and the button stopped reading
                    # as a button once it was switched on.
                    row.append(
                        f" {label} " if face_row else edge[1] * width,
                        style=lit if (face_row and enabled) else body,
                    )
                    row.append(edge[2], style=body)
        return rows

    def _keycaps(self, hits: Hits, body: str, dim: str, lit: str) -> list[Text]:
        """Capped keys on one line, the way a terminal did it before boxes.

        `[ z << ]` is a button because the caps say so, not because anything
        was drawn around it, which is how a BBS or a curses program of the era
        wrote one. The caps are the layout's: `ascii` keeps them to brackets
        and its glyphs to ASCII, and the themed looks bring their own.
        """
        layout = self.app.looks.layout
        compact = self.app.looks.compact
        opening, closing = layout.keycaps
        rows = [Text("", style=body) for _row in range(3)]
        row = rows[1]
        row.append("  ", style=body)
        # `[ z << ]` needs eight columns for a two-glyph button; at 60 the six
        # of them plus the menu do not fit, so the caps close up instead of
        # the row wrapping into the one below it.
        pad = "" if compact else " "
        gap = " " if compact else "  "
        buttons = self.buttons(words=True, plain=layout.ascii_only)
        for group_index, group in enumerate(buttons):
            if group_index:
                row.append(gap, style=dim)
            for action, label, enabled in group:
                row.append(gap, style=body)
                width = cell_len(f"{opening}{pad}{label}{pad}{closing}")
                hits.append((row.cell_len, row.cell_len + width, action))
                row.append(f"{opening}{pad}", style=dim)
                row.append(label, style=lit if enabled else body)
                row.append(f"{pad}{closing}", style=dim)
        return rows

    def _nova(self, hits: Hits, body: str, dim: str, lit: str) -> list[Text]:
        """Modern: no boxes at all. State is a colour and a rule underneath.

        Nothing is drawn around a button, so the row that a frame would have
        used carries the meaning instead: an underline in the accent under
        whichever toggle is on. Inverted blocks would have put the loudest
        thing on screen on the quietest control.
        """
        rows = [Text("", style=body) for _row in range(3)]
        labels, marks = rows[1], rows[2]
        labels.append("  ", style=body)
        marks.append("  ", style=body)
        accent = self.app.tidalamp_palette["accent"]
        for group_index, group in enumerate(self.buttons(words=True, lower=True)):
            if group_index:
                labels.append("     ", style=body)
                marks.append("     ", style=body)
            for button_index, (action, label, enabled) in enumerate(group):
                if button_index:
                    labels.append("   ", style=body)
                    marks.append("   ", style=body)
                width = cell_len(label)
                hits.append((labels.cell_len, labels.cell_len + width, action))
                labels.append(label, style=f"bold {accent}" if enabled else body)
                marks.append("─" * width if enabled else " " * width, style=accent)
        return rows

    def refresh(self, relayout: bool = False) -> None:
        """Draw the transport, with shuffle and repeat lit by their state.

        `relayout` re-measures the left half instead of reusing the width it
        already had. It is off for the ticks, which redraw this several times
        a second and must not ask for a layout pass each time; it is on when
        the layout changes underfoot, because the three looks are different
        widths and the buttons were being cropped to the old one.
        """
        app = self.app
        palette = app.tidalamp_palette
        ground = palette["transport_background"]
        body = f"{palette['transport_foreground']} on {ground}"
        dim = f"{palette['inactive']} on {ground}"
        lit = f"bold {palette['active_foreground']} on {palette['accent']}"

        hits: Hits = []
        builder = getattr(self, f"_{app.looks.layout.transport}")
        rows = builder(hits, body, dim, lit)
        for row in rows:
            row.highlight_words(["▶", about.PAUSE], style="bold")
            row.append("  ", style=body)
        app.query_one("#transport-play", Static).update(
            Text("\n", style=body).join(rows), layout=relayout
        )
        self.hits = hits

        menu = _(
            "? ayuda · / buscar · l lib · y letra · e eq · o config"
            " · f/F favorito · q salir"
        )
        widget = app.query_one("#transport-menu", Static)
        # Fitted here rather than left to wrap: a Rich Text wraps whatever the
        # stylesheet says, and the overflow climbed into the rows the buttons
        # are drawn on. `? ayuda` leads, so it is the tail that goes.
        room = max(0, widget.size.width - 2)
        line = separated(menu, body, dim, room)
        if room:
            line.append("  ", style=body)
        # The menu sits on the buttons' middle row, not above them.
        widget.update(
            Text("\n", style=body).join(
                [Text("", style=body), line, Text("", style=body)]
            ),
            layout=relayout,
        )
