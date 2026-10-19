"""Interface strings.

Spanish is the source language: the strings live in the code written out, not
behind opaque keys, so reading `app.py` still tells you what the screen says.
The catalogue maps each Spanish string to its English one, and the locale
decides which comes back. Anything without a translation falls through to the
Spanish it was written in, which is a worse experience than a translation and
a much better one than a crash or a `MISSING_KEY_42`.

No gettext, no `.mo` files to compile and ship: a dict is enough for one
language, and it keeps the package a pure wheel.

Strings that carry values use ``str.format`` placeholders rather than
f-strings, because an f-string is interpolated before it can be looked up::

    _("«{label}» añadido a favoritos").format(label=entry.label)
"""

from __future__ import annotations

import locale
import os
import sys

from .catalogue import ENGLISH

_CATALOGUES = {"en": ENGLISH}


def _language(env: dict[str, str] | None = None) -> str:
    """The two-letter language, from the usual variables then the C library.

    ``LANGUAGE`` first because that is what the gettext convention says, and
    it is the one a user sets to override a system locale for one program.
    """
    values = os.environ if env is None else env
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = values.get(name)
        if value:
            candidates = value.split(":")
            codes = [
                candidate.split("_")[0].split(".")[0].lower() for candidate in candidates
            ]
            for code in codes:
                if code in ("c", "posix"):
                    return "es"
                if code == "es" or code in _CATALOGUES:
                    return code
            # An explicitly requested but unsupported language uses the
            # Spanish source text instead of silently consulting a lower-
            # priority environment variable.
            return codes[0]
    if env is None:
        locale_code = _system_language()
        if locale_code:
            return locale_code.split("_")[0].lower()
    return "es"


def _system_language() -> str:
    """The language the system itself is in, as ``en_US``, or "".

    Windows has no ``LC_MESSAGES``, and the `AttributeError` used to swallow
    that without a word: an English Windows got the Spanish interface. It
    also answers `locale.getlocale()` with names like ``Spanish_Spain``, so
    it is asked for its UI language instead.
    """
    if sys.platform == "win32":
        return _windows_ui_language()
    try:
        return locale.getlocale(locale.LC_MESSAGES)[0] or ""
    except (ValueError, AttributeError):
        return ""


def _windows_ui_language() -> str:
    """The Windows display language, as ``en_US``; "" when it cannot say."""
    if sys.platform != "win32":
        return ""
    import ctypes

    try:
        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return ""
    return from_lcid(lcid)


def from_lcid(lcid: int) -> str:
    """A Windows language id to a locale name: 0x0409 is ``en_US``."""
    return locale.windows_locale.get(lcid, "")


def selected(env: dict[str, str] | None = None) -> str:
    """The language to use: the `language` setting when it pins one, else the locale.

    The setting comes first because it is a choice and `$LANG` is ambient: a
    system in Spanish is not a request for this program to be in Spanish. An
    unrecognised value falls through to the locale rather than failing, same
    as everywhere else in the config file.
    """
    # Imported here, not at module level: config's template generator imports
    # this module back, and only one of the two can afford to be first.
    from . import config

    chosen = (config.LANGUAGE or "auto").strip().lower()
    if chosen == "es" or chosen in _CATALOGUES:
        return chosen
    return _language(env)


_catalogue: dict[str, str] = _CATALOGUES.get(selected(), {})


def use(language: str) -> None:
    """Switch language. For the tests, and for anything that wants to force one."""
    global _catalogue
    _catalogue = _CATALOGUES.get(language, {})


def refresh() -> None:
    """Re-read the language setting, after the config screen changed it."""
    use(selected())


def _(text: str) -> str:
    """Translate ``text``, or return it as written."""
    return _catalogue.get(text, text)


def config_template() -> str:
    """Return the commented config template in the selected language."""
    return _(
        "# Configuración de tidalamp. Todo es opcional: lo que no esté aquí usa su "
        "valor\n"
        "# por defecto, y una variable de entorno gana siempre sobre este fichero.\n\n"
        "# LOW, HIGH, LOSSLESS o HI_RES_LOSSLESS.\n"
        "# Ojo: pedir LOSSLESS al cliente del device flow devuelve HIGH siempre. Ver el\n"
        "# README, sección «Calidad».\n"
        'quality = "HI_RES_LOSSLESS"\n\n'
        "# Cómo dibujar la carátula: auto, kitty, sixel, blocks u off.\n"
        'artwork = "auto"\n\n'
        "# Forma de la carátula: square (cuadrada), rounded (esquinas redondeadas)\n"
        "# o round (redonda).\n"
        'cover_shape = "square"\n\n'
        "# Idioma: auto sigue al locale del sistema; es o en lo fijan.\n"
        'language = "auto"\n\n'
        "# Columnas de la cola, separadas por coma. Disponibles: track, version,\n"
        "# artist, album, year, quality, explicit, popularity, disc, isrc, duration.\n"
        'columns = "artist,album,year,duration"\n\n'
        "# Estilo visual: quattro, retro, nova o ascii, o un tema que trae su paleta:\n"
        "# unidad-morada, pirata, cuaderno, neon-noir, runas, reggae, comodin,\n"
        "# gotico, death-metal o bosque.\n"
        'theme = "quattro"\n\n'
        "# Paleta: auto sigue Omarchy; también classic, tokyo-night, catppuccin,\n"
        "# nord, gruvbox, phosphor, black, la de cualquier tema o un TOML en\n"
        "# ~/.config/tidalamp/palettes/.\n"
        'palette = "auto"\n\n'
        "# Disposición: stacked pone la cola debajo del reproductor; split la pone\n"
        "# en una columna a la derecha (necesita un terminal ancho, y si no cabe\n"
        "# vuelve sola a stacked).\n"
        'arrangement = "stacked"\n\n'
        "# Fondo de la cola: auto usa la imagen del tema; none la quita; o el\n"
        "# nombre de un tema temático para usar su imagen con otro tema o paleta.\n"
        'backdrop = "auto"\n\n'
        "# Visualizador: bars (barras), mirror (espejo), curve (línea) o fine "
        "(línea\n"
        "# en Braille, necesita una fuente que lo traiga). Los cuatro se dibujan al "
        "lado\n"
        "# de la carátula y llegan al borde derecho de la ventana.\n"
        'visualizer = "bars"\n\n'
        "# Registro en ~/.local/state/tidalamp/tidalamp.log.\n"
        "debug = false\n\n"
        "# Deja ver el reproductor a través de las ventanas superpuestas. Al "
        "activarla,\n"
        "# la carátula pasa a medios bloques: kitty y sixel pintan la imagen por "
        "encima\n"
        "# del texto y taparían la ventana.\n"
        "transparency = false\n\n"
        "# Reproducción automática: al terminar la cola, sigue con la radio de\n"
        "# TIDAL de la última pista.\n"
        "autoplay = false\n\n"
        "# Volumen normalizado con el ReplayGain de TIDAL: off, track (por pista) o\n"
        "# album (por disco). Nunca sube una pista más allá de su pico.\n"
        'replaygain = "off"\n\n'
        "# Vista de la biblioteca: list (listado) o grid (cuadrícula con la carátula\n"
        "# de cada álbum, playlist, artista o mix). Un nivel de pistas es siempre un\n"
        "# listado.\n"
        'library_view = "list"\n\n'
        "# Teclas. La izquierda es la acción, la derecha la tecla; varias se "
        "separan con\n"
        "# comas. Las de navegación (flechas, RePág/AvPág, Enter, Esc) no se cambian.\n"
        "[keys]\n"
        "%(keys)s\n"
    )
