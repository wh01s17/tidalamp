"""English for the Spanish source strings, part of `tidalamp.catalogue`.

Errors from sign-in and playback, the command line, and the config file
tidalamp writes on first start.
"""

from __future__ import annotations

ENGLISH: dict[str, str] = {
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
    "{package} no está instalado ({command})": ("{package} is not installed ({command})"),
    "{package} no está instalado": "{package} is not installed",
    "¿Instalarlo ahora con winget?": "Install it now with winget?",
    "mpv no está instalado, y sin él no suena nada.": (
        "mpv is not installed, and nothing plays without it."
    ),
    "cava no está instalado: sin él, el visualizador mide el nivel "
    "en lugar de dibujar el espectro.": (
        "cava is not installed: without it the visualiser shows the level "
        "instead of drawing the spectrum."
    ),
    "Modo exclusivo": "Exclusive mode",
    "cada pista llega al DAC a su frecuencia; no suena nada más": (
        "each track reaches the DAC at its own rate; nothing else plays"
    ),
    "Dispositivo": "Device",
    "la salida de mpv; auto sigue la predeterminada de {system}": (
        "mpv's output; auto follows {system}'s default"
    ),
    "auto · {name}": "auto · {name}",
    "no conectado; suena por el predeterminado": (
        "not connected; playing through the default"
    ),
    "DISPOSITIVO DE SALIDA": "OUTPUT DEVICE",
    "auto: el predeterminado de {system} · {name}": "auto: {system}'s default · {name}",
    "auto: el predeterminado de {system}": "auto: {system}'s default",
    "dispositivo de salida: el predeterminado de {system}": (
        "output device: {system}'s default"
    ),
    "dispositivo de salida cambiado": "output device changed",
    "ese dispositivo no está conectado; suena por el predeterminado": (
        "that device is not connected; playing through the default"
    ),
    "silenciado en Windows": "muted in Windows",
    "  Silenciada en Windows: no se oye nada hasta quitarle el silencio": (
        "  Muted in Windows: nothing is heard until it is unmuted"
    ),
    "volvió el dispositivo de salida; suena por él": (
        "the output device is back; playing through it"
    ),
    "se desconectó el dispositivo de salida; suena por el predeterminado": (
        "the output device was unplugged; playing through the default"
    ),
    "modo exclusivo: sólo suena tidalamp, a la frecuencia de cada pista": (
        "exclusive mode: only tidalamp plays, at each track's own rate"
    ),
    "modo exclusivo desactivado: suena todo, remuestreado": (
        "exclusive mode off: everything plays, resampled"
    ),
    "mpv_path no apunta a un ejecutable: {path}": (
        "mpv_path does not point to an executable: {path}"
    ),
    "mpv no abrió el socket IPC a tiempo": "mpv did not open its IPC socket in time",
    "la ruta del socket de mpv es demasiado larga "
    "({length} bytes, máximo {limit}): {path}": (
        "mpv's socket path is too long ({length} bytes, at most {limit}): {path}"
    ),
    "no se pudo guardar en disco ({error})": "could not save to disk ({error})",
    "· sin guardar en disco": "· not saving to disk",
    "TIDAL no devolvió stream para «{name}»: {error}": (
        "TIDAL returned no stream for “{name}”: {error}"
    ),
    "«{name}» viene con DRM (Widevine); mpv no puede reproducirla. "
    "Prueba con TIDALAMP_QUALITY=HIGH.": (
        "“{name}” is DRM-protected (Widevine); mpv cannot play it. "
        "Try TIDALAMP_QUALITY=HIGH."
    ),
    "Manifest vacío para «{name}»": "Empty manifest for “{name}”",
    "eso no es una pista, un álbum, un artista ni una playlist": (
        "that is not a track, album, artist, or playlist"
    ),
    "no se pudo reclamar un nombre MPRIS ({reply})": (
        "could not claim an MPRIS name ({reply})"
    ),
    "acción desconocida: {action}": "unknown action: {action}",
    # --- command line
    "Cliente TIDAL para terminal con interfaz retro.": (
        "TIDAL client for the terminal with a retro interface."
    ),
    "Autoriza el cliente con tu cuenta TIDAL (device flow).": (
        "Authorize the client with your TIDAL account (device flow)."
    ),
    "Abre esta URL y autoriza el acceso:\n": ("Open this URL and authorize access:\n"),
    "Caduca en {minutes} minutos. Esperando…": ("Expires in {minutes} minutes. Waiting…"),
    "Sesión guardada para {user_id}.": "Session saved for {user_id}.",
    "Lanza la interfaz.": "Launch the interface.",
    "Muestra la versión y sale.": "Show the version and exit.",
    "Debug log en {path}": "Debug log at {path}",
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
    "# Visualizador: bars (barras), mirror (espejo), curve (línea) o fine (línea\n"
    "# en Braille, necesita una fuente que lo traiga). Los cuatro se dibujan al lado\n"
    "# de la carátula y llegan al borde derecho de la ventana.\n"
    'visualizer = "bars"\n\n'
    "# Registro en ~/.local/state/tidalamp/tidalamp.log.\n"
    "debug = false\n\n"
    "# Deja ver el reproductor a través de las ventanas superpuestas. Al activarla,\n"
    "# la carátula pasa a medios bloques: kitty y sixel pintan la imagen por encima\n"
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
        "# Cover shape: square, rounded (rounded corners) or round.\n"
        'cover_shape = "square"\n\n'
        "# Language: auto follows the system locale; es or en pin it.\n"
        'language = "auto"\n\n'
        "# Queue columns, comma separated. Available: track, version, artist,\n"
        "# album, year, quality, explicit, popularity, disc, isrc, duration.\n"
        'columns = "artist,album,year,duration"\n\n'
        "# Visual style: quattro, retro, nova or ascii, or a theme that brings its\n"
        "# palette: unidad-morada, pirata, cuaderno, neon-noir, runas, reggae,\n"
        "# comodin, gotico, death-metal or bosque.\n"
        'theme = "quattro"\n\n'
        "# Palette: auto follows Omarchy; also classic, tokyo-night, catppuccin,\n"
        "# nord, gruvbox, phosphor, black, any theme's own, or a TOML file in\n"
        "# ~/.config/tidalamp/palettes/.\n"
        'palette = "auto"\n\n'
        "# Arrangement: stacked puts the queue under the player; split puts it in a\n"
        "# column to the right (it needs a wide terminal, and falls back to stacked\n"
        "# on its own where it does not fit).\n"
        'arrangement = "stacked"\n\n'
        "# Queue backdrop: auto uses the theme's own picture; none removes it; or\n"
        "# a themed look's name, to use its picture with another theme or palette.\n"
        'backdrop = "auto"\n\n'
        "# Visualizer: bars, mirror, curve, or fine (a Braille line, which needs "
        "a\n"
        "# font that has it). All four are drawn beside the cover and run to the "
        "right\n"
        "# edge of the window.\n"
        'visualizer = "bars"\n\n'
        "# Log to ~/.local/state/tidalamp/tidalamp.log.\n"
        "debug = false\n\n"
        "# Let the player show through the windows that open over it. Turning it "
        "on\n"
        "# switches the cover to half blocks: kitty and sixel paint the image over "
        "the\n"
        "# text, and it would cover the window.\n"
        "transparency = false\n\n"
        "# Autoplay: when the queue ends, carry on with TIDAL's radio for the\n"
        "# last track.\n"
        "autoplay = false\n\n"
        "# Normalised volume with TIDAL's ReplayGain: off, track, or album. A\n"
        "# track is never raised past its peak.\n"
        'replaygain = "off"\n\n'
        "# Library view: list, or grid (tiles with the cover of each album,\n"
        "# playlist, artist or mix). A level of tracks is always a list.\n"
        'library_view = "list"\n\n'
        "# Keys. The action is on the left and the key on the right; separate multiple\n"
        "# keys with commas. Navigation keys (arrows, Page Up/Down, Enter, Esc) "
        "are fixed.\n"
        "[keys]\n"
        "%(keys)s\n"
    ),
}
