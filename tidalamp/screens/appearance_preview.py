"""Choose a look beside a small, live preview of the player."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .. import artwork, config, theme
from ..i18n import _
from ..layouts import backdrop_for, label, layout_for

if TYPE_CHECKING:
    from ..app import TidalAmp


APPEARANCE_KEYS = ("theme", "palette", "backdrop", "arrangement")
MIN_PREVIEW_WIDTH = 110


@dataclass(frozen=True)
class Appearance:
    theme: str
    palette: str
    backdrop: str
    arrangement: str

    @classmethod
    def current(cls) -> Appearance:
        return cls(config.THEME, config.PALETTE, config.BACKDROP, config.ARRANGEMENT)

    def choosing(self, key: str, value: str) -> Appearance:
        if value == getattr(self, key):
            return self
        if key == "theme" and (paired := theme.paired_palette(value)) is not None:
            return replace(self, theme=value, palette=paired, backdrop=value)
        return replace(self, **{key: value})


def _crop(value: str, width: int) -> str:
    return set_cell_size(value, max(0, width))


def _rgb(value: tuple[int, int, int]) -> str:
    return f"rgb({value[0]},{value[1]},{value[2]})"


def _line(text: Text, value: str, width: int, foreground: str, ground: str) -> None:
    text.append(_crop(value, width) + "\n", style=f"{foreground} on {ground}")


def _transport(layout_name: str) -> str:
    layout = layout_for(layout_name)
    if layout.transport == "retro":
        return "┌───┐ ┌───┐ ┌───┐\n│ ◀ │ │ ▶ │ │ ■ │\n└───┘ └───┘ └───┘"
    if layout.transport == "keycaps":
        left, right = layout.keycaps
        return f"{left} z << {right}  {left} x > {right}  {left} c [] {right}"
    if layout.transport == "nova":
        return "◀◀    ▶    ■    ▶▶       ⇄ ◯   ⟳ –"
    return "  ◀◀     ▶     ■     ▶▶    │    ⇄ ◯   ⟳ –"


def render_player(state: Appearance, width: int, height: int, *, split: bool) -> Text:
    """A compact sample made from the same layout names, colours and emblem data."""
    width, height = max(12, width), max(5, height)
    colors = theme.load_palette(name=state.palette)
    layout = layout_for(state.theme)
    result = Text()
    title = layout.title(width)
    simple = state.theme in ("quattro", "nova")
    _line(
        result,
        title,
        width,
        colors["accent"] if simple else colors["title_foreground"],
        colors["panel"] if simple else colors["title_background"],
    )

    def player(
        w: int, rows: int, *, with_transport: bool = True
    ) -> list[tuple[str, str, str]]:
        ground = (
            colors["panel"] if state.theme == "nova" else colors["display_background"]
        )
        transport_lines = _transport(state.theme).splitlines()
        if rows <= 4 and with_transport:
            short = [
                ("  01:24 / 04:08", colors["accent"], ground),
                ("  " + _("Pista de ejemplo"), colors["body"], ground),
                (
                    transport_lines[len(transport_lines) // 2],
                    colors["transport_foreground"],
                    colors["transport_background"],
                ),
            ]
            if rows <= 2:
                short = short[1:]
            return (short + [("", colors["body"], ground)] * rows)[:rows]
        cover = (
            ("  +-----+", "  | (o) |", "  +-----+")
            if state.theme == "ascii"
            else ("  ┌─────┐", "  │  ◉  │", "  └─────┘")
        )
        lines = [
            ("", colors["body"], ground),
            (cover[0] + "  01:24 / 04:08", colors["accent"], ground),
            (cover[1] + "  " + _("Pista de ejemplo"), colors["body"], ground),
            (cover[2] + "  " + _("Artista"), colors["muted"], ground),
            ("  ━━━━━━━━━╸────────────", colors["accent"], colors["track_background"]),
        ]
        if with_transport:
            for transport_line in transport_lines:
                lines.append(
                    (
                        transport_line,
                        colors["transport_foreground"],
                        colors["transport_background"],
                    )
                )
        return (lines + [("", colors["body"], colors["panel"])] * rows)[:rows]

    def queue(w: int, rows: int) -> list[Text]:
        if rows <= 0:
            return []
        ground = (
            colors["panel"] if state.theme == "nova" else colors["display_background"]
        )
        source = backdrop_for(state.backdrop, layout)
        emblem = artwork.emblem_path(source.emblem) if source is not None else None
        rgb = cast("artwork.Pixel", tuple(int(ground[i : i + 2], 16) for i in (1, 3, 5)))
        cells = (
            artwork.emblem_cells(
                emblem,
                w,
                rows,
                rgb,
                anchor=source.emblem_anchor if source else "middle",
                scale=max(source.emblem_scale, 2.0 if rows < 6 else 1.0)
                if source
                else 1.0,
            )
            if emblem is not None
            else {}
        )
        lines: list[Text] = []
        headings = [
            layout.queue_heading(w, ""),
            "  01  " + _("Pista de ejemplo") + "  04:08",
            "  02  " + _("Otra pista") + "  03:32",
        ]
        for row in range(rows):
            foreground = colors["accent"] if row == 0 else colors["body"]
            characters = _crop(headings[row], w) if row < len(headings) else " " * w
            background = {
                col: (glyph, fg, bg, mean)
                for col, glyph, fg, bg, mean in cells.get(row, [])
            }
            line = Text()
            col = 0
            for char in characters:
                if col in background:
                    glyph, fg, bg, mean = background[col]
                    if char == " ":
                        line.append(glyph, style=f"{_rgb(fg)} on {_rgb(bg)}")
                    else:
                        line.append(char, style=f"{foreground} on {_rgb(mean)}")
                else:
                    line.append(char, style=f"{foreground} on {ground}")
                col += cell_len(char)
            lines.append(line)
        return lines

    body_rows = height - 1
    if split and width >= 50:
        left_width = (width - 1) // 2
        right_width = width - left_width - 1
        transport_lines = _transport(state.theme).splitlines()
        split_rows = max(0, body_rows - len(transport_lines))
        left = player(left_width, split_rows, with_transport=False)
        right = queue(right_width, split_rows)
        for row, (value, foreground, ground) in enumerate(left):
            result.append(_crop(value, left_width), style=f"{foreground} on {ground}")
            result.append("│", style=colors["border"])
            result.append(right[row])
            result.append("\n")
        for index, value in enumerate(transport_lines):
            transport_style = (
                f"{colors['transport_foreground']} on {colors['transport_background']}"
            )
            result.append(
                _crop(value, width),
                style=transport_style,
            )
            if index != len(transport_lines) - 1:
                result.append("\n")
    else:
        player_rows = min(max(3, body_rows // 2), 7)
        for value, foreground, ground in player(width, player_rows):
            _line(result, value, width, foreground, ground)
        queue_lines = queue(width, body_rows - player_rows)
        for index, line in enumerate(queue_lines):
            result.append(line)
            if index != len(queue_lines) - 1:
                result.append("\n")
    return result


class AppearancePreviewScreen(ModalScreen[str | None]):
    """Browse a setting without changing either the player or config file."""

    BINDINGS = [
        Binding("escape", "cancel", _("cancelar")),
        Binding("up", "up", "", show=False),
        Binding("down", "down", "", show=False),
        Binding("enter", "apply", _("aplicar"), show=False),
    ]

    def __init__(self, key: str, choices: tuple[str, ...]) -> None:
        super().__init__()
        if key not in APPEARANCE_KEYS:
            raise ValueError(key)
        self.key = key
        self.choices = choices
        self.original = Appearance.current()
        current = getattr(self.original, key)
        self.cursor = choices.index(current) if current in choices else 0
        self.draft = self.original.choosing(key, choices[self.cursor])

    def compose(self) -> ComposeResult:
        with Vertical(id="appearance-preview-box"):
            yield Static(_("PREVISUALIZAR APARIENCIA"), id="appearance-preview-title")
            with Horizontal(id="appearance-preview-body"):
                with Vertical(id="appearance-preview-choice-column"):
                    yield Static(_("Opciones"), id="appearance-preview-choice-title")
                    yield Static("", id="appearance-preview-options", markup=False)
                with Vertical(id="appearance-preview-stage"):
                    yield Static(_("REPRODUCTOR"), id="appearance-preview-stage-title")
                    yield Static("", id="appearance-preview-player", markup=False)
            yield Static("", id="appearance-preview-note", markup=False)
            with Horizontal(id="appearance-preview-actions"):
                yield Button(_("Aplicar"), id="appearance-preview-apply")
                yield Button(_("Cancelar"), id="appearance-preview-cancel")

    def on_mount(self) -> None:
        self._redraw()

    def on_resize(self, event: Resize) -> None:
        self.query_one("#appearance-preview-box").set_class(
            event.size.width < MIN_PREVIEW_WIDTH, "narrow"
        )
        # The class changes the child sizes on the next layout pass.
        self.app.call_after_refresh(self._redraw)

    def _redraw(self) -> None:
        if not self.is_mounted:
            return
        colors = theme.load_palette(name=self.draft.palette)
        options = self.query_one("#appearance-preview-options", Static)
        width = max(12, options.size.width - 2)
        height = max(1, options.size.height)
        start = max(0, min(self.cursor - height // 2, len(self.choices) - height))
        listing = Text()
        for index in range(start, min(len(self.choices), start + height)):
            selected = index == self.cursor
            current = self.choices[index] == getattr(self.original, self.key)
            marker = "●" if current else " "
            row = f" {'›' if selected else ' '} {marker} {label(self.choices[index])}"
            style = (
                f"bold {colors['active_foreground']} on {colors['accent']}"
                if selected
                else colors["body"]
            )
            listing.append(_crop(row, width) + "\n", style=style)
        options.update(listing)

        note_widget = self.query_one("#appearance-preview-note", Static)
        if self.app.size.width < MIN_PREVIEW_WIDTH:
            note_widget.update(
                _("Previsualización: mínimo {width} columnas").format(
                    width=MIN_PREVIEW_WIDTH
                )
            )
            return

        preview = self.query_one("#appearance-preview-player", Static)
        width = max(12, preview.size.width - 2)
        height = max(5, preview.size.height)
        app = cast("TidalAmp", self.app)
        fits = (
            app.size.width >= app.SPLIT_MIN_WIDTH
            and app.size.height >= app.SPLIT_MIN_HEIGHT
        )
        preview.update(
            render_player(
                self.draft,
                width,
                height,
                split=self.draft.arrangement == "split" and fits,
            )
        )
        note = (
            _("split: mínimo {width}×{height}; cola apilada").format(
                width=app.SPLIT_MIN_WIDTH, height=app.SPLIT_MIN_HEIGHT
            )
            if self.draft.arrangement == "split" and not fits
            else ""
        )
        note_widget.update(note or _("● actual  ·  › selección temporal"))

    def action_up(self) -> None:
        self.cursor = (self.cursor - 1) % len(self.choices)
        self.draft = self.original.choosing(self.key, self.choices[self.cursor])
        self._redraw()

    def action_down(self) -> None:
        self.cursor = (self.cursor + 1) % len(self.choices)
        self.draft = self.original.choosing(self.key, self.choices[self.cursor])
        self._redraw()

    def action_apply(self) -> None:
        self.dismiss(self.choices[self.cursor])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "appearance-preview-apply":
            self.action_apply()
        elif event.button.id == "appearance-preview-cancel":
            self.action_cancel()

    def on_click(self, event) -> None:
        options = self.query_one("#appearance-preview-options", Static)
        if event.widget is not options:
            return
        height = max(1, options.size.height)
        start = max(0, min(self.cursor - height // 2, len(self.choices) - height))
        at = start + event.y - options.styles.padding.top
        if 0 <= at < len(self.choices):
            self.cursor = at
            self.draft = self.original.choosing(self.key, self.choices[at])
            self._redraw()
