# Registro de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el
versionado es [semántico](https://semver.org/lang/es/).

## [Sin publicar]

Todavía no hay ninguna versión publicada en PyPI ni en el AUR. Cuando la haya, esta
sección se cierra con su número y su fecha; el procedimiento completo está en
[`publish.md`](publish.md).

### Añadido

- Interfaz TUI con la estética de Winamp 2.x: reloj de siete segmentos, marquesina,
  analizador de 19 bandas, barra de posición y sliders de volumen y balance.
- Play y pausa comparten un único botón y una única tecla (`x`), cuyo icono es la
  acción que hará al pulsarlo: `▶` parado o en pausa, `‖` sonando.
- El transporte ocupa cuatro teclas contiguas, en el orden de los botones:
  `z` anterior, `x` play/pausa, `c` parar, `v` siguiente. Los rótulos de los
  botones salen de los bindings efectivos, así que siguen a `config.toml`.
- El transporte se dibuja como botones de tres filas, en dos grupos: el transporte por
  un lado y shuffle/repetición por otro.
- La cola se dibuja en columnas —título, artista, álbum, año y duración— cuando el
  terminal da para ello, en vez de meter el artista dentro del título. Se van cayendo
  en el orden en que se pueden perder: primero el año, luego el álbum y el artista, y
  al final queda `artista - título` en una línea con la duración a la derecha.
- **Cuatro estructuras visuales, elegibles con `theme`**, independientes del color:
  `quattro` (por defecto, plana y moderna), `retro` (barras de título dibujadas como
  una regla con el nombre centrado, teclas cuadradas pegadas y los conmutadores con las
  palabras `SHUFFLE` y `REPEAT`) y `nova` (sin marcos, un solo fondo, y una regla del
  acento bajo el conmutador encendido) y `ascii` (un terminal de antes del dibujo de
  cajas: botones `[ z << ]`, reglas de `=` y `-`, y ningún glifo en el cromado que no
  se pueda teclear). Se cambian desde la ventana de `o` sin parar la reproducción.
- **Paletas portables** además de seguir a Omarchy: `classic`, `tokyo-night`,
  `catppuccin`, `nord`, `gruvbox`, o un TOML propio en
  `~/.config/tidalamp/palettes/`, con el mismo formato que el `colors.toml` de
  Omarchy. Cualquier paleta funciona con cualquiera de las tres estructuras.
- La ventana de configuración avisa en su propia línea, y en el color de aviso, cuando
  el grafo de PipeWire está fijo en un ritmo y remuestrea todo: la insignia dice la
  verdad sobre el stream mientras el DAC recibe otra cosa, y no había nada en pantalla
  que lo delatara sin mover el cursor.
- **`v` (parar) rearrancaba la lista desde el principio**: dejaba mpv en idle y el
  tick lo leía como «la pista acabó», así que avanzaba a la siguiente — que desde
  una cola parada es la primera.
- Reproducción con `mpv` de larga vida por socket IPC, con reinicio automático si el
  proceso muere.
- Autenticación por *device flow* de TIDAL, sin registrar ninguna app, con refresco del
  token al arrancar y a media sesión.
- Cola con shuffle, repetición en tres modos, reordenado y persistencia entre sesiones.
  Ambos viven en la barra de transporte como botones `s ⇄` y `r ↻`, encendidos con
  el acento del tema; la barra separa transporte y ventanas con `·` y alinea las
  ventanas a la derecha.
- Navegador de la biblioteca: playlists, favoritos, álbumes y artistas, paginado y con
  caché de niveles en memoria.
- Búsqueda de pistas, álbumes, artistas y playlists.
- Menú de acciones al pulsar `↵` sobre una canción: reproducir ahora (`a`),
  reproducir a continuación (`c`), reproducir la radio que TIDAL genera para esa
  pista (`d`) y añadir a favoritos (`v`), cada uno con su icono.
- Favoritos de TIDAL con `f` y `F`.
- Servicio MPRIS2 completo, incluida la interfaz `TrackList`.
- Carátula en el terminal por protocolo de kitty, sixel o medios bloques, en un
  recuadro que crece con el terminal (de 18×9 a 40×20) junto con el analizador.
- Letras sincronizadas (LRC) con respaldo a texto plano.
- Ecualizador de diez bandas y balance, como filtros de mpv, con persistencia.
- Espectro real con `cava` cuando está instalado, y vúmetro RMS cuando no.
- Paleta tomada del tema Omarchy activo, con cambio en vivo.
- Fichero de configuración `config.toml` y teclas rebindables.
- Ventana de configuración (`o`) que escribe ese fichero: calidad, carátula,
  idioma y registro, avisando cuando una variable de entorno los pisa. Incluye
  el estado de la salida de audio, y activa los ritmos hi-res de PipeWire —sin
  los cuales un 24/96 llega al DAC remuestreado a 48 kHz— y su reinicio.
- El idioma pasa a ser un ajuste del fichero; antes sólo salía de `$LANG`.
- Entrada de escritorio e icono, y aviso cuando el terminal es más pequeño de 76×20.
- Empaquetado para el AUR y para PyPI, con publicación por *Trusted Publishing*.
- Interfaz y CLI bilingües español/inglés según el locale, con fallback al español.
- Ventana de ayuda (`?` o `h`) con todos los atajos agrupados y leídos de los
  bindings efectivos, así que una tecla rebindeada en `config.toml` aparece como
  la que hay que pulsar. Incluye «Acerca de» —versión, autor, repositorio y
  licencia— y el resumen de cambios de cada versión.
- README público en inglés.

### Corregido

- **El hi-res no sonaba.** La playlist HLS que genera `tidalapi` lista el segmento de
  inicialización como si fuera audio y no emite `#EXT-X-MAP`; además ffmpeg bloquea
  `https` desde una playlist local. Las dos cosas están resueltas.
- **La calidad por defecto no producía lossless nunca.** Pedir `LOSSLESS` al cliente del
  device flow devuelve `HIGH` siempre; el valor por defecto es `HI_RES_LOSSLESS`.
- **Una página corta de TIDAL no es el final de la lista.** La biblioteca dejaba fuera
  676 de 766 pistas favoritas.
- **«Mis playlists» tardaba 20 segundos** con 110 playlists, porque `tidalapi` pedía
  cada una por separado. Ahora tarda 0,4 s.
- **La app no arrancaba con un access token caducado**, que es el caso normal al abrirla
  al día siguiente.
- **La barra de estado quedaba fuera de la pantalla**, así que todo lo que la aplicación
  tenía que decir se escribía donde nadie lo veía.
- La insignia mostraba «16bit» sobre audio con pérdida.
- **La barra de volumen se rompía por encima de 100.** El relleno no estaba
  acotado al ancho de la pista, así que a 105 el número se corría, a 115 salía
  del widget y a 130 la línea era tan larga que no se dibujaba nada: quedaba
  «VOL» y una fila vacía. El widget ya no deja que ningún valor le deforme la
  pista, y el volumen tiene tope en 100 —por encima mpv aplica ganancia digital
  sobre una señal ya normalizada, que satura—, tanto por teclado como por MPRIS.
- **Sin Pillow no había carátula y no se decía por qué**: el widget se quedaba
  oculto y el único rastro era un `log.info` en un fichero. Ahora la barra de
  estado nombra el extra que lo arregla al arrancar, y las instrucciones de
  instalación desde el repositorio incluyen `".[art]"`, que era donde faltaba.
- **Los corchetes desaparecían del texto que no escribimos nosotros.**
  `Static.update` interpreta un `str` como marcado de Rich: un álbum llamado
  «Lateralus [Deluxe Edition]» se dibujaba como «Lateralus », y un nombre con
  una etiqueta de cierre (`[/]`) lanzaba `MarkupError` en pleno render. Los
  cuatro `Static` que reciben nombres de TIDAL, títulos de pista o mensajes de
  excepción se construyen ahora con `markup=False`.
