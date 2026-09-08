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

# Spanish source -> English. Every string wrapped in _() must appear here;
# tests/test_i18n.py walks the AST and fails when one does not.
ENGLISH: dict[str, str] = {
    # --- transport and status
    "listo": "ready",
    "cola vaciada": "queue cleared",
    "nada que añadir": "nothing to add",
    "no hay una pista reproduciéndose": "no track is playing",
    "no hay ninguna pista seleccionada": "no track selected",
    "cola restaurada ({count} pistas)": "queue restored ({count} tracks)",
    "{count} pistas añadidas a la cola": "{count} tracks added to the queue",
    "reproduciendo {label}": "playing {label}",
    "resolviendo «{title}»…": "resolving “{title}”…",
    "sesión refrescada": "session refreshed",
    "error: {error}": "error: {error}",
    "pausa": "pause",
    "reproduciendo": "playing",
    "detenido": "stopped",
    "pista quitada de la cola": "track removed from the queue",
    "shuffle activado": "shuffle enabled",
    "shuffle desactivado": "shuffle disabled",
    "sin repetición": "repeat off",
    "repetir cola": "repeat queue",
    "repetir pista": "repeat track",
    "MPRIS no disponible ({error})": "MPRIS unavailable ({error})",
    "MPRIS como {name} (ya había otra instancia)": (
        "MPRIS as {name} (another instance was already running)"
    ),
    "mpv murió y no se pudo reiniciar ({error})": (
        "mpv died and could not be restarted ({error})"
    ),
    "mpv se reinició; recargando la pista": "mpv restarted; reloading the track",
    "mpv se reinició": "mpv restarted",
    "ecualizador activo": "equalizer active",
    "ecualizador plano": "equalizer flat",
    "balance: {value}": "balance: {value}",
    "centro": "centre",
    "izquierda": "left",
    "derecha": "right",
    # --- quality
    "{status} · TIDAL entregó {got}, no {asked}": (
        "{status} · TIDAL delivered {got}, not {asked}"
    ),
    # --- artwork
    "sin carátula: {error}": "no cover: {error}",
    # --- favourites
    "«{label}» añadido a favoritos": "“{label}” added to favourites",
    "«{label}» quitado de favoritos": "“{label}” removed from favourites",
    "favoritos: {error}": "favourites: {error}",
    "añadiendo a favoritos…": "adding to favourites…",
    "quitando de favoritos…": "removing from favourites…",
    # --- browser
    "cargando…": "loading…",
    "vacío": "empty",
    "cargando {level}…": "loading {level}…",
    "abriendo {label}…": "opening {label}…",
    "cargando más…": "loading more…",
    "recargando {level}…": "reloading {level}…",
    "añadiendo {label}…": "adding {label}…",
    "buscando la letra…": "looking for the lyrics…",
    "más…": "more…",
    "siguientes {page}": "next {page}",
    "siguientes {page} de {total}": "next {page} of {total}",
    "cola vacía — / para buscar, l para tu biblioteca": (
        "empty queue — / to search, l for your library"
    ),
    "MI BIBLIOTECA": "MY LIBRARY",
    "BUSCAR: {query}": "SEARCH: {query}",
    "BUSCAR EN TIDAL": "SEARCH TIDAL",
    "artista, canción o álbum…": "artist, song or album…",
    "Mis playlists": "My playlists",
    "Pistas favoritas": "Favourite tracks",
    "Álbumes favoritos": "Favourite albums",
    "Artistas favoritos": "Favourite artists",
    "{label} con «{query}»": "{label} matching “{query}”",
    "Álbumes": "Albums",
    "Artistas": "Artists",
    "Playlists": "Playlists",
    "abrir": "open",
    "artista": "artist",
    "{count} pistas": "{count} tracks",
    # --- lyrics
    "sincronizada": "synced",
    "texto": "text",
    "▓ LETRA ▓  {title}": "▓ LYRICS ▓  {title}",
    "▓ LETRA ▓  {title} · {mode}{provider}": ("▓ LYRICS ▓  {title} · {mode}{provider}"),
    "Letra no disponible para «{name}»": "Lyrics unavailable for “{name}”",
    "Letra no disponible para «{name}»: {error}": (
        "Lyrics unavailable for “{name}”: {error}"
    ),
    "esta pista": "this track",
    # --- equalizer
    "▓ ECUALIZADOR ▓": "▓ EQUALIZER ▓",
    " ←→ banda  ↑↓ ±1 dB  0 plano  ,. balance  \\ centro  esc": (
        " ←→ band  ↑↓ ±1 dB  0 flat  ,. balance  \\ centre  esc"
    ),
    # --- binding descriptions
    "cancelar": "cancel",
    "cerrar": "close",
    "arriba": "up",
    "abajo": "down",
    "abrir/reproducir": "open/play",
    "atrás": "back",
    "añadir": "add",
    "añadir todo": "add all",
    "recargar": "reload",
    "favorito": "favourite",
    "quitar favorito": "remove favourite",
    "banda anterior": "previous band",
    "banda siguiente": "next band",
    "subir": "up",
    "bajar": "down",
    "plano": "flat",
    "balance izq": "balance left",
    "balance der": "balance right",
    "centrar": "centre",
    "anterior": "previous",
    "siguiente": "next",
    "buscar": "search",
    "biblioteca": "library",
    "letra": "lyrics",
    "ecualizador": "equalizer",
    "reproducir": "play",
    "quitar": "remove",
    "vaciar": "clear",
    "centrar balance": "centre balance",
    "tiempo": "time",
    "salir": "quit",
    # --- window furniture
    "▓ PLAYLIST ▓   d quitar   C vaciar   alt+↑↓ mover": (
        "▓ PLAYLIST ▓   d remove   C clear   alt+↑↓ move"
    ),
    " ↵ abrir/reproducir   a añadir   A añadir todo   f/F favorito"
    "   ⌫ atrás   R recargar   esc cerrar": (
        " ↵ open/play   a add   A add all   f/F favourite   ⌫ back   R reload   esc close"
    ),
    " ↑↓ desplazar   y/esc cerrar": " ↑↓ scroll   y/esc close",
    "  z ◀◀   x ▶   c ‖   v ■   b ▶▶   / buscar  l lib  y letra  e eq"
    "  f/F favorito  s shuf  r rep  q salir": (
        "  z ◀◀   x ▶   c ‖   v ■   b ▶▶   / search  l lib  y lyrics  e eq"
        "  f/F favourite  s shuf  r rep  q quit"
    ),
    "\n  La ventana es de {width}×{height}.\n"
    "  TIDAL AMP necesita al menos {min_width}×{min_height}.\n\n"
    "  Agranda el terminal o reduce el tamaño de letra.\n": (
        "\n  The window is {width}×{height}.\n"
        "  TIDAL AMP needs at least {min_width}×{min_height}.\n\n"
        "  Make the terminal bigger or the font smaller.\n"
    ),
    # --- authentication and playback errors
    "La sesión expiró y no hay refresh token. Ejecuta: tidalamp login": (
        "The session expired and there is no refresh token. Run: tidalamp login"
    ),
    "No se pudo refrescar la sesión ({error}). Ejecuta: tidalamp login": (
        "The session could not be refreshed ({error}). Run: tidalamp login"
    ),
    "No se pudo refrescar la sesión. Ejecuta: tidalamp login": (
        "The session could not be refreshed. Run: tidalamp login"
    ),
    "La sesión refrescada no fue aceptada. Ejecuta: tidalamp login": (
        "The refreshed session was not accepted. Run: tidalamp login"
    ),
    "No hay sesión guardada. Ejecuta: tidalamp login": (
        "No saved session was found. Run: tidalamp login"
    ),
    "mpv no está instalado (pacman -S mpv)": ("mpv is not installed (pacman -S mpv)"),
    "mpv no abrió el socket IPC a tiempo": "mpv did not open its IPC socket in time",
    "TIDAL no devolvió stream para «{name}»: {error}": (
        "TIDAL returned no stream for “{name}”: {error}"
    ),
    "«{name}» viene con DRM (Widevine); mpv no puede reproducirla. "
    "Prueba con TIDALAMP_QUALITY=HIGH.": (
        "“{name}” is DRM-protected (Widevine); mpv cannot play it. "
        "Try TIDALAMP_QUALITY=HIGH."
    ),
    "Manifiesto vacío para «{name}»": "Empty manifest for “{name}”",
    "eso no es una pista, un álbum, un artista ni una playlist": (
        "that is not a track, album, artist, or playlist"
    ),
    "cava no está instalado (pacman -S cava)": ("cava is not installed (pacman -S cava)"),
    "no se pudo reclamar un nombre MPRIS ({reply})": (
        "could not claim an MPRIS name ({reply})"
    ),
    "acción desconocida: {action}": "unknown action: {action}",
    # --- command line
    "Cliente TIDAL con interfaz estilo Winamp.": (
        "TIDAL client with a Winamp-style interface."
    ),
    "Autoriza el cliente con tu cuenta TIDAL (flujo de dispositivo).": (
        "Authorize the client with your TIDAL account (device flow)."
    ),
    "Abre esta URL y autoriza el acceso:\n": ("Open this URL and authorize access:\n"),
    "Caduca en {minutes} minutos. Esperando…": ("Expires in {minutes} minutes. Waiting…"),
    "Sesión guardada para {user_id}.": "Session saved for {user_id}.",
    "Lanza la interfaz.": "Launch the interface.",
    "Registro de depuración en {path}": "Debug log at {path}",
    "Muestra la configuración efectiva y crea el fichero si no existe.": (
        "Show the effective configuration and create the file if it is missing."
    ),
    "Fichero: {path}": "File: {path}",
    "Ajustes en uso:": "Settings in use:",
    "Teclas cambiadas:": "Changed keys:",
    "  {action:<16} {key}   (por defecto {default})": (
        "  {action:<16} {key}   (default {default})"
    ),
    "Teclas: todas por defecto.": "Keys: all defaults.",
    "Estas acciones de [keys] no existen y se ignoran: {actions}": (
        "These [keys] actions do not exist and are ignored: {actions}"
    ),
    "Busca pistas y muestra sus IDs (útil para scripts).": (
        "Search for tracks and print their IDs (useful in scripts)."
    ),
    # --- generated config file
    "# Configuración de tidalamp. Todo es opcional: lo que no esté aquí usa su valor\n"
    "# por defecto, y una variable de entorno gana siempre sobre este fichero.\n\n"
    "# LOW, HIGH, LOSSLESS o HI_RES_LOSSLESS.\n"
    "# Ojo: pedir LOSSLESS al cliente del device flow devuelve HIGH siempre. Ver el\n"
    "# README, sección «Calidad».\n"
    'quality = "HI_RES_LOSSLESS"\n\n'
    "# Cómo dibujar la carátula: auto, kitty, sixel, blocks u off.\n"
    'artwork = "auto"\n\n'
    "# Registro en ~/.local/state/tidalamp/tidalamp.log.\n"
    "debug = false\n\n"
    "# Teclas. La izquierda es la acción, la derecha la tecla; varias se separan con\n"
    "# comas. Las de navegación (flechas, RePág/AvPág, Enter, Esc) no se cambian.\n"
    "[keys]\n"
    "%(keys)s\n": (
        "# tidalamp configuration. Everything is optional: omitted values use their\n"
        "# defaults, and environment variables always take precedence over this file.\n\n"
        "# LOW, HIGH, LOSSLESS, or HI_RES_LOSSLESS.\n"
        "# Note: requesting LOSSLESS through the device-flow client always "
        "returns HIGH.\n"
        "# See the README's Quality section.\n"
        'quality = "HI_RES_LOSSLESS"\n\n'
        "# How to draw cover art: auto, kitty, sixel, blocks, or off.\n"
        'artwork = "auto"\n\n'
        "# Log to ~/.local/state/tidalamp/tidalamp.log.\n"
        "debug = false\n\n"
        "# Keys. The action is on the left and the key on the right; separate multiple\n"
        "# keys with commas. Navigation keys (arrows, Page Up/Down, Enter, Esc) "
        "are fixed.\n"
        "[keys]\n"
        "%(keys)s\n"
    ),
}

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
        try:
            locale_code = locale.getlocale(locale.LC_MESSAGES)[0]
        except (ValueError, AttributeError):
            locale_code = None
        if locale_code:
            return locale_code.split("_")[0].lower()
    return "es"


_catalogue: dict[str, str] = _CATALOGUES.get(_language(), {})


def use(language: str) -> None:
    """Switch language. For the tests, and for anything that wants to force one."""
    global _catalogue
    _catalogue = _CATALOGUES.get(language, {})


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
        "# Registro en ~/.local/state/tidalamp/tidalamp.log.\n"
        "debug = false\n\n"
        "# Teclas. La izquierda es la acción, la derecha la tecla; varias se "
        "separan con\n"
        "# comas. Las de navegación (flechas, RePág/AvPág, Enter, Esc) no se cambian.\n"
        "[keys]\n"
        "%(keys)s\n"
    )
