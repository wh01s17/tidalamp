"""English for the Spanish source strings, part of `tidalamp.catalogue`.

The windows over the player: library pages and grid, playlists, the
track menu, help and its older release notes, the browser, equaliser,
lyrics, key descriptions and window furniture.
"""

from __future__ import annotations

ENGLISH: dict[str, str] = {
    # --- pages as the cursor nears the end
    "cargando el resto del nivel…": "loading the rest of the level…",
    "cargando el resto del nivel… {count}": "loading the rest of the level… {count}",
    "no se pudo cargar el resto: {error}": "could not load the rest: {error}",
    "no se pudo cargar más: {error}": "could not load more: {error}",
    # --- the library's grid
    "Vista de la biblioteca": "Library view",
    "grid muestra la carátula de cada álbum, playlist, artista o mix": (
        "grid shows the cover of each album, playlist, artist or mix"
    ),
    "vista de la biblioteca: {value}": "library view: {value}",
    "vista": "view",
    "cuadrícula": "grid",
    "listado": "list",
    "vista: {view}": "view: {view}",
    "vista: {view}; este nivel sigue en listado": (
        "view: {view}; this level stays a list"
    ),
    "ver el nivel como listado o como cuadrícula de carátulas": (
        "show the level as a list or as a grid of covers"
    ),
    "en la cuadrícula: moverse entre las carátulas": (
        "in the grid: move between the covers"
    ),
    "volver al nivel anterior; ← también, en el listado": (
        "back to the previous level; ← too, in the list"
    ),
    # --- your playlists
    "renombrar": "rename",
    "cambiar la descripción": "change the description",
    "borrar la playlist": "delete the playlist",
    "renombrar (solo tus playlists)": "rename (your playlists only)",
    "cambiar la descripción (solo tus playlists)": (
        "change the description (your playlists only)"
    ),
    "borrar la playlist (solo tus playlists)": (
        "delete the playlist (your playlists only)"
    ),
    "RENOMBRAR PLAYLIST": "RENAME PLAYLIST",
    "DESCRIPCIÓN DE LA PLAYLIST": "PLAYLIST DESCRIPTION",
    "descripción…": "description…",
    "guardando…": "saving…",
    "«{old}» ahora se llama «{new}»": "“{old}” is now called “{new}”",
    "descripción de «{title}» cambiada": "description of “{title}” changed",
    "«{title}» es de otra cuenta: no se puede cambiar": (
        "“{title}” belongs to another account: it cannot be changed"
    ),
    "playlist: {error}": "playlist: {error}",
    "TIDAL no aceptó el cambio": "TIDAL did not accept the change",
    "BORRAR PLAYLIST": "DELETE PLAYLIST",
    "borrar «{title}» de TIDAL": "delete “{title}” from TIDAL",
    "borrando…": "deleting…",
    "«{title}» borrada": "“{title}” deleted",
    "subir la pista": "move the track up",
    "bajar la pista": "move the track down",
    "mover la pista dentro de tu playlist": "move the track within your playlist",
    "solo se reordenan las pistas de tus playlists": (
        "only the tracks of your own playlists can be reordered"
    ),
    "para mover una pista, la playlist tiene que estar en su orden y sin filtro": (
        "to move a track, the playlist has to be in its own order and unfiltered"
    ),
    "carga la página siguiente con «más…» antes de bajarla": (
        "load the next page with “more…” before moving it down"
    ),
    "moviendo…": "moving…",
    "«{label}» movida": "“{label}” moved",
    "TIDAL no dejó «{label}» donde se pidió; R recarga la playlist": (
        "TIDAL did not leave “{label}” where it was sent; R reloads the playlist"
    ),
    "mover: {error}": "move: {error}",
    "cola restaurada ({count} pistas); «{title}» sigue en {time}": (
        "queue restored ({count} tracks); “{title}” resumes at {time}"
    ),
    "volver": "back",
    "pantalla completa": "full screen",
    "la pantalla completa necesita al menos {width}×{height}": (
        "full screen needs at least {width}×{height}"
    ),
    "pantalla completa: la carátula en grande; w o esc vuelve": (
        "full screen: the cover large; w or esc comes back"
    ),
    "abre la cola con tab para eso": "open the queue with tab for that",
    "la búsqueda de la cola está en el reproductor": (
        "the queue's search is in the player"
    ),
    "Pantalla completa": "Full screen",
    "volver al reproductor": "back to the player",
    "mostrar u ocultar la cola, a la derecha de la letra": (
        "show or hide the queue, to the right of the lyrics"
    ),
    "mostrar u ocultar la letra, al lado de la carátula": (
        "show or hide the lyrics, beside the cover"
    ),
    "en la cola: moverse y reproducir": "in the queue: move and play",
    "ir a la pista que suena; abre la cola": "go to the playing track; opens the queue",
    "mover la pista en la cola": "move the track in the queue",
    "anterior, reproducir o pausar, detener, siguiente": (
        "previous, play or pause, stop, next"
    ),
    "¿SALIR DE TIDALAMP?": "QUIT TIDALAMP?",
    "salir sin preguntar": "quit without asking",
    "salir; pregunta antes": "quit; asks first",
    "velocidad": "speed",
    "velocidad: {value}": "speed: {value}",
    "velocidad de reproducción, de 0.25× a 2×": "playback speed, from 0.25× to 2×",
    "▓ VELOCIDAD ▓": "▓ SPEED ▓",
    " ↑↓ elegir  ↵ aplicar  esc cerrar": " ↑↓ choose  ↵ apply  esc close",
    "normal": "normal",
    "unidad-morada": "purple-unit",
    "pirata": "pirate",
    "cuaderno": "notebook",
    "runas": "runes",
    "comodin": "wild-card",
    "gotico": "gothic",
    "bosque": "forest",
    "Forma de la carátula": "Cover shape",
    "cuadrada, redondeada o redonda, con cualquier tema": (
        "square, rounded or round, under any theme"
    ),
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
    "  El graph hace resampling de todo a {rate} Hz": (
        "  The graph resamples everything to {rate} Hz"
    ),
    "  PipeWire hace resampling de {stream} Hz a {rate} Hz": (
        "  PipeWire resamples {stream} Hz to {rate} Hz"
    ),
    "resampling desde {rate} kHz": "resampled from {rate} kHz",
    "no se pudo consultar PipeWire": "could not ask PipeWire",
    "la salida es Bluetooth: no hay hi-res real por ahí": (
        "the output is Bluetooth: no real hi-res goes through it"
    ),
    "el graph está fijo en {rate} Hz y hace resampling de todo": (
        "the graph is stuck at {rate} Hz and resamples everything"
    ),
    "el DAC llega a {rate} Hz": "the DAC reaches {rate} Hz",
    "el graph puede cambiar de rate": "the graph can change rate",
    "corta el audio un momento; la pista sigue donde iba": (
        "cuts audio for a moment; the track goes on where it was"
    ),
    "rates hi-res escritos; reinicia PipeWire para aplicarlo": (
        "hi-res rates written; restart PipeWire to apply them"
    ),
    "rates hi-res quitados; reinicia PipeWire para aplicarlo": (
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
    "debug log: {value}": "debug log: {value}",
    "el idioma cambia al reiniciar tidalamp": (
        "the language changes when tidalamp restarts"
    ),
    # --- track action menu
    "reproducir o pausar (▶ / {pause})": "play or pause (▶ / {pause})",
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
    "{count} pistas sonarán a continuación": "{count} tracks will play next",
    "reproducir todo ahora": "play all now",
    "Las peticiones a TIDAL ya no esperan para siempre.": (
        "Requests to TIDAL no longer wait forever."
    ),
    "Guardar en una playlist no la crea ni la llena dos veces.": (
        "Saving to a playlist never creates or fills it twice."
    ),
    "La cola y los ajustes se guardan sin quedar a medias.": (
        "The queue and the settings are never saved halfway."
    ),
    "Una pista vieja no suena tras «siguiente» o detener.": (
        "An older track no longer plays after “next” or stop."
    ),
    "m: el menú de un álbum, artista o playlist entero.": (
        "m: the menu of a whole album, artist or playlist."
    ),
    "reproducir todo a continuación": "play all next",
    "añadir todo a una playlist": "add all to a playlist",
    "menú": "menu",
    "cargando {label}…": "loading {label}…",
    "menú de la pista, o del álbum, artista o playlist": (
        "the track's menu, or the album's, artist's or playlist's"
    ),
    "Menú de un álbum, artista o playlist (m en la biblioteca)": (
        "Album, artist or playlist menu (m in the library)"
    ),
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
    "repetición ⟳: off, toda la cola, una pista": (
        "repeat ↻: off, the whole queue, one track"
    ),
    "buscar en TIDAL": "search TIDAL",
    "tu biblioteca": "your library",
    "letra de la pista actual": "lyrics for the current track",
    "esta ayuda": "this help",
    "ayuda": "help",
    "añadir a favoritos de TIDAL": "add to your TIDAL favourites",
    "quitar de favoritos": "remove from favourites",
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
    # --- notas de versión 0.9.0
    "Sin corte entre pistas; la siguiente llega con su carátula.": (
        "No gap between tracks; the next one arrives with its cover."
    ),
    "Volumen normalizado con el ReplayGain de TIDAL.": (
        "Normalised volume with TIDAL's ReplayGain."
    ),
    "Mis mixes, en la biblioteca.": "My mixes, in the library.",
    "Un mpv que no contesta ya no congela la pantalla.": (
        "An mpv that stops answering no longer freezes the screen."
    ),
    # --- notas de versión 0.8.0
    "s ordena la biblioteca y d quita; ? con su propia ayuda.": (
        "s sorts the library and d removes; ? with its own help."
    ),
    "w: pantalla completa, con la cola al lado.": (
        "w: full screen, with the queue beside it."
    ),
    "Reproducción automática; la velocidad, también por MPRIS.": (
        "Autoplay; the speed over MPRIS too."
    ),
    "Carátula más nítida en blocks y más ligera en kitty y sixel.": (
        "Sharper covers in blocks, lighter ones in kitty and sixel."
    ),
    "Calidad, rates y reiniciar PipeWire se eligen de una lista.": (
        "Quality, rates and PipeWire's restart chosen from a list."
    ),
    # --- notas de versión 0.7.0
    "bosque, un décimo tema, ecológico; marcos más finos en todos.": (
        "bosque, a tenth, ecological theme; finer frames on all of them."
    ),
    "b cambia la velocidad, de 0.25× a 2×.": "b changes the speed, from 0.25× to 2×.",
    "La carátula puede ser redonda (cover_shape).": (
        "The cover can be round (cover_shape)."
    ),
    "Los temas se llaman en tu idioma; la cuenta atrás cabe.": (
        "Theme names follow your language; the countdown clock fits."
    ),
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
    "Menú de la pista (↵ o m en la biblioteca, m en la cola)": (
        "Track menu (↵ or m in the library, m in the queue)"
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
    "Populares": "Popular",
    "EPs y sencillos": "EPs and singles",
    "Otros: recopilatorios y colaboraciones": "Other: compilations and appearances",
    "ir al artista": "go to the artist",
    "ir al álbum": "go to the album",
    "TIDAL no dice de qué álbum es esta pista": (
        "TIDAL does not say which album this track is on"
    ),
    "TIDAL no dice de qué artista es esta pista": (
        "TIDAL does not say whose track this is"
    ),
    "buscando el artista…": "looking up the artist…",
    "buscando el álbum…": "looking up the album…",
    "no se pudo abrir: {error}": "could not open it: {error}",
    "¿QUÉ ARTISTA?": "WHICH ARTIST?",
    "Un artista abre a sus discos: álbumes, EPs, sencillos, otros.": (
        "An artist opens to its discs: albums, EPs, singles, other."
    ),
    "t y b en el menú de la pista: ir al artista o al álbum.": (
        "t and b in the track menu: go to the artist or the album."
    ),
    "Con varios artistas, se elige a cuál ir.": (
        "With several artists, you pick which one."
    ),
    "Un guardado que falla se dice en la línea de estado.": (
        "A save that fails is reported on the status line."
    ),
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
}
