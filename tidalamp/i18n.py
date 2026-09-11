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
    "volumen: {value}": "volume: {value}",
    "centro": "centre",
    "izquierda": "left",
    "derecha": "right",
    # --- quality
    "{status} · TIDAL entregó {got}, no {asked}": (
        "{status} · TIDAL delivered {got}, not {asked}"
    ),
    # --- artwork
    "sin carátula: {error}": "no cover: {error}",
    'sin carátula: falta Pillow (pip install "tidalamp[art]")': (
        'no cover: Pillow is missing (pip install "tidalamp[art]")'
    ),
    # --- config screen
    "Ventana de configuración, con los ritmos hi-res de PipeWire.": (
        "A settings window, including PipeWire's hi-res rates."
    ),
    "configuración": "settings",
    "▓ CONFIGURACIÓN ▓": "▓ SETTINGS ▓",
    " ↑↓ elegir   ↵ cambiar   o/esc cerrar": " ↑↓ choose   ↵ change   o/esc close",
    "config": "config",
    "cambiar": "change",
    "Calidad": "Quality",
    "Carátula": "Cover art",
    "Idioma": "Language",
    "Visualizador": "Visualizer",
    "forma del analizador; fine necesita una fuente con Braille": (
        "the analyser's shape; fine needs a font with Braille"
    ),
    "Columnas de la cola": "Queue columns",
    "qué metadatos se ven en la lista": "which metadata the list shows",
    "{count} de {total}": "{count} of {total}",
    "▓ COLUMNAS DE LA COLA ▓": "▓ QUEUE COLUMNS ▓",
    " ↑↓ elegir   ↵ marcar   0 reset   o/esc cerrar": (
        " ↑↓ choose   ↵ toggle   0 reset   o/esc close"
    ),
    "  {count} de {total} · nº de cola y título van siempre": (
        "  {count} of {total} · queue no. and title are always shown"
    ),
    "marcar": "toggle",
    "por defecto": "defaults",
    "Nº dentro del álbum": "No. within the album",
    "Artista": "Artist",
    "Álbum": "Album",
    "Año": "Year",
    "Calidad del stream": "Stream quality",
    "Explícito": "Explicit",
    "Popularidad": "Popularity",
    "Disco": "Disc",
    "ISRC": "ISRC",
    "Duración": "Duration",
    "Tema": "Theme",
    "Paleta": "Palette",
    "Registro de depuración": "Debug log",
    "Ritmos hi-res en PipeWire": "Hi-res rates in PipeWire",
    "Reiniciar PipeWire": "Restart PipeWire",
    "acción": "action",
    "activado": "on",
    "desactivado": "off",
    "configurado": "configured",
    "sin configurar": "not configured",
    "al reiniciar": "on restart",
    "se aplica a la siguiente pista": "applies to the next track",
    "estructura visual; se aplica al instante": "visual structure; applies instantly",
    "auto sigue Omarchy; las demás funcionan en cualquier Linux": (
        "auto follows Omarchy; the others work on any Linux"
    ),
    "tema: {value}": "theme: {value}",
    "visualizador: {value}": "visualizer: {value}",
    "paleta: {value}": "palette: {value}",
    "disposición: {value}": "arrangement: {value}",
    "split necesita al menos {width}×{height}; la cola sigue debajo": (
        "split needs at least {width}×{height}; the queue stays below"
    ),
    "Disposición": "Arrangement",
    "Fondo de la cola": "Queue backdrop",
    "Forma de la carátula": "Cover shape",
    "cuadrada o redonda, con cualquier tema": "square or round, under any theme",
    "forma de la carátula: {value}": "cover shape: {value}",
    "auto usa el del tema; se puede mezclar con cualquier tema y paleta": (
        "auto uses the theme's own; mix it with any theme and palette"
    ),
    "fondo de la cola: {value}": "queue backdrop: {value}",
    "split pone la cola a la derecha si el terminal es ancho": (
        "split puts the queue on the right on a wide terminal"
    ),
    "columnas: {count}": "columns: {count}",
    "lo pisa {variable} del entorno": "{variable} in the environment overrides it",
    "  Salida: desconocida": "  Output: unknown",
    "  Salida: {name} · {rate} Hz {format}": "  Output: {name} · {rate} Hz {format}",
    "  Bluetooth: no hay hi-res real por esta salida": (
        "  Bluetooth: no real hi-res goes through this output"
    ),
    "  El grafo remuestrea todo a {rate} Hz": (
        "  The graph resamples everything to {rate} Hz"
    ),
    "no se pudo consultar PipeWire": "could not ask PipeWire",
    "la salida es Bluetooth: no hay hi-res real por ahí": (
        "the output is Bluetooth: no real hi-res goes through it"
    ),
    "el grafo está fijo en {rate} Hz y remuestrea todo": (
        "the graph is stuck at {rate} Hz and resamples everything"
    ),
    "el DAC llega a {rate} Hz": "the DAC reaches {rate} Hz",
    "el grafo puede cambiar de ritmo": "the graph can change rate",
    "corta el audio un momento; la reproducción se detiene antes": (
        "cuts audio for a moment; playback is stopped first"
    ),
    "ritmos hi-res escritos; reinicia PipeWire para aplicarlo": (
        "hi-res rates written; restart PipeWire to apply them"
    ),
    "ritmos hi-res quitados; reinicia PipeWire para aplicarlo": (
        "hi-res rates removed; restart PipeWire to apply it"
    ),
    "reiniciando PipeWire…": "restarting PipeWire…",
    "PipeWire reiniciado": "PipeWire restarted",
    "reinicio de PipeWire desactivado por el entorno": (
        "PipeWire restart disabled by the environment"
    ),
    "no se pudo reiniciar PipeWire; hazlo tú: systemctl --user restart {services}": (
        "could not restart PipeWire; do it yourself: systemctl --user restart {services}"
    ),
    "calidad: {value}": "quality: {value}",
    "registro: {value}": "log: {value}",
    "el idioma cambia al reiniciar tidalamp": (
        "the language changes when tidalamp restarts"
    ),
    # --- track action menu
    "reproducir o pausar (▶ / ‖)": "play or pause (▶ / ‖)",
    "Menú de pista: ahora, a continuación, radio y favoritos.": (
        "Track menu: play now, play next, radio and favourites."
    ),
    "abrir el nivel, o el menú de la pista": "open the level, or the track menu",
    "elegir con el cursor": "choose with the cursor",
    "reproducir ahora": "play now",
    "reproducir a continuación": "play next",
    "reproducir la radio de la pista": "play the track radio",
    "añadir a favoritos": "add to favourites",
    "elegir": "choose",
    " ↑↓ elegir   ↵ aceptar   esc cancelar": " ↑↓ choose   ↵ accept   esc cancel",
    "«{label}» sonará a continuación": "“{label}” will play next",
    "buscando la radio de «{label}»…": "looking for the radio of “{label}”…",
    "radio de «{label}»: {count} pistas": "radio of “{label}”: {count} tracks",
    "TIDAL no tiene radio para «{label}»": "TIDAL has no radio for “{label}”",
    # --- help and about
    "Reproducción": "Playback",
    "Volumen y sonido": "Volume and sound",
    "Cola": "Queue",
    "Ventanas": "Windows",
    "Favoritos": "Favourites",
    "Dentro de la búsqueda y la biblioteca": "Inside search and the library",
    "detener": "stop",
    "pista anterior": "previous track",
    "pista siguiente": "next track",
    "retroceder 5 s": "back 5 s",
    "avanzar 5 s": "forward 5 s",
    "tiempo transcurrido o restante": "elapsed or remaining time",
    "subir volumen": "volume up",
    "bajar volumen": "volume down",
    "balance a la izquierda": "balance left",
    "balance a la derecha": "balance right",
    "centrar el balance": "centre the balance",
    "ecualizador de 10 bandas": "10-band equalizer",
    "mover el cursor": "move the cursor",
    "una página": "one page",
    "reproducir la pista del cursor": "play the track under the cursor",
    "quitar la pista del cursor": "remove the track under the cursor",
    "subir la pista en la cola": "move the track up the queue",
    "bajar la pista en la cola": "move the track down the queue",
    "vaciar la cola": "clear the queue",
    "aleatorio (⇄)": "shuffle (⇄)",
    "repetición ↻: off, toda la cola, una pista": (
        "repeat ↻: off, the whole queue, one track"
    ),
    "buscar en TIDAL": "search TIDAL",
    "tu biblioteca": "your library",
    "letra de la pista actual": "lyrics for the current track",
    "esta ayuda": "this help",
    "ayuda": "help",
    "añadir a favoritos de TIDAL": "add to your TIDAL favourites",
    "quitar de favoritos": "remove from favourites",
    "volver al nivel anterior": "back to the previous level",
    "añadir a la cola": "add to the queue",
    "añadir el nivel entero": "add the whole level",
    "recargar, ignorando la caché": "reload, ignoring the cache",
    "filtrar el nivel: escribe y la lista se estrecha": (
        "filter the level: type and the list narrows"
    ),
    "añadir o quitar de favoritos": "add to or remove from favourites",
    "AYUDA": "HELP",
    "ACERCA DE": "ABOUT",
    "acerca de": "about",
    " ↑↓ desplazar   / buscar   → acerca de   ?/h/esc cerrar": (
        " ↑↓ scroll   / search   → about   ?/h/esc close"
    ),
    " ↑↓ desplazar   / buscar   ← ayuda   ?/h/esc cerrar": (
        " ↑↓ scroll   / search   ← help   ?/h/esc close"
    ),
    " escribe para filtrar   ↵ listo   esc quitar la búsqueda": (
        " type to filter   ↵ done   esc clear the search"
    ),
    "buscar en la ayuda…": "search the help…",
    "Acerca de": "About",
    # --- notas de versión 0.6.0
    "Nueve temas temáticos, cada uno con su paleta y su imagen.": (
        "Nine themed looks, each with its palette and its picture."
    ),
    "La imagen del tema, de fondo de la cola; se puede mezclar.": (
        "The theme's picture behind the queue, free to mix."
    ),
    "split: la cola a la derecha y la letra sobre la carátula.": (
        "split: the queue on the right, lyrics above the cover."
    ),
    "/ busca en la ayuda; los textos largos se deslizan.": (
        "/ searches the help; long lines glide."
    ),
    # --- notas de versión 0.5.1
    "OUT ya no muestra la frecuencia de la pista anterior.": (
        "OUT no longer shows the previous track's sample rate."
    ),
    "Las pistas hi-res se reproducen con buffer de verdad.": (
        "Hi-res tracks now stream with a real buffer."
    ),
    # --- notas de versión 0.5.0
    "u deshace el último vaciado de la cola.": "u undoes the last queue clear.",
    "Ocho presets de ecualizador, con p y P.": "Eight equalizer presets, on p and P.",
    "Añadir una pista a una playlist que ya tienes.": (
        "Add a track to a playlist you already have."
    ),
    "La carátula en blocks, al doble de resolución.": (
        "Cover art in blocks, at twice the resolution."
    ),
    "space reproduce; m abre el menú sobre la cola.": (
        "space plays; m opens the menu on the queue."
    ),
    # --- notas de versión 0.4.0
    "g vuelve a la pista que suena; p guarda la cola en TIDAL.": (
        "g goes back to the playing track; p saves the queue to TIDAL."
    ),
    "La barra de posición y los sliders responden al clic.": (
        "The seek bar and the sliders answer to a click."
    ),
    "La columna «Año» ya no sale vacía.": "The Year column is no longer empty.",
    "Artista, álbum y año bajo el reloj; el título arriba, solo.": (
        "Artist, album and year under the clock; the title alone above."
    ),
    "Las cuatro disposiciones cuadran sus bordes y sus anchos.": (
        "The four layouts agree on their edges and their widths."
    ),
    # --- notas de versión 0.3.0
    "El analizador llega al borde y tiene cuatro formas.": (
        "The analyzer reaches the edge and comes in four shapes."
    ),
    "Buscador en la cola con ctrl+f, sin renumerar las pistas.": (
        "Search the queue with ctrl+f; the track numbers stay true."
    ),
    "La ayuda en dos pestañas: atajos y acerca de.": (
        "The help screen in two tabs: keys, and about."
    ),
    "tidalamp --version imprime la versión en el terminal.": (
        "tidalamp --version prints the version in the terminal."
    ),
    "El analizador cuesta mucho menos en pantallas 4K.": (
        "The analyzer costs far less on 4K displays."
    ),
    "Filtro en el navegador con /: estrecha el nivel donde estés.": (
        "Filter in the browser with /: it narrows the level you are on."
    ),
    "Las ventanas toman la pantalla; opcionalmente translúcidas.": (
        "Windows take the screen; translucent if you want them to be."
    ),
    "Con transparencia, la carátula va en medios bloques.": (
        "With transparency on, the cover is drawn with half blocks."
    ),
    "Configuración agrupada en Audio, Apariencia y General.": (
        "Settings grouped into Audio, Appearance and General."
    ),
    "Paleta black: fondo negro con acentos grises y blancos.": (
        "black palette: a black ground with grey and white accents."
    ),
    "Cliente de TIDAL para terminal, con una interfaz retro.": (
        "A TIDAL client for the terminal, with a retro player interface."
    ),
    "Reproduce con mpv; el catálogo y los streams vienen de tidalapi.": (
        "Playback through mpv; catalogue and streams come from tidalapi."
    ),
    "Versión": "Version",
    "Autor": "Author",
    "Repositorio": "Repository",
    "Licencia": "Licence",
    "Software libre, sin garantía de ningún tipo.": (
        "Free software, with no warranty of any kind."
    ),
    "Sin relación con TIDAL, Aspiro ni los dueños de la marca Winamp.": (
        "Not affiliated with TIDAL, Aspiro, or the Winamp trademark holders."
    ),
    "Cambios por versión": "Changes by version",
    "Si falta mpv o cava, el mensaje da la orden de tu distribución.": (
        "If mpv or cava is missing, the message gives your distribution's command."
    ),
    "README reescrito: requisitos por distribución y menos rodeos.": (
        "Rewritten README: per-distribution requirements and less detour."
    ),
    "Interfaz retro: reloj, marquesina, analizador y playlist.": (
        "Retro interface: clock, marquee, analyser and playlist."
    ),
    "Reproducción con mpv por IPC, hasta FLAC 24 bit/96 kHz.": (
        "Playback through mpv over IPC, up to 24-bit/96 kHz FLAC."
    ),
    "Búsqueda, biblioteca paginada, favoritos y cola persistente.": (
        "Search, paginated library, favourites and a queue that persists."
    ),
    "Letras sincronizadas, ecualizador de 10 bandas y balance.": (
        "Synchronized lyrics, a 10-band equalizer and balance."
    ),
    "Carátula en kitty, sixel o medios bloques, y espectro con cava.": (
        "Cover art in kitty, sixel or half blocks, and a cava spectrum."
    ),
    "MPRIS2 completo, incluida la lista de pistas.": "Full MPRIS2, track list included.",
    "Arranque directo con tidalamp; interfaz bilingüe según el locale.": (
        "Direct launch with tidalamp; bilingual interface chosen by locale."
    ),
    # --- favourites
    "«{label}» añadido a favoritos": "“{label}” added to favourites",
    "«{label}» quitado de favoritos": "“{label}” removed from favourites",
    "favoritos: {error}": "favourites: {error}",
    "añadiendo a favoritos…": "adding to favourites…",
    "quitando de favoritos…": "removing from favourites…",
    # --- browser
    "cargando…": "loading…",
    "vacío": "empty",
    "Transparencia": "Transparency",
    "Audio": "Audio",
    "Apariencia": "Appearance",
    "General": "General",
    "deja ver el reproductor detrás de las ventanas": (
        "lets the player show through the windows"
    ),
    "transparencia activada": "transparency on",
    "transparencia desactivada": "transparency off",
    "  La carátula pasa a blocks: kitty y sixel pintan la imagen sobre el\n"
    "  texto y taparían la ventana.\n"
    "  {url}": (
        "  The cover switches to blocks: kitty and sixel paint the image over\n"
        "  the text, and it would cover the window.\n"
        "  {url}"
    ),
    "blocks se dibuja con texto y sobrevive a las ventanas": (
        "blocks is drawn with text and survives the windows"
    ),
    "con transparencia sólo caben las que dibuja el texto": (
        "with transparency, only the ones drawn with text fit"
    ),
    "carátula: {value}": "cover: {value}",
    "filtrar este nivel…": "filter this level…",
    "nada coincide con «{query}»": "nothing matches “{query}”",
    "{shown} de {total}": "{shown} of {total}",
    "{total} en este nivel": "{total} in this level",
    "buscar en la cola…": "search the queue…",
    "buscar en la cola": "search the queue",
    "menú de la pista": "track menu",
    # --- añadir a una playlist existente
    "añadir a una playlist": "add to a playlist",
    "▓ AÑADIR A UNA PLAYLIST ▓": "▓ ADD TO A PLAYLIST ▓",
    " ↑↓ elegir   ↵ añadir   esc cancelar": " ↑↓ choose   ↵ add   esc cancel",
    "no tienes playlists": "you have no playlists",
    "añadiendo a la playlist…": "adding to the playlist…",
    "{count} pistas añadidas a la playlist": ("{count} tracks added to the playlist"),
    "«{title}»: entraron {added} de {total}": ("“{title}”: {added} of {total} made it"),
    # --- ecualizador: presets
    " ←→ banda  ↑↓ ±1 dB  0 plano  p/P preset  ,. balance  esc": (
        " ←→ band  ↑↓ ±1 dB  0 flat  p/P preset  ,. balance  esc"
    ),
    "preset siguiente": "next preset",
    "preset anterior": "previous preset",
    "  preset: {name}": "  preset: {name}",
    "rock": "rock",
    "pop": "pop",
    "jazz": "jazz",
    "clásica": "classical",
    "voz": "vocal",
    "graves": "bass",
    "agudos": "treble",
    "manual": "manual",
    "deshacer el vaciado": "undo the clear",
    "no hay ningún vaciado que deshacer": "there is no clear to undo",
    "deshacer el último vaciado de la cola": "undo the last queue clear",
    "menú de la pista del cursor": "menu for the track under the cursor",
    "Menú de la pista (↵ en la biblioteca, m en la cola)": (
        "Track menu (↵ in the library, m in the queue)"
    ),
    "buscar en la cola: escribe y se estrecha": "search the queue: type and it narrows",
    "volver a la pista que suena": "go to the playing track",
    "guardar la cola como playlist": "save the queue as a playlist",
    "{total} en la cola": "{total} in the queue",
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
    "GUARDAR COLA COMO PLAYLIST": "SAVE QUEUE AS PLAYLIST",
    "nombre de la playlist…": "playlist name…",
    "la cola está vacía; no hay nada que guardar": (
        "the queue is empty; there is nothing to save"
    ),
    "guardando la cola como «{title}»…": "saving the queue as “{title}”…",
    "playlist «{title}» creada con {count} pistas": (
        "playlist “{title}” created with {count} tracks"
    ),
    "playlist «{title}» creada con {added} de {total} pistas: {error}": (
        "playlist “{title}” created with {added} of {total} tracks: {error}"
    ),
    "no se pudo guardar la cola: {error}": "could not save the queue: {error}",
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
    "filtrar": "filter",
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
    "↵ reproducir · ↑↓ navegar": "↵ play · ↑↓ navigate",
    "↵ reproducir · ↑↓ navegar · d quitar · alt+↑↓ mover": (
        "↵ play · ↑↓ navigate · d remove · alt+↑↓ move"
    ),
    "LISTA DE REPRODUCCIÓN": "PLAYLIST",
    "cola": "queue",
    "COLA": "QUEUE",
    "BITÁCORA": "LOG",
    "páginas": "pages",
    "CRÓNICA": "CHRONICLE",
    "baraja": "deck",
    # --- guiños de los temas temáticos
    "sincronía al 400 %": "synchronisation at 400 %",
    "rumbo a la gran ruta": "bound for the grand line",
    "trae manzanas": "bring apples",
    "despierta: la ciudad no duerme": "wake up: the city never sleeps",
    "un anillo para oírlas a todas": "one ring to hear them all",
    "un solo amor, un solo corazón": "one love, one heart",
    "¿por qué tan serio?": "why so serious?",
    "nunca más, dijo el cuervo": "quoth the raven, nevermore",
    "hasta el once": "all the way up to eleven",
    "semillero": "seedbed",
    "no hay planeta B": "there is no planet B",
    " ↑↓ desplazar   y/esc cerrar": " ↑↓ scroll   y/esc close",
    "? ayuda · / buscar · l lib · y letra · e eq · o config · f/F favorito · q salir": (
        "? help · / search · l lib · y lyrics · e eq · o config · f/F favourite · q quit"
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
    "{package} no está instalado ({command})": ("{package} is not installed ({command})"),
    "{package} no está instalado": "{package} is not installed",
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
    "no se pudo reclamar un nombre MPRIS ({reply})": (
        "could not claim an MPRIS name ({reply})"
    ),
    "acción desconocida: {action}": "unknown action: {action}",
    # --- command line
    "Cliente TIDAL para terminal con interfaz retro.": (
        "TIDAL client for the terminal with a retro interface."
    ),
    "Autoriza el cliente con tu cuenta TIDAL (flujo de dispositivo).": (
        "Authorize the client with your TIDAL account (device flow)."
    ),
    "Abre esta URL y autoriza el acceso:\n": ("Open this URL and authorize access:\n"),
    "Caduca en {minutes} minutos. Esperando…": ("Expires in {minutes} minutes. Waiting…"),
    "Sesión guardada para {user_id}.": "Session saved for {user_id}.",
    "Lanza la interfaz.": "Launch the interface.",
    "Muestra la versión y sale.": "Show the version and exit.",
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
    "# Forma de la carátula: square (cuadrada) o round (redonda).\n"
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
    "# nord, gruvbox, black, la de cualquier tema o un TOML en\n"
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
        "# Cover shape: square or round.\n"
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
        "# nord, gruvbox, black, any theme's own, or a TOML file in\n"
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
        "# Forma de la carátula: square (cuadrada) o round (redonda).\n"
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
        "# nord, gruvbox, black, la de cualquier tema o un TOML en\n"
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
        "# Teclas. La izquierda es la acción, la derecha la tecla; varias se "
        "separan con\n"
        "# comas. Las de navegación (flechas, RePág/AvPág, Enter, Esc) no se cambian.\n"
        "[keys]\n"
        "%(keys)s\n"
    )
