"""English for the Spanish source strings, part of `tidalamp.catalogue`.

The player: transport, status, quality, artwork, the settings window,
Discover, the free lofi row and its credits, and the newest release notes.
"""

from __future__ import annotations

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
    "{name} no disponible ({error})": "{name} unavailable ({error})",
    "controles multimedia": "media controls",
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
    "Ventana de configuración, con los rates hi-res de PipeWire.": (
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
    "Debug log": "Debug log",
    "Rates hi-res en PipeWire": "Hi-res rates in PipeWire",
    "Reiniciar PipeWire": "Restart PipeWire",
    "acción": "action",
    "activado": "on",
    "desactivado": "off",
    "configurado": "configured",
    "sin configurar": "not configured",
    "al reiniciar": "on restart",
    "se aplica a la siguiente pista": "applies to the next track",
    "estructura visual; Enter muestra una previsualización": (
        "visual structure; Enter opens a preview"
    ),
    "auto es classic: la paleta de Omarchy sólo existe en Linux": (
        "auto is classic: Omarchy's palette only exists on Linux"
    ),
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
    "CALIDAD": "QUALITY",
    "LOSSLESS  (con device flow llega como HIGH)": (
        "LOSSLESS  (through device flow it arrives as HIGH)"
    ),
    "RATES HI-RES EN PIPEWIRE": "HI-RES RATES IN PIPEWIRE",
    "configurar: PipeWire ofrece los rates del DAC": (
        "configure: PipeWire offers the DAC's rates"
    ),
    "quitar: PipeWire vuelve a un solo rate": (
        "remove: PipeWire goes back to a single rate"
    ),
    "REINICIAR PIPEWIRE": "RESTART PIPEWIRE",
    "reiniciar ahora; corta el audio un momento": (
        "restart now; the audio drops for a moment"
    ),
    "orden original": "original order",
    "fecha de agregado: recientes primero": "date added: newest first",
    "fecha de agregado: antiguas primero": "date added: oldest first",
    "fecha de creación: recientes primero": "date created: newest first",
    "fecha de creación: antiguas primero": "date created: oldest first",
    "lanzamiento: recientes primero": "release: newest first",
    "lanzamiento: antiguos primero": "release: oldest first",
    "nombre: A-Z": "name: A-Z",
    "nombre: Z-A": "name: Z-A",
    "artista: A-Z": "artist: A-Z",
    "artista: Z-A": "artist: Z-A",
    "álbum: A-Z": "album: A-Z",
    "álbum: Z-A": "album: Z-A",
    "ORDENAR": "SORT",
    "ordenar": "sort",
    "este nivel no se puede ordenar": "this level cannot be sorted",
    "orden: {order}": "order: {order}",
    "ordenar el nivel: fecha, nombre, artista o álbum": (
        "sort the level: date, name, artist or album"
    ),
    "QUITAR": "REMOVE",
    "favoritos": "favourites",
    "aquí no hay de dónde quitar": "there is nothing to remove from here",
    "quitar «{label}» de {where}": "remove «{label}» from {where}",
    "quitando…": "removing…",
    "«{label}» quitada de «{playlist}»": "«{label}» removed from «{playlist}»",
    "«{label}» ya no está en la playlist": "«{label}» is no longer in the playlist",
    "«{title}» es de otra cuenta: no se puede quitar nada": (
        "«{title}» belongs to another account: nothing can be removed"
    ),
    "quitar: {error}": "remove: {error}",
    "quitar de favoritos o de la playlist abierta": (
        "remove from favourites or from the open playlist"
    ),
    " ↑↓ desplazar   / buscar   ?/esc cerrar": " ↑↓ scroll   / search   ?/esc close",
    "Reproducción automática": "Autoplay",
    "al terminar la cola sigue con la radio de la última pista": (
        "when the queue ends, carry on with the last track's radio"
    ),
    "reproducción automática: radio de «{label}»": "autoplay: radio for «{label}»",
    "reproducción automática: no hay más para «{label}»": (
        "autoplay: nothing more for «{label}»"
    ),
    "reproducción automática: {error}": "autoplay: {error}",
    "reproducción automática activada": "autoplay on",
    "reproducción automática desactivada": "autoplay off",
    "Volumen normalizado": "Normalised volume",
    "ReplayGain de TIDAL: por pista o por disco; sin recortar": (
        "TIDAL's ReplayGain: per track or per album; never clipped"
    ),
    "volumen normalizado: {value}": "normalised volume: {value}",
    "mpv no contesta": "mpv is not answering",
    "mpv cerró la conexión": "mpv closed the connection",
    "mpv no contesta; esperando a que vuelva…": "mpv is not answering; waiting for it…",
    "mpv vuelve a contestar": "mpv is answering again",
    "mpv no responde; reiniciándolo…": "mpv is not responding; restarting it…",
    "Mis mixes": "My mixes",
    # --- discover
    "Descubrir": "Discover",
    "Inicio": "Home",
    "Para ti": "For you",
    "Explorar": "Explore",
    "Más": "More",
    "página": "page",
    "{count} elementos": "{count} items",
    "1 elemento": "1 item",
    # --- copyright-free lofi, from the Internet Archive
    "Lofi sin copyright": "Copyright-free lofi",
    "experimental · la selección de hoy": "experimental · today’s selection",
    # The credits window. CC BY and CC BY-SA require attribution, so this is
    # not decoration: it is what the licence asks of whoever reuses the work.
    "▓ CRÉDITOS ▓": "▓ CREDITS ▓",
    "créditos y licencia": "credits and licence",
    "Título": "Title",
    "Fuente": "Source",
    "Para citarla:": "To credit it:",
    "de {artist}": "by {artist}",
    " esc cerrar": " esc close",
    "no pide nada: está en el dominio público": (
        "asks for nothing: it is in the public domain"
    ),
    "cita al autor, y puedes usarla para lo que quieras": (
        "credit the author, and use it for whatever you like"
    ),
    "cita al autor, y comparte los cambios con esta misma licencia": (
        "credit the author, and share your changes under this same licence"
    ),
    "«{title}» no abrió; reintentando…": "“{title}” did not open; trying again…",
    "no se pudo abrir «{title}»; saltando": ("could not open “{title}”; skipping it"),
    "Todos los discos": "Every record",
    "el catálogo entero": "the whole catalogue",
    "ninguno de los discos de hoy trae audio que mpv pueda abrir": (
        "none of today’s records carries audio mpv can open"
    ),
    "dominio público": "public domain",
    "{who} contestó algo que no es JSON": (
        "{who} answered with something that is not JSON"
    ),
    "no se pudo hablar con {who}: {error}": "could not reach {who}: {error}",
    "{who} rechazó la petición: {error}": "{who} refused the request: {error}",
    "{who} contestó sin resultados varias veces seguidas": (
        "{who} answered with no results several times running"
    ),
    "{who} no devolvió nada con licencia permisiva": (
        "{who} returned nothing under a permissive licence"
    ),
    "no hay un client_id de Jamendo configurado": ("no Jamendo client_id is configured"),
    "no se encontró música con licencia libre": ("no freely licensed music was found"),
    "créditos": "credits",
    "créditos y licencia de la pista": "the track’s credits and licence",
    "créditos y licencia (solo «Lofi sin copyright»)": (
        "credits and licence (“Copyright-free lofi” only)"
    ),
    "los créditos son de «Lofi sin copyright»": ("credits are for “Copyright-free lofi”"),
    "el Internet Archive no devolvió resultados": (
        "the Internet Archive returned no results"
    ),
    "«Lofi sin copyright» no está en TIDAL: no hay dónde guardarlo": (
        "“Copyright-free lofi” is not on TIDAL: there is nowhere to save it"
    ),
    "«{name}» no trae audio que mpv pueda abrir": (
        "“{name}” carries no audio mpv can open"
    ),
    "«{name}» no trae audio que reproducir": "“{name}” carries no audio to play",
    "«{name}» no trae ficheros": "“{name}” carries no files",
    "«{name}» es todo con voz": "“{name}” is all vocals",
    "«{name}» no viene de TIDAL, que es de donde salen las letras": (
        "“{name}” does not come from TIDAL, which is where the lyrics come from"
    ),
    # --- 0.22.0, in the help's list of changes
    "Tema, paleta, fondo y disposición se previsualizan antes de aplicar.": (
        "Preview theme, palette, backdrop and arrangement before applying."
    ),
    "Aplicar guarda la apariencia; Cancelar conserva el reproductor.": (
        "Apply saves the look; Cancel keeps the current player."
    ),
    "La vista previa aparece desde 110 columnas.": (
        "The preview appears from 110 terminal columns."
    ),
    # --- 0.21.1, in the help's list of changes
    "Una pista subida con alt+flechas suena justo en su nuevo puesto.": (
        "A track moved up with alt+arrows plays in its new place."
    ),
    "El debug log empieza y termina al cambiarlo en o, sin reabrir.": (
        "The debug log starts and stops when switched in o, no restart."
    ),
    "El debug log cuenta el paso de una pista a la siguiente.": (
        "The debug log tells how one track hands over to the next."
    ),
    # --- 0.21.0, in the help's list of changes
    "Linux: elige el dispositivo de salida en o; auto dice cuál es.": (
        "Linux: choose the output device in o; auto says which it is."
    ),
    "Linux: suena por el DAC sin cambiar la salida del escritorio.": (
        "Linux: plays through the DAC without moving the desktop's output."
    ),
    "Linux: los rates, OUT y cava siguen al dispositivo elegido.": (
        "Linux: the rates, OUT and cava follow the chosen device."
    ),
    "Linux: sin el DAC suena por el predeterminado, y vuelve a él.": (
        "Linux: without the DAC it plays through the default, and goes back."
    ),
    # --- 0.20.0, in the help's list of changes
    "Una pista con varios artistas los nombra a todos.": (
        "A track with several artists names them all."
    ),
    "El artista que no cabe en la cola se desliza para verse entero.": (
        "An artist too long for the queue slides to show the rest."
    ),
    "En pantalla completa, el álbum ya no se sale con muchos artistas.": (
        "In full screen, many artists no longer push the album out."
    ),
    "Ratón: clic selecciona, doble clic reproduce, derecho abre el menú.": (
        "Mouse: click selects, double click plays, right click opens the menu."
    ),
    # --- 0.19.0, in the help's list of changes
    "Windows: las teclas multimedia llegan a tidalamp, no a mpv.": (
        "Windows: the media keys reach tidalamp, not mpv."
    ),
    "Windows: el espectro de cava funciona, y no miente en exclusivo.": (
        "Windows: cava's spectrum works, and does not lie in exclusive mode."
    ),
    "Windows: una salida silenciada lo dice en OUT y en o.": (
        "Windows: a muted output says so in OUT and in o."
    ),
    "Reiniciar PipeWire retoma la pista donde iba, y cava con ella.": (
        "Restart PipeWire picks the track up where it was, and cava with it."
    ),
    # --- 0.18.0, in the help's list of changes
    "Windows: el reproductor llega al borde de Windows Terminal.": (
        "Windows: the player reaches the edge of Windows Terminal."
    ),
    "Windows: el acceso directo también va al escritorio.": (
        "Windows: the shortcut goes on the desktop too."
    ),
    "Windows: elige el dispositivo de salida en o; auto dice cuál es.": (
        "Windows: choose the output device in o; auto says which it is."
    ),
    "Windows: sin el DAC suena por el predeterminado, y vuelve a él.": (
        "Windows: without the DAC it plays through the default, and goes back."
    ),
    # --- 0.17.0, in the help's list of changes
    "Windows: si falta mpv o cava, se instalan con winget al arrancar.": (
        "Windows: a missing mpv or cava is installed with winget on start."
    ),
    "Windows: al cerrar la terminal, mpv ya no se queda sonando.": (
        "Windows: closing the terminal no longer leaves mpv playing."
    ),
    "Windows: carátulas en el .exe, y en sixel enteras y sin parpadeo.": (
        "Windows: covers in the .exe, and sixel ones whole and steady."
    ),
    "Windows: la pausa ya no es un emoji azul.": (
        "Windows: pause is no longer a blue emoji."
    ),
    # --- 0.16.0, in the help's list of changes
    "Windows en vista previa: pipx install o el tidalamp.exe del Release.": (
        "Windows, in preview: pipx install, or tidalamp.exe from the Release."
    ),
    "En Windows: teclas multimedia, menú Inicio y modo exclusivo.": (
        "On Windows: media keys, the Start menu and exclusive mode."
    ),
    "mpv_path: la ruta de mpv, si el del PATH no es el que quieres.": (
        "mpv_path: the path to mpv, when the one on the PATH is not the one."
    ),
    "Al salir, lo que queda en segundo plano ya no falla ni la retiene.": (
        "On quitting, what is left in the background no longer fails or holds it."
    ),
    # --- 0.15.0, in the help's list of changes
    "«Lofi sin copyright» en la biblioteca: la selección lofi del día.": (
        "“Copyright-free lofi” in the library: the day’s lofi selection."
    ),
    "Experimental: es lo más cerca que llega un catálogo libre.": (
        "Experimental: it is the closest a freely licensed catalogue gets."
    ),
    "k: créditos y licencia, que CC BY y CC BY-SA exigen.": (
        "k: credits and licence, which CC BY and CC BY-SA require."
    ),
    "En pantalla completa, los nombres que no caben se deslizan.": (
        "In the full-screen view, names too long for the queue slide."
    ),
    "Una pista que no abre se reintenta y se dice, en vez de saltarse.": (
        "A track that will not open is retried and named, not dropped in silence."
    ),
    # --- 0.11.1, in the help's list of changes
    "Cerrar sesión": "Log out",
    "borra la sesión, y si quieres los datos; cierra tidalamp": (
        "deletes the session, and the data if you like; closes tidalamp"
    ),
    "¿CERRAR SESIÓN?": "LOG OUT?",
    "cerrar sesión": "log out",
    "[{mark}] borrar también los datos de tidalamp": (
        "[{mark}] delete tidalamp's data too"
    ),
    (
        "Se borra la sesión guardada y tidalamp se cierra.\n"
        "Para volver a entrar hará falta: tidalamp login"
    ): (
        "The saved session is deleted and tidalamp closes.\n"
        "To come back you will need: tidalamp login"
    ),
    (
        "Los datos son la configuración, la cola, el ecualizador,\n"
        "la caché y el acceso directo del menú."
    ): (
        "The data is the settings, the queue, the equaliser,\n"
        "the cache and the menu shortcut."
    ),
    (
        "Los datos son la configuración, la cola, el ecualizador,\n"
        "la caché y los accesos directos del menú Inicio y del escritorio."
    ): (
        "The data is the settings, the queue, the equaliser,\n"
        "the cache and the shortcuts in the Start menu and on the desktop."
    ),
    " ↑↓ elegir  ↵ marcar o aplicar  esc cerrar": (
        " ↑↓ choose  ↵ tick or apply  esc close"
    ),
    "Se borró la sesión.": "The session was deleted.",
    "Se borraron la sesión y los datos de tidalamp.": (
        "The session and tidalamp's data were deleted."
    ),
    "Para volver a usar tidalamp, inicia sesión con:": (
        "To use tidalamp again, log in with:"
    ),
    "  No se pudo cerrar la sesión:\n  {error}": "  Could not log out:\n  {error}",
    "SESIÓN CERRADA": "LOGGED OUT",
    "aceptar": "accept",
    " ↵ aceptar y cerrar tidalamp": " ↵ accept and close tidalamp",
    "¿AÑADIR TIDALAMP AL MENÚ DE APLICACIONES?": "ADD TIDALAMP TO THE APPLICATION MENU?",
    "sí, crear el acceso directo": "yes, create the shortcut",
    "Acceso directo en el menú": "Menu shortcut",
    "añade tidalamp al menú de aplicaciones": "adds tidalamp to the application menu",
    "creado": "created",
    "sin crear": "not created",
    "en {path}": "at {path}",
    "  El acceso directo ya existe:\n  {path}": (
        "  The shortcut already exists:\n  {path}"
    ),
    "no, y no volver a preguntar": "no, and do not ask again",
    " ↑↓ elegir  ↵ aplicar  esc preguntar la próxima vez": (
        " ↑↓ choose  ↵ apply  esc ask next time"
    ),
    "tidalamp ya está en el menú de aplicaciones": (
        "tidalamp is now in the application menu"
    ),
    "Accesos directos": "Shortcuts",
    "añade tidalamp al menú Inicio y al escritorio": (
        "adds tidalamp to the Start menu and the desktop"
    ),
    "¿AÑADIR TIDALAMP AL MENÚ INICIO Y AL ESCRITORIO?": (
        "ADD TIDALAMP TO THE START MENU AND THE DESKTOP?"
    ),
    "tidalamp ya está en el menú Inicio y en el escritorio": (
        "tidalamp is now in the Start menu and on the desktop"
    ),
    "no se pudo crear el acceso directo; mira el log": (
        "could not create the shortcut; see the log"
    ),
    "sin acceso directo; no se volverá a preguntar": (
        "no shortcut; you will not be asked again"
    ),
    "En pantalla completa, y pone la letra al lado de la carátula.": (
        "In full screen, y puts the lyrics beside the cover."
    ),
    "Con la cola abierta: carátula, letra y cola, de izquierda a derecha.": (
        "With the queue open: cover, lyrics and queue, left to right."
    ),
    "Iconos del transporte más gruesos y con aire entre signo y marca.": (
        "Heavier transport icons, with air between sign and mark."
    ),
    "Cerrar sesión desde o; si quieres, borra también los datos.": (
        "Log out from o; optionally, delete the data too."
    ),
    "Los versos largos de la letra (y) se parten bajo su texto.": (
        "Long lyric lines (y) wrap under their own text."
    ),
    "Términos técnicos en inglés: rates, graph, resampling.": (
        "Technical terms stay in English: rates, graph, resampling."
    ),
    "Al primer inicio, ofrece añadirse al menú de aplicaciones.": (
        "On the first start, offers to add itself to the application menu."
    ),
    "Acceso directo en el menú, también desde o.": "Menu shortcut, also from o.",
    "El pie de la ventana o se desliza si no cabe.": (
        "The foot of the o window glides when it does not fit."
    ),
    "El DAC sigue el rate de cada pista, no sólo de la primera.": (
        "The DAC follows every track's rate, not just the first's."
    ),
    "El título de la letra (y) cabe entero, o se desliza.": (
        "The lyrics title (y) fits whole, or glides."
    ),
    # --- 0.11.0, in the help's list of changes
    "Descubrir: la home de TIDAL, Para ti y Explorar.": (
        "Discover: TIDAL's home, For you and Explore."
    ),
    "v en la biblioteca: una cuadrícula de carátulas.": (
        "v in the library: a grid of covers."
    ),
    "Tus playlists: renombrar, describir, borrar, mover pistas.": (
        "Your playlists: rename, describe, delete, move tracks."
    ),
    "La página siguiente llega sola; el filtro busca en todo.": (
        "The next page comes on its own; the filter searches it all."
    ),
}
