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
            "0.8.0",
            "2026-09-11",
            (
                _("s ordena la biblioteca y d quita; ? con su propia ayuda."),
                _("m: el menú de un álbum, artista o playlist entero."),
                _("w: pantalla completa, con la cola al lado."),
                _("Reproducción automática; la velocidad, también por MPRIS."),
                _("Carátula más nítida en blocks y más ligera en kitty y sixel."),
                _("Calidad, ritmos y reiniciar PipeWire se eligen de una lista."),
            ),
        ),
        Release(
            "0.7.0",
            "2026-09-11",
            (
                _("bosque, un décimo tema, ecológico; marcos más finos en todos."),
                _("b cambia la velocidad, de 0.25× a 2×."),
                _("La carátula puede ser redonda (cover_shape)."),
                _("Los temas se llaman en tu idioma; la cuenta atrás cabe."),
            ),
        ),
        Release(
            "0.6.0",
            "2026-09-11",
            (
                _("Nueve temas temáticos, cada uno con su paleta y su imagen."),
                _("La imagen del tema, de fondo de la cola; se puede mezclar."),
                _("split: la cola a la derecha y la letra sobre la carátula."),
                _("/ busca en la ayuda; los textos largos se deslizan."),
            ),
        ),
        Release(
            "0.5.1",
            "2026-09-10",
            (
                _("OUT ya no muestra la frecuencia de la pista anterior."),
                _("Las pistas hi-res se reproducen con buffer de verdad."),
            ),
        ),
        Release(
            "0.5.0",
            "2026-09-10",
            (
                _("u deshace el último vaciado de la cola."),
                _("Ocho presets de ecualizador, con p y P."),
                _("Añadir una pista a una playlist que ya tienes."),
                _("La carátula en blocks, al doble de resolución."),
                _("space reproduce; m abre el menú sobre la cola."),
            ),
        ),
        Release(
            "0.4.0",
            "2026-09-10",
            (
                _("g vuelve a la pista que suena; p guarda la cola en TIDAL."),
                _("La barra de posición y los sliders responden al clic."),
                _("La columna «Año» ya no sale vacía."),
                _("Artista, álbum y año bajo el reloj; el título arriba, solo."),
                _("Las cuatro disposiciones cuadran sus bordes y sus anchos."),
            ),
        ),
        Release(
            "0.3.0",
            "2026-09-10",
            (
                _("El analizador llega al borde y tiene cuatro formas."),
                _("Buscador en la cola con ctrl+f, sin renumerar las pistas."),
                _("La ayuda en dos pestañas: atajos y acerca de."),
                _("tidalamp --version imprime la versión en el terminal."),
                _("El analizador cuesta mucho menos en pantallas 4K."),
            ),
        ),
        Release(
            "0.2.0",
            "2026-09-10",
            (
                _("Filtro en el navegador con /: estrecha el nivel donde estés."),
                _("Las ventanas toman la pantalla; opcionalmente translúcidas."),
                _("Con transparencia, la carátula va en medios bloques."),
                _("Configuración agrupada en Audio, Apariencia y General."),
                _("Paleta black: fondo negro con acentos grises y blancos."),
            ),
        ),
        Release(
            "0.1.1",
            "2026-09-09",
            (
                _("Si falta mpv o cava, el mensaje da la orden de tu distribución."),
                _("README reescrito: requisitos por distribución y menos rodeos."),
            ),
        ),
        Release(
            "0.1.0",
            "2026-09-09",
            (
                _("Interfaz retro: reloj, marquesina, analizador y playlist."),
                _("Reproducción con mpv por IPC, hasta FLAC 24 bit/96 kHz."),
                _("Búsqueda, biblioteca paginada, favoritos y cola persistente."),
                _("Menú de pista: ahora, a continuación, radio y favoritos."),
                _("Ventana de configuración, con los ritmos hi-res de PipeWire."),
                _("Letras sincronizadas, ecualizador de 10 bandas y balance."),
                _("Carátula en kitty, sixel o medios bloques, y espectro con cava."),
                _("MPRIS2 completo, incluida la lista de pistas."),
                _("Arranque directo con tidalamp; interfaz bilingüe según el locale."),
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
    # For the windows that show one section alone: the browser's `?`.
    name: str = ""


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
                (key("speed"), _("velocidad de reproducción, de 0.25× a 2×")),
                (
                    key("fullscreen"),
                    _("pantalla completa: la carátula en grande; w o esc vuelve"),
                ),
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
                (key("filter_queue"), _("buscar en la cola: escribe y se estrecha")),
                (key("track_menu"), _("menú de la pista del cursor")),
                (key("to_playing"), _("volver a la pista que suena")),
                (key("save_playlist"), _("guardar la cola como playlist")),
                (key("remove"), _("quitar la pista del cursor")),
                (key("move_up"), _("subir la pista en la cola")),
                (key("move_down"), _("bajar la pista en la cola")),
                (key("clear"), _("vaciar la cola")),
                (key("undo_clear"), _("deshacer el último vaciado de la cola")),
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
                (key("config"), _("configuración")),
                (key("help"), _("esta ayuda")),
                (key("quit"), _("salir; pregunta antes")),
                (key("force_quit"), _("salir sin preguntar")),
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
            _("Pantalla completa"),
            (
                (f"{key('fullscreen')} / esc", _("volver al reproductor")),
                ("tab", _("mostrar u ocultar la cola, al lado de la carátula")),
                ("↑ / ↓   ↵", _("en la cola: moverse y reproducir")),
                (key("to_playing"), _("ir a la pista que suena; abre la cola")),
                (key("remove"), _("quitar la pista del cursor")),
                (
                    f"{key('move_up')} / {key('move_down')}",
                    _("mover la pista en la cola"),
                ),
                (key("track_menu"), _("menú de la pista")),
                (
                    f"{key('prev')} {key('play')} {key('stop')} {key('next')}",
                    _("anterior, reproducir o pausar, detener, siguiente"),
                ),
                ("?", _("esta ayuda")),
            ),
            name="fullscreen",
        ),
        Section(
            _("Dentro de la búsqueda y la biblioteca"),
            (
                ("↵", _("abrir el nivel, o el menú de la pista")),
                ("← / ⌫", _("volver al nivel anterior")),
                ("a", _("añadir a la cola")),
                ("A", _("añadir el nivel entero")),
                ("m", _("menú de la pista, o del álbum, artista o playlist")),
                ("/", _("filtrar el nivel: escribe y la lista se estrecha")),
                ("R", _("recargar, ignorando la caché")),
                ("s", _("ordenar el nivel: fecha, nombre, artista o álbum")),
                ("d", _("quitar de favoritos o de la playlist abierta")),
                ("f / F", _("añadir o quitar de favoritos")),
                ("esc", _("cerrar")),
            ),
            name="browser",
        ),
        Section(
            _("Menú de la pista (↵ o m en la biblioteca, m en la cola)"),
            (
                ("a", _("reproducir ahora")),
                ("c", _("reproducir a continuación")),
                ("d", _("reproducir la radio de la pista")),
                ("v", _("añadir a favoritos")),
                ("↑ / ↓ / ↵", _("elegir con el cursor")),
                ("esc", _("cancelar")),
            ),
        ),
        Section(
            _("Menú de un álbum, artista o playlist (m en la biblioteca)"),
            (
                ("a", _("reproducir todo ahora")),
                ("c", _("reproducir todo a continuación")),
                ("v", _("añadir a favoritos")),
                ("l", _("añadir todo a una playlist")),
                ("esc", _("cancelar")),
            ),
        ),
    )
