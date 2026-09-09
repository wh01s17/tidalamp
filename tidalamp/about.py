"""Who wrote this, under what licence, and what changed in each version.

The release notes live here as data rather than being parsed out of
`CHANGELOG.md` at runtime: that file is not shipped inside the wheel, so a
help screen that read it would work from a git checkout and be empty for
everyone who installed the package — which is everyone the screen is for.

Nothing here imports Textual, so it stays testable without an app.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import __version__
from .i18n import _

REPO_URL = "https://github.com/wh01s17/tidalamp"
AUTHOR = "wh01s17"
LICENSE = "GPL-3.0-or-later"
LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"


def version() -> str:
    """The running version. Installed metadata wins over the source constant.

    They agree in a release — `release.yml` refuses a tag that disagrees with
    `pyproject.toml` — but an editable install of a working tree can be ahead
    of the string in `__init__.py`.
    """
    try:
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as installed

        return installed("tidalamp")
    except (ImportError, PackageNotFoundError):
        return __version__


@dataclass(frozen=True)
class Release:
    """One version and what it brought, short enough to read on one screen."""

    version: str
    date: str
    changes: tuple[str, ...] = field(default_factory=tuple)


def releases() -> tuple[Release, ...]:
    """Newest first. Translated at call time, not at import time."""
    return (
        Release(
            "0.1.0",
            _("sin publicar"),
            (
                _("Interfaz Winamp 2.x: reloj, marquesina, analizador y playlist."),
                _("Reproducción con mpv por IPC, hasta FLAC 24 bit/96 kHz."),
                _("Búsqueda, biblioteca paginada, favoritos y cola persistente."),
                _("Menú de pista: ahora, a continuación, radio y favoritos."),
                _("Letras sincronizadas, ecualizador de 10 bandas y balance."),
                _("Carátula en kitty, sixel o medios bloques, y espectro con cava."),
                _("MPRIS2 completo, incluida la lista de pistas."),
                _("Interfaz en español e inglés según el locale."),
            ),
        ),
    )


# Textual's key names are meant for the config file, not for reading: the
# screen shows the character you actually press.
_KEY_NAMES: dict[str, str] = {
    "slash": "/",
    "backslash": "\\",
    "comma": ",",
    "full_stop": ".",
    "plus": "+",
    "minus": "-",
    "equals_sign": "=",
    "question_mark": "?",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "enter": "↵",
    "escape": "esc",
    "pageup": "pgup",
    "pagedown": "pgdn",
    "delete": "del",
    "space": "␣",
    "alt+up": "alt+↑",
    "alt+down": "alt+↓",
}


def pretty_keys(binding: str) -> str:
    """«slash» -> «/», «d,delete» -> «d / del». One binding, as you type it."""
    parts = [key.strip() for key in binding.split(",") if key.strip()]
    return " / ".join(_KEY_NAMES.get(key, key) for key in parts)


@dataclass(frozen=True)
class Section:
    """A titled block of the help screen: what to press, and what it does."""

    title: str
    rows: tuple[tuple[str, str], ...]


def shortcuts(keys) -> tuple[Section, ...]:
    """The whole key map, grouped for reading.

    ``keys`` resolves an action to its effective binding — the config file's
    if the user rebound it — so what the screen shows is what the app answers
    to. Keys given as literals here are the ones `DEFAULT_KEYS` deliberately
    leaves unbindable, because a typo in them locks you out of the browser.
    """

    def key(action: str) -> str:
        return pretty_keys(keys(action))

    return (
        Section(
            _("Reproducción"),
            (
                (key("play"), _("reproducir o pausar (▶ / ‖)")),
                (key("stop"), _("detener")),
                (key("prev"), _("pista anterior")),
                (key("next"), _("pista siguiente")),
                (key("seek_back"), _("retroceder 5 s")),
                (key("seek_fwd"), _("avanzar 5 s")),
                (key("toggle_time"), _("tiempo transcurrido o restante")),
            ),
        ),
        Section(
            _("Volumen y sonido"),
            (
                (key("vol_up"), _("subir volumen")),
                (key("vol_down"), _("bajar volumen")),
                (key("balance_left"), _("balance a la izquierda")),
                (key("balance_right"), _("balance a la derecha")),
                (key("balance_centre"), _("centrar el balance")),
                (key("equalizer"), _("ecualizador de 10 bandas")),
            ),
        ),
        Section(
            _("Cola"),
            (
                ("↑ / ↓", _("mover el cursor")),
                ("pgup / pgdn", _("una página")),
                ("↵", _("reproducir la pista del cursor")),
                (key("remove"), _("quitar la pista del cursor")),
                (key("move_up"), _("subir la pista en la cola")),
                (key("move_down"), _("bajar la pista en la cola")),
                (key("clear"), _("vaciar la cola")),
                (key("shuffle"), _("aleatorio (⇄)")),
                (key("repeat"), _("repetición ↻: off, toda la cola, una pista")),
            ),
        ),
        Section(
            _("Ventanas"),
            (
                (key("search"), _("buscar en TIDAL")),
                (key("library"), _("tu biblioteca")),
                (key("lyrics"), _("letra de la pista actual")),
                (key("equalizer"), _("ecualizador")),
                (key("help"), _("esta ayuda")),
                (key("quit"), _("salir")),
            ),
        ),
        Section(
            _("Favoritos"),
            (
                (key("favourite"), _("añadir a favoritos de TIDAL")),
                (key("unfavourite"), _("quitar de favoritos")),
            ),
        ),
        Section(
            _("Dentro de la búsqueda y la biblioteca"),
            (
                ("↵", _("abrir el nivel, o el menú de la pista")),
                ("← / ⌫", _("volver al nivel anterior")),
                ("a", _("añadir a la cola")),
                ("A", _("añadir el nivel entero")),
                ("R", _("recargar, ignorando la caché")),
                ("f / F", _("añadir o quitar de favoritos")),
                ("esc", _("cerrar")),
            ),
        ),
        Section(
            _("Menú de la pista (↵ sobre una canción)"),
            (
                ("a", _("reproducir ahora")),
                ("c", _("reproducir a continuación")),
                ("d", _("reproducir la radio de la pista")),
                ("v", _("añadir a favoritos")),
                ("↑ / ↓ / ↵", _("elegir con el cursor")),
                ("esc", _("cancelar")),
            ),
        ),
    )
