"""The settings window."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static

from .. import artwork, audio, columns, config
from ..i18n import _
from ..layouts import BACKDROPS, label
from ..theme import LAYOUTS, available_palettes, paired_palette, palette_for
from ..widgets import Analyzer
from .choice import ChoiceScreen
from .column_picker import ColumnsScreen, _crop

if TYPE_CHECKING:  # The screens report back to the app; the app owns them.
    from ..app import TidalAmp


@dataclass(frozen=True)
class Option:
    """One line of the config screen.

    ``key`` is the config file's, when the row writes one; ``choices`` are the
    values ↵ cycles through. A row with neither is a system action, and
    ``action`` names which one.
    """

    label: str
    key: str = ""
    choices: tuple[str, ...] = ()
    action: str = ""
    note: str = ""
    # The heading this row lives under. Rows are drawn in this order and the
    # heading is printed once, when it changes.
    group: str = ""


class ConfigScreen(ModalScreen[None]):
    """Everything the config file holds, plus the audio stack under it.

    The settings were only reachable by editing `config.toml` or by exporting
    a variable before launching, which meant the two things a user changes
    most — quality and whether the DAC is being handed hi-res at all — were
    the two least visible. Every row here writes the file, so a change made
    once stays made.
    """

    BINDINGS = [
        Binding("escape,o", "close", _("cerrar")),
        Binding("up", "up", _("arriba"), show=False),
        Binding("down", "down", _("abajo"), show=False),
        Binding("enter,space", "activate", _("cambiar"), show=False),
        Binding("right", "advance", "", show=False),
        Binding("left", "back", "", show=False),
    ]

    cursor = reactive(0)

    # What the window spends on everything that is not the list of settings:
    # the box's border (2), its title bar, the hint at its foot, and the
    # list's own top and bottom padding (2). Kept next to the stylesheet that
    # sets them, because it is the stylesheet this has to agree with.
    CHROME = 6

    QUALITIES = ("LOW", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS")
    ARTWORKS = ("auto", "kitty", "sixel", "blocks", "off")
    # What is left of that list once a window has to be drawn over the cover.
    # `auto` is not on it because it is a promise the terminal keeps, and on a
    # kitty terminal it promises exactly the thing transparency cannot have.
    ARTWORKS_OVER_PLAYER = ("blocks", "off")
    LANGUAGES = ("auto", "es", "en")
    SWITCH = ("false", "true")
    ARRANGEMENTS = ("stacked", "split")
    COVER_SHAPES = ("square", "round")

    def __init__(self, on_change=None) -> None:
        super().__init__()
        # Called after a setting is written, so the app can apply what it can
        # apply without a restart.
        self._on_change = on_change
        self._sink = audio.Sink()
        self._allowed: tuple[int, ...] = ()
        self._hardware: tuple[int, ...] = ()
        self._rows: list[Option] = []
        # Set when a change here drags another setting with it. It stays up
        # until the screen closes, which is as long as it is true.
        self._notice = ""

    # ------------------------------------------------------------------ rows

    def _options(self) -> list[Option]:
        """Every row, in the order they are drawn, grouped by what they are
        about rather than by the order they happened to be written in.

        Ten settings in one column read as a list of unrelated switches: the
        quality of the stream sat next to the colour of the borders. Three
        headings cost three lines and turn it into three short lists.
        """
        audio = _("Audio")
        looks = _("Apariencia")
        general = _("General")
        return [
            Option(
                _("Calidad"),
                key="quality",
                choices=self.QUALITIES,
                note=_("se aplica a la siguiente pista"),
                group=audio,
            ),
            Option(_("Ritmos hi-res en PipeWire"), action="rates", group=audio),
            Option(_("Reiniciar PipeWire"), action="restart", group=audio),
            Option(
                _("Tema"),
                key="theme",
                choices=LAYOUTS,
                note=_("estructura visual; se aplica al instante"),
                group=looks,
            ),
            Option(
                _("Paleta"),
                key="palette",
                choices=available_palettes(),
                note=_("auto sigue Omarchy; las demás funcionan en cualquier Linux"),
                group=looks,
            ),
            Option(
                _("Fondo de la cola"),
                key="backdrop",
                choices=BACKDROPS,
                note=_(
                    "auto usa el del tema; se puede mezclar con cualquier tema y paleta"
                ),
                group=looks,
            ),
            Option(
                _("Disposición"),
                key="arrangement",
                choices=self.ARRANGEMENTS,
                note=_("split pone la cola a la derecha si el terminal es ancho"),
                group=looks,
            ),
            Option(
                _("Transparencia"),
                key="transparency",
                choices=self.SWITCH,
                note=_("deja ver el reproductor detrás de las ventanas"),
                group=looks,
            ),
            Option(
                _("Carátula"),
                key="artwork",
                choices=(
                    self.ARTWORKS_OVER_PLAYER if config.TRANSPARENCY else self.ARTWORKS
                ),
                note=(
                    _("con transparencia sólo caben las que dibuja el texto")
                    if config.TRANSPARENCY
                    else _("blocks se dibuja con texto y sobrevive a las ventanas")
                ),
                group=looks,
            ),
            Option(
                _("Forma de la carátula"),
                key="cover_shape",
                choices=self.COVER_SHAPES,
                note=_("cuadrada o redonda, con cualquier tema"),
                group=looks,
            ),
            Option(
                _("Visualizador"),
                key="visualizer",
                choices=Analyzer.MODES,
                note=_("forma del analizador; fine necesita una fuente con Braille"),
                group=looks,
            ),
            Option(
                _("Columnas de la cola"),
                action="columns",
                note=_("qué metadatos se ven en la lista"),
                group=looks,
            ),
            Option(
                _("Idioma"),
                key="language",
                choices=self.LANGUAGES,
                note=_("al reiniciar"),
                group=general,
            ),
            Option(
                _("Registro de depuración"),
                key="debug",
                choices=self.SWITCH,
                group=general,
            ),
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="config-box"):
            yield Static(_("▓ CONFIGURACIÓN ▓"), id="config-title")
            yield Static("", id="config-list", markup=False)
            yield Static(_(" ↑↓ elegir   ↵ cambiar   o/esc cerrar"), id="config-hint")

    def on_mount(self) -> None:
        self._rows = self._options()
        self._probe()

    @work(thread=True, exclusive=True, group="config")
    def _probe(self) -> None:
        """Ask the audio stack what it is doing. Off the UI loop: it shells out."""
        found = (audio.sink(), audio.allowed_rates())
        hardware = audio.hardware_rates(found[0].name)
        self.app.call_from_thread(self._probed, found[0], found[1], hardware)

    def _probed(self, found, allowed, hardware) -> None:
        self._sink, self._allowed, self._hardware = found, allowed, hardware
        self._render_list()

    def watch_cursor(self) -> None:
        if self.is_mounted:
            self._render_list()

    def on_resize(self, event) -> None:
        """Draw again once the box has a size.

        On mount there is no layout yet, so the window below has no idea how
        many rows it may spend and hands back the whole list. This is where it
        finds out, and where a terminal resized under an open window does too.
        """
        self._render_list()

    # --------------------------------------------------------------- drawing

    @staticmethod
    def _stored(option: Option) -> str:
        """The row's value as the file holds it, the way `choices` spell it."""
        current = getattr(config, _ATTRIBUTES[option.key])
        # `debug` is a bool in the file and "true"/"false" in the choices.
        return str(current).lower() if isinstance(current, bool) else str(current)

    def _value(self, option: Option) -> str:
        if option.key:
            # Themes, palettes and pictures go by their names in the language
            # in use; the file keeps the one it always had, and `_cycle`
            # steps through those, never through the labels.
            if option.key in ("theme", "palette", "backdrop"):
                return label(self._stored(option))
            return self._stored(option)
        if option.action == "rates":
            if audio.rates_configured():
                return _("configurado")
            return _("sin configurar")
        if option.action == "columns":
            return _("{count} de {total}").format(
                count=len(config.COLUMNS), total=len(columns.ALL)
            )
        return _("acción")

    def _detail(self, option: Option) -> str:
        """The line under a row: why it matters here, on this machine."""
        if option.key:
            shadowing = config.overridden(option.key)
            if shadowing:
                return _("lo pisa {variable} del entorno").format(variable=shadowing)
            return option.note
        if option.action == "rates":
            return self._rates_detail()
        if option.action == "columns":
            return option.note
        return _("corta el audio un momento; la reproducción se detiene antes")

    def _rates_detail(self) -> str:
        if not self._sink.known:
            return _("no se pudo consultar PipeWire")
        if self._sink.bluetooth:
            return _("la salida es Bluetooth: no hay hi-res real por ahí")
        if len(self._allowed) == 1:
            return _("el grafo está fijo en {rate} Hz y remuestrea todo").format(
                rate=self._allowed[0]
            )
        if self._hardware:
            return _("el DAC llega a {rate} Hz").format(rate=max(self._hardware))
        return _("el grafo puede cambiar de ritmo")

    def _render_list(self) -> None:
        palette = palette_for(self)
        widget = self.query_one("#config-list", Static)
        # Cropped, not wrapped: a detail that wrapped came back at column
        # zero and broke the indent that ties it to its own row.
        room = widget.size.width or 72
        labels = max(cell_len(option.label) for option in self._rows)

        # Rows and headings first, as (text, style, row index) so the window
        # below can find the cursor among them.
        lines: list[tuple[str, str, int]] = []
        group = ""
        for index, option in enumerate(self._rows):
            if option.group != group:
                group = option.group
                # No blank line before the first heading: the row above it is
                # the title bar, which already separates them.
                if index:
                    lines.append(("", palette["body"], -1))
                lines.append((f" {group}", f"bold {palette['accent']}", -1))
            selected = index == self.cursor
            marker = "›" if selected else " "
            style = (
                f"bold {palette['active_foreground']} on {palette['accent']}"
                if selected
                else palette["body"]
            )
            lines.append(
                (
                    f" {marker} {set_cell_size(option.label, labels)}   "
                    f"{self._value(option)}",
                    style,
                    index,
                )
            )

        current = self._rows[self.cursor]
        footer = [(f"     {current.label}: {self._detail(current)}", palette["muted"])]
        footer.append((self._status(), palette["muted"]))
        warning = self._warning()
        if warning:
            footer.append((warning, palette["warning"]))
        footer += [(line, palette["warning"]) for line in self._notice.splitlines()]

        rendered = Text()
        for text, style in self._window(lines, len(footer)):
            rendered.append(_crop(text, room) + "\n", style=style)
        for text, style in footer:
            rendered.append("\n" + _crop(text, room), style=style)
        widget.update(rendered)

    def _window(
        self, lines: list[tuple[str, str, int]], footer: int
    ) -> list[tuple[str, str]]:
        """The slice of the rows that fits, with the cursor inside it.

        The box grows to its content and stops at the terminal, so on a small
        one the rows past the fold used to be selectable and invisible at the
        same time: the cursor went somewhere nobody could see. Grouping the
        settings cost five more lines and made that reachable, so the list
        scrolls now — by hand, the way the help and the plain lyrics do.
        """
        # From the terminal, not from the widgets. The box grows to its text
        # and stops at the screen, so both it and the list report the height
        # of the text right up until the layout clips them — which happens
        # after this runs, and this is what decides what there is to clip.
        height = self.size.height - self.CHROME
        # The blank line between the rows and the footer is part of the cost.
        room = height - footer - 1
        if height <= 0 or room >= len(lines):
            return [(text, style) for text, style, _index in lines]
        cursor = next(
            (at for at, (_t, _s, index) in enumerate(lines) if index == self.cursor), 0
        )
        start = max(0, min(cursor - room // 2, len(lines) - room))
        return [(text, style) for text, style, _index in lines[start : start + room]]

    def _status(self) -> str:
        if not self._sink.known:
            return _("  Salida: desconocida")
        name = self._sink.description or self._sink.name
        return _("  Salida: {name} · {rate} Hz {format}").format(
            name=name, rate=self._sink.rate or "?", format=self._sink.sample_format
        )

    def _warning(self) -> str:
        """What the output line cannot say on its own.

        A graph pinned to one rate belongs here and not only in the detail of
        the row that fixes it: the badge tells the truth about the stream
        while the DAC receives something else, and nothing else on screen
        gives that away. Its own line, in the warning colour, because a tail
        appended to the output line was the first thing to be cropped away.
        """
        if not self._sink.known:
            return ""
        if self._sink.bluetooth:
            return _("  Bluetooth: no hay hi-res real por esta salida")
        if len(self._allowed) == 1:
            return _("  El grafo remuestrea todo a {rate} Hz").format(
                rate=self._allowed[0]
            )
        return ""

    # --------------------------------------------------------------- actions

    def action_up(self) -> None:
        self.cursor = (self.cursor - 1) % len(self._rows)

    def action_down(self) -> None:
        self.cursor = (self.cursor + 1) % len(self._rows)

    @staticmethod
    def _picked(option: Option) -> bool:
        """The rows chosen from a list instead of stepped with the arrows.

        The three where a stray arrow cost the most: the quality changed
        under the next track, PipeWire's rates were written or removed, or
        PipeWire was restarted and the audio cut. Only ↵ opens them now.
        """
        return option.key == "quality" or option.action in ("rates", "restart")

    def action_activate(self) -> None:
        option = self._rows[self.cursor]
        if self._picked(option):
            self._pick(option)
        else:
            self._change(1)

    def action_advance(self) -> None:
        if not self._picked(self._rows[self.cursor]):
            self._change(1)

    def action_back(self) -> None:
        if not self._picked(self._rows[self.cursor]):
            self._change(-1)

    def _pick(self, option: Option) -> None:
        """Open the list for one of the three picked rows."""
        if option.key == "quality":
            labels = {"LOSSLESS": _("LOSSLESS  (con device flow llega como HIGH)")}
            self.app.push_screen(
                ChoiceScreen(
                    _("CALIDAD"),
                    [(value, labels.get(value, value)) for value in self.QUALITIES],
                    config.DEFAULT_QUALITY,
                ),
                lambda value: self._set(option, value),
            )
        elif option.action == "rates":
            configured = audio.rates_configured()
            self.app.push_screen(
                ChoiceScreen(
                    _("RITMOS HI-RES EN PIPEWIRE"),
                    [
                        ("write", _("configurar: PipeWire ofrece los ritmos del DAC")),
                        ("remove", _("quitar: PipeWire vuelve a un solo ritmo")),
                    ],
                    "write" if configured else "remove",
                ),
                lambda value: self._rates_chosen(value, configured),
            )
        elif option.action == "restart":
            # The cursor starts on «cancel»: ↵ twice by reflex must not cut
            # the audio.
            self.app.push_screen(
                ChoiceScreen(
                    _("REINICIAR PIPEWIRE"),
                    [
                        ("restart", _("reiniciar ahora; corta el audio un momento")),
                        ("cancel", _("cancelar")),
                    ],
                    cursor=1,
                ),
                lambda value: self._restart() if value == "restart" else None,
            )

    def _rates_chosen(self, value: object, configured: bool) -> None:
        if value is None or (value == "write") == configured:
            return
        self._toggle_rates()

    def _change(self, step: int) -> None:
        option = self._rows[self.cursor]
        if option.key:
            self._cycle(option, step)
            return
        if option.action == "columns":
            self.app.push_screen(ColumnsScreen(self._on_change), self._columns_closed)

    def _columns_closed(self, _result) -> None:
        self._render_list()

    def _cycle(self, option: Option, step: int) -> None:
        current = self._stored(option)
        try:
            index = option.choices.index(current)
        except ValueError:
            index = 0
            step = 0
        value: object = option.choices[(index + step) % len(option.choices)]
        if option.key in _FLAGS:
            value = value == "true"
        self._set(option, value)

    def _set(self, option: Option, value: object) -> None:
        """Write one row's new value, and everything that follows from it."""
        if value is None or value == getattr(config, _ATTRIBUTES[option.key]):
            return
        config.set_option(option.key, value)
        if self._on_change is not None:
            self._on_change(option.key)
        if option.key == "theme":
            self._pair_palette(str(value))
        if option.key == "transparency":
            if value is True:
                self._limit_artwork()
            # The cover's own choices depend on this switch, so the rows are
            # rebuilt rather than left describing the setting as it was.
            self._rows = self._options()
        self._render_list()

    def _pair_palette(self, layout: str) -> None:
        """A themed layout brings its palette and its picture, written once
        and left alone.

        Only on choosing the layout: the palette stays a setting of its own,
        so whoever wants the layout in other colours picks them afterwards
        and nothing here puts the pair back.
        """
        palette = paired_palette(layout)
        if palette is None:
            return
        # Its picture too, by the same rule: written once, then the user's.
        for key, value, current in (
            ("palette", palette, config.PALETTE),
            ("backdrop", layout, config.BACKDROP),
        ):
            if value == current:
                continue
            config.set_option(key, value)
            if self._on_change is not None:
                self._on_change(key)

    # Terminals that paint the cover over the text instead of among it. The
    # protocol is the terminal's, not ours, and neither one lets a window open
    # on top of an image that the terminal draws last.
    PIXEL_PROTOCOLS = (artwork.Protocol.KITTY, artwork.Protocol.SIXEL)
    KITTY_DOCS = "https://sw.kovidgoyal.net/kitty/graphics-protocol/"

    def _limit_artwork(self) -> None:
        """Turning transparency on leaves the cover only what a window can be
        drawn over.

        Otherwise the one thing the user turned transparency on to see — the
        player behind the window — comes with a hole in it, because a pixel
        cover has to be taken down for the window to be visible at all. Half
        blocks are ordinary characters, so they stay put and the window draws
        over them, and `off` was already nothing to take down.

        Announced only when it actually took a picture away: moving `auto` to
        `blocks` on a terminal where `auto` already meant blocks changes the
        word on the row and nothing on the screen.
        """
        if config.ARTWORK in self.ARTWORKS_OVER_PLAYER:
            return
        loses_the_image = self.player.art_protocol in self.PIXEL_PROTOCOLS
        config.set_option("artwork", "blocks")
        if self._on_change is not None:
            self._on_change("artwork")
        if not loses_the_image:
            return
        self._notice = _(
            "  La carátula pasa a blocks: kitty y sixel pintan la imagen sobre el\n"
            "  texto y taparían la ventana.\n"
            "  {url}"
        ).format(url=self.KITTY_DOCS)

    def _toggle_rates(self) -> None:
        if audio.rates_configured():
            audio.remove_rates()
            message = _("ritmos hi-res quitados; reinicia PipeWire para aplicarlo")
        else:
            audio.write_rates()
            message = _("ritmos hi-res escritos; reinicia PipeWire para aplicarlo")
        self.player.status = message
        self._render_list()

    def _restart(self) -> None:
        # mpv is holding the sink; let go of it before the daemon goes away.
        self.player.action_stop()
        self.player.status = _("reiniciando PipeWire…")
        self._restart_worker()

    @work(thread=True, exclusive=True, group="config")
    def _restart_worker(self) -> None:
        message = audio.restart()
        self.app.call_from_thread(self._restarted, message)

    def _restarted(self, message: str) -> None:
        self.player.status = message
        self._probe()

    @property
    def player(self) -> TidalAmp:
        return cast("TidalAmp", self.app)

    def action_close(self) -> None:
        self.dismiss(None)


# The module attribute each config key is resolved into.
# Settings the file holds as booleans while the screen cycles "true"/"false".
_FLAGS = ("debug", "transparency")


_ATTRIBUTES = {
    "quality": "DEFAULT_QUALITY",
    "artwork": "ARTWORK",
    "cover_shape": "COVER_SHAPE",
    "language": "LANGUAGE",
    "theme": "THEME",
    "palette": "PALETTE",
    "arrangement": "ARRANGEMENT",
    "backdrop": "BACKDROP",
    "visualizer": "VISUALIZER",
    "debug": "DEBUG",
    "transparency": "TRANSPARENCY",
}
