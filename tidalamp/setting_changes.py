"""What changing a setting does to the player that is running.

The settings window writes the file and calls `SettingChanges.apply` with the
setting's name: whatever can follow without a restart follows here, and the
status line says what changed or what waits for the next start.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import tidalapi

from . import audio, config, i18n, theme
from .i18n import _
from .layouts import label as theme_label
from .screens import RowList
from .stream import gain_for

if TYPE_CHECKING:
    from .app import TidalAmp


class SettingChanges:
    """Applies a setting the moment the settings window changes it."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app

    def apply(self, name: str) -> None:
        """Apply what can be applied without a restart, and say what cannot."""
        if name == "quality":
            # The session carries the quality it asks TIDAL for; the next
            # track resolved picks the new one up.
            session_config = getattr(self.app.session, "config", None)
            if session_config is not None:
                with contextlib.suppress(Exception):
                    session_config.quality = tidalapi.Quality(config.DEFAULT_QUALITY)
            self.app.status = _("calidad: {value}").format(value=config.DEFAULT_QUALITY)
        elif name == "language":
            i18n.refresh()
            self.app.status = _("el idioma cambia al reiniciar tidalamp")
        elif name == "artwork":
            self.app.cover.reload()
            self.app.status = _("carátula: {value}").format(value=config.ARTWORK)
        elif name == "cover_shape":
            self.app.cover.reshape()
            # The full-screen view cuts its own cover, to the old shape.
            fullscreen = self.app.fullscreen_view()
            if fullscreen is not None:
                fullscreen.reload_cover()
            self.app.status = _("forma de la carátula: {value}").format(
                value=config.COVER_SHAPE
            )
        elif name == "theme":
            self.app.looks.apply_appearance()
            self.app.status = _("tema: {value}").format(value=theme_label(config.THEME))
        elif name == "palette":
            self.app.tidalamp_palette = theme.load_palette(name=config.PALETTE)
            self.app.refresh_css(animate=False)
            self.app.looks.paint_terminal_margin()
            self.app.looks.apply_appearance()
            self.app.status = _("paleta: {value}").format(
                value=theme_label(config.PALETTE)
            )
        elif name == "backdrop":
            self.app.looks.apply_emblem()
            self.app.status = _("fondo de la cola: {value}").format(
                value=theme_label(config.BACKDROP)
            )
        elif name == "arrangement":
            self.app.looks.check_size()
            if config.ARRANGEMENT == "split" and not self.app.looks.split:
                self.app.status = _(
                    "split necesita al menos {width}×{height}; la cola sigue debajo"
                ).format(width=self.app.SPLIT_MIN_WIDTH, height=self.app.SPLIT_MIN_HEIGHT)
            else:
                self.app.status = _("disposición: {value}").format(
                    value=config.ARRANGEMENT
                )
        elif name == "visualizer":
            self.app.spectrum.apply_shape()
            self.app.status = _("visualizador: {value}").format(value=config.VISUALIZER)
        elif name == "columns":
            # RowList reads the setting at render time, so the queue only
            # needs telling to draw itself again — no reload, and the browser
            # underneath a modal gets the same treatment.
            for screen in self.app.screen_stack:
                for widget in screen.query(RowList):
                    widget.refresh()
            self.app.status = _("columnas: {count}").format(count=len(config.COLUMNS))
        elif name == "replaygain":
            if (
                self.app.playback.playable is not None
                and self.app.queue.current is not None
            ):
                self.app.mpv.gain = gain_for(self.app.playback.playable)
            # The track queued for a gapless start carries the old gain as
            # its own option; it is resolved and queued again at the new one.
            self.app.prefetch.drop()
            self.app.readout.refresh()
            self.app.status = _("volumen normalizado: {value}").format(
                value=config.REPLAYGAIN
            )
        elif name == "library_view":
            # The browser reads it when it shows a level: nothing to redraw.
            self.app.status = _("vista de la biblioteca: {value}").format(
                value=config.LIBRARY_VIEW
            )
        elif name == "audio_device":
            wanted = config.AUDIO_DEVICE
            if wanted not in ("", "auto") and not audio.connected(wanted):
                # mpv asked for it would play in silence.
                self.app.mpv.set_device("auto")
                self.app.status = _(
                    "ese dispositivo no está conectado; suena por el predeterminado"
                )
            else:
                self.app.mpv.set_device(wanted)
                # By name the line would show a guid; OUT says which one it is.
                self.app.status = (
                    _("dispositivo de salida: el predeterminado de {system}").format(
                        system=audio.SYSTEM
                    )
                    if wanted in ("", "auto")
                    else _("dispositivo de salida cambiado")
                )
            # mpv opened the output again, on another device and maybe rate.
            self.app.output.follow()
            self.app.spectrum.pick()
        elif name == "exclusive":
            self.app.mpv.set_exclusive(config.EXCLUSIVE)
            self.app.status = (
                _("modo exclusivo: sólo suena tidalamp, a la frecuencia de cada pista")
                if config.EXCLUSIVE
                else _("modo exclusivo desactivado: suena todo, remuestreado")
            )
            # The output was opened again, maybe at another rate.
            self.app.output.follow()
            # And cava can hear it again, or no longer (`SpectrumFeed.start`).
            self.app.spectrum.pick()
        elif name == "autoplay":
            self.app.status = (
                _("reproducción automática activada")
                if config.AUTOPLAY
                else _("reproducción automática desactivada")
            )
        elif name == "transparency":
            # Each screen by the one under it, as `push_screen` decided: the
            # settings opened over the full-screen view stay opaque.
            stack = self.app.screen_stack
            for index, screen in enumerate(stack):
                see_through = (
                    self.app.see_through(below=stack[index - 1])
                    if index
                    else config.TRANSPARENCY
                )
                screen.set_class(see_through, "transparent")
            self.app.status = (
                _("transparencia activada")
                if config.TRANSPARENCY
                else _("transparencia desactivada")
            )
        elif name == "debug":
            self.app.status = _("debug log: {value}").format(
                value=_("activado") if config.DEBUG else _("desactivado")
            )
