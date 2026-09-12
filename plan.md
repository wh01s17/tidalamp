# plan.md — estado del proyecto `tidalamp`

Documento de traspaso. Describe qué existe, qué está verificado, qué falta y con qué
criterio se tomaron las decisiones, para que cualquiera (humano o modelo) pueda
retomar el trabajo sin contexto previo.

**Última actualización:** 2026-09-12, versión `0.9.0` preparada, lo nuevo probado
a mano por el mantenedor contra TIDAL real: mpv que
no contesta ya no congela la pantalla (espera de 1 s una vez, sondeo y reinicio en
workers, EOF leído como muerte), la pista siguiente preparada en mpv para que no haya
corte, volumen normalizado con el ReplayGain de TIDAL y «Mis mixes» en la biblioteca.
Antes, 2026-09-11, versión `0.8.1` preparada (timeouts reales para
TIDAL, escrituras de playlists que no se duplican, el estado escrito de forma
atómica y una resolución vieja descartada al pasar de pista o detener. En `0.8.0`: `s` ordena la
biblioteca y el orden persiste, `d` quita de favoritos o de una playlist y `?` trae
su ayuda; `m` abre el menú de un álbum, artista o playlist entero, y `a` sobre uno
trae todas sus páginas; la ventana de la letra sigue a la pista que suena; `q` pregunta
antes de salir; `w`, la pantalla completa con la cola al lado; reproducción automática; la
velocidad también por MPRIS; `rounded`; la carátula más nítida en `blocks` y mucho más
ligera en kitty y sixel; calidad, ritmos y reiniciar PipeWire, desde una lista. En
`0.7.0`: el décimo tema temático, `bosque`; marcos más finos en los temáticos; la
forma de la carátula como ajuste; la velocidad de reproducción; los nombres de los
temas en el idioma en uso; el reloj en cuenta atrás, que no cabía. En `0.6.0`: nueve temas temáticos
con su paleta, su frase y su imagen de fondo en la cola, dibujada como la carátula y
mezclable con cualquier tema desde el ajuste `backdrop`; disposición `split` con la
letra sobre la carátula; buscador en la ayuda; las líneas que no caben se deslizan;
la cola repinta dos filas al mover el cursor, lo que en 4K bajó de 245 a menos de 5
KiB por pulsación; antes, 2026-09-10: la carátula en `blocks` pasa a los glifos de
cuadrante: cuatro muestras por celda en vez de una, el doble de resolución horizontal;
el alto de la banda del display se recalcula en cada pasada y no sólo al redimensionar
la carátula, que era por qué al cambiar de tema —o al arrancar en `nova`— la imagen se
montaba sobre la barra de posición; `space` reproduce y `m` abre el menú de la pista
sobre la cola; `u` deshace un vaciado; ocho presets de ecualizador; se puede añadir a
una playlist que ya existe; las cuatro disposiciones cuadran bordes y anchos y las
capturas del README se rehicieron; antes: `TooManyRequests` respeta `Retry-After` con un
tope de un minuto; `g` devuelve el cursor a la pista que suena incluso si estaba
filtrada; `p` guarda una instantánea de la cola como playlist de TIDAL por lotes y
reporta creaciones parciales; posición, volumen y balance responden al clic; antes: el
analizador con cuatro formas —`bars`,
`mirror`, `curve` y `fine`, esta última un trazo continuo sobre la rejilla Braille— elegibles desde la ventana de ajustes, todas dibujadas donde ha estado
siempre pero llegando al borde derecho, y **mucho más baratas en 4K**: 55% de un núcleo
antes, 8% ahora, topando las bandas y mandando los tramos de un color de una vez;
buscador en la cola con `ctrl+f`, en una barra
bajo la lista como el filtro del navegador, con las filas conservando el número que
tienen de verdad en la cola; `tidalamp -v` / `--version` imprime la versión
en el terminal, que hasta ahora sólo estaba dentro de la TUI; la ayuda en dos pestañas —los atajos y «Acerca
de»— con → y ← para pasar de una a otra, en vez de un documento único donde los
créditos y las notas de versión quedaban tres pantallas por debajo de lo que se venía
a mirar; antes: ventanas superpuestas proporcionales al terminal
—inservibles en 4K a 84x26— sobre un velo translúcido que deja ver el reproductor, con
el fondo congelado mientras hay un modal abierto para que eso cueste menos que antes;
antes: filtro `/` dentro del navegador de la
biblioteca, en una barra al pie que estrecha el nivel sin taparlo, y barra de ayuda del
navegador que ya no se corta a mitad de palabra; antes: versión `0.1.0` cerrada y preparada para PyPI;
Trusted Publishing configurado; publicación en el AUR aplazada sin fecha porque el
registro público de cuentas nuevas continúa cerrado durante el endurecimiento de seguridad;
cadena hi-res verificada en el hardware —el DAC
marca `PCM 176.4K`—; pantalla de configuración con todo lo que antes pedía editar el
TOML o exportar variables, incluidos los ritmos hi-res de PipeWire;
menú de acciones al pulsar ↵ sobre una pista,
con radio de TIDAL y «reproducir a continuación»; tope de volumen en 100 y slider que
no se deforma; pantalla de ayuda con todos los atajos, créditos y notas de versión; los modales salieron de `app.py` a `screens.py`,
la carátula sigue el tamaño del terminal, `markup=False` en los `Static` que reciben
texto de TIDAL, aviso visible cuando falta Pillow y un job de CI que instala sin
extras; antes: interfaz bilingüe español/inglés y README público en inglés)

---

## 1. Qué es esto

Cliente de TIDAL para terminal con interfaz estilo Winamp 2.x (TUI). Reproduce audio
con `mpv` y obtiene catálogo y streams con `tidalapi`.

Antes se llamaba `tidal-cli-omarchy` porque se pensó como plugin de Omarchy. Se
renombró a `tidalamp` al decidir que el producto es una TUI autónoma. El directorio ya
está renombrado a `~/workspace/tidalamp`.

**Secuela del renombrado (ya resuelta):** el venv se había creado en la ruta antigua y
los scripts de `.venv/bin` llevaban un shebang inexistente (`bad interpreter`). Se
rehizo el 2026-09-08 con `python -m venv .venv && .venv/bin/python -m pip install -e ".[dev]" pyte`. Si vuelve a pasar tras mover el directorio, la cura es esa.

## 2. Decisiones de arquitectura (y por qué)

Estas son las decisiones que **no** hay que volver a litigar sin motivo nuevo:

| Decisión                                                 | Motivo                                                                                                                                                                                                                                                           |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No usar la API oficial** (`developer.tidal.com`)       | Exige registrar una app, y aun así no entrega URLs de stream. Sólo sirve para metadata.                                                                                                                                                                          |
| **Usar el device flow vía `tidalapi`**                   | Es el mismo OAuth que los clientes oficiales de TV/escritorio. No requiere registrar nada: el usuario abre un enlace, autoriza, y la sesión refrescable se cachea.                                                                                               |
| **mpv como motor, no un player embebido**                | Maneja HLS/DASH/FLAC sin que nosotros toquemos códecs. Un solo proceso `--idle` de larga vida sobrevive a los cambios de pista.                                                                                                                                  |
| **IPC por socket unix con JSON**, no `python-mpv`/libmpv | Cero dependencias nativas, y da acceso directo a las propiedades (`time-pos`, `volume`, `af-metadata`) que necesita el display.                                                                                                                                  |
| **Textual para la TUI**                                  | Tiene CSS, que hace tratable clonar la estética de Winamp.                                                                                                                                                                                                       |
| **GPL-3.0-or-later** (2026-09-08)                        | Aplicación de usuario final en un ecosistema copyleft (mpv es GPL, `tidalapi` LGPL-3). Mantiene libre cualquier versión redistribuida. La LGPL de `tidalapi` no obligaba a nada —en Python se importa, no se enlaza—, así que fue elección, no imposición.       |
| **No cruzar la línea del DRM**                           | `stream.py` rechaza los manifiestos cifrados en vez de descifrarlos, y no se descarga audio a disco. Es lo que mantiene el proyecto fuera de las leyes anti-elusión (DMCA §1201 y equivalentes); el README lo declara y los parches que lo crucen no se aceptan. |

Alternativas descartadas y su motivo: `tidal-hifi` + MPRIS (mete un Electron de por
medio), Puppeteer sobre `listen.tidal.com` (Widevine, frágil), Mopidy (demasiadas
piezas).

## 3. Mapa de ficheros

```
tidalamp/
  config.py     Rutas XDG, fichero de configuración TOML y ajustes resueltos
                (entorno → fichero → defecto). Sin dependencias internas.
  auth.py       Device flow y persistencia de sesión. Lanza NotLoggedIn.
  stream.py     Track -> Playable (URL o playlist HLS local). Lanza StreamUnavailable.
  player.py     Clase Mpv: spawn del proceso, socket IPC, transporte, medición RMS.
  widgets.py    TimeDisplay, SeekBar, Slider, Spinner, Artwork. Reexporta los de
                `analyzer.py` y `scrolling.py`. Sin lógica de negocio.
  analyzer.py   Analyzer (cinco formas) y EqualizerBars: los que pintan bandas.
  scrolling.py  Texto que se mueve: Glide, Marquee y LyricsPane.
  screens/      Un módulo por ventana (browser, tracks, help, config_window,
                equalizer, lyrics_window, column_picker, prompts, speed) y `rowlist.py`
                con RowList y `fit_hints()`. `__init__.py` lo reexporta todo. No
                guardan estado del reproductor: reciben lo que necesitan al
                construirse y contestan por `dismiss`.
  app.py        TidalAmp: layout, transporte, workers y el pegamento con MPRIS.
  styles/       La hoja en cinco ficheros que `CSS_PATH` lee en orden: base
                (pantalla y ventanas), player, compact, looks y themed. A igual
                especificidad gana la regla posterior, así que el orden importa.
  queue.py      Entry (metadatos serializables + Track perezoso) y Queue (orden,
                shuffle, repeat, persistencia). No conoce la UI.
  library.py    Navegación de la biblioteca. Devuelve listas de Row, paginadas.
  net.py        with_retries(): reintentos con backoff para las llamadas a TIDAL.
  spectrum.py   Cava: proceso cava + lector de frames. Opcional por diseño.
  settings.py   Balance y ecualizador: grafos de filtro y persistencia.
  lyrics.py     Carga de letras, parseo LRC y modelo de sincronización. Sin Textual.
  theme.py      Paleta semántica: tema Omarchy activo o fallback clásico validado.
  layouts.py    Las disposiciones como datos: `Layout` (título, encabezado de la
                cola, constructor del transporte, presupuesto de glifos) y
                `LAYOUT_TABLE`. `app.py` no compara `config.THEME` con nombres.
  artwork.py    Carátula: descarga con cache, y codificación kitty / sixel /
                medios bloques. Sin Textual ni tidalapi.
  i18n.py       Español como fuente y fallback, catálogo inglés y detección de locale.
  about.py      Créditos, licencia, repositorio y notas de versión, más el mapa de
                atajos que pinta la ayuda. Datos puros: sin Textual.
  audio.py      La pila de audio bajo mpv: sink por defecto, ritmos que permite
                PipeWire, ritmos que acepta el DAC, y el drop-in que los desbloquea.
                Todo por subprocess, y todo contesta con lo que encontró en vez de
                lanzar: nada de esto está en el camino que reproduce música.
  mpris.py      Servicio MPRIS2 en D-Bus. Habla con la app por el Protocol
                PlayerBackend, así que no conoce Textual ni tidalapi.
  cli.py        Entrypoint typer: login / tui / config / search, y `--version`.

packaging/
  README.md     Procedimiento de publicación en PyPI y en el AUR.
  aur/PKGBUILD  Receta de Arch; `.SRCINFO` se regenera con makepkg.
.github/workflows/
  ci.yml        pytest en 3.11–3.14, un job sin extras y ruff/mypy.
  release.yml   tag v* -> build -> twine check -> PyPI por OIDC.
```

Dependencia en un solo sentido:

```text
cli -> app -> {player, stream, widgets, screens, mpris, lyrics, spectrum, settings}
       app -> {queue, net, artwork, library} -> {auth, config}
       screens -> {widgets, library, settings, lyrics, theme, about, audio, config}
       widgets -> {analyzer, scrolling}
       widgets -> artwork  (sólo los tipos Cover/Protocol y el borrado de kitty)
```

`RowList` vive en `screens/rowlist.py` y no en `widgets.py` a propósito: pinta un
`library.Row`, y `library` importa `tidalapi`. Ponerlo con los demás widgets
arrastraría TIDAL al único módulo que deliberadamente no lo conoce.

`widgets.py`, `analyzer.py` y `scrolling.py` no conocen TIDAL ni mpv; recibe valores por reactives. Mantener esa
separación: es lo que permitiría añadir otro frontend (ver §6).

## 4. Implementado

### Autenticación — `auth.py`

- [x] `login()`: device flow, imprime la URL de verificación, bloquea hasta aprobación.
- [x] `load_session()`: carga desde `~/.config/tidalamp/session.json` y valida.
- [x] Excepción `NotLoggedIn` con mensaje accionable.

### Resolución de streams — `stream.py`

- [x] Manifiestos `BTS` (URLs progresivas) -> se pasa la primera URL a mpv.
- [x] Manifiestos `MPD` (DASH segmentado) -> se vuelca como playlist HLS local en cache.
- [x] **La playlist se reescribe antes de dárse la a mpv** (`_to_fmp4_hls`). El HLS de
      `tidalapi` lista el segmento de inicialización (`ftyp`+`moov`) como si fuera
      audio y nunca emite `#EXT-X-MAP`, así que ffmpeg abre cada segmento por su cuenta,
      no encuentra el `trex` y aborta con *error reading header*. Comprobado sobre una
      pista hi-res real: 69 segmentos, el 0 es `ftyp+moov` y el resto `moof+mdat`.
- [x] **Calidad por defecto `HI_RES_LOSSLESS`, no `LOSSLESS`.** Pedir `LOSSLESS` al
      cliente del device flow devuelve `HIGH` siempre, incluso en pistas que TIDAL
      etiqueta `LOSSLESS`; pedir `HI_RES_LOSSLESS` devuelve FLAC 24/96 donde lo hay y
      `HIGH` donde no. El valor anterior no producía lossless en ningún caso.
- [x] `Playable.downgraded`: cuando TIDAL entrega menos de lo pedido, la barra de
      estado lo dice, en vez de dejar que la insignia lo insinúe.
- [x] `Playable.kbps` decide por calidad, no por `bit_depth`: TIDAL informa 16 bits
      también para AAC de 320 kbps, así que el display ponía «16bit» sobre audio con
      pérdida.
- [x] Detección de manifiestos cifrados -> `StreamUnavailable` con mensaje explicando
      el DRM, en vez de dejar que mpv falle con un error de códec.
- [x] `Playable` expone `kbps`/`khz` para las insignias del display.
- [x] `cleanup_playlists()` borra los `.m3u8` temporales al salir.

### Reproducción — `player.py`

- [x] Spawn de `mpv --idle --no-video` con `--input-ipc-server`.
- [x] `--demuxer-lavf-o=protocol_whitelist=…`: sin eso, ffmpeg hereda del protocolo
      padre y una playlist abierta como `file:` sólo puede seguir `file,crypto,data`,
      de modo que **todos** los segmentos https del hi-res fallaban. El valor lleva
      comas, así que necesita el escape `%<longitud>%` de mpv o la opción se parte.
- [x] Cliente IPC con lock, `request_id` correlacionado y descarte de eventos async.
- [x] `load` / `toggle_pause` / `stop` / `seek`; propiedades `position`, `duration`,
      `volume`, `paused`, `idle`.
- [x] `rms()`: nivel en dBFS vía el filtro `astats` de mpv.
- [x] `close()` con terminación limpia y borrado del socket.

### Interfaz — `app.py`, `widgets.py`, `styles/`

- [x] Reloj de siete segmentos, con alternancia transcurrido/restante (`t`).
- [x] Marquee del título con scroll. Lleva **el número y el título y nada más**: es una
      línea, y el artista, el álbum, el año y la duración caben mejor bajo el reloj, que
      tenía cinco filas vacías debajo. `#clockbox` agrupa los dos y conserva las 24
      celdas que el reloj declaraba, porque `_fit_artwork` mide esa columna con
      `CLOCK_WIDTH` para calcular el recuadro de la carátula.
- [x] El bloque bajo el reloj recorta en vez de envolver: veintitrés celdas de ancho, y
      un álbum largo envuelto empujaría el año fuera de la banda. El año desaparece
      cuando vale `0`, que es lo que trae una cola guardada antes de que existiera esa
      columna, en vez de dejar un separador suelto.
- [x] Se escribe al arrancar la pista (`_refresh_track_meta`) y no sólo desde
      `_refresh_readout`: la línea del códec espera a que resuelva el stream y esto no
      tiene por qué. En la disposición compacta desaparece; cinco filas de banda son el
      reloj y nada más.
- [x] Analizador de 19 bandas con balística ataque rápido / caída lenta y marcas de pico.
- [x] Barra de posición y slider de volumen, este último con tope en
      `Mpv.VOLUME_MAX` (100). El slider lee esa constante en vez de heredar su propio
      máximo: cuando los dos rangos se separaron, la barra se dibujaba más ancha que su
      pista y se llevaba por delante el número.
- [x] **Posición, volumen y balance responden al clic.** Los widgets traducen la
      coordenada relativa a su región de contenido —descontando el `padding: 0 1`— y
      la app decide el efecto: seek absoluto, volumen de mpv o filtro de balance. La
      celda central del balance devuelve `0` exacto; posición con duración cero no
      llama a mpv. Arrastrar queda deliberadamente fuera de alcance.
- [x] Playlist con cursor, marcador de pista en curso y scroll centrado.
- [x] Búsqueda en TIDAL en modal, ejecutada en hilo para no bloquear la UI.
- [x] Avance automático al terminar la pista (se detecta por `idle-active` de mpv).
- [x] Transporte en `z` `x` `c` `v` —anterior, play/pausa, parar, siguiente— más
      `/` `l` `y` `e`, navegación, balance, volumen, shuffle/repeat y salida. Winamp
      usaba `z x c v b`, con `c` para una pausa aparte; al fusionar play y pausa en un
      botón sobró una tecla y el transporte quedó en cuatro contiguas, en el mismo
      orden en que están los botones en pantalla.
- [x] Los rótulos de los botones salen de `keys_for`, no de literales: un botón
      rebindeado en `config.toml` enseña la tecla que de verdad funciona.
- [x] Indicadores de shuffle y repetición encendidos con el acento del tema, con
      actualización inmediata por teclado o MPRIS.
- [x] **Aspecto y color son dos ajustes distintos.** `theme` elige la estructura
      —`quattro` (por defecto, plano y moderno), `retro` (la piel del 97 hasta donde
      llega un terminal), `nova` (sin marcos, un solo fondo) y `ascii` (un terminal de
      antes del dibujo de cajas)— y `palette` elige el color. Cualquiera de los tres funciona con cualquier paleta, y los dos cambian
      en vivo desde la ventana de `o` sin parar la reproducción. La lista de
      estructuras vive una sola vez, en `theme.LAYOUTS`.
- [x] `retro` es lo que hace reconocible al original: las barras de título se dibujan
      como una regla con el nombre centrado encima, los botones son teclas cuadradas
      pegadas hombro con hombro —no un marco segmentado— y los dos conmutadores llevan
      escritas las palabras `SHUFFLE` y `REPEAT`.
- [x] `ascii` no gasta un solo glifo fuera de ASCII en el cromado: botones
      `[ z << ]`, reglas de `=` y `-`, y el borde del panel con el `border: ascii` del
      propio Textual. Los medidores conservan sus bloques.
- [x] `nova` no dibuja ni una caja: un único fondo, aire por separación, y el color
      reservado a los dos controles que llevan estado, con una regla del acento debajo
      del que está encendido.
- [x] Paletas portables además de Omarchy: `classic`, `tokyo-night`, `catppuccin`,
      `nord`, `gruvbox`, `black`, o un TOML propio en `~/.config/tidalamp/palettes/` con el
      mismo formato que el `colors.toml` de Omarchy. El nombre se valida contra
      `[a-z0-9_-]+` antes de tocar el disco, así que una paleta no es una ruta.
- [x] Paleta completa tomada del tema Omarchy activo cuando existe; recarga en vivo
      cada dos segundos. En otras distros conserva exactamente los colores clásicos.
- [x] `Spinner`: indicador animado de espera que dice **qué** se está cargando, en la
      barra de título del navegador, en la de la letra y en la de estado. Cada trabajo
      lento corre en un worker para que la UI siga pintando, y precisamente por eso una
      espera se parecía a un cuelgue. El título del nivel no se sustituye por
      «cargando»: es lo único que dice dónde estás. Volver atrás apaga el indicador.
- [x] **La barra de estado estaba fuera de la pantalla.** `#playlist` no declaraba
      altura, y `RowList` pinta tantas filas como se le den, así que el auto crecía
      hasta empujar `#status` por debajo del borde inferior: todo lo que la aplicación
      tenía que decir (errores, «resolviendo…», la cola restaurada) se escribía donde
      nadie podía verlo. Ahora es `height: 1fr` y hay una prueba que lo fija.

### MPRIS — `mpris.py`

- [x] Implementado con `dbus-fast>=5.0.22`; `dbus-next` ya no es dependencia ni queda
      instalado en el venv.
- [x] Publica `org.mpris.MediaPlayer2.tidalamp` en el bus de sesión.
- [x] Interfaz raíz `org.mpris.MediaPlayer2`: Identity, CanQuit, Quit, etc.
- [x] Interfaz `Player`: Play, Pause, PlayPause, Stop, Next, Previous, Seek,
      SetPosition; propiedades PlaybackStatus, Metadata, Position, Volume (lectura y
      escritura), CanGoNext/CanGoPrevious.
- [x] Metadata completa incluida `mpris:artUrl` (carátula, que Waybar muestra).
- [x] Interfaz `org.mpris.MediaPlayer2.TrackList` (`HasTrackList` ya es True):
      `Tracks`, `GetTracksMetadata` y `GoTo`. `CanEditTracks` es False a propósito —
      `AddTrack` recibe una URI y no publicamos esquemas soportados, y la
      especificación ata los dos métodos de edición a esa misma bandera, así que decir
      True prometería un `AddTrack` que no podemos cumplir. `GoTo` no depende de ella.
- [x] `mpris:trackid` pasa a identificar **la fila**, no la pista: `Entry.uid`, un
      contador persistido en `queue.json`. La misma canción puede estar dos veces en la
      cola y MPRIS exige identificadores distintos; el uid además sobrevive a
      reordenar. Una cola guardada antes de esto recibe uids nuevos al cargarla, y el
      contador se coloca por delante de lo restaurado para no reutilizar ninguno.
- [x] Los cambios de cola se anuncian con `TrackListReplaced`, no con
      `PropertiesChanged` — es lo que pide la especificación para `Tracks` — y el
      diff se hace sobre los identificadores, sin construir metadata, porque eso corre
      en el tick de 4 Hz.
- [x] `PropertiesChanged` emitido por diferencia contra la última emisión, no en cada
      tick — los clientes MPRIS repintan con cada señal.
- [x] Degradación limpia: sin bus de sesión la app arranca igual y lo dice en la barra
      de estado.
- [x] `--load-scripts=no` en mpv para que un `mpv-mpris` del sistema no publique un
      reproductor duplicado.
- [x] El servicio vive en el loop asyncio de Textual, no en un hilo aparte.

### Cola — `queue.py`

- [x] `Entry` guarda metadatos planos y resuelve el `Track` de la API sólo al
      reproducir, de modo que restaurar una cola larga no cuesta N peticiones.
- [x] `Queue` con append/replace/remove/clear y cursor de reproducción.
- [x] Shuffle como permutación paralela, no reordenando la lista: al desactivarlo se
      recupera el orden original y la numeración visible nunca cambia bajo el usuario.
      Al activarlo, la pista actual queda primera para que «siguiente» continúe desde ahí.
- [x] Repeat con tres modos, cuyos valores coinciden literalmente con `LoopStatus`
      de MPRIS (`None` / `Track` / `Playlist`).
- [x] Persistencia en `~/.local/state/tidalamp/queue.json`, con `resume_at` para dejar
      el cursor donde estaba. Los fallos de disco son deliberadamente no fatales.

### Biblioteca — `library.py`

- [x] Playlists del usuario, pistas/álbumes/artistas favoritos.
- [x] Drill-down perezoso: cada nivel se pide sólo al abrirlo, en un hilo.
- [x] La búsqueda reutiliza la misma estructura de `Row` que la biblioteca.
- [x] Paginación: `_paged()` pide `PAGE` (100) elementos y cuelga una fila `más…` al
      final cuando queda más. `↵` sobre ella carga la siguiente página **en el mismo
      nivel** (`RowList.extend_at`), sin perder el scroll.
- [x] **Una página corta NO es el final.** Era la regla anterior y estaba mal: TIDAL
      aplica el límite y *después* filtra la ventana, así que pedir 100 pistas
      favoritas devolvía 90 —de 766— y el navegador se paraba ahí. El usuario no podía
      alcanzar 676 de sus favoritos, ni 439 de sus álbumes, ni 297 de sus artistas.
      Ahora, cuando el nivel sabe su recuento (`get_tracks_count`, `num_tracks`,
      `totalNumberOfItems`), es ese número el que decide, y el offset avanza de 100 en
      100 porque TIDAL cuenta offsets sobre la colección sin filtrar. Sin recuento se
      mantiene la regla vieja, que allí sí vale.
- [x] La búsqueda también pagina, y ahora cubre **álbumes, artistas y playlists** además
      de pistas: tres filas de categoría arriba y las pistas en línea debajo, porque una
      pista es lo que se busca casi siempre y no debía costar una pulsación más. Cada
      categoría se pide sólo al abrirla.
- [x] Favoritos de TIDAL con `f` y `F` sobre pistas, álbumes, artistas y playlists.
      **No es un interruptor**: la API no permite preguntar si algo ya es favorito, así
      que alternar exigiría descargar la lista entera o adivinar, y adivinar mal borra.
      Al escribir se invalidan los niveles de favoritos en caché.
- [x] **Guardar la cola como playlist de TIDAL con `p`.** `save_queue_playlist()` crea
      la playlist y manda los ids de una instantánea en orden de cola, no de shuffle,
      en lotes de 100 y con duplicados permitidos. Cada escritura pasa por
      `with_retries`; al crear se invalida la clave `playlists` de `_LEVELS`. Si falla
      un lote, la playlist ya creada se conserva y `PlaylistSaveFailed` lleva nombre,
      cantidad terminada y total para que la UI informe la creación parcial.
- [x] **«Mis playlists» costaba 20 s con 110 playlists.** `session.user.playlists()`
      parece una llamada y no lo es: al parsear cada elemento lo pasa por
      `Playlist.factory()`, que para una playlist propia construye un `UserPlaylist`,
      y ese constructor **vuelve a pedir la playlist entera para leer el ETag**. Medido
      con cProfile contra la cuenta real: 111 peticiones HTTP, 19,87 s, de las cuales
      la red útil eran 0,25 s. Como no editamos playlists, `_playlists_level()` parsea
      el listado con `Playlist.parse()` (que no pide nada) y se salta la factoría.
      Además ahora pagina como el resto. Resultado en la app real: **0,39 s**.
- [x] **Filtro del nivel con `/`** (`library.matches` + `BrowserScreen`). Una barra al
      pie del navegador, como el buscador de un navegador web: no es un modal, no tapa
      la lista, la estrecha debajo mientras se teclea y a la derecha dice «12 de 103».
      Filtra lo que el nivel contenga, que es justo lo que el usuario pidió: pistas en
      «Pistas favoritas», playlists en «Mis playlists», álbumes, artistas o una categoría
      de resultados de búsqueda.
      - `matches()` compara sin mayúsculas ni acentos (NFD + descarte de combinantes),
        exige que **cada palabra** escrita aparezca en algún sitio, y mira etiqueta,
        detalle y **álbum de la pista** —que no está en la línea salvo que se haya
        activado esa columna, y es lo que la gente recuerda.
      - La fila «más…» **nunca se filtra**. Un nivel tiene una página hasta que alguien
        pide el resto; esconder la única forma de pedirlo diría que 12 de 766 favoritos
        son todo lo que hay, que es la misma mentira que se arregló en `_paged`.
      - El filtro pertenece al nivel: entrar en otro, volver con `⌫` o recargar con `R`
        lo dejan limpio, porque abrir un nivel ya escondido a medias y sin nada que lo
        explique es peor que no filtrar.
      - `↵` aplica y devuelve las flechas a la lista; `esc` lo quita **y deja el
        navegador abierto**, con el cursor en la fila a la que se había llegado; el
        segundo `esc` ya cierra.
      - `RowList.extend_at` desapareció: la página que llega se empalma sobre la lista
        del nivel **identificando la fila «más…» por sí misma**, no por su número, porque
        bajo un filtro el número en pantalla no es su sitio en el nivel. Sigue siendo un
        empalme in situ sobre la lista que entregó la caché, así que las páginas ya
        traídas siguen ahí al volver.
- [x] Caché de niveles en memoria (`library.cached` / `library.forget`): volver a
      entrar en un nivel ya visitado es instantáneo. Sólo en memoria, porque una
      biblioteca cambia desde otros dispositivos; `R` en el navegador olvida el nivel y
      lo vuelve a pedir. La lista cacheada se entrega tal cual, no copiada, para que
      las páginas que el usuario ya cargó con «más…» sigan ahí al volver.

### Configuración — `screens/config_window.py`, `config.py`

- [x] **Agrupada por temática**: Audio (calidad, ritmos hi-res, reiniciar PipeWire),
      Apariencia (tema, paleta, transparencia, carátula, columnas) y General (idioma,
      registro). Diez ajustes en una columna se leían como diez interruptores sin
      relación. Las cabeceras se dibujan desde `Option.group`, así que el cursor sigue
      indexando sólo filas reales y ningún test que busca por etiqueta se entera.
- [x] La lista se desplaza a mano alrededor del cursor cuando no cabe. Las cabeceras
      costaron cinco líneas y en 60x18 dejaron filas seleccionables e invisibles a la
      vez. La ventana se calcula desde el alto del **terminal** menos `CHROME`, no desde
      el widget: la caja crece con su texto y sólo la recorta el layout, que ocurre
      *después* de este render, así que preguntarle a la caja o a la lista devuelve el
      alto del texto justo cuando hace falta el otro.
- [x] La ventana crece con su propio texto (`height: auto`) con un suelo de 24 filas.
      Un `1fr` dentro de una caja `auto` se come todas las filas del terminal —se probó,
      y quedaba media ventana vacía en 4K—; una altura fija dejaba el mismo hueco.
- [x] **La carátula sigue al ajuste en vivo** (`_reload_art`). Antes pedía reiniciar, lo
      cual convertía «enciendo la transparencia para ver el reproductor» en «veo el
      reproductor con un agujero donde estaba la carátula hasta el próximo arranque».
      Baja la imagen vieja con `show(None)` —que es lo que manda el borrado de kitty—,
      redetecta el protocolo y vuelve a pedir la carátula de la pista en curso.
- [x] **Una carátula que aterriza con un modal abierto se retira sola** (`_art_ready`).
      No era sólo cosa del cambio de protocolo: una imagen de píxeles se pinta sobre el
      texto llegue cuando llegue, así que empezar una pista desde el navegador dejaba la
      portada encima del navegador. Las de medios bloques se quedan donde caen.
- [x] **La carátula se restringe mientras hay transparencia**: `ARTWORKS_OVER_PLAYER`
      deja `blocks` y `off`, y las filas se reconstruyen al cambiar el interruptor para
      que la lista de al lado no siga describiendo el ajuste como era. `auto` se cae de
      la lista a propósito: es una promesa que cumple el terminal, y en uno con kitty
      promete exactamente lo que la transparencia no puede tener. Al apagarla vuelven
      los cinco modos, y el valor no se restaura solo porque no se guarda cuál era.
- [x] **Transparencia como ajuste** (`transparency`, `TIDALAMP_TRANSPARENCY`), apagada
      por defecto. Encenderla escribe `artwork = "blocks"` cuando la carátula la dibuja
      kitty o sixel, y lo anuncia en la propia pantalla con enlace a la especificación
      del protocolo de kitty. No es un capricho: esas imágenes las pinta el terminal por
      encima del texto, así que la ventana se abriría debajo de la carátula, y quien
      enciende la transparencia lo hace justamente para ver lo que hay detrás. Se apagó
      por defecto para que nadie pierda resolución de carátula sin haberlo pedido.
      El ajuste viaja como clase CSS (`ModalScreen.transparent`), no como una segunda
      hoja de estilos, y se aplica también a las ventanas ya abiertas.

### Ventanas superpuestas — `styles/base.tcss`, `app.py`

- [x] **Tamaño proporcional al terminal.** Eran 84x26 fijas: en 4K, un sello en medio de
      un campo vacío. Los paneles (biblioteca, letra, ayuda) toman el 85% del terminal,
      con `min-width: 60` para el mínimo que la app acepta y `max-width: 160` porque
      pasada esa anchura una línea de pista es casi todo hueco y el ojo tiene que viajar
      para leer una fila. Los diálogos crecen con el terminal dentro de lo que pide su
      contenido.
- [x] **Velo translúcido en vez de fondo opaco.** La regla `Screen` de este fichero
      pisaba el `background: $background 60%` que Textual ya da a `ModalScreen` —un
      selector de tipo alcanza a las subclases—, así que abrir un modal borraba el
      reproductor de la pantalla. Ahora `ModalScreen` lleva `$tidalamp-screen 55%` y las
      cajas van esmeriladas (`panel 85%`, borde al 70%), de modo que el borde de la
      ventana se lee como cristal sobre el reproductor y no como un bisel recortado
      encima. Un terminal no sabe desenfocar; el velo es lo que hace de desenfoque.
      El 85% del panel no es capricho: al 60% se transparentaba el texto de la cola a
      través de los diálogos, y eso parece un fallo de dibujo, no cristal.
- [x] **El fondo se congela mientras hay un modal delante**, que es lo que hace que el
      velo salga gratis. Con la pantalla translúcida, Textual ya no puede saltarse lo
      que hay debajo: cada fotograma del analizador repintaba el reproductor y volvía a
      mezclar el terminal entero, diez veces por segundo. Medido en 240x62 con la
      biblioteca abierta: **37,7% de un núcleo contra 0,5%** con el fondo quieto, y el
      opaco de antes costaba 8,8%. `_tick_fast` sale antes de animar y `_tick_slow` no
      mueve reloj, barra ni volumen mientras `len(screen_stack) > 1`.
      - Sigue corriendo lo que no es cosmético: fin de pista, `mpv.alive`, MPRIS y el
        botón de play/pausa cuando el estado da la vuelta, para que cerrar el modal no
        enseñe un glifo viejo.
      - La línea de estado es la excepción deliberada: un favorito añadido desde el
        navegador informa ahí y a través del velo se lee. Se escribe siempre, pero sólo
        cuando cambia (`_refresh_status`), porque `Static.update()` repinta aunque las
        palabras sean las mismas y esto corre cuatro veces por segundo.
- [x] **La carátula de medios bloques ya no se retira** al abrir un modal: son
      caracteres normales y la ventana se dibuja encima sin más. La de kitty o sixel
      sigue retirándose, y no es un descuido: el terminal pinta esas imágenes por encima
      de las celdas, así que el modal se abriría *debajo* de la carátula. Quien quiera
      verla mientras navega puede poner `Carátula: blocks` en la pantalla de `o`.
      La decisión se toma por el protocolo de la carátula que hay puesta, no por el que
      el terminal sabría hacer.

### Robustez — `net.py`, `player.py`, `auth.py`

- [x] `net.with_retries()`: 3 intentos con backoff 0.6s→1.2s. Reintenta lo transitorio
      (conexión, timeout, 408/429/5xx) y propaga de inmediato lo que no va a cambiar
      (401, 404). Envuelve `track.get_stream()`, `entry.resolve()` y los niveles de la
      biblioteca.
- [x] **El 429 convertido por tidalapi también es transitorio.** tidalapi 0.8.11
      transforma el `requests.HTTPError` en `TooManyRequests`, así que se reconoce ese
      tipo explícitamente y se respeta su `retry_after`. `-1` cae al backoff anterior;
      más de 60 s se relanza para que la TUI lo explique en vez de parecer congelada.
- [x] `Mpv.alive` / `Mpv.restart()`: si el proceso muere, el tick lo detecta, lo
      relanza con el volumen guardado y recarga la pista en curso. Antes la UI se
      quedaba congelada contra un socket muerto.
- [x] `auth.ensure_fresh()`: comprueba la sesión antes de resolver cada pista y la
      refresca con el refresh token si el access token caducó, reguardando el fichero.
      Sólo exige `tidalamp login` cuando ya no queda nada que refrescar.
- [x] **`load_session()` también refresca al arrancar.** Antes no: un access token
      caducado —lo normal al abrir la app al día siguiente— hacía que
      `load_session_from_file()` de tidalapi validara el token con una petición y
      dejara escapar un `HTTPError 401` crudo, así que el usuario veía un traceback con
      un refresh token perfectamente bueno al lado. Ahora se atrapa, se refresca y se
      **rehace el handshake**: `token_refresh()` sólo cambia el access token, y sin
      `load_oauth_session()` la sesión vuelve a medias, sin usuario, país ni session id.
      El refresh token se lee del propio fichero si la carga falló antes de asignarlo.
- [x] Registro opcional: `TIDALAMP_DEBUG=1` escribe en
      `~/.local/state/tidalamp/tidalamp.log`. Sin él, un `NullHandler` en el paquete
      evita que el handler de último recurso de `logging` pinte sobre la TUI.
- [x] Instrumentación de la rama de manifiesto: `stream.resolve()` registra si tomó
      `BTS` o `MPD`, y `Playable.manifest` lo expone.

### Espectro — `spectrum.py`, `analyzer.py`

- [x] `Cava`: escribe una config en cache, lanza `cava -p`, y un hilo lee frames
      binarios (un byte por banda) quedándose sólo con el último; la UI muestrea a su
      ritmo y los frames viejos no le sirven de nada.
- [x] `Analyzer` tiene dos modos y `Analyzer.source` (`FFT`/`RMS`) dice cuál está
      activo; la insignia del display lo enseña, así que nunca se presenta como FFT lo
      que no lo es.
- [x] Degradación limpia: sin cava, si muere, o si no puede abrir el sink, se vuelve al
      vúmetro RMS sin cortar la reproducción.
- [x] Con espectro real no se aplica la ponderación por bandas del vúmetro: cava ya
      suaviza, y reponderar sólo distorsionaría lo que ha medido.
- [x] **Cuatro formas, un ajuste** (`visualizer`): `bars` son las barras de siempre,
      `mirror` las hace crecer hacia arriba y hacia abajo desde una línea central,
      `curve` dibuja el contorno del espectro con un glifo por columna, y `fine` dibuja
      esa misma línea sobre la rejilla de puntos del Braille.
- [x] **Las tres se dibujan en el mismo sitio**: el widget del readout, al lado de la
      carátula y bajo los datos de la pista, y las tres llegan al borde derecho. Hubo
      una versión con una fila propia a todo el ancho bajo el reproductor y estaba mal
      por dos motivos: empezaba debajo de la carátula en vez de al lado, y le quitaba
      cinco filas a la cola. Un widget, un `mode`, cero cambios de disposición.
- [x] Las barras ya no se paran a las 19. Eso dejaba vacíos dos tercios de la columna
      en cualquier terminal ancho, que es donde se pasa el rato.
- [x] A cava se le piden `Analyzer.BANDS` (128) bandas, que no es lo que dibuja ninguna
      de las tres: cada forma remuestrea ese frame a lo suyo. Pedirle exactamente lo
      que hay en pantalla obligaría a reiniciar el proceso en cada redimensionado y en
      cada cambio de forma, y un reinicio es un hueco en la imagen. Al bajar se
      promedia y al subir se interpola: lo segundo es un dibujo más suave de la misma
      curva, no una medición más fina, y nada aguas abajo la trata como tal.
- [x] **El coste en 4K era el problema, y eran las secuencias de escape.** Rich hace un
      tramo (`Span`) por cada `append`, y el terminal una secuencia por tramo. Sin
      topar las bandas y con un `append` por celda, a 380 columnas eran **950 tramos
      por frame** a 10 fps. Dos arreglos:
      - `MAX_BARS = 64`: las barras se topan ahí y se **ensanchan** para cubrir el
        ancho en vez de multiplicarse y adelgazar. `_slots()` reparte el ancho exacto
        entre las bandas (`width * i // count`), porque un `width // count` a secas
        deja hasta `count` celdas sin pintar a la derecha, que es justo el borde al que
        estas formas existen para llegar.
      - `_runs()`: una línea se manda como un tramo por **racha de mismo estilo**, no
        uno por celda. Un espectro real es sobre todo tramos largos del mismo color.
      Y de paso `_styles()` resuelve la paleta y el color de cada banda **una vez por
      frame**; antes era una llamada a `palette_for` por celda, mil por frame.
- [x] Medido a 380x50 (un 4K), 10 fps, con la app real headless: **54,5% de un núcleo
      antes, 7,3% después** en `bars`; 57,9% → 8,2% en `mirror`; 12,2% → 7,7% en
      `curve`. Los tramos por frame pasan de 950 a 76 en `bars`. Dos pruebas lo fijan:
      una con un espectro con forma de música y otra con uno construido para reventar
      las rachas, que comprueba el techo duro de `filas × MAX_BARS`.
- [x] `mirror` usa medios bloques en las dos mitades en lugar de la rampa de octavos de
      las barras: la gracia de la forma es la simetría, y una mitad dibujada ocho veces
      más fina que la otra no la tiene. Con menos de tres filas —la disposición compacta
      deja una— no hay dónde poner la línea central y dibuja `bars`.
- [x] `curve` dibuja un glifo por columna y nada debajo. Eso es lo que la hace una
      línea y no una segunda forma de barras. Sus celdas vacías van sin estilo, así que
      una fila callada entera es una sola racha.
- [x] `fine` es la misma línea sobre Braille: una celda es una rejilla de 2x4 puntos y
      un punto de código los lleva los ocho (`U+2800` más un bit por punto), así que
      hay ocho posiciones direccionables donde antes había un bloque.
- [x] Lo que `fine` gana sobre `curve` **no es precisión vertical**: la rampa de
      octavos tiene ocho pasos por celda y los puntos tienen cuatro. Gana las dos cosas
      que hacen que una línea sea una línea: el doble de resolución horizontal —dos
      bandas por columna— y que se encienden también los puntos entre una muestra y la
      siguiente, encontrándose con los vecinos a mitad de camino. Sin eso es una fila
      de marcas sueltas y cada pendiente fuerte se rompe en huecos.
- [x] Una celda es un glifo y no puede ser de dos colores: el color de la celda sale de
      la más fuerte de sus dos bandas.
- [x] `fine` **necesita una fuente con Braille** y no hay manera de preguntárselo al
      terminal por adelantado. Casi todas lo traen (las Nerd Fonts, DejaVu, Noto), pero
      una que no dibuja cuadraditos. Por eso es una forma que se elige a mano y no una
      a la que nada cae solo, y el ajuste lo dice en su nota. No se intenta detectar:
      una detección que no puede acertar es peor que la advertencia.
- [x] `curve` y `fine` son las dos sin tope de bandas: su gracia es justo la resolución
      por columna. `fine` cuesta 1,69 ms de render a 380 columnas frente a 0,86 de
      `curve`, y 12 tramos por frame; a 380x50 la app va a 9,5% de un núcleo contra el
      8,0% de `curve`. Sigue a un mundo del 55% que había que arreglar.
- [x] Hubo un `waterfall` (espectrograma desplazándose). Se quitó: en cinco filas y con
      medios bloques se veía como una mancha, no como un espectrograma.
- [x] Un nombre que no esté entre los cuatro cae a `bars`. El ajuste sale de un fichero
      que se edita a mano.

### Dos teclas que unifican lo que ya había — `app.py`

- [x] **`space` reproduce y pausa**, detrás de `x`. Va segunda a propósito: `_button_key`
      dibuja en el botón del transporte la **primera** tecla enlazada, así que el botón
      conserva su letra de Winamp y el espacio no la ensucia. Nada en la ventana
      principal la usaba, y es lo que hace cualquier otro reproductor.
- [x] **`m` (`track_menu`) abre sobre la fila de la cola el mismo menú** que la
      biblioteca abre con ↵. Allí hay que preguntarlo porque ↵ encola el nivel entero;
      aquí ↵ ya reproduce la fila, así que todo lo demás que el menú ofrece no tenía por
      dónde entrar.
- [x] La única respuesta que difiere es `play`: en el navegador manda el nivel a la cola
      y arranca ahí, y en la cola el nivel **ya es** la cola, así que sólo arranca. El
      resto reutiliza `_browser_result`, que ya sabía qué hacer con cada una.

### Cola: deshacer el vaciado — `app.py`

- [x] `C` vacía sin preguntar, y `c` detiene: un resbalón con shift borraba la cola. `u`
      la devuelve, con el cursor donde estaba.
- [x] **Deshacer y no confirmar.** Una confirmación molesta las cien veces que sí
      querías vaciar y sirve la que no; deshacer no cuesta nada cuando no hace falta.
- [x] No reanuda la reproducción. Vaciar detuvo, y devolver la lista no es devolver el
      sonido: una canción arrancando sola porque alguien deshizo un error sorprende más
      que el error.
- [x] Un solo nivel y en memoria. `_sync_queue` ya reescribió `queue.json` cuando se
      pulsa la tecla, así que lo restaurado vive sólo en RAM; cerrar la app entre medias
      lo pierde, y está bien: esto es para el resbalón de hace dos segundos.
- [x] Un segundo `C` reemplaza lo guardado. No es una pila.

### Balance y ecualizador — `settings.py`, `player.py`, `app.py`

- [x] `Mpv.set_filter(label, graph)`: `af remove @label` + `af add @label:lavfi=[…]`.
      No se usa `af set` porque reemplazaría toda la cadena y se llevaría por delante
      el `astats` del vúmetro.
- [x] Balance como filtro `pan`; ecualizador de 10 bandas (las de Winamp, 60 Hz–16 kHz,
      ±12 dB) como `equalizer` encadenados. Las bandas planas no entran en el grafo y
      con todo neutro no se instala filtro alguno, para no reinicializar la cadena en
      balde.
- [x] `EqScreen`: ventana con las diez barras, `←→` banda, `↑↓` ±1 dB, `0` plano, y el
      balance también ahí. Se aplica en vivo.
- [x] Persistencia en `~/.local/state/tidalamp/settings.json`, y reaplicado tras un
      reinicio de mpv (un proceso nuevo arranca con la cadena vacía).
- [x] Los filtros sólo se reconstruyen al arrancar, cambiar un ajuste o reiniciar mpv;
      el tick de sondeo no toca la cadena y evita cortes de audio periódicos.

### Letras — `lyrics.py`, `app.py`

- [x] `y` abre un modal para la pista actual; la carga se ejecuta en un worker y no
      bloquea la reproducción ni el loop de Textual.
- [x] Parseo de subtítulos LRC con varias marcas por línea, fracciones de distinta
      precisión, orden cronológico y resaltado según `mpv.position` a 4 Hz.
- [x] Fallback a texto plano con scroll manual cuando TIDAL no entrega timestamps.
- [x] Reutiliza refresco de sesión, reintentos de red y una cache por pista durante la
      sesión. Una letra ausente muestra un error local sin afectar al reproductor.

### Carátula — `artwork.py`, `widgets.py`

- [x] Tres salidas, de más a menos fidelidad: protocolo gráfico de kitty (PNG en
      trozos base64), sixel (cuantizado a 255 colores y codificado por longitud de
      series) y medios bloques `▀`, que no necesitan protocolo alguno y funcionan en
      cualquier terminal.
- [x] Detección por entorno (`$TERM`, `$TERM_PROGRAM`, `$KITTY_WINDOW_ID`) con
      `TIDALAMP_ART=kitty|sixel|blocks|off` para forzarla. **No se consulta al
      terminal**: la respuesta entraría por el mismo canal que el teclado y Textual la
      leería como pulsaciones.
- [x] Descarga en un worker, con los reintentos de `net.py`, y cache en
      `~/.cache/tidalamp/art/` con la URL como clave. Una cache que no se puede
      escribir no impide ver la carátula.
- [x] Recorte centrado al aspecto del recuadro antes de escalar, para no deformar una
      portada cuadrada dentro de un rectángulo de celdas.
- [x] El recuadro **crece con el terminal** (`Artwork.resize`, `TidalAmp._fit_artwork`):
      de 18×9 en el mínimo de 76×20 hasta 40×20, con dos topes — un cuarto de la altura,
      para no comerse la playlist, y lo que deje la fila que comparte con el reloj (24
      celdas) y el marquee (30). Un terminal alto pero estrecho se queda en 18×9. Al
      cambiar de tamaño se vuelve a pedir la carátula, porque la que había era del
      tamaño viejo. El analizador pasó a `height: 1fr` para llenar la banda que crece.
- [x] La banda se dimensiona a la carátula **más el relleno vertical que le ponga la
      estructura**. `height` es border-box, así que el `padding-top` de `nova` salía
      del contenido: la banda medía 10 filas, dentro quedaban 9 y la imagen se dibujaba
      a 10. Un protocolo gráfico no se recorta a su widget, así que la fila sobrante
      caía sobre la barra de posición. Ahora cualquier estructura puede separar el
      contenido sin que la carátula se derrame.
- [x] Pillow es opcional: sin él `decode()` devuelve `None`, no hay carátula y no
      cambia nada más. Mismo trato que cava. **Pero se avisa**: `have_decoder()` se
      consulta al final de `on_mount` y la barra de estado nombra `".[art]"`. Antes el
      widget se quedaba oculto en silencio y un clon recién hecho parecía roto — es
      justo lo que pasó al clonar el repo en otro equipo (2026-09-08).
- [x] Las imágenes de kitty y sixel se pintan por encima del texto, en una capa que el
      compositor de Textual desconoce: la carátula se retira al apilar una pantalla
      modal y se restaura desde el tick lento al desapilarla, y se borra por id al
      desmontar el widget.

### Barra de transporte — `app.py`, `styles/player.tcss`

- [x] **Velocidad de reproducción** (2026-09-11). `b` o el botón del transporte abren
      `SpeedScreen` (`screens/speed.py`) con `Mpv.SPEEDS`: 0.25 a 2 en cuartos, 1 la
      grabada. Se aplica con ↵ o con un clic, no al mover el cursor, para no arrastrar
      la canción por cada velocidad intermedia. mpv no acepta 0 ni negativas (lo
      negativo sería reproducir al revés, que con los streams de TIDAL no puede).
      El botón va con aleatorio y repetición, se enciende fuera de 1× y tiene ancho
      fijo (`0.25×`) para que la fila no se mueva; el reproductor compacto lo deja
      fuera y conserva la tecla. `Mpv.speed` se reaplica en `restart`, como el
      volumen. No se guarda en `config.toml`: dura hasta salir. mpv conserva el tono
      con un filtro, así que fuera de 1× la señal deja de ser bit-perfect.
- [x] **La velocidad por MPRIS** (2026-09-11). `Rate` se lee y se escribe,
      `MinimumRate` y `MaximumRate` son los extremos de `Mpv.SPEEDS` y `publish()`
      avisa cuando cambia. `mpris_set_rate` redondea al cuarto más cercano, para que
      el botón y la ventana sigan diciendo una de las ocho, e ignora 0 y lo negativo
      (la especificación pide pausar en vez de poner 0).
- [x] **El reloj en cuenta atrás** cabe: `-03:17` eran seis glifos de cuatro columnas
      en un reloj de veinte, las filas se partían y los dígitos salían a trozos. El
      menos ocupa ahora una columna pegada al primer dígito y no sobra espacio al
      final. Venía así desde el primer commit y nadie lo había probado.

- [x] Dos mitades en un `Horizontal`: a la izquierda las teclas de transporte, a la
      derecha las ventanas alineadas al borde (`width: 1fr; text-align: right`). Antes
      era una sola cadena y el menú arrancaba pegado a `b ▶▶`.
- [x] El transporte se dibuja como **botones enmarcados de tres filas**, agrupados en
      dos marcos segmentados —`╭──┬──╮`— y no en seis cajas sueltas: dentro de un grupo
      los botones comparten marco, así que la fila se lee como un control y no como un
      montón de cajas sin orden. Son dos grupos porque son dos clases de cosa: el
      transporte hace algo y vuelve, mientras que shuffle y repetición se quedan
      pulsados. El ancho de cada celda sale de `cell_len()` sobre su rótulo, no de
      `len()`: `◀◀` y `▶▶` no miden una celda en todos los terminales.
- [x] Separador `·` en el color atenuado de la paleta para el menú de la derecha, no
      `│`: es una lista de cosas pequeñas y una barra sólida entre cada una pesa más
      que lo que separa. `_separated()` parte la cadena traducida y atenúa sólo los
      separadores, así que el catálogo sigue teniendo una entrada por mitad.
- [x] El menú se **recorta a mano** al ancho de su widget. `text-wrap: nowrap` de la
      hoja de estilos no sirve sobre un `Text` de Rich —comprobado—, y al envolverse se
      metía en las filas donde se dibujan los botones. Como `? ayuda` va primero, lo
      que se pierde es la cola. El recorte necesita el ancho, que sólo existe tras el
      layout, así que `_check_size()` vuelve a pintar la barra al redimensionar.
- [x] Shuffle y repetición dejaron de ser una fila propia con las palabras
      `SHUF OFF` / `REP ALL`: ahora son dos botones más del transporte, `s ⇄` y `r ↻`,
      encendidos con el acento del tema cuando están activos. Repetir-una es `r ↻1`,
      porque es el único estado que el color no puede decir solo.
- [x] `↻ ` y `↻1` miden lo mismo a propósito: al cambiar de modo la fila no se desplaza.
- [x] Play y pausa son **un solo botón y una sola tecla**: `x ▶` parado o en pausa,
      `x ‖` sonando —el icono es la acción que hará al pulsarlo—. `action_play` cubre
      los tres estados. La `c` de Winamp desapareció: después de fusionar los botones
      hacía exactamente lo mismo que `x`, y dos atajos para una función es el desorden
      que la fusión venía a quitar. `pause` ya no está en `DEFAULT_KEYS` ni en la
      plantilla de configuración; el toggle sobrevive como `_toggle_pause()`, sin
      prefijo `action_`, porque MPRIS `PlayPause` lo usa y nada del teclado lo alcanza
      —un nombre bindeable que no se puede bindear miente en el fichero de config.
- [x] El botón sigue el estado desde `_tick_fast`, pero sólo repinta cuando el estado
      cambia de verdad: ese tick corre diez veces por segundo.
- [x] `? ayuda` va primero en el menú: en un terminal estrecho el bloque derecho se
      recorta por la derecha, y la entrada que explica todas las demás sobrevive.

### Disposiciones como datos - `layouts.py`, `app.py`

- [x] Lo que distingue una disposición de otra vive en una `Layout` por entrada de
      `LAYOUT_TABLE`: el título (`title(width)`), el encabezado de la cola
      (`queue_heading(width, hints)`), qué `_transport_<nombre>` dibuja los botones y
      el presupuesto de glifos (`ascii_only`). Antes eran cuatro cadenas de
      `if config.THEME ==` repartidas por `app.py`; con más disposiciones en camino
      (`next.md` §1 y §2) cada una nueva se habría pagado en cuatro sitios.
- [x] `theme.LAYOUTS` sale de la tabla, así que la pantalla de ajustes, la plantilla
      de config y la app no pueden desincronizarse. Un nombre desconocido cae en
      `quattro` (`layout_for`).
- [x] Los encabezados son funciones y no cadenas: el texto pasa por `_()` al
      dibujarse, porque el idioma cambia en caliente, y cada `_()` conserva un literal
      para que el test del catálogo lo encuentre.
- [x] El transporte sigue siendo código (`_transport_*` en la app): cada disposición
      dibuja sus botones de forma demasiado distinta para que una tabla de glifos no
      sea un programa disfrazado. Un test comprueba que cada entrada nombra un
      constructor que existe, y otro que las disposiciones con `ascii_only` pintan
      título, marco del encabezado y transporte en ASCII puro.
- [x] **Emparejamiento por nombre** (`theme.PAIRED`, `paired_palette`). Un tema
      temático es una disposición y una paleta incorporada con el mismo nombre. Elegir
      la disposición en ajustes escribe esa paleta en el config **una vez**
      (`ConfigScreen._pair_palette`) y ahí acaba: cambiar la paleta después, o salir
      a otra disposición, no la revierte. `load_palette(name="auto")` no se tocó a
      propósito: `auto` es la elección «sigue a mi escritorio» y pisarla sería
      restringir la paleta.
- [x] Las parejas se **declaran**, no se deducen: un test exige que los nombres
      compartidos entre `LAYOUTS` y `_BUILTIN_SOURCES` sean exactamente `PAIRED`.
      Sin eso, añadir una paleta `nova` recolorearía la disposición `nova` para todo
      el mundo. Las paletas de usuario no emparejan nunca.
- [x] Contraste mínimo en las paletas incorporadas (`contrast_ratio`, WCAG): `body`
      contra `screen` a 4,5 y `accent` contra `screen` a 3,0. Las seis actuales pasan
      con holgura (la peor, `gruvbox`, deja el acento en 6,6).
- [x] **Nueve temas temáticos** (2026-09-10): `unidad-morada`, `pirata`, `cuaderno`,
      `neon-noir`, `runas`, `reggae`, `comodin`, `gotico` y `death-metal`. Los nombres
      **evocan sin nombrar**, por decisión del mantenedor: seis de las fuentes son
      marcas registradas y tidalamp se publica a nombre propio. Cada uno es una
      `Layout`, una paleta en `_BUILTIN_SOURCES` y su nombre en `PAIRED`.
- [x] **`bosque`**, el décimo (2026-09-11): temática ecológica, verde hoja sobre musgo.
      No evoca ninguna obra: su emblema (un árbol y brotes sobre medio globo) está
      dibujado desde cero, así que no depende del aviso de `tidalamp/emblems/NOTICE`.
- [x] **Marcos más finos** (2026-09-11). `ruled` acepta un patrón además de un glifo
      (repetido, cortado a la medida y reflejado a la izquierda), y cada temático
      tiene el suyo: franjas, olas, línea punteada de cuaderno, tubo de neón, cenefa
      con rombos, olas con notas, los cuatro palos, reja, ruido y la enredadera de
      `bosque`. `Layout.frame_subtitle` es un remate centrado al pie del marco
      (`border_subtitle` del panel; se asigna solo cuando cambia, porque corre en
      cada resize). `Layout.tint` y `tint_colors` tiñen glifos del título por turnos
      con roles de la paleta, y `flourish_colors` los del remate: las notas de
      `reggae` van verdes y rojas entre olas doradas, y rojo, oro y verde al pie. Los
      cuatro básicos no se tocaron: quattro y retro imitan a Winamp, `ascii` es
      solo ASCII y nova no tiene marco a propósito.
- [x] **Forma de la carátula como ajuste**, `cover_shape` (`square` o `round`), con
      cualquier tema. `artwork.shape` corta la imagen ya encajada con una máscara
      dibujada a 4x y reducida, y pinta las esquinas con el fondo real de la banda
      (`#display`, que en nova y `cuaderno` es el panel): sixel no tiene alfa fiable
      y los bloques ninguna, así que así se ve igual en los tres. `_art_look` guarda
      con qué forma y fondo se cortó la que está en pantalla, y `_reshape_art` la
      vuelve a pedir si un cambio de tema o de ajuste los cambia. Se probó también
      que cada tema cambiara la barra, los sliders y el analizador (`Skin`); al
      mantenedor no le gustó y se quitó entero.
- [x] **`rounded`**, la tercera forma (2026-09-11): el cuadrado con las esquinas
      redondeadas, `rounded_rectangle` sobre la misma máscara a 4x, con un radio del
      12 % del lado. En proporción y no en píxeles fijos: en `blocks` una celda son
      cuatro píxeles, y un radio pensado para kitty desaparecería.
- [x] **Los nombres de los temas en el idioma en uso** (2026-09-11). `layouts.label`
      da la etiqueta (`bosque` → forest, `pirata` → pirate…) y la usan la ventana de
      ajustes (tema, paleta y fondo de la cola) y la barra de estado. `config.toml`
      guarda siempre el nombre de la tabla. Trampa ya pisada: `_cycle` buscaba la
      etiqueta entre los nombres guardados, no la encontraba y volvía al primero;
      ahora recorre `_stored`, y un test en inglés da la vuelta entera a los temas en
      los dos sentidos.
- [x] El transporte de `ascii` pasó a `_transport_keycaps`, con las tapas de cada tecla
      en `Layout.keycaps`: `ascii` las deja en `[ ]` y en glifos ASCII, y cinco temas
      traen las suyas (`⟦ ⟧`, `( )`, `▐ ▌`, `{ }`, `╣ ╠`). Los demás reutilizan
      `quattro`, `retro` o `nova`. La estructura propia de cada uno (marco, qué barras
      llevan fondo, alineación) vive en su bloque de `styles/themed.tcss`.
- [x] Las paletas nuevas se quedan en el vocabulario de Omarchy. Añaden
      `dark_foreground` a los diez básicos, por la razón que da `black`: sin él, el
      texto secundario brilla igual que el principal.
- [x] Un test prohíbe glifos anchos (East Asian Width `W`/`F`) en título y encabezado:
      `⚓`, que se presenta como emoji, ocupa dos celdas en casi todos los terminales y
      echaba las pistas del encabezado fuera del marco. Rich lo mide como dos, pero el
      encabezado se había compuesto contando uno.
- [x] Vistos en capturas SVG de Textual a 120x34 y 80x26, con su paleta. Ojo al
      mirarlas: `rsvg-convert` tira de fuentes de reserva más anchas para `▰`, `☠` o
      `◢` y parece que desbordan; `render_line` confirma que ocupan exactamente el
      ancho del widget. Vistos después en el terminal del mantenedor, los nueve, con
      su emblema detrás de la cola (2026-09-11).
- [x] **Emblemas y guiños** (2026-09-11). Cada tema temático tiene una imagen, un
      PNG pequeño en `tidalamp/emblems/` (`Layout.emblem` es su nombre), y una frase
      guiño (`Layout.tagline`) que va en el marquee cuando no suena nada y en el panel
      de letra de split cuando no hay letra.
- [x] **La imagen es el fondo de la cola, dibujada como la carátula**
      (`artwork.emblem_cells`, `RowList.render_line`). Cuatro píxeles por celda con
      los glifos de cuadrante y color real: en una celda vacía va el glifo con sus
      dos colores; en una con letra, el color medio de sus cuatro píxeles como fondo,
      y la letra conserva el suyo. Ocupa como mucho el 70 % del alto y el 55 % del
      ancho de la cola, contra el borde derecho, y escala a cualquier tamaño, así que
      crece en 4K. Un velo oscuro, como el de detrás de un modal, la mezcla al 30 %
      con el fondo de la cola. La fila del cursor no se toca. Sin Pillow no hay
      emblema, igual que no hay carátula.
- [x] Trampa: un píxel de cuadrante es media celda de ancho por media de alto, es
      decir, **el doble de alto que de ancho**, igual que la celda. Muestrear la
      imagen como si fuera cuadrado la aplastaba de lado (la luna salía huevo). Se
      calculan columnas y filas con esa proporción; un test lo fija con la luna.
- [x] **Fondo de la cola como ajuste propio** (`backdrop`, «Fondo de la cola»):
      `auto` es la imagen del tema (y el valor por defecto, para que las
      configuraciones que ya existían se vean igual), `none` la quita y el nombre de
      cualquier tema temático toma prestada su imagen con su colocación
      (`layouts.backdrop_for`). Elegir un tema temático en ajustes escribe su paleta y
      su fondo una vez (`ConfigScreen._pair_palette`); después los tres ajustes son
      libres y se pueden mezclar.
- [x] Colocación por tema (`Layout.emblem_anchor`, `Layout.emblem_scale`): `middle`
      centra el emblema en el borde derecho y `bottom` lo mete en la esquina inferior
      derecha, a una fila del borde; la escala agranda el espacio que puede ocupar,
      nunca más que la cola. A elección del mantenedor: la bandera pirata abajo y un
      30 % mayor, la ciudad de neón abajo, el Joker abajo y un 15 % mayor; el resto,
      en medio.
- [x] Rendimiento: la primera versión cortaba cada línea en cada celda del emblema con
      `Strip.divide`, y la cola pasó de 11 a 61 ms por repintado (274x100, 90 filas);
      se notaba al mover el cursor. Ahora `RowList._paint` recorre la línea una vez
      juntando celdas del mismo estilo, los estilos de cada celda se construyen una vez
      por tamaño y paleta, y las líneas pintadas se cachean por contenido: 17 ms con
      la caché caliente y 26 en frío.
- [x] Al salir de split, la banda de la carátula cambia de sitio sin cambiar siempre de
      tamaño, y una carátula kitty se queda donde se pintó hasta que alguien la borra:
      `_replace_pixel_cover` la quita y la vuelve a poner, así que se borra la
      colocación vieja, haga lo que haga el terminal. La letra sin sincronizar avanza
      sola en el panel de split con la canción (`LyricsPane._plain_start`): sin
      marcas de tiempo no hay línea que seguir, y el panel no tiene teclas propias
      porque son de la cola. Las dos cosas eran lo que quedaba de split en `next.md`.
- [x] Trampa de la carátula de píxeles tras una ventana: `_art_ready` la ponía y
      llamaba a `_hide_art` para quitarla, pero `_hide_art` vuelve sin hacer nada si ya
      hay una oculta, y la hay siempre que la ventana se abrió sobre una carátula kitty
      o sixel. Una segunda carátula (pista cambiada desde la biblioteca, o el tema
      cambiado en ajustes, que vuelve a medir el recuadro y la descarga otra vez) se
      quedaba pintada encima de la ventana. Visto por el mantenedor sin poder
      repetirlo, porque depende de que hubiera una carátula de píxeles al abrir. Ahora
      la que llega con una ventana delante se guarda para cuando se cierre, con test.
- [x] **4K** (2026-09-11). Medido en un pty con pyte a 480x130: cada movimiento del
      cursor mandaba al terminal **245 KiB** con un emblema detrás (39 sin él),
      porque `cursor` repintaba la lista entera y la lista seguía al cursor al
      centro, así que pasada la mitad cada pulsación desplazaba todas las filas.
      Ahora `watch_cursor` repinta solo las dos filas que cambian si la ventana no se
      mueve, y la ventana (`_window_start`) solo se desplaza cuando el cursor sale
      por un borde, y entonces media pantalla, dejándolo en el centro: **0,6 KiB**
      por pulsación dentro de la ventana y 4,4 de media recorriendo la cola entera.
      Sin tocar la imagen: se probó bajar a 16-32 colores, fusionar celdas parecidas
      y poner tope de filas, y se descartó a petición del mantenedor (bajaba la
      calidad por un 15-30 % de bytes). Se quedaron los cambios sin pérdida: el velo
      aplicado a la imagen entera con Pillow, un objeto `Style` compartido por par de
      colores y el atajo en las celdas vacías.
- [x] Textual no rellena las líneas al ancho del widget (`Visual.to_strips` con
      `pad=False`): la que sigue a la última fila llega vacía, y el emblema se perdía
      en ella. Cada línea se rellena al ancho del contenido antes de pintar; un test
      pone el final de la cola en mitad del dibujo. El mantenedor vio además el
      emblema cortado a partir de la última fila; el relleno lo arregló (confirmado en
      su terminal). El relleno va con el estilo de fondo del widget: con espacios sin
      estilo, esa línea no tenía fondo y un terminal translúcido enseñaba el fondo de
      pantalla a través, como una franja bajo la última canción.
- [x] La transparencia parcial se respeta: cada píxel se mezcla con el fondo según su
      alfa antes del velo, así que una imagen con el borde difuminado (el Ojo, el
      cuervo) se funde con la cola en vez de acabar en un rectángulo; el Joker también. Ryuk va
      recortado a su luna, con las puntas de las alas que salen de ella.
- [x] Historia, para no repetirla: primero fue un dibujo de 18x18 en letras de papel
      en el hueco de la carátula (se veía solo sin pista y los personajes no daban
      de sí); luego ese dibujo, más grande, de fondo de la cola a un píxel por dos
      celdas (poca definición, y los papeles de paleta destrozaban las fotos). La
      comparación con la carátula del mantenedor decidió el formato actual.
- [x] Trampa: `Strip.divide`, como `Segment.divide` de Rich, devuelve lo que queda
      antes de cada corte y **descarta lo que sigue al último**. Sin pasarle el final
      de la línea como corte, la cola de cada línea pintada desaparecía; en headless
      no se nota, pero el terminal real conservaba lo que hubiera en esas celdas (el
      resaltado del cursor de posiciones anteriores, en escalera). Un test compara
      cada línea con la misma sin fondo: mismo ancho, y solo los espacios pueden
      volverse glifos.
- [x] Las imágenes salen de las referencias del mantenedor (que no se versionan):
      recortadas al motivo, fondo liso a transparente, reducidas a 192 px y 48
      colores. El damero pintado de la parca se quita rellenando desde las esquinas
      con un umbral de 160 (PIL suma los tres canales). El cuervo y la parca, oscuros,
      se aclaran antes de reducirlos o desaparecen bajo el velo. La ciudad de neón
      está dibujada a mano. El Joker y Ryuk del pixel art llevan firma de otros
      artistas; se usan por decisión del mantenedor.

### Dos columnas - `app.py`, `styles/player.tcss`, `config.py`, `scrolling.py`

- [x] `compose()` pone el reproductor en `#player-half`, la cola en `#queue-half` y el
      transporte entre los dos como hermano de ambos, también en la forma apilada.
      Cambiar de forma es la clase `split` en `#main`: la CSS convierte `#main` en una
      rejilla de dos columnas con el título, el transporte y la barra de estado
      ocupando las dos (`column-span: 2`), y `_place_transport()` pasa el transporte
      detrás de la cola con `move_child`, porque la rejilla coloca las celdas en el
      orden de los hijos. `move_child` solo reordena: **no se reparenta ni se remonta
      nada**, así que el `RowList` conserva el cursor, la carátula no se vuelve a
      decodificar y el marquee no pierde la fase. Un test comprueba que son los mismos
      objetos antes y después.
- [x] El transporte fue primero dentro de la mitad izquierda. Con las teclas deletreadas
      (77 columnas en las disposiciones con tapas) el menú se amontonaba y llegaba a
      envolverse en una segunda fila; a lo ancho de las dos columnas cabe entero, y el
      umbral dejó de depender de él.
- [x] Ajuste `arrangement` (`stacked` o `split`, `TIDALAMP_ARRANGEMENT`), en la
      pantalla de ajustes bajo Apariencia. Se aplica desde `_setting_changed` llamando
      a `_check_size()`, que es quien decide la clase: no toca mpv.
- [x] Umbral propio: `SPLIT_MIN_WIDTH = 160` y `SPLIT_MIN_HEIGHT = 26`. La mitad del
      reproductor necesita reloj y readout (54 columnas) más la carátula, casi las 80
      de la forma apilada entera. Por debajo **vuelve sola** a apilada y la línea de
      estado dice cuánto hace falta.
- [x] **La letra arriba** (`LyricsPane`). En split la columna del reproductor sobraba:
      la primera versión estiraba la banda del display a `1fr` y quedaba un analizador
      enorme sobre media pantalla vacía. Ahora la banda conserva su alto apilado, abajo
      con los sliders, y el panel de letra ocupa el resto, separado por una regla en
      el color del marco. Carga en un worker una vez por pista, con la misma caché que
      `y`, y el tick lento lo sincroniza: la línea que suena en el acento, centrada, y
      lo ya cantado atenuado. `follow()` solo repinta cuando cambia la línea.
- [x] El resto de lo que se dibuja por ancho (título, encabezado de la cola, menú del
      transporte) ya se medía contra su propio widget; como el panel no cambia de
      tamaño al cambiar de forma y no llega ningún resize, `_refresh_widths()` se vuelve
      a llamar con `call_after_refresh`.
- [x] Aire alrededor de la carátula (2026-09-10, a petición del mantenedor tras verlo en
      su terminal): la banda lleva una fila arriba y otra abajo y dos celdas a la
      izquierda. Antes iba pegada al marco a propósito, con la idea de que un hueco la
      hacía parecer suelta; en uso se leía como pegada al borde. `_fit_artwork` resta
      las dos columnas y `_fit_display_band` ya sumaba el padding vertical.
- [x] El seek es una línea con un punto (`●`), lo reproducido en `━` del acento, y una
      fila de margen hasta el volumen (no en compacto). El `▓` de antes, de celda
      entera, parecía un bloque clavado en la barra.
- [x] En split, quattro perdía el título: la fila de la rejilla mide el widget y no
      cuenta márgenes, y su margen inferior se comía la única fila. Ahí ese aire va como
      alto (`height: 2`). Un test recorre las trece disposiciones en las dos formas.
- [x] `Glide` (`scrolling.py`): artista, disco y año bajo el reloj, `SRC`, `OUT` y el
      título. Una línea que cabe se ve entera; una que no, se para unos dos segundos,
      se desliza una celda cada 0,3 s hasta que se ve su final, se para y vuelve. Varias
      líneas comparten fase y cada una se detiene en su final. Corta en fronteras de
      grafema (`_window`). Antes se recortaban y el final se perdía; el título daba la
      vuelta en bucle con `***`, rápido. Se para detrás de un modal, como el resto.
- [x] `Measured(Static)` para lo que se dibuja a su propio ancho (título, encabezado
      de la cola, menú del transporte): se redibuja en su propio `on_resize`. Al volver
      de split desde ajustes, en el terminal del mantenedor el encabezado se quedaba
      medido a media anchura y las pistas acababan a mitad de fila; el
      `call_after_refresh` no llegaba después del layout del fondo. En headless no se
      reproduce, así que no hay test que falle sin el arreglo: **comprobarlo a mano**.

### Configuración — `config.py`, `audio.py`, `screens/config_window.py`

- [x] `o` abre `ConfigScreen`. Todo lo que hoy se configuraba editando el TOML o
      exportando una variable está ahí: calidad, carátula, idioma y registro.
- [x] `config.set_option()` escribe **una línea a la vez** y descomenta en su sitio la
      que ya trae la plantilla, en vez de volcar un dict: una ida y vuelta por el
      parser devolvería los ajustes y tiraría todos los comentarios del usuario. Se
      detiene antes del primer `[sección]`, así que una clave de `[keys]` que se llame
      igual que un ajuste no se confunde con él.
- [x] `config.reload()` recarga los globales tras escribir. `stream.py` y `auth.py`
      pasaron a leer `config.DEFAULT_QUALITY` por el módulo en vez de importar el
      nombre: un `from .config import DEFAULT_QUALITY` se queda con el valor del
      import y un cambio no llegaría nunca.
- [x] **El idioma es por fin un ajuste.** Antes sólo salía de `$LANG`, que es ambiente
      y no elección: era el único que no se podía dejar escrito. `i18n.selected()` mira
      primero el ajuste y cae al locale si dice `auto`.
- [x] `config.overridden()` delata la variable de entorno que pisa un ajuste. Una
      pantalla que mostrara un valor que la aplicación no está usando mentiría.
- [x] `audio.py` responde a lo que ningún otro módulo puede ver: PipeWire corre su
      grafo a un solo ritmo y remuestrea todo hacia él, así que un 24/96 llega al DAC
      a 48 kHz **con la insignia diciendo la verdad sobre el stream**. La pantalla lo
      dice, escribe el drop-in de `allowed-rates` y reinicia los servicios.
- [x] El reinicio para la reproducción antes: mpv tiene el sink abierto y no se le
      puede quitar el demonio de debajo. `TIDALAMP_NO_RESTART` lo desactiva.
- [x] Avisa cuando la salida es Bluetooth, que no lleva lossless digan lo que digan
      los ritmos.
- [x] **Comprobado en el hardware** (2026-09-08): con el drop-in puesto y PipeWire
      reiniciado desde la pantalla, el FiiO BTR15 muestra `PCM 176.4K` en su propia
      pantalla. Ver §5.

### Menú de la pista — `screens/tracks.py`, `queue.py`, `library.py`

- [x] `↵` sobre una canción abre `TrackActionsScreen` en vez de encolar el nivel a
      ciegas: reproducir ahora (`a`), a continuación (`c`), la radio de la pista (`d`)
      y añadir a favoritos (`v`), con icono `▶ ↳ ≈ ♥` y navegación por cursor.
- [x] «Ahora» conserva el comportamiento anterior —el nivel entero a la cola,
      empezando por la pista elegida—, así que nadie pierde lo que ya tenía.
- [x] `Queue.insert_next()`: inserta después de la pista actual **en orden de
      reproducción**, no en la lista. Con shuffle activo remapea `_order` y mete lo
      nuevo justo detrás de la posición actual, en vez de rebarajar. Sin nada sonando
      no hay «después de esto» y cae en `append`.
- [x] `library.track_radio()`: `Track.get_track_radio(limit)` de tidalapi, con los
      reintentos de `net.py`. Una pista sin estación es una **respuesta normal**, no un
      fallo: TIDAL contesta 404 y tidalapi lanza `MetadataNotAvailable`; se convierte
      en `NoRadio` y sale por la barra de estado. Una estación vacía se trata igual.
- [x] La radio pone la semilla primero: una emisora que arranca con otra canción
      parece que se equivocó de pista. **TIDAL ya encabeza su estación con la propia
      pista**, así que `track_radio` la filtra por id antes de devolverla; si no, salía
      duplicada en la cola. Una estación que sólo trae la semilla cuenta como `NoRadio`.
- [x] `↵` sobre un álbum, artista o playlist sigue abriendo el nivel. El menú es para
      pistas, que son las que admiten más de una cosa razonable.
- [x] `m` en el navegador (0.8.0) abre el menú sobre la fila: el de la pista en una
      pista y, en un álbum, artista o playlist, `CONTAINER_ACTIONS`: reproducir todo
      ahora, a continuación, favoritos (el contenedor mismo, por su clave) y añadir
      todo a una playlist. Sin radio: nace de una pista y TIDAL no la da para un álbum.
      `TrackActionsScreen` recibe la lista de acciones; las letras son las mismas y
      una que el menú no enseña no hace nada.
- [x] El contenedor se carga entero con `library.all_entries()`, que sigue los «más…»
      hasta el final, y en el orden elegido con `s` (`_level_of`). Antes `a` sobre un
      contenedor se quedaba en la primera página, cien pistas. En un artista, «todo»
      son sus pistas más escuchadas, el mismo nivel que abre `↵`.
- [x] El menú vale también en la biblioteca, no sólo en la búsqueda: es la misma
      `BrowserScreen`, y separarlas habría pedido una bandera para empeorar un lado.

### Añadir a una playlist existente — `library.py`, `screens/browser.py`

- [x] Va en el menú de la pista, que desde la 0.4.0 se abre con ↵ en la biblioteca y con
      `m` en la cola: es el sitio donde ya se pregunta qué hacer con una canción.
- [x] El selector sólo ofrece **las playlists que creó el usuario**. No hace falta
      filtrar por propietario: `users/{id}/playlists` son las suyas, y las que sigue
      viven bajo favoritos y no entran en ese listado. Aun así, si TIDAL devolviera una
      sin `add`, se reporta como `PlaylistNotWritable` en vez de reventar.
- [x] Escribir necesita `factory()` y no el `parse()` barato del listado: sólo un
      `UserPlaylist` tiene `add`, y construirlo cuesta una petición. El listado la evita
      a propósito —110 playlists eran 111 peticiones—, y aquí se paga una sola vez, en
      el momento de escribir, que es donde toca.
- [x] Lotes de 100 y la misma regla que al crear: lo que entró se queda si falla un
      lote, y la excepción lleva cuántas llegaron.
- [x] Se olvida la caché **del listado y la de esa playlist**. Sólo la primera dejaría
      que abrirla después la enseñara como estaba.
- [x] Los duplicados se permiten. Pedir que se añada la misma cola dos veces es algo que
      alguien puede querer, y deduplicar a sus espaldas no es una decisión de esto.

### Alto de la banda del display — `app.py`

- [x] La banda se dimensiona con `_fit_display_band()`: el alto de la carátula **más el
      padding** que le ponga la disposición. `height` es border-box, así que el padding
      sale del contenido y una banda medida sólo por la carátula la deja una fila corta.
- [x] Y esa fila importa porque **un protocolo gráfico no se recorta a su widget**:
      pinta encima de lo que haya debajo. La fila sobrante cae sobre la barra de
      posición en vez de perderse.
- [x] Son **dos** las cosas que cambian esa suma, y durante un tiempo sólo se atendía
      una. Que la carátula cambie de tamaño era la evidente; cambiar de disposición es
      la otra, porque cada una lleva un padding distinto, y al cambiar de tema en vivo
      la banda conservaba el alto calculado bajo la anterior. En `nova` eso ponía la
      carátula justo encima de la línea de tiempo.
- [x] Por eso el alto se reasigna **siempre** que corre `_fit_artwork`, y no sólo cuando
      la carátula cambió de tamaño. El padding se asienta a su ritmo: al arrancar, la
      clase de la disposición se pone antes de que Textual recalcule los estilos, así
      que la primera pasada lee cero padding y la segunda —la del tamaño real del
      terminal— no redimensiona nada y se saltaba la corrección. Asignar un alto que ya
      era correcto no cuesta nada; llegar hasta ahí y no asignarlo costaba una fila de
      carátula sobre la barra de posición.

### Carátula en `blocks` — `artwork.py`, `widgets.py`

- [x] **Cada celda elige sus dos colores entre todos los repartos** (2026-09-11):
      `quadrant_cell` prueba las ocho formas de partir los cuatro píxeles en dos
      grupos (una es no partir) y se queda con la de menor error, con pesos por canal
      (3, 4, 2). Antes partía por brillo en la mitad del rango, que acierta con un
      borde claro-oscuro y pierde uno entre dos colores de brillo parecido. El grupo
      claro sigue siendo el glifo, así que lo que ya salía bien no cambia; un test
      compara contra el reparto por brillo en 2000 celdas al azar. `blocks()` reduce
      con LANCZOS.
- [x] Cuesta más, así que no corre en el hilo de la interfaz: `block_cells` trabaja
      las celdas en el worker que baja la carátula (`Cover.cells`) y el widget solo
      arma las líneas, que además guarda (`Artwork._lines`). Medido en una carátula
      de pantalla completa en 4K (31 250 celdas): 0,73 s en el peor caso (ruido) y
      19 ms en una imagen suave, fuera del bucle de eventos.

- [x] **Cuatro muestras por celda** con los glifos de cuadrante, no una con `▀`. El
      medio bloque gastaba el ancho entero de la celda en un píxel: dos por celda a lo
      alto y **uno** a lo ancho, que es exactamente por qué las portadas se veían
      estiradas. Ahora `blocks()` muestrea a `cols*2 × rows*2`.
- [x] Los dieciséis repartos posibles de cuatro cuadrantes entre dos colores existen en
      Block Elements, el mismo rango de donde ya salían `▀` y `█`. No hay riesgo de
      fuente nuevo, que es lo que descarta los sextantes (2x3, Unicode 13) pese a dar
      más resolución.
- [x] El corte entre el grupo claro y el oscuro va en **el punto medio del rango** y no
      en la media. La media sigue a la mayoría y aplana el borde que tres píxeles
      oscuros forman con uno brillante, que es justo el detalle que esto conserva.
- [x] Una celda plana cae entera en el grupo oscuro, sale como espacio y se pinta de su
      propio promedio, que es lo que una celda plana debe parecer.
- [x] El aspecto no cambia con la densidad de la rejilla: `decode` ya recorta la imagen
      al recuadro, y cualquier rejilla que se muestree se mapea de vuelta sobre ese
      recuadro. Por eso no hubo que tocar `CELL`.
- [x] La aritmética vive en `artwork.py`, que no importa Textual, y el widget sólo pide
      glifo y dos colores por celda. Así el reparto se prueba sin levantar una app.

### Ayuda y acerca de — `about.py`, `screens/help.py`

- [x] `?` o `h` abren `HelpScreen`: todos los atajos agrupados por lo que estás
      haciendo (reproducción, volumen, cola, ventanas, favoritos, y los del navegador),
      más «Acerca de» y el resumen de cambios por versión.
- [x] Dos pestañas, no un documento seguido: «Ayuda» son los atajos, y `→` pasa a
      «Acerca de», que lleva los créditos, la licencia y los cambios por versión; `←`
      vuelve. Todo eso vivía debajo de los atajos y estaba a tres pantallas de scroll
      de lo único que se abre la ventana a mirar.
- [x] Cada pestaña guarda su desplazamiento (`_offsets`), así que volver a los atajos
      cae donde se dejaron y no arriba del todo. `_lines` y `_offset` son propiedades
      sobre la pestaña activa: el scroll no sabe que hay pestañas.
- [x] Las dos páginas se construyen al montar, no al pulsar `→`: son datos fijos
      mientras la ventana está abierta y así el cambio de pestaña es un repintado.
- [x] La barra de título es el selector: la pestaña activa va en `▓ … ▓` con el acento
      y la otra en `inactive`. La versión sigue al final, donde un terminal estrecho la
      recorta sin perder nada que «Acerca de» no repita.
- [x] La línea del pie dice a dónde lleva la flecha que queda (`→ acerca de` o
      `← ayuda`), que es la única pista de que la segunda pestaña existe.
- [x] La tabla se construye con `keys_for`, **no** con `DEFAULT_KEYS`: una tecla
      rebindeada en `config.toml` aparece como la que hay que pulsar de verdad. Los
      atajos que el diseño deja fijos (flechas, ↵, esc, a, A, R) van como literales.
- [x] `about.pretty_keys` traduce los nombres de Textual a la tecla que se pulsa:
      `slash` → `/`, `d,delete` → `d / del`, `alt+up` → `alt+↑`.
- [x] Créditos: autor `wh01s17`, repositorio, licencia GPL-3.0-or-later con su URL, y
      versión leída de la metadata instalada con `__version__` de respaldo.
- [x] Las notas de versión son datos en `about.py` y no un parseo de `CHANGELOG.md`:
      ese fichero no va dentro del wheel, así que la pantalla habría salido vacía para
      todo el que instalase el paquete — que es justo para quien es la pantalla.
- [x] `about.py` no importa Textual, así que se prueba sin levantar una app.
- [x] La caja cede a `max-width: 100%`, al revés que los demás modales, porque lleva
      URLs y a 76×20 se cortarían.
- [x] `push_screen` ya retiraba la carátula de kitty al apilar; la ayuda lo hereda.
- [x] Buscador (`/`, 2026-09-10): una caja bajo el texto, como la de la cola y la del
      navegador, que estrecha la pestaña en curso con `library.text_matches` (la misma
      regla que `matches`, sin tildes ni mayúsculas). Cada fila que queda va bajo el
      título de su sección, y un título que coincide trae su sección entera. `esc`
      quita la búsqueda antes de cerrar; la barra de abajo nombra la tecla. Al abrir y
      cerrar la caja la página se vuelve a pintar tras el layout, o quedaba una línea
      corta.

### Tests — `tests/`

- [x] `pytest`, 472 pruebas, sin red y sin TIDAL. `pip install -e ".[dev]"`.
- [x] `tests/fake_mpv.py`: un mpv falso que habla el IPC JSON real y **emite eventos
      asíncronos antes de cada respuesta**, que es justo la trampa del §7. Lleva la
      cuenta de los filtros con etiqueta y rechaza la sintaxis con la etiqueta detrás.
- [x] `tests/fake_cava.py`: emite frames binarios como cava, leyendo el número de
      bandas de la config que generamos.
- [x] `tests/test_mpris.py`: backend falso para metadatos, unidades, transporte,
      diferencias y `Seeked`; además levanta un `dbus-daemon` temporal para verificar
      propiedades, controles, señales y colisión sin tocar el bus del usuario.
- [x] `tests/test_theme.py`: detección XDG, mapeo semántico, variables TCSS y fallback
      ante ausencia, tema incompleto o TOML inválido; Textual cubre el cambio en vivo.
- [x] `tests/test_artwork.py`: detección y override, cache, recorte centrado, medios
      bloques, troceado de kitty (que se reensambla al PNG original) y **un
      descodificador de sixel escrito en la propia prueba**, para comprobar el
      codificador contra píxeles y no contra una cadena esperada.
- [x] Cubren: cola (traversal, shuffle, repeat, mover, persistencia), paginación de la
      biblioteca, las dos ramas de `stream.resolve()` más DRM y manifiesto vacío,
      política de reintentos, `player` contra el mpv falso incluida la muerte y el
      reinicio del proceso y los filtros con etiqueta, `spectrum` contra el cava falso,
      `settings` (recortes, grafos y persistencia), letras LRC/texto, indicadores de
      shuffle/repeat, 429 de tidalapi con `Retry-After`, volver a la pista que suena,
      creación por lotes y parcial de playlists, controles clicables y la garantía de
      que el tick lento no reinstala filtros.

### Navegador y cola en la UI — `app.py`

- [x] `BrowserScreen` con pila de niveles, `⌫` para volver y carga en worker.
- [x] `↵` reproduce y encola el nivel entero; `a` añade uno (o el contenedor completo);
      `A` añade todo el nivel, y si el nivel sólo tiene contenedores cae en `a`.
- [x] `RowList` es un único widget compartido por la cola y por el navegador.
- [x] `s` shuffle, `r` repeat, `d` quitar, `C` vaciar; indicadores `[SHUF REP:ALL]`.
- [x] La cola se dibuja en columnas —título, artista, álbum, año y duración— cuando
      hay ancho, en vez de meter el artista dentro del título. Caen en el orden en que
      se pueden perder: el año primero, que son cuatro celdas que el título siempre usa
      mejor; después el álbum y el artista juntos; y al final queda `artista - título`
      en una línea. Una fila sin `entry` —un álbum, un artista, una playlist en el
      navegador— no tiene nada que poner en esas columnas y se queda la línea entera.
- [x] **Qué columnas se ven es un ajuste** (`columns`), elegido desde un selector que
      abre la ventana de `o`. El catálogo vive en `columns.py`, un módulo que no importa
      nada interno porque lo necesitan los dos extremos y ninguno puede importar al
      otro: `config` valida los nombres que el usuario escribió en el fichero y
      `screens` los dibuja. **Diez de las once** vienen rellenas en un listado normal
      —comprobado contra la cuenta real— y encenderlas no cuesta ninguna petición. La
      excepción es el año; ver abajo.
- [x] El ajuste es una cadena separada por comas y no un array TOML, para que pase por
      las mismas `setting`/`_toml`/`set_option` que todo lo demás y para que
      `TIDALAMP_COLUMNS="artist,year"` funcione desde una shell sin comillar una lista.
      Un nombre inventado cuesta esa columna y nada más.
- [x] El cambio repinta las listas que ya están en pantalla, en toda la pila de
      pantallas: `RowList` lee el ajuste al dibujar, así que basta con pedirle que se
      redibuje. Antes sólo se veía en la siguiente cola que se cargara.
- [x] Qué columna cae primero al estrecharse la lista es un dato del catálogo (`drop`),
      no un umbral escrito a mano en el renderizador: añadir una columna no obliga a
      tocar ningún número. El artista sólo sale del título cuando tiene una columna
      propia adonde ir.
- [x] **El año es la única columna que sí cuesta peticiones, y hubo que descubrirlo.**
      Durante meses la celda salió siempre vacía y la promesa de arriba parecía
      cumplirse. El motivo: `Entry.year` sale de `album.year` de tidalapi, que lo deduce
      de `releaseDate` o `streamStartDate` del JSON del álbum, pero el álbum que viene
      **anidado dentro de una pista** en un listado es la versión corta —id, título y
      portada— y no trae fecha. Medido sobre una cola real: 100 entradas, 15 álbumes
      distintos, 0 años.
- [x] Se pide aparte, con `library.album_year`, **una vez por álbum y no por pista**:
      esas 100 pistas cuestan 15 peticiones. La caché `_YEARS` dura la sesión y guarda
      también el `0` de un álbum sin fecha, para no volver a preguntar por él en cada
      repintado. Un fallo no se cachea: la próxima cola puede reintentarlo.
- [x] Se rellena **en segundo plano** (`_fill_years` y su worker), después de que la
      cola esté en pantalla, no mientras carga el nivel. Si no, cada nivel esperaría una
      petición por disco antes de dibujar una sola fila. Y sólo si la columna está
      encendida: quien no mira el año no lo paga.
- [x] Se descartó usar el `streamStartDate` de la propia pista, que sí viaja en el
      listado y costaría cero peticiones. Es la fecha en que TIDAL empezó a emitirla, no
      la de publicación: pintaría 2011 en un disco de 1997. Un dato equivocado con cara
      de dato bueno es peor que una celda vacía, que es el mismo criterio de la insignia
      `FFT`/`RMS`.
- [x] `Entry.album_id` existe para esto: sin id no hay a qué preguntarle. Una cola
      guardada antes de que ese campo existiera se carga igual, pero sus entradas no se
      pueden rellenar y se quedan sin año hasta la siguiente recarga. Un álbum sin fecha
      en TIDAL da `0` y deja la celda en blanco en vez de dibujar un «0».
- [x] La columna de duración se mide **una vez para toda la lista**, no por fila, y va
      alineada a la derecha dentro de ella. Medida por fila, un `11:53` era una celda
      más ancho que un `5:07` y empujaba la columna de álbum: una columna que sólo
      cuadra mientras ninguna pista pasa de diez minutos no es una columna.
- [x] **Buscador en la cola con `ctrl+f`** (`filter_queue`, rebindeable). Barra bajo la
      lista, la misma forma que el filtro `/` del navegador porque es el mismo gesto
      sobre otra lista, y `library.matches` es la misma función: acentos, varias
      palabras y el álbum de la pista.
- [x] La tecla no es `/` porque `/` ya es «buscar en TIDAL» en la ventana principal.
      `ctrl+f` es lo que busca en un navegador o en un editor, y es de las pocas
      combinaciones que no chocaban con las letras sueltas del reproductor.
- [x] Filtrar rompe la equivalencia «fila en pantalla = posición en la cola», que era
      lo que usaban `↵`, `d`, `alt+↑↓` y la marca de reproducción. `_shown` es el mapa
      entre las dos, y `_queue_index`, `_cursor_index` y `_row_at` son los tres únicos
      sitios donde se traduce: ninguna acción vuelve a leer el cursor a pelo.
- [x] Las filas conservan **el número real** en la cola (`Row.number`). Renumerar las
      coincidencias 1, 2, 3 habría afirmado un orden de reproducción que no es el que
      sigue el reproductor, y el número es justo lo que dice dónde está la pista.
- [x] `_row_at` devuelve `-1` cuando el filtro esconde la posición, y eso es una
      respuesta: la pista que suena puede no ser una de las que se están buscando. La
      marca `▶` desaparece, el cursor no salta a una fila ajena, y la reproducción
      sigue exactamente igual.
- [x] **`g` (`to_playing`) vuelve a lo que suena.** Usa `_row_at(queue.playing)`; si da
      `-1`, limpia el filtro con `_clear_queue_filter()` y traduce de nuevo antes de
      mover cursor y marca. Con `playing < 0` no inventa la primera fila: no mueve nada
      y deja la explicación en estado.
- [x] **`p` (`save_playlist`) abre `PlaylistNameScreen`** sólo con una cola no vacía.
      El modal devuelve el nombre o `None`; la cola se copia antes de lanzar el worker,
      que llama `ensure_fresh` y la escritura de biblioteca. El spinner incluye el
      nombre y el resultado, también parcial, termina en la línea de estado.
- [x] Mover una pista con el filtro puesto sí funciona, aunque la lista no parezca
      reordenarse —la pista con la que se intercambia puede estar escondida—: lo que
      cambia a la vista es el número de la cabecera de la línea, que es la posición.
- [x] `AUTO_FOCUS = None` en la app. Textual enfoca solo el primer widget enfocable de
      la pantalla, y desde que la principal tiene un `Input` ese widget se comía `x`,
      `c` y todo lo demás nada más arrancar. Las pantallas que quieren cursor en una
      caja ya lo pedían explícitamente.
- [x] La cola se restaura al arrancar.
- [x] `alt+↑` / `alt+↓` reordenan la cola. `Queue.move()` remapea la permutación de
      shuffle en vez de regenerarla, así que reordenar no vuelve a barajar lo que suena
      después, y el cursor y la marca de «sonando» siguen a la pista movida.

### Fichero de configuración — `config.py`, `app.py`

Lo que la pantalla de `o` escribe está en «Configuración» más arriba; esto es el
fichero en sí.

- [x] `~/.config/tidalamp/config.toml`, leído con `tomllib` (sin dependencias).
      Precedencia **entorno → fichero → defecto**: una variable de entorno es para una
      ejecución suelta y tiene que ganar. Un TOML roto no impide arrancar: se registra
      y mandan los valores por defecto.
- [x] Ajustes: `quality`, `artwork`, `language` y `debug`. `ENV_VARS` es la lista única
      de los cuatro con su variable de entorno, así que añadir uno lo hace aparecer a la
      vez en la plantilla, en la pantalla y en `overridden()`.
- [x] Teclas rebindables por acción en `[keys]`, con `DEFAULT_KEYS` como fuente única.
      **Las de navegación no son rebindables** a propósito: un error de dedo en las
      flechas dejaría al usuario sin poder salir del navegador.
- [x] `tidalamp config` muestra los ajustes en uso, crea la plantilla comentada si no
      existe —y nunca pisa la que ya haya— y avisa de las acciones inventadas en
      `[keys]`, que si no se ignorarían en silencio.

### CLI — `cli.py`

- [x] `tidalamp` abre la TUI por defecto; `tidalamp tui` conserva la forma explícita.
      También están `tidalamp login`, `tidalamp config` y `tidalamp search <query>`.
- [x] `tidalamp -v` / `--version` imprime `tidalamp <versión>` y sale. Es opción eager
      del callback, no una orden: así responde antes de que nada pida sesión, mpv o un
      terminal de cierto tamaño, que es justo la instalación rota desde la que se pide
      el número para un informe de fallo. La versión sale de `about.version()`, la
      misma que enseña la ayuda, así que no hay dos números que puedan discrepar.
- [x] Ayuda, mensajes y plantilla de configuración siguen el locale del proceso.

### Internacionalización — `i18n.py`

- [x] Interfaz TUI, navegador, CLI y errores visibles en español e inglés. El español
      sigue escrito directamente en el código como idioma fuente y es el fallback para
      locales no soportados.
- [x] Decide el ajuste `language`; `auto` delega en el locale, y ahí la detección va
      por `LANGUAGE` → `LC_ALL` → `LC_MESSAGES` → `LANG`. El ajuste manda a propósito:
      `$LANG` es ambiente y no elección, y un sistema en español no es una petición de
      que *este* programa lo esté. Hay override sencillo para pruebas.
- [x] El catálogo no usa gettext ni artefactos compilados. Una prueba recorre el AST,
      exige que cada llamada a `_()` sea literal y tenga exactamente una traducción,
      comprueba los placeholders y prohíbe sombrear la función `_`.
- [x] `README.md` está en inglés y documenta cómo forzar ambos idiomas.
- [x] Los nombres de los temas y paletas se traducen en pantalla con `layouts.label`
      (ver «Temas»); el valor del fichero no cambia con el idioma.

### Ordenar la biblioteca — `library.py`, `screens/browser.py`

- [x] `s` en un nivel abre una lista (`ChoiceScreen`) con sus órdenes en los dos
      sentidos: pistas favoritas y pistas de una playlist por fecha de agregado,
      nombre, artista o álbum; álbumes favoritos por fecha de agregado, nombre,
      artista o lanzamiento; artistas favoritos y playlists propias por fecha
      (de creación, en las playlists) o nombre. `Row.orders` dice cuáles tiene un
      nivel y `Row.sort` da la clave y el cargador de uno.
- [x] **Lo ordena TIDAL**, con los enums de tidalapi (`ItemOrder`, `AlbumOrder`,
      `ArtistOrder`, `OrderDirection`): la biblioteca carga de 100 en 100, y ordenar
      la página cargada ordenaría 100 pistas de 766 y lo llamaría biblioteca.
      «Mis playlists» se pide a mano (ver `_playlists_level`) y manda `order` y
      `orderDirection` como los manda tidalapi para favoritos; TIDAL lo respeta en ese
      endpoint: comprobado por el mantenedor contra TIDAL real (2026-09-11).
- [x] Dentro de un álbum o de un artista TIDAL no ordena, y el nivel es una página:
      `_in_order` lo ordena aquí, en una lista nueva (la de la caché sigue como vino),
      con «más…» al final.
- [x] Cada orden es un nivel propio en la caché (`clave|name-asc`) y el de TIDAL
      conserva la clave de siempre. El elegido se recuerda por nivel y persiste entre
      sesiones, en `~/.local/state/tidalamp/library-orders.json` (`ORDERS_FILE`),
      no en `config.toml`, que crecería con una entrada por playlist. Se guarda el
      código (`name-asc`) y se busca entre los órdenes del nivel al leerlo, así que
      la fecha de una playlist sigue siendo la de creación; el título lo dice, y `R` recarga el orden
      que está puesto.

### Quitar de favoritos o de una playlist — `library.py`, `screens/browser.py`

- [x] `d` o Supr en el explorador quita la fila de donde está: de favoritos en un
      nivel de favoritos, y de la playlist en una playlist propia. Pregunta antes con
      `ChoiceScreen` abierta en «cancelar»: volver a añadir una pista no la devuelve
      a su sitio. Al confirmar, la fila sale del nivel; `F` hace lo mismo en su nivel.
- [x] `remove_from_playlist` busca el índice página a página, en el orden de la
      playlist, y quita por índice. `remove_by_id` de tidalapi lee una sola página
      del tamaño por defecto y da por ausente una pista más allá; y el explorador
      puede estar mostrando la playlist ordenada, así que el número en pantalla no es
      un índice. El DELETE no se reintenta: quita por posición, y un reintento tras
      una respuesta perdida quitaría la pista que pasó a ocupar ese sitio. Una pista
      repetida pierde su primera aparición.
- [x] `forget_level` tira un nivel y todas sus copias ordenadas; lo usan quitar de
      una playlist (más la lista de playlists, por el contador) y los favoritos.

### La ayuda de la biblioteca — `screens/browser.py`, `screens/help.py`

- [x] El pie del explorador dice solo `? ayuda` y `esc cerrar`. `?` abre
      `HelpScreen(keys, only="browser")`, que muestra la sección cuyo
      `about.Section.name` es `browser` y ninguna otra, sin la pestaña «Acerca de».
      El pie que intentaba listar todas las teclas perdía la mitad en cualquier
      terminal más estrecha que la lista.

### Filas de ajustes que se eligen de una lista — `screens/config_window.py`

- [x] Calidad, Ritmos hi-res en PipeWire y Reiniciar PipeWire no cambian con las
      flechas: una de más cambiaba la calidad, reescribía el drop-in o reiniciaba
      PipeWire y cortaba el audio. Enter abre `ChoiceScreen`, la lista de elegir uno
      sacada de la ventana de velocidad (que ahora es un caso de ella). La de
      reiniciar abre en «cancelar», así que dos Enter por reflejo no cortan nada.

### Reproducción automática — `app.py`, `config.py`

- [x] `autoplay` (sí o no, apagado por defecto, «Reproducción automática» en
      ajustes): cuando `action_next` llega al final de la cola, pide la radio de TIDAL
      de la última pista en vez de detenerse. Engancha ahí porque es por donde pasan
      tanto el tick (mpv en reposo tras haber sonado) como la tecla de siguiente.
- [x] No reutiliza `_radio_ready`, que reemplaza la cola y empieza por la semilla:
      aquí la semilla es lo que acaba de sonar y la cola sigue siendo del usuario.
      La radio se **añade** al final sin las pistas que la cola ya tiene (la semilla
      incluida) y suena la primera añadida.
- [x] Una sola petición en vuelo (`_autoplaying`): mientras llega, mpv sigue en
      reposo y otro «siguiente» no pide más. Radio vacía o sin nada nuevo, o fallida:
      se detiene como antes y lo dice.

### Pantalla completa — `screens/fullscreen.py`, `app.py`

- [x] `w` (solo por tecla) abre `FullscreenScreen`, una `Screen` que no es modal: la
      carátula centrada y tan grande como deja la pantalla, una barra de tres filas
      (pista; controles, barra de posición y tiempos; calidad y el botón de la cola)
      y la cola al lado con `tab` o con ese botón. `esc` vuelve. Solo se abre desde
      el reproductor y con el tamaño mínimo de siempre.
- [x] **La carátula es suya:** `FullArtwork` es un `Artwork` sin el tope de
      `MAX_ROWS` y con su propio `image_id` de kitty, y la vista la pide a su tamaño,
      con la forma y el fondo de siempre. `App.query_one` solo busca en la pantalla
      principal (comprobado), así que el camino de la carátula del reproductor no
      encuentra nunca esta. La del reproductor se esconde al entrar, como bajo
      cualquier pantalla; la de aquí se esconde con `ScreenSuspend` cuando se abre
      una ventana encima (ayuda, velocidad) y vuelve con `ScreenResume`.
- [x] **kitty y sixel en 4K** (2026-09-11). En pantalla completa bajaba el
      rendimiento: la cola pide las carátulas a 320 px (`album.image(320)`) y la vista
      las estiraba a unos 2500 px, 8 MB de escape de kitty para una imagen borrosa, y
      el codificador de sixel, píxel a píxel en Python, tardaba 29 s y retenía el
      intérprete. Tres cambios: la vista pide 1280 px (`artwork.sized`, cambiando el
      tamaño en la URL de TIDAL); kitty recibe la imagen a su tamaño y la escala él
      (`decode(upscale=False)`), 0,9 MB en 0,43 s; y sixel se codifica por bandas y
      colores con `bytes.translate` y enteros grandes, los mismos bytes que antes (un
      test lo compara con el codificador viejo), unas nueve veces más rápido. Como
      sixel se dibuja a su tamaño en píxeles, la vista no lo pasa de 1280 px
      (`SIXEL_ROWS`, 64 filas): 2,7 MB en 0,9 s. Una medición en 2 s de vista con
      carátula kitty mostró que la barra de abajo no provoca reenvíos de la imagen.
- [x] **Las ventanas sobre la vista no son translúcidas**, ni con `transparency`
      (`_see_through`, que decide `push_screen` y también el cambio del ajuste con
      ventanas abiertas). Medido en un pty a 480x130 con la carátula en `blocks`:
      abrir la ayuda sobre la vista, 0,86 MB translúcida contra 0,22 opaca; 20 líneas
      de scroll, 1,21 MB contra 0,35. No era la caja: con la caja opaca y el velo
      translúcido costaba lo mismo. Textual reenvía enteras las filas que cambian, y a
      los lados de la caja esas filas son la carátula mezclada con el velo, miles de
      celdas de colores distintos. En reposo la vista escribe 8 KiB/s con
      transparencia o sin ella.
- [x] **Una imagen kitty que quedaba pegada** (encontrado por el mantenedor): kitty,
      `w`, los ajustes, activar la transparencia, cerrarlos y cerrar la vista con `w`.
      La vista se había guardado su carátula kitty al abrirse los ajustes y la volvía
      a poner al cerrarlos, aunque la transparencia había pasado la carátula a
      `blocks`; en kitty esa imagen quedaba en pantalla sobre el reproductor.
      Reproducido en un pty contando envíos y borrados por id. Ahora `_reload_art`
      avisa a la vista (`reload_cover`), que tira la carátula guardada y pide una en
      el protocolo nuevo; al volver de una ventana no pone una guardada en otro
      protocolo; y al cerrarse borra su imagen kitty por id siempre que haya mostrado
      una, tenga lo que tenga en ese momento.
- [x] El tick lento le pasa posición y duración mientras está delante (`follow`),
      y ahí se redibujan la barra, los controles y, si está abierta, la cola, solo
      cuando cambió. La barra de posición se llama `#fs-seek`: con `#seek`, el clic
      llegaría al manejador de la app, que mide la barra del reproductor.
- [x] **La cola del panel es la del reproductor**, no una copia con su propio
      cursor: muestra `main.rows`, su marca y su cursor, así que una fila de aquí es
      la misma de allí y `g`, `d`, `alt+↑↓`, `m` y `f` actúan donde apuntan. Un
      `watch` sobre el cursor del reproductor lo sigue al instante y `_sync_queue`
      avisa cuando cambian las filas. Con el panel cerrado, las que editan una fila
      piden abrirlo (`_queue_hidden`) en vez de actuar a ciegas; `g` lo abre, y
      `ctrl+f` avisa de que la búsqueda está en el reproductor. `w` otra vez cierra la
      vista, como `esc`. `?` abre la ayuda con la sección `fullscreen` sola, como la
      biblioteca con la suya.
- [x] Colores de la paleta; el marco se copia del `#main` del reproductor, así que
      cada tema viste también esta vista.

### mpv que no contesta - `player.py`, `app.py`

- [x] **Tres fallos distintos, y se distinguen.** `_request` separa un socket que ya no
      está (EOF o un `send` que falla), una respuesta que no llega a tiempo y una
      respuesta con error. Antes los tres volvían como `None`, y un mpv muerto por EOF
      se leía como volumen 0 y posición 0 sin que nadie lo reiniciara. Ahora el EOF
      suelta el socket, `alive` pasa a False y el tick lo reinicia.
- [x] **Una espera, no una por propiedad.** `TIMEOUT` es 1 s (eran 2). El primer
      comando que no recibe respuesta deja el reproductor `stalled`, y desde ese
      momento todos los comandos se rinden al instante. Sin eso, un mpv vivo pero
      colgado costaba la espera entera en cada propiedad que leen los ticks, varias
      por tick, para siempre.
- [x] **El sondeo y el reinicio, en workers.** Mientras está atascado, el tick lento
      escribe «mpv no contesta» y lanza `_probe_mpv_worker`, que es el único comando al
      que el atasco deja esperar el timeout completo. Si contesta, se sigue. Si pasan
      `STALL_LIMIT` (5 s), `_recover_mpv` lo reinicia en `_restart_mpv_worker`. Los
      ticks no hacen nada mientras `_recovering`. Un reinicio que falla espera
      `MPV_RETRY` (5 s) antes del siguiente intento; antes se reintentaba cuatro veces
      por segundo.
- [x] `restart()` sólo sujeta el lock para quitar el socket viejo. Matar el proceso y
      esperar el socket nuevo tardan segundos, y un comando del hilo de la interfaz
      tiene que encontrar el socket vacío y rendirse, no hacer cola detrás.
- [x] Una respuesta que llega después de su plazo se descarta como un evento más: su
      `request_id` es uno viejo. Una línea partida en varias lecturas se recompone en
      `_buf`. Los dos casos están en `tests/test_player.py` con el mpv falso, que ahora
      sabe colgarse (`FAKE_MPV_HANG_ON`), cerrar el socket (`FAKE_MPV_EOF_ON`) y mandar
      las respuestas de tres en tres bytes (`FAKE_MPV_SPLIT`).
- [x] **La pista vuelve donde iba, no a 0:00.** Salía del principio tras cada
      reinicio, y el mantenedor lo oyó en las dos pruebas a mano. A un mpv muerto o
      atascado ya no se le puede preguntar la posición, así que el tick guarda la suya
      (`_last_position`); `_recover_mpv` la deja en `_resume` con la pista, y `_start`
      carga esa pista con la opción por fichero `start=<segundos>` en el propio
      `loadfile`, como `volume-gain`. No un `seek` después: tendría que esperar a que el
      stream abra, y nada dice cuándo. Sólo esa recarga y sólo esa pista: un
      «siguiente» mientras resuelve arranca la otra desde el principio.

### Recordar el segundo al salir - `queue.py`, `app.py`

Estaba en «Descartado» (2026-09-10) porque ni el cliente oficial de TIDAL lo hace. Se
retomó el 2026-09-12, a petición del mantenedor, cuando el `start=` de arriba dejó sin
efecto las tres trampas que lo hacían caro:

- [x] **El seek tras resolver** ya no existe: el segundo va como opción del `loadfile`.
- [x] **Guardar en cada tick** reescribiría `queue.json` diez veces por segundo. Se
      guarda una vez, en `_close_player` (`_remember_position`), que es por donde salen
      `q` y `ctrl+c`. El precio: un cuelgue conserva el segundo de la última salida
      limpia, no el del cuelgue.
- [x] **`_was_idle` lee un mpv en idle como «la pista terminó»**, y por eso nada se pone
      a sonar solo al arrancar: `_restore_position` deja el segundo en `_resume`, la
      barra de estado dice ««Título» sigue en 1:23», y se aplica cuando esa pista
      suena, por el mismo camino que la recarga tras un reinicio. Otra pista antes lo
      descarta.
- [x] `queue.json` lleva `position` junto a `playing`. Una cola de antes, o con basura
      en el campo, arranca en 0:00. Salir sin haber tocado la pista restaurada conserva
      su segundo, y salir mientras se recarga guarda el segundo al que iba y no el 0:00
      que marca mpv mientras abre el stream.

### Sin corte entre pistas - `app.py`, `player.py`

- [x] **La siguiente se resuelve antes de que haga falta.** A `PREFETCH_LEAD` (20 s)
      del final, el tick lento pide la siguiente a TIDAL en `_prefetch_worker` y
      `_prefetched` la pone en la playlist de mpv con `loadfile … append`. Con
      `--prefetch-playlist=yes` mpv la abre antes de terminar la actual, y con el
      `gapless-audio=weak` que trae por defecto pasa a ella sin cortar. No antes de 20
      s: la URL del stream caduca.
- [x] **El avance se detecta por `playlist-pos`.** mpv no pasa por idle entre las dos,
      así que el `_was_idle` de siempre no se entera. Lo que suena está siempre en la
      posición 0 y lo preparado en la 1; cuando `playlist_pos` vale 1,
      `_advance_to_prepared` hace `playlist-clear` (queda sólo lo que suena, otra vez
      en la 0) y `_announce` + `_now_playing` ponen la pantalla al día sin cargar nada.
      Se eligió la posición y no la URL porque repetir una pista puede traer la misma.
- [x] **Sólo se guarda lo que la cola dice que va después.** `_check_prepared` corre
      en cada `_sync_queue`, que es por donde pasa toda edición de la cola, y al cambiar
      shuffle o repeat. Si la siguiente ya no es la preparada, sale de mpv
      (`drop_queued`). Un resultado que vuelve para una pista que ya no es la siguiente
      se descarta en `_prefetched`, con el mismo cuidado que `_resolving`.
- [x] `_play_index` quita lo preparado antes de resolver: la pista vieja sigue sonando
      mientras la nueva resuelve y, si terminara en ese hueco, mpv pasaría a la
      preparada y no a la pedida. `stop` y el reinicio de mpv ya vacían su playlist,
      así que sólo olvidan (`_forget_prepared`).
- [x] Lo preparado caduca a los `PREPARED_TTL` (5 min): una pista en pausa cerca del
      final volvería a una URL muerta. Un fallo al preparar no dice nada y no se
      reintenta en cada tick (`_prefetch_failed`): cuando le toque se resuelve como
      siempre, y ese fallo sí se enseña.
- [x] `_play_index` se partió en `_announce` (marcador, cursor, título, carátula) y la
      resolución; `_start`, en la carga y `_now_playing`. Las dos mitades sirven para
      las dos formas de empezar una pista.
- [x] **La carátula y la letra, también por adelantado.** El sonido pasaba sin corte y
      la carátula llegaba un momento después, de la red. `_warm` baja la carátula a su
      caché de disco y, si algo en pantalla sigue la letra (split o la ventana de `y`),
      la letra a `_lyrics_cache`. Va **después** de encolar el audio, porque es
      decoración, y sus fallos no dicen nada. Sólo se adelanta la descarga: dibujarla
      depende del recuadro y del aspecto de ese momento, y desde el disco es rápido. La
      letra no se pide si nada la enseña: sería una petición por pista que nadie lee.

### Volumen normalizado - `settings.py`, `stream.py`, `player.py`, `app.py`

- [x] **Confirmado que viene gratis.** `Track.get_stream()` de tidalapi parsea
      `trackReplayGain`, `trackPeakAmplitude`, `albumReplayGain` y
      `albumPeakAmplitude` de la misma respuesta (`playbackinfopostpaywall`) que trae
      el manifiesto. `stream._loudness` los pasa a `Playable`.
- [x] **tidalapi rellena con 1.0 lo que falta**, ganancia y pico. Un 1.0 de ganancia es
      +1 dB de verdad, así que una ganancia y un pico que valen exactamente 1.0 los dos
      se toman por ausentes: ninguna pista masterizada mide eso.
- [x] `settings.replaygain(mode, track, album)` es puro: `off` da 0, `album` sin
      ganancia de disco cae a la de pista, y **el pico es el techo**: una ganancia que
      sube se recorta a `-20·log10(pico)`, lo que lleva ese pico a 1.0 justo. Una que
      baja no se recorta nunca.
- [x] **`volume-gain`, no un filtro.** next.md proponía un filtro de volumen junto al
      balance y el ecualizador, y habría roto lo anterior: cambiar un filtro reinicia
      la cadena, y eso es un hueco audible justo en el cambio de pista. mpv tiene una
      propiedad de ganancia en dB aparte del volumen, y se pasa como opción por
      fichero en el `loadfile` (`options=volume-gain=…`), así que la pista preparada
      entra con la suya desde la primera muestra y la anterior conserva la suya hasta
      la última.
- [x] `loadfile` va con argumentos con nombre: mpv 0.38 metió un índice entre las
      banderas y las opciones, y por posición la misma línea significa cosas distintas
      según la versión. Un mpv que no conozca `volume-gain` rechaza el comando entero,
      así que se reintenta sin la opción: mejor sonar sin normalizar que no sonar.
- [x] Cambiar el modo en la ventana de `o` fija `volume-gain` en la pista que suena y
      quita la preparada, que llevaba la ganancia vieja como opción.
- [x] **La insignia lo dice.** Con el volumen normalizado, la línea de insignias acaba
      en `RG -7.5 dB`: la ganancia aplicada, con el tope del pico incluido, porque es la
      que se oye. Una pista sin ganancia de TIDAL dice `RG —` y no `0 dB`, que se leería
      como medida y neutra. Apagado, no aparece. Sin ella, una pista podía sonar más
      baja que la anterior sin que nada en pantalla explicara por qué; y es la forma de
      leer los valores reales que manda TIDAL sin abrir el registro.

### Mis mixes - `library.py`

- [x] `session.mixes()` es la página que el cliente oficial llama My Mixes (diario,
      descubrimiento, novedades…). **No** es `user.mixes()`, que son los mixes que
      alguien guardó como favoritos. La página puede traer otras cosas además de
      mixes; `_is_mix` se queda con lo que tiene `mix_type` e `items()`.
- [x] Cada mix se pide al abrirlo (`Mix.items()` pide la página del mix), se cachea con
      la clave `mix:<id>` y deja fuera los vídeos. tidalapi lanza `ValueError` para un
      mix vacío, y eso es un nivel vacío.
- [x] **Sin `s` ni `d` sin tocar el navegador.** La fila no trae `orders` ni `sort`, así
      que `s` dice «este nivel no se puede ordenar»; y `d` sólo sabe quitar de claves
      `fav:` y `playlist:`, así que dentro de `mix:` dice «aquí no hay de dónde
      quitar».
- [x] La fila va la última de la raíz y no junto a «Mis playlists»: las cuatro de antes
      son lo que la cuenta guarda, y hay tests que las encuentran por su posición.

### Revisión antes de la 0.8.0 (2026-09-11)

Leído todo lo nuevo desde la `0.7.0` buscando lo que los tests no cubrían. Cuatro
cosas, con su test cada una:

- [x] **Quitar de una playlist podía borrar la pista vecina.** La posición se contaba
      sobre lo que devolvía la página, y TIDAL deja fuera de una página lo que no
      puede servir después de aplicar el límite (le pasa con los favoritos): tras el
      hueco, cada posición queda una corta. Ahora `_position_of` confirma con una
      lectura de una pista que en esa posición está la que se quita, y si no, recorre
      la ventana de la página pista a pista antes de borrar nada.
- [x] **La reproducción automática pisaba al usuario:** una radio que llegaba después
      de detener o de elegir otra pista se ponía a sonar. `action_stop` y
      `_play_index` la cancelan y una respuesta tardía se descarta.
- [x] **Cambiar la forma de la carátula con la pantalla completa abierta** no llegaba a
      la vista, que corta su propia carátula: ahora se la pide de nuevo.
- [x] **`TidalAmp._shutdown` pisaba el `App._shutdown` de Textual**, el que cierra
      las pantallas, envía el desmontaje y cierra el driver cuando la app sale:
      nuestro método del mismo nombre lo reemplazaba sin llamarlo, así que al salir
      Textual corría el nuestro en lugar del suyo. Salía igual, pero no por su camino.
      Lo destapó un test que lo sustituía y dejaba a Textual esperando un cierre que
      no llegaba. Ahora se llama `_close_player`. Con el cierre de Textual corriendo de
      verdad salió otra cosa: un tick o un cambio de tamaño ya en cola podía llegar
      después de que Textual vaciara las pantallas y buscar widgets que ya no estaban
      (solo bajo carga, en la suite completa). `_quiet_after_teardown` envuelve
      `_check_size` y los tres temporizadores: durante el cierre no hacen nada, y con la
      app en marcha el error sigue saliendo.
- [x] **Las tablas del codificador de sixel** se construían al importar `artwork`,
      unos 20 ms de cada arranque para un protocolo que casi ningún terminal usa;
      ahora se hacen la primera vez que se usa cada color.

## 5. Estado de verificación

Distinguir esto importa: parte del código nunca se ha ejecutado contra TIDAL real.

| Área                               | Estado                            | Cómo se comprobó                                                                                                                                                                |
| ---------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| IPC de mpv                         | **Verificado**                    | Script directo: get/set de volumen, `idle`, `paused`.                                                                                                                           |
| Medición RMS                       | **Verificado**                    | Tono de 440 Hz generado con ffmpeg; devuelve −21 dBFS estable.                                                                                                                  |
| Layout y render de la TUI          | **Verificado**                    | La app real corriendo en un pty, con `pyte` emulando el terminal y datos stub.                                                                                                  |
| i18n español / inglés              | **Verificado**                    | Catálogo exhaustivo por AST, igualdad de placeholders, precedencia de locale, fallback y CLI/plantilla en ambos idiomas.                                                       |
| MPRIS: registro y propiedades      | **Verificado con `dbus-fast`**    | Integración automatizada contra un `dbus-daemon` temporal más la comprobación manual previa con `gdbus`.                                                                        |
| MPRIS: controles                   | **Verificado con `dbus-fast`**    | Play y Volume cruzan el bus real; todos los transportes y setters están cubiertos con backend falso.                                                                            |
| MPRIS: señales                     | **Verificado con `dbus-fast`**    | El bus aislado recibe un solo `PropertiesChanged`, ninguno si no cambia el estado, y `Seeked` conserva microsegundos.                                                           |
| MPRIS: LoopStatus / Shuffle        | **Verificado con `dbus-fast`**    | Lectura/escritura del adaptador, más la integración Textual de sus indicadores persistentes.                                                                                    |
| MPRIS: colisión de nombre          | **Verificado con `dbus-fast`**    | Dos conexiones reales al bus aislado: la segunda reclama `.instance<pid>`.                                                                                                     |
| MPRIS: TrackList                   | **VERIFICADO EN LA INSTANCIA REAL** | Lectura del bus del usuario con la app corriendo: `HasTrackList` True, 100 filas con ids **todos distintos** pese a haber cinco pistas llamadas «Thriller», `GetTracksMetadata` responde y `Shuffle` coincide con el `SHUF ON` de la pantalla. Antes: `Tracks`, `GetTracksMetadata`, `GoTo` y `CanEditTracks` contra el bus aislado, con `TrackListReplaced` recibido por un cliente real; más unitarias de identidad de fila (dos veces la misma canción, reordenado, ida y vuelta a disco) y una que fija que el tick no construye metadata. |
| Cola: shuffle / repeat             | **Verificado**                    | Unitarias de recorrido en los tres modos y prueba Textual de indicadores persistentes por teclado y setters MPRIS.                                                             |
| Cola: persistencia                 | **Verificado**                    | Ida y vuelta a disco, y dos sesiones reales de la app encadenadas.                                                                                                              |
| Navegador de biblioteca            | **Verificado**                    | Drill-down, `↵`, `a` y `A` con una sesión simulada.                                                                                                                             |
| Configuración agrupada             | **Verificado**                    | Dos unitarias: el orden Audio, Apariencia y General con cada fila bajo su cabecera, y en 60x18 el cursor en la última fila sigue dibujado, con su cabecera. Renderizado a imagen en 240x62 y 60x18. |
| Transparencia como ajuste          | **Verificado**                    | Tres unitarias: el modal abre sólido, encenderla lo vuelve translúcido en la ventana ya abierta, y con carátula kitty escribe `artwork = blocks` y enseña el aviso con el enlace; con carátula de bloques no toca nada. |
| Ventanas proporcionales y velo    | **Verificado**                    | Renderizado real a 240x62, 100x30 y el mínimo 60x18, con captura a imagen de biblioteca, búsqueda, configuración, ayuda y ecualizador. |
| Coste del velo                     | **Medido**                        | 240x62 con la biblioteca abierta: 37,7% de un núcleo con el fondo animándose, 8,8% con el modal opaco de antes, **0,5%** con el fondo congelado. Tres pruebas fijan que el analizador y el reloj se paran detrás de un modal y que la línea de estado no. |
| Filtro del nivel (`/`)             | **Verificado**                    | Seis unitarias de `library.matches` (acentos, varias palabras, álbum) y siete en la app real headless: la barra abre sin tapar el nivel, «sober» deja 1 de 3, la fila «más…» sobrevive, la página que llega bajo filtro cae en su sitio dentro del nivel, `esc` quita el filtro antes de cerrar y el nivel siguiente abre limpio. Falta verlo contra la biblioteca real. |
| Formas del analizador              | **Verificado**                    | Dieciséis unitarias: las cuatro usan todas las columnas que se les dan a 80, 200 y 380, `mirror` es simétrica sobre su línea central y cae a `bars` cuando no caben tres filas, `curve` dibuja un glifo por columna y nada debajo, `fine` dibuja sólo Braille o espacios, pasa por todas las columnas con un espectro en rampa —que es donde se vería si no uniera las muestras—, no rellena hasta el suelo con la señal al máximo y pone dos bandas por columna; el remuestreo promedia al bajar e interpola al subir, y las cuatro leen el mismo frame de 128 bandas. En la app real: cambiar el ajuste cambia la forma sin mover el widget, la forma llega al borde, el analizador empieza en la misma columna que los datos de la pista y a la derecha de la carátula, un valor inventado cae a `bars`, y la ventana de ajustes escribe el fichero y lo aplica al instante. Render de las cuatro a 120x32 en retro + nord. Falta verlo con audio real y cava, y `fine` en la fuente del usuario. |
| Coste del analizador en 4K         | **Medido**                        | 380x50 a 10 fps con la app real headless: `bars` **54,5% de un núcleo → 7,3%**, `mirror` 57,9% → 8,2%, `curve` 12,2% → 7,7%. `fine` llegó después y va a 9,5%, la más cara de las cuatro y aun así lejos del problema. Los tramos de estilo por frame pasan de 950 a 76 en `bars`, de 950 a 49 en `mirror` y de 379 a 28 en `curve`; el render del widget, de 4,56 ms a 0,45 ms. Dos pruebas fijan el techo. |
| Buscador de la cola (`ctrl+f`)      | **Verificado**                    | Siete unitarias en la app real headless: `ctrl+f` abre la barra y enfoca la caja, «later» deja 1 de 3, `esc` la cierra y devuelve las 3 filas dejando el cursor en la pista a la que se había llegado, la fila filtrada conserva el número 3, `↵` sobre ella reproduce la tercera de la cola y `d` quita esa, la marca `▶` desaparece mientras el filtro esconde lo que suena y vuelve cuando lo enseña, y escribir `x` en la caja no pausa el reproductor. Render a 96x28 con la barra abierta. Falta verlo contra una cola larga real. |
| Volver a lo que suena (`g`)         | **Verificado**                    | Tres pruebas en la app headless: mueve desde otra fila, limpia un filtro que escondía la pista y, sin reproducción, conserva el cursor y explica por qué. |
| Guardar cola como playlist (`p`)    | **Verificado con dobles**         | Crea con el nombre del modal tras `ensure_fresh`, usa una instantánea en orden, divide 700 pistas en siete lotes de 100, permite duplicados, invalida la caché, deja una creación parcial con recuento visible y no abre nada con la cola vacía. Falta probar la escritura contra una cuenta real. |
| Temas temáticos                     | **VERIFICADO A LA VISTA**         | Tests: cada `Layout` nombra un transporte que existe, `ascii_only` pinta su cromo en ASCII, sin glifos anchos en títulos, nombres compartidos solo los de `PAIRED`, contraste mínimo en todas las paletas, y elegir un tema escribe su paleta una vez. Las trece disposiciones pasan los tests de 60x18 y de la carátula. Capturas SVG de los nueve a 120x34 y 80x26, y después capturas del mantenedor en su terminal (unas 274x100, split, cola de 100 pistas) de los nueve con su emblema: posición y tamaño ajustados a su gusto a partir de ellas. El rendimiento en 4K, medido en un pty con pyte a 480x130. `bosque`, su emblema y los marcos nuevos de los diez, vistos por el mantenedor en su terminal (2026-09-11). |
| Velocidad de reproducción | **VERIFICADO POR EL USUARIO** | Oída por el mantenedor contra TIDAL real (2026-09-11). Tests: la ventana ofrece las ocho velocidades y aplica con ↵, `esc` no toca nada, el botón dice la velocidad y se enciende fuera de 1×. |
| Carátula redonda, reloj en cuenta atrás | **CUBIERTO POR TESTS** | Tests: la máscara redonda deja las esquinas en el fondo de la banda y el centro intacto; el reloj en cuenta atrás no pasa de veinte columnas (el test falla con el código viejo). Vistos en capturas SVG. |
| Ordenar la biblioteca, filas de ajustes con lista | **VERIFICADO CONTRA TIDAL REAL** | Tests: favoritos pide a TIDAL el orden con los enums de tidalapi; cada sección ofrece solo sus órdenes; «Mis playlists» manda `order` y `orderDirection`; el orden local deja «más…» al final y no toca la caché; en la app, `s` ordena, el título lo dice y volver al nivel lo conserva. Las flechas no tocan las tres filas y dos Enter en reiniciar no reinician. Probado por el mantenedor contra TIDAL real (2026-09-11), «Mis playlists» incluida: TIDAL respeta el orden en esa petición. |
| Quitar de favoritos o de una playlist | **VERIFICADO CONTRA TIDAL REAL** | Tests: la pista se encuentra más allá de la primera página y se quita por índice; una playlist ajena no se toca; una pista que ya no está lo dice sin quitar nada; quitar un favorito tira su nivel en todos los órdenes; en la app, `d` pregunta en «cancelar», confirmado la fila sale, y en la raíz avisa. Quitar de una playlist propia, probado por el mantenedor contra TIDAL real (2026-09-11). |
| Reproducción automática | **VERIFICADO CONTRA TIDAL REAL** | Tests: encendida, la radio de la última pista va al final sin la semilla ni repetidas y suena la primera nueva, y un segundo «siguiente» mientras llega no pide otra; apagada, el final de la cola se detiene sin pedir nada; una radio sin nada nuevo se detiene y lo dice. Oída por el mantenedor contra TIDAL real (2026-09-11). |
| Pantalla completa | **VERIFICADO POR EL USUARIO** | Tests: `w` abre y `esc` vuelve con la cola y la reproducción intactas; `tab` abre y cierra la cola y ↵ reproduce desde ella; los controles responden al clic; la carátula kitty se queda en la vista, pasa del tope de 20 filas y se esconde bajo una ventana abierta encima; todas las disposiciones caben en el mínimo. Vista por el mantenedor en su terminal 4K con kitty, sixel y `blocks`, ya fluida, y sin la imagen kitty pegada al cerrarla tras activar la transparencia (2026-09-11). |
| Menú de álbum, artista o playlist (`m`) | **CUBIERTO POR TESTS** | Siete tests en la app headless con un álbum de dos páginas: `a` reproduce las tres pistas, `c` las mete detrás de la que suena y el aviso dice cuántas, `l` manda las tres a la playlist elegida, `v` marca el álbum por su clave, el menú no ofrece radio y su `d` no hace nada, `m` sobre una pista abre el menú de siempre, y `a` fuera del menú también trae las dos páginas. Falta probarlo contra TIDAL real con una playlist de más de cien pistas. |
| Ventana de la letra al cambiar de pista | **CUBIERTO POR TESTS** | Con `y` abierta, un «siguiente» por MPRIS cambia título y letra; la de una pista anterior que llegue tarde se descarta. Falta verlo con las teclas multimedia reales. |
| Dos columnas (`split`)              | **Verificado en headless y a mano** | Cuatro tests: mismos objetos (cola, carátula, transporte) y cursor al cambiar de forma, vuelta sola a apilada por ancho y por alto, las trece disposiciones caben en el umbral con el transporte bajo las dos columnas, y la letra se carga una vez por pista y sigue la línea. Capturas SVG de las trece. El mantenedor lo usó en su terminal con audio real y letra. |
| Barras clicables                    | **Verificado**                    | Cuatro pruebas con `pilot.click`: seek a mitad, seek parado sin llamada a mpv, volumen al extremo y balance en cero exacto pese al padding. |
| Ayuda en dos pestañas              | **Verificado**                    | Dos unitarias en la app headless: `→` lleva a «Acerca de» y dibuja el repositorio, `←` vuelve a los atajos con el desplazamiento donde se dejó, y ninguna de las dos flechas se sale por los extremos. Render a 100x30 de las dos pestañas, con la activa marcada en la barra de título. |
| Barra de ayuda del navegador       | **Verificado**                    | Medida en la app real: a 82 columnas entraba `… ⌫ atrás   R` y el resto lo comía el borde. Ahora `fit_hints()` suelta entradas enteras por prioridad y la línea termina siempre en `esc cerrar`. |
| Paginación de la biblioteca        | **Verificado**                    | Unitarias sobre `_paged`, y la app real headless: nivel de 103 pistas → 101 filas con `más…`, `↵` sobre ella → 103 filas sin `más…`.                                            |
| Paginación con páginas filtradas   | **VERIFICADO CONTRA TIDAL REAL**  | En la cuenta del usuario, «Pistas favoritas» pasó de 90 filas sin `más…` a 8 páginas y **699 pistas alcanzables de 766**; los 67 restantes TIDAL no los devuelve en ninguna página. Álbumes 539 y artistas 397 igual. Unitarias con un doble que filtra la página después del límite. |
| Búsqueda por categorías            | **VERIFICADO CONTRA TIDAL REAL**  | «tool» devuelve 101 pistas en 0,34 s con tres filas de categoría; abrirlas da 101 álbumes, 101 artistas y 76 playlists, una petición cada una y sólo al abrirlas. |
| Favoritos (escritura)              | **VERIFICADO CONTRA TIDAL REAL**  | Añadir y quitar una pista que no estaba en favoritos: el contador de la cuenta subió a 767 y volvió a 766. Saldo neto cero. Unitarias para pista, álbum, artista, playlist y para las filas que no son favoritables. |
| Configuración y teclas             | **Verificado**                    | `tidalamp config` sobre un XDG temporal crea la plantilla, y con `quality`, `artwork` y dos teclas cambiadas la app arranca con `HIGH`, `Protocol.BLOCKS` y `play→p`, `quit→ctrl+q`; la acción inventada sale avisada. 13 unitarias de precedencia, TOML roto y plantilla. |
| Reordenar la cola                  | **Verificado**                    | Unitarias de `Queue.move` (bordes, cursor, shuffle intacto) y `alt+↓` en la app real.                                                                                           |
| Reinicio de mpv                    | **Verificado**                    | SIGKILL a mpv con la app corriendo: el tick lo relanza con otro PID y la pista vuelve a sonar. Desde la 0.9.0 el reinicio va en un worker, y el SIGKILL se repitió a mano con él (2026-09-12): mpv nuevo al instante, sin la espera de 5 s de un atasco, y la pista otra vez sonando desde 0:00. Ahora vuelve al segundo donde iba (opción `start=` del `loadfile`, comprobada contra mpv 0.41); **pendiente de repetir el SIGKILL a mano**. |
| mpv que no contesta (0.9.0)        | **VERIFICADO POR EL USUARIO**     | El mantenedor congeló el mpv de la app con `kill -STOP` mientras sonaba (2026-09-12): la pantalla siguió dibujándose, a los 5 s se levantó un mpv nuevo y la pista volvió a sonar, desde 0:00; desde entonces vuelve al segundo donde iba, cubierto por tests y **pendiente de repetir a mano**. En tests: contra el mpv falso por el socket de verdad: un mpv colgado cuesta una espera y no más, un sondeo lo despeja, el EOF se lee como muerte, las respuestas partidas de tres en tres bytes se recomponen. En la app: el atasco se dice en la línea de estado y se sondea fuera del hilo, un mpv muerto se reinicia en un worker y recarga la pista, un reinicio fallido espera. Queda sin ver a mano el otro camino, descongelarlo antes de los 5 s (`kill -CONT`) y que diga «mpv vuelve a contestar»; está cubierto por tests. |
| Sin corte entre pistas (0.9.0)     | **VERIFICADO POR EL USUARIO**     | Oído por el mantenedor contra TIDAL real en un disco en vivo, sin corte (2026-09-12); que suene así dice también que la URL resuelta 20 s antes aguantó. También probado a mano: quitar o barajar la siguiente en los últimos 20 s hace sonar la que dice la cola, y la carátula y la letra de la siguiente llegan con el sonido. En tests: la siguiente se prepara a 20 s del final y no antes, mpv pasa a ella sin volver a resolver, una cola editada o un repeat cambiado quitan lo preparado y se prepara la correcta, un resultado tardío no se encola, lo caducado se vuelve a pedir. Contra el mpv falso: `append`, `playlist-clear` y `playlist-pos`. |
| Volumen normalizado (0.9.0)        | **VERIFICADO POR EL USUARIO**     | Oído por el mantenedor contra TIDAL real, con la insignia `RG` enseñando los valores de cada pista (2026-09-12). En tests: | Los tres modos, el pico como techo, la caída de disco a pista, el 1.0 de relleno de tidalapi, la ganancia como opción por fichero y el reintento sin ella. En la app: la ganancia que llega a mpv cambia con el modo, la preparada lleva la suya, y al apagarlo vuelve a 0; la insignia `RG` enseña la aplicada, y `RG —` sin datos. **Falta oírlo**; los valores reales de TIDAL se leen ahora en la propia insignia. |
| Mis mixes (0.9.0)                  | **VERIFICADO CONTRA TIDAL REAL**  | La página real de mixes, vista por el mantenedor en su cuenta (2026-09-12). En tests: sesión simulada con dos mixes y un enlace entre ellos: la sección lista los dos, cada uno se pide al abrirlo, abrirlo trae sus pistas, un mix vacío es un nivel vacío, y en la app `s` y `d` se niegan. Si deja de funcionar, mirar primero la página: es la parte de TIDAL que más cambia. |
| Espectro con cava                  | **VERIFICADO CON AUDIO REAL**     | El usuario instaló cava 0.10.7 y reprodujo Thriller: la insignia dice `FFT` y las bandas dibujan un espectro con forma, graves y agudos por separado. `pgrep` confirma `cava -p ~/.cache/tidalamp/cava.conf` vivo junto al mpv de la app. |
| Balance y ecualizador              | **Verificado**                    | Grafos validados con `ffmpeg -af` de verdad; en la app real los filtros llegan a mpv, se guardan, y se reaplican tras reiniciar mpv.                                            |
| Reintentos de red                  | **Verificado**                    | Unitarias: reintenta conexión/timeout/503 y `TooManyRequests`; el 429 respeta `retry_after`, cae al backoff con `-1` y abandona sin dormir por encima del tope. No reintenta 404 y se rinde al tercer intento. |
| Letras sincronizadas               | **VERIFICADO CONTRA TIDAL REAL**  | Una letra real de TIDAL, probada por el mantenedor (2026-09-11). 9 pruebas de LRC, texto plano, ventanas, carga y fallos transitorios; el trabajo de red queda fuera del loop. |
| Paletas: Omarchy, integradas y propias | **Verificado**                 | Unitarias con paletas temporales, las seis integradas (`classic`, `tokyo-night`, `catppuccin`, `nord`, `gruvbox`, `black`), un TOML propio leído de su directorio y un nombre con `../` rechazado sin tocar el disco; más montaje Textual y cambio en vivo. La máquina cambió de Wh01s17 a Tokyo Night y el lector tomó el nuevo acento. |
| Estructuras (`theme`): las cuatro | **VERIFICADO A LA VISTA, A MEDIAS** | Pruebas Textual por estructura: los botones cuadrados de `retro` y sus dos barras regladas, el subrayado del acento en `nova`, los corchetes de `ascii`, que ninguna se sale a 60×18 y que ninguna deja la carátula sobre la barra de posición. **A la vista en kitty el usuario confirmó `quattro` y `nova`.** De `retro` sólo llegó a verse la versión de medios bloques, que se descartó por eso mismo (§7); la de teclas cuadradas y `ascii` no se han visto nunca en un terminal real, sólo bajo prueba. |
| Red, escrituras y estado (0.8.1) | **CUBIERTO POR TESTS** | Toda petición a TIDAL, el login incluido, pasa por `net.TimeoutSession` (5 s para conectar, 20 s por lectura). `with_retries(..., idempotent=False)` solo reintenta un 429 o un `ConnectTimeout`: crear una playlist y cada lote de `add` no se repiten si la respuesta se pierde. `config.write_atomically` escribe a un temporal en la misma carpeta, fsync y `os.replace`, y conserva los permisos; lo usan cola, ajustes, órdenes, `config.toml` y los ritmos de PipeWire. `_resolving` descarta en `_start` y `_resolve_failed` una resolución que vuelve después de pedir otra pista. Tests: lectura perdida y conexión cortada no se reintentan en una escritura, 429 y `ConnectTimeout` sí; el timeout por defecto sin pisar uno explícito; la sesión de tidalapi es la nuestra; una playlist y un lote con la respuesta perdida se mandan una vez; un fallo a mitad deja el fichero anterior entero y sin temporales; una resolución vieja no carga nada ni apaga el indicador. Revisión externa (Codex). |
| Permisos de la sesión (0.8.0) | **CUBIERTO POR TESTS** | La sesión guarda los tokens de TIDAL y salía 0644 con el umask 022, legible por cualquier usuario. Ahora el fichero se crea 0600 antes de que tidalapi escriba en él, y la carpeta queda 0700; al cargar, una sesión antigua se corrige. Dos tests: guardar bajo umask 022 deja 0600 y 0700, y cargar una sesión 0644 la cierra. Detectado por una revisión externa (Codex). |
| Refresco del token                 | **VERIFICADO CONTRA TIDAL REAL**  | Copia de la sesión real con el access token invalidado a mano: la app arranca, reescribe el token, completa el handshake (user id y país) y la API responde. El fichero real quedó intacto. Además 10 unitarias con dobles, incluida la del 401 que tidalapi deja escapar. |
| **`login` y reproducción real**    | **VERIFICADO POR EL USUARIO**     | El usuario ejecutó `tidalamp tui` con su cuenta y reprodujo TOOL - Schism (Lateralus) el 2026-09-08. Login, búsqueda, `stream.resolve()` y salida de audio funcionan de verdad. |
| Reproducción real (`ao` de verdad) | **VERIFICADO**                    | Sale sonido por PipeWire, y la prueba es el propio analizador: cava lee el **monitor del sink**, no nuestro mpv, así que un espectro con forma sólo puede venir de audio que llegó al sink. Se comprobó primero con un sink Bluetooth y después con el DAC USB (ver la fila siguiente). |
| Ruta BTS / MPD -> HLS              | **VERIFICADO CONTRA TIDAL REAL**  | Ambas ramas cubiertas por tests con manifiestos fijados, y `stream.resolve()` registra cuál toma. La lectura real ya se hizo: es la matriz de las cuatro calidades sobre dos pistas de la fila siguiente, donde `HI_RES_LOSSLESS` cae en MPD y el resto en BTS —lo que dice la trampa de §7 sobre pedir una calidad y no obtenerla. Esta fila decía «PARCIAL» por una reproducción real que llevaba hecha desde entonces. |
| Hi-res **hasta el DAC**            | **VERIFICADO EN EL HARDWARE**     | La pantalla del propio FiiO BTR15 muestra `PCM 176.4K` mientras la app dice `24bit 176kHz HI_RES_LOSSLESS` y la pantalla de configuración `Salida: FIIO BTR15 · 176400 Hz s32le`. Es la única comprobación que ninguna capa de software puede falsear: está aguas abajo de TIDAL, de mpv y de PipeWire. Confirma además que el drop-in de `allowed-rates` respeta **las dos familias**: 176,4 kHz es múltiplo de 44,1, no de 48, así que el grafo siguió a la pista en vez de acercarla a su ritmo. Antes de esto, con `allowed-rates = [ 48000 ]`, el mismo stream llegaba remuestreado a 48 kHz con la insignia diciendo la verdad sobre el stream. |
| Ruta MPD -> HLS (hi-res)           | **VERIFICADO CONTRA TIDAL REAL**  | Matriz de las cuatro calidades sobre dos pistas reales; con `HI_RES_LOSSLESS` la rama es MPD, FLAC 24 bit/96 kHz, 69 segmentos. `ffprobe` sobre la playlist reescrita da flac/96000/24 y `ffmpeg` decodifica 3 s a un WAV de 1.152.102 bytes (exactamente 96000×3×2×2). La app real con mpv de verdad: insignias `24bit 96kHz HI_RES_LOSSLESS`, posición 12,3 s de 266 s, RMS −19,2 dBFS. La playlist sin reescribir falla con *error reading header* en el mismo ffmpeg. |
| Empaquetado (sdist / wheel / AUR)  | **Verificado salvo la publicación** | `python -m build` + `twine check` en ambos artefactos; 89 pruebas desde el sdist extraído; `bash -n` y `makepkg --printsrcinfo` sobre el PKGBUILD; `pacman -Si` confirma que todas las dependencias están en `extra`. El environment de GitHub y el *pending publisher* de PyPI ya están configurados. No se ha ejecutado `makepkg -si` ni se ha publicado nada porque aún no existe el tag; el envío final al AUR está además bloqueado externamente mientras siga cerrado el registro de cuentas nuevas. |
| Carátula                           | **VERIFICADO A LA VISTA**     | Capturas del usuario en kitty, dos veces: la portada de Thriller se dibuja con el protocolo gráfico en su recuadro, a la izquierda del reloj, sin invadir el marquee ni el analizador, y con el recuadro ya adaptativo. Unidades sobre los tres codificadores, incluida una vuelta completa de sixel a píxeles; la app real bajo un pty con `TERM=xterm-kitty` emite el APC gráfico anclado en la esquina del widget, y en medios bloques pyte muestra el recuadro con el resto del display intacto. |
| Indicador de carga y barra de estado | **Verificado**                  | Unitarias del `Spinner` y de los tres momentos del navegador (raíz, abrir un nivel, volver atrás) con un loader bloqueado a propósito; la app real bajo pty midió `#statusbar` dentro de la pantalla y pintó `⠦ resolviendo «Schism»…` en la última fila. |
| «Mis playlists» y caché de niveles | **Verificado contra TIDAL real**  | cProfile sobre la cuenta del usuario localizó las 111 peticiones; tras el cambio, la app real bajo un pty abre «Mis playlists» en 0,39 s (antes 19,87 s) y en 0,13 s la segunda vez. Unitarias: una petición por página, paginación, claves de caché y `R`. |

**Sobre la sesión:** `~/.config/tidalamp/session.json` **existe** (comprobado el
2026-09-08, después de que el usuario reprodujera hi-res con ella). Si desaparece,
todo lo que diga «contra TIDAL real» en esta tabla vuelve a empezar por
`tidalamp login`, que es interactivo por definición: el device flow pide abrir una URL
y autorizar, y eso no se automatiza desde aquí.

La instrumentación de la rama de manifiesto sigue puesta, por si hace falta repetirla:
`TIDALAMP_DEBUG=1 tidalamp tui` —o `debug = true` desde la pantalla de `o`—, reproducir
una pista en cada calidad y leer `~/.local/state/tidalamp/tidalamp.log`.

## 6. Pendiente

> [!NOTE]
> La funcionalidad comprometida para la próxima versión vive en
> [next.md](./next.md), con sus trampas y su forma de comprobarse. Tras la `0.9.0`
> está vacía. Esta sección sigue siendo el estado general y aquella, la cola de
> trabajo.

P1–P4 están cerradas: lo que queda no es funcionalidad que falte para que el
reproductor sirva, sino acabado, distribución y confirmar contra TIDAL real cosas hoy
probadas sólo con dobles.

**Orden propuesto (2026-09-11):** ~~P5 empaquetado~~ y ~~carátula~~ ✅ hechos. Cada
versión se publica siguiendo `publish.md`; la última publicada es la `0.8.1`
(2026-09-11), en PyPI y en GitHub, y la `0.9.0` está preparada (2026-09-12). Lo que queda abierto aquí pide credenciales tuyas o un par de ojos.

1. Publicar en el AUR cuando vuelva a abrir el registro de cuentas nuevas. El paquete
   está preparado y se puede probar localmente, pero el alta final depende del
   servicio externo y no tiene fecha anunciada.
2. ~~Mirar `retro` y `ascii` en un terminal de verdad~~ ✅ hecho el 2026-09-10; ver §9.5.
   Queda el extremo pequeño: la disposición compacta no se ha visto nunca.
3. ~~Una letra real de TIDAL~~ ✅ probada por el mantenedor el 2026-09-11; era lo
   último de §5 que sólo se había probado con dobles.
4. §9.4, que es una decisión y no una prueba.

**Aviso para quien retome esto:** hay sesión guardada y funciona (§5). Lo que no se
puede automatizar desde aquí sigue siendo rehacerla: `tidalamp login` es interactivo
por definición (device flow).

### ~~P1 — Exponer MPRIS en D-Bus~~ ✅ HECHO

Implementado en `mpris.py` con `dbus-fast`. Ver §4 y §5.

### ~~P2 — Colas y biblioteca~~ ✅ HECHO

Ver §4. Paginación y reordenado con `Alt+↑/↓` incluidos. Queda uno menor:

- [x] `TrackList` de MPRIS. Hecho: ver §4 y §5.

### ~~P3 — Espectro real~~ ✅ HECHO

`spectrum.py` lanza cava contra el sink y el analizador dibuja sus frames; sin cava
sigue el vúmetro RMS y la insignia `FFT`/`RMS` dice cuál es cuál. Pendientes:

- [x] Arrancar el cava real instalado: proceso vivo y frame de bandas (19 entonces; se
      le piden 64 desde que las formas anchas remuestrean el mismo frame).
- [x] Observar el frame con señal de audio real para validar la captura del sink.
- [ ] cava escucha el sink, no nuestro mpv: si suena otra cosa a la vez, se cuela. Se
      arreglaría enrutando mpv a un sink propio de PipeWire, a cambio de un nodo por
      ejecución. No parece que compense todavía.

### ~~P4 — Robustez~~ ✅ HECHO

Ver §4: reinicio de mpv, refresco del token, reintentos con backoff y suite de
`pytest` con mpv falso y manifiestos fijados. Queda menor:

- [x] Verificado contra TIDAL real, invalidando el token de una copia de la sesión.
      Descubrió que `load_session()` ni siquiera llegaba a `ensure_fresh`: ver §4.

### ~~P6 — Migrar de `dbus-next` a `dbus-fast`~~ ✅ HECHO

`dbus-next` **no publica una versión desde julio de 2021** y usa
`typing.no_type_check_decorator`, deprecado y **marcado para eliminación en Python
3.15**: son los 34 avisos de la suite. Cuando Arch actualice el intérprete, `mpris.py`
dejará de importar y con él no arranca la aplicación entera.

- [x] Dependencia e imports cambiados a `dbus-fast>=5.0.22`; `pip check` limpio y
      `dbus-next` retirado del venv.
- [x] Contrato fijado con siete pruebas nuevas, incluida una integración sobre un
      `dbus-daemon` temporal: registro, propiedades, controles, señales, `Seeked` y
      colisión de nombre. Suite completa sin los 34 avisos anteriores.

### P5 — Acabado

- [x] Slider de balance (`,` `.` `\`), como filtro `pan`. El de volumen va de 0 a
      `Mpv.VOLUME_MAX` (100): mpv llega a 130, pero eso es ganancia digital sobre una
      señal ya normalizada y satura. El tope vale igual para el teclado y para MPRIS.
- [x] Ventana de ecualizador de 10 bandas (`e`) sobre el filtro `equalizer`.
- [x] **Ocho presets** (`p` y `P` dentro de la ventana), como datos en `settings.py`,
      que no importa Textual y por tanto se prueban sin levantar una app. Ocho y no los
      treinta del original: caben en la ventana y cubren lo que se busca.
- [x] El preset activo **se deduce de las ganancias**, no se guarda. Uno guardado
      seguiría diciendo «rock» después de mover una banda, hasta que algo lo reiniciara.
      Cuando no coincide con ninguno el estado es `manual`.
- [x] Recorrer desde `manual` empieza por el primero: las bandas están en un sitio que
      el catálogo no describe, y la curva más parecida no es la idea que nadie tiene de
      «el siguiente».
- [x] Las ganancias se recortan al aplicarse y no al escribirse, para que el catálogo se
      lea como lo que cada curva quiso decir y no como lo que sobrevivió al límite.
- [x] Carátula en el terminal vía protocolo Kitty/sixel, con medios bloques como
      fallback universal. Ver §4. Verificada a la vista en kitty. El recuadro ya no es
      18×9 fijo: sigue al terminal entre 18×9 y 40×20.
- [x] Letras sincronizadas y fallback a texto plano (`y`).
- [x] Colores adaptados al tema Omarchy activo, con cambio en vivo y fallback clásico.
- [x] Interfaz bilingüe español/inglés según el locale, incluidos errores, CLI y la
      plantilla de configuración; README público en inglés.
- [x] Empaquetado, dos canales que se complementan. El procedimiento completo de
      publicación está en `publish.md`; aquí sólo el estado.
      - [x] `packaging/aur/PKGBUILD` + `.SRCINFO`. Construye desde el tarball del tag de
            GitHub con `python -m build --no-isolation`, corre la suite en `check()` e
            instala con `python -m installer`. `mpv` es dependencia real y `cava`
            `optdepends`. **Todas las dependencias Python están en `extra`**
            (`python-tidalapi`, `python-textual`, `python-typer`, `python-dbus-fast`,
            `python-requests`), así que el paquete no arrastra nada del AUR — se
            comprobó con `pacman -Si` el 2026-09-08.
      - [x] PyPI: metadata con URLs, keywords y clasificadores; `sdist` que incluye
            `tests/` y `packaging/`, de modo que el `check()` del PKGBUILD funciona
            también desde el sdist (verificado: 89 pruebas desde el tarball extraído).
            `python -m build` produce sdist y wheel y ambos pasan `twine check`.
      - [x] `.github/workflows/release.yml`: al empujar un tag `v*` comprueba que el tag
            coincide con la versión del `pyproject.toml`, construye, pasa `twine check`
            y publica con `pypa/gh-action-pypi-publish` mediante OIDC. Ningún token de
            larga vida. `.github/workflows/ci.yml` corre la suite en 3.11–3.14 e
            instala `dbus` para que la integración MPRIS no se salte.
      - [x] El aviso de `mpv` está en la primera línea de `description` del
            `pyproject.toml` (lo que ve PyPI) y encabeza la sección de instalación del
            README.
      - [x] PyPI Trusted Publishing configurado el 2026-09-09: environment `pypi` en
            GitHub con revisión manual y *pending publisher* con owner `wh01s17`,
            repositorio `tidalamp`, workflow `release.yml` y environment `pypi`.
      - [ ] **AUR bloqueado externamente:** el registro público de cuentas nuevas
            continúa cerrado por el endurecimiento de seguridad y el mantenedor no
            tiene una cuenta anterior. No hay fecha anunciada ni un alta manual que
            completar. `sha256sums` sigue en `SKIP` hasta que exista el tag; después se
            puede ejecutar `updpkgsums` y `makepkg -Csi` aunque el push al AUR tenga que
            esperar.

## 7. Trampas conocidas

Cosas que ya costaron tiempo una vez:

- **tidalapi convierte el 429 antes de que llegue a la app.** En 0.8.11 un límite de
  peticiones deja de ser `requests.HTTPError` y pasa a
  `tidalapi.exceptions.TooManyRequests`; buscar sólo el código 429 en la respuesta no
  sirve porque esa rama ya no la ve. La excepción lleva `retry_after` (`-1` cuando no
  hubo cabecera). `net.with_retries()` reconoce ambos tipos y no duerme más de 60 s.
- **Sintaxis de la etiqueta de filtro en mpv**: es `--af=@etiqueta:lavfi=[...]`, con la
  etiqueta **delante**. Ponerla detrás (`lavfi=[...]@etiqueta`) hace que mpv aborte al
  arrancar y el socket IPC nunca aparece.
- **Un widget no debe fiarse del valor que le dan.** `Slider` calculaba el relleno
  como `int(valor / máximo * pista)` sin acotarlo, y el player permitía 130 mientras
  el slider seguía creyendo que el máximo era 100. Con el valor fuera de rango la barra
  crecía más que su pista, empujaba el número fuera del widget y, pasado cierto punto,
  la línea era tan larga que Textual no dibujaba nada. Dos lecciones: acotar en el
  render, y no dejar que un rango viva como número mágico en un módulo mientras otro
  supone otro (`Mpv.VOLUME_MAX`, leído por el slider en `on_mount`).
- **`box-sizing` de Textual es `border-box`**: el `padding` come de la altura
  declarada. Un widget con `height: 3` y `padding-top: 1` sólo pinta 2 filas. Con una
  carátula dentro no se queda en un recorte: un protocolo gráfico pinta por encima de
  lo que haya debajo en vez de recortarse, así que esa fila que no cabía apareció
  encima de la barra de posición. Quien fije la altura de una banda tiene que sumarle
  su propio relleno.
- **El socket IPC comparte stream con los eventos async de mpv**: hay que leer líneas
  hasta encontrar la que lleva nuestro `request_id`, no asumir que la primera respuesta
  es la nuestra.
- **Un selector CSS agrupado (`#a, #b {}`) editado con sed** puede dejar reglas
  aplicadas al widget equivocado. Pasó con `#seek, #volume`.
- **dbus-fast exige anotaciones de tipo que sean constantes de cadena.** Un método
  D-Bus que devuelve void no lleva anotación **ninguna**: poner `-> None` hace que
  falle al importar el módulo, porque intenta leerlo como firma de salida.
- **zsh no hace word-splitting de variables sin comillas.** Guardar flags en una
  variable (`D="-d foo -o /bar"`) y pasarla como `$D` los entrega como un único
  argumento. Usar arrays de bash en los scripts de prueba.
- **Cuidado con `pkill -f <patrón>` / `pgrep -f` en estos scripts**: el patrón suele
  aparecer en la propia línea de comandos del shell que lo ejecuta, y el shell se mata
  a sí mismo. Matar por PID. (Esta trampa ya mordió dos veces.)
- **`request_name` de D-Bus no lanza excepción si el nombre está ocupado**: devuelve
  un `RequestNameReply` distinto de `PRIMARY_OWNER` y la instancia se queda muda
  mientras todo el tráfico va a la primera. Hay que comprobar la respuesta.
- **Al probar por D-Bus, verifica a QUIÉN estás preguntando.** Una prueba contra
  `org.mpris.MediaPlayer2.tidalamp` puede acabar hablando con la instancia real del
  usuario y modificándole el estado. Usa el nombre con sufijo de instancia y compara
  el PID dueño antes de escribir nada.
- **`af set` reemplaza toda la cadena de filtros de mpv.** Usarlo para el ecualizador
  se llevaría por delante el `astats` del que vive el vúmetro. Para cambiar un filtro
  con etiqueta: `af remove @etiqueta` y luego `af add @etiqueta:lavfi=[…]`.
- **No reaplicar filtros desde un tick de sondeo.** `af remove` + `af add` reinicializa
  el filtro y puede introducir un hueco audible. `_apply_audio()` sólo corresponde al
  montaje, a un cambio explícito y al reinicio de mpv.
- **Las rutas de socket unix se cortan en ~108 bytes.** El directorio de scratchpad de
  la sesión ya gasta casi todo el presupuesto, así que un `--input-ipc-server` ahí
  falla con `AF_UNIX path too long`. Los scripts de prueba crean el socket en un
  `mkdtemp()` corto.
- **`logging` tiene un handler de último recurso que escribe a stderr.** Un
  `log.warning` sin handlers propios pinta encima de la TUI. Por eso `__init__.py`
  registra un `NullHandler` en el logger `tidalamp`: basta con que exista uno en la
  cadena para que el de último recurso no entre.
- **Un protocolo gráfico que responde escribe en el teclado.** El terminal contesta
  a cada trozo del protocolo de kitty por la misma vía por la que llegan las teclas, y
  Textual lo lee como pulsaciones. `q=2` silencia esas respuestas; y por eso tampoco
  se consulta al terminal para detectar el protocolo. `C=1` es el otro imprescindible:
  sin él la imagen mueve el cursor por debajo del compositor.
- **Parar mpv y que una pista termine son indistinguibles desde el tick.** El tick
  lento interpreta «mpv pasó a idle» como «la pista acabó» y avanza. `action_stop()`
  deja mpv en idle a propósito, así que sin avisar (`_was_idle = True`) el tick
  siguiente llamaba a `action_next()` y, con `playing = -1`, `next_index()` devuelve 0:
  pulsar «v» rearrancaba la lista desde el principio.
- **Una prueba que no espera al tick pasa en vacío.** La primera versión de la
  regresión de «v» ponía `idle = False` y hacía `pilot.pause()` sin retardo: el tick
  lento de 250 ms nunca corría, `_was_idle` seguía en `True`, la transición no se
  producía y la prueba pasaba **también sin el arreglo**. Toda prueba de esta clase
  tiene que afirmar el estado previo (`assert application._was_idle is False`) antes
  de provocar el suceso.
- **`Static.update` lee un `str` como marcado de Rich.** Un texto que no escribimos
  nosotros —un nombre de TIDAL («Lateralus [Deluxe Edition]»), el título de una pista,
  el mensaje de una excepción— pierde todo lo que va desde el primer corchete, y si
  lleva una etiqueta de cierre (`[/]`) lanza `MarkupError` en pleno render. Los cuatro
  `Static` que reciben texto ajeno se construyen con `markup=False`; los que reciben un
  `Text` ya construido (playlist, marquesina, letras) nunca corrieron peligro.
- **Una imagen de kitty flota por encima del texto.** Un modal se abre *debajo* de la
  carátula, no encima. Hay que retirarla al apilar la pantalla y restaurarla al
  desapilarla; `z=-1` no sirve, porque entonces el fondo del propio widget la taparía.
- **`Segment(texto, None, True)` es un segmento de control**: mide cero celdas, así
  que cabe dentro de una línea que el compositor ya está pintando sin descuadrarla.
  Que sobreviva al recorte de `Strip` no era evidente: está comprobado bajo un pty.
- **`tidalapi` valida el token guardado con una petición, y deja escapar el 401.**
  `load_session_from_file()` no «carga» sin más: llama a `load_oauth_session()`, que
  hace `GET /sessions` y revienta con `HTTPError` si el token caducó. Su docstring dice
  que refresca automáticamente; no lo hace. Y `token_refresh()` sólo cambia el access
  token: hay que rehacer el handshake o la sesión queda sin `user`, `country_code` ni
  `session_id`.
- **Una respuesta corta de TIDAL no significa que no haya más.** El límite se aplica
  antes de filtrar la ventana, así que `limit=100` puede devolver 90 con 766 detrás.
  Cualquier paginación que deduzca el final del tamaño de la página está rota; hay que
  preguntar el recuento.
- **`add_track` devuelve True y la lista no cambia.** No es que falle: la lista de
  favoritos que estabas mirando venía cortada por lo anterior. Para comprobar una
  escritura, mira `totalNumberOfItems`, no el listado.
- **Pedir una calidad no es obtenerla.** Con el cliente del device flow, `LOSSLESS`
  vuelve como `HIGH` siempre. Sólo `HI_RES_LOSSLESS` alcanza la rama MPD, y sólo en
  pistas etiquetadas `HIRES_LOSSLESS`. Cualquier medida sobre «lossless» que no mire
  `stream.audio_quality` devuelto está midiendo otra cosa.
- **El primer segmento de un DASH no es audio.** Es `ftyp`+`moov`. Listarlo como
  segmento en un HLS hace que ffmpeg falle con *error reading header* en todos; va en
  `#EXT-X-MAP`, con `#EXT-X-VERSION:7`.
- **ffmpeg hereda la lista de protocolos permitidos del padre.** Un `.m3u8` local que
  apunta a https no puede seguirlos sin `protocol_whitelist`. Y en mpv esa opción lleva
  comas, que su parser usa como separador: hay que escribirla como
  `%<longitud>%<valor>` o se parte en trozos que ffmpeg nunca ve.
- **El error de mpv puede estar enterrado.** El síntoma era un timeout y un muro de
  *error reading header*; la causa (`Protocol 'https' not on whitelist`) sólo aparecía
  en la primera línea del log. Leer el principio, no el final.
- **En `tidalapi`, parsear puede costar una petición por elemento.**
  `Playlist.factory()` convierte en `UserPlaylist` toda playlist tuya, y ese
  constructor hace un GET para leer el ETag. Cualquier listado que se sienta lento
  merece un cProfile antes que una teoría: aquí el 99 % del tiempo estaba en `send()`,
  no en el parseo, aunque el síntoma pareciera «parsear 110 objetos».
- **La caché de niveles es estado de módulo.** Las pruebas la limpian con una fixture
  autouse en `conftest.py`; sin ella, un test se lleva las filas del anterior.
- **Un widget de altura `auto` que pinta lo que le den crece sin freno.** `RowList`
  dibuja `size.height` filas, así que medirlo en `auto` daba una altura enorme y
  empujaba la barra de estado fuera de la pantalla. Los paneles que llenan hueco van
  con `1fr`, no con `auto`.
- **Un reactive que cambia el tamaño necesita `layout=True`.** El `Spinner` es de
  ancho `auto`: sin eso quedaba medido a cero cuando no tenía texto y no volvía a
  aparecer nunca.
- **La suite leía el `config.toml` real del usuario.** `config.FILE` se lee al
  importar el módulo, y sólo los tests que llamaban a `isolate_config` lo desviaban a
  un temporal. Mientras no hubo un ajuste que cambiara el dibujo daba igual; en cuanto
  `theme` existió, la misma suite pasaba o fallaba según lo que el usuario hubiera
  elegido por última vez en la app corriendo — verde dos veces y roja a la tercera sin
  tocar una línea de código. La fixture `pristine_config` de `conftest.py` apunta
  `CONFIG_FILE` a un temporal vacío, limpia las variables de entorno y restaura los
  globales al terminar.
- **Los ajustes son estado de módulo, como la caché de niveles.** Un test que cambiaba
  el tema dejaba a todos los siguientes dibujando el otro. Misma fixture.
- **Los medios bloques no son un contorno.** `▛▀▜` parecía el bisel de un botón de
  Winamp en un volcado ASCII; en color cada `▀` rellena su celda y la fila entera sale
  como una losa gris de lado a lado del panel. La única arista que tiene de verdad un
  terminal es una línea dibujada.
- **`Static.update(..., layout=False)` conserva el ancho que ya tenía.** Es lo correcto
  para los ticks, que repintan el transporte varias veces por segundo. Deja de serlo
  cuando el contenido cambia de tamaño: al cambiar de tema en vivo, los botones se
  recortaban al ancho del tema anterior y la fila salía cortada a media palabra. El
  cambio de aspecto y el redimensionado piden `layout=True`; los ticks no.
- **Los corchetes de un rótulo desaparecen.** Misma trampa que la de `Static.update` y
  el marcado de Rich, pero desde dentro: el tema `ascii` dibuja su barra de título como
  «[ TIDAL AMP ]», y Rich se comió los corchetes y todo lo que iba entre ellos. Las dos
  cabeceras se construyen ya con `markup=False`.
- **Textual captura stdout mientras la app corre**: un `print` dentro de `run_test()`
  no aparece hasta que el bloque termina. Para sacar datos de una app que sigue viva,
  escribe a un fichero.
- **Un mpv sin corte no pasa por idle.** Con una pista en cola (`loadfile … append`),
  mpv va de una a otra sin que `idle-active` se encienda, así que el `_was_idle` que
  detecta el final no se entera. El avance se lee en `playlist-pos`.
- **`loadfile` cambió de forma en mpv 0.38**: entró un índice entre las banderas y las
  opciones. Por posición, las opciones de una versión son el índice de la otra; con
  argumentos con nombre (`{"name": "loadfile", "url": …, "options": …}`) no importa.
- **Un filtro nuevo en mpv es un hueco.** Por eso el ReplayGain no es un filtro:
  cambiarlo en cada pista rompía justo lo que el cambio sin corte arregla.
  `volume-gain` es un volumen y se pasa por fichero.
- **tidalapi rellena con 1.0 la ganancia y el pico que TIDAL no manda.** Una ganancia
  de 1.0 son +1 dB reales; los dos a 1.0 a la vez se tratan como ausentes.
- **`session.mixes()` y `user.mixes()` no son lo mismo.** El primero es la página de
  mixes que TIDAL hace para la cuenta; el segundo, los mixes marcados como favoritos.

## 8. Entorno

**El proyecto se está trabajando desde más de una máquina.** Lo que sigue describe la
segunda (2026-09-08, host `omarchy`), no la que se documentó al principio: no des por
instalado nada sin comprobarlo.

- Arch Linux, Hyprland (Omarchy), Wayland. Python 3.14. `mpv`, `ffmpeg`, `kitty`,
  `dbus-daemon` y `pw-cli` presentes.
- **Ausentes aquí:** `cava` (el espectro cae al vúmetro RMS, por diseño) y `playerctl`
  (sólo hace falta para probar MPRIS a mano; la suite levanta su propio bus).
- El sink por defecto es **Bluetooth**. Importa para el espectro: cava lee el monitor
  del sink, y por Bluetooth la latencia es alta, así que las barras irán algo por detrás
  del sonido. No es un fallo del analizador.
- Venv en `.venv/`, rehecho tras el renombrado; `.venv/bin/tidalamp` funciona de nuevo.
  Lleva el paquete en editable más `pytest` y `pyte`.
- Tests: `.venv/bin/python -m pytest` (375 pruebas, ~60 s, sin red ni bus de usuario).
  El extra `dev` arrastra Pillow, así que las pruebas de carátula corren de verdad; si
  falta, se saltan solas.
- En la primera máquina `cava` sí estaba, en `/usr/bin/cava`, y arrancó con la
  configuración real de 19 bandas. Las pruebas automatizadas usan `tests/fake_cava.py`
  y no lo necesitan en ninguna de las dos.
- Para ver el layout sin terminal interactivo hay un atajo más corto que pyte:
  `app.export_screenshot()` dentro de `run_test()` da un SVG del que se saca el texto.
- Smoke headless de la app entera (mpv falso + sesión doble) en el scratchpad de la
  sesión: ejerce paginación, reordenado y muerte/reinicio de mpv sobre la app real.
- MPRIS tiene una integración reproducible en `tests/test_mpris.py`: levanta un bus de
  sesión temporal, conecta dos servicios y un cliente, y lo destruye al terminar.
- Para verificar la TUI sin terminal interactivo: correr la app bajo `pty.fork()` y
  emular la pantalla con `pyte`. Es como se generaron las capturas de este repo.


## 9. Qué queda para el usuario

**Las tres comprobaciones de esta sección están hechas** (2026-09-08). El usuario
instaló cava, reprodujo Michael Jackson – Thriller en hi-res y mandó una captura:
carátula dibujada con el protocolo de kitty, insignias `24bit 176kHz HI_RES_LOSSLESS`,
analizador en `FFT` con espectro real, barra de estado visible con
«reproduciendo Michael Jackson – Thriller». Se conserva el procedimiento por si hay que
repetirlo tras un cambio.

Más tarde, la misma pista sirvió para la comprobación que faltaba y que ninguna de
estas tres cubría: que el hi-res llegue **al DAC** sin remuestrear. La pantalla del
FiiO BTR15 marcando `PCM 176.4K` es la prueba; está en la tabla de §5.

Queda §9.5, que sí es una comprobación, y §9.4, que es una decisión y no una prueba.
La versión `0.1.0` ya está cerrada y PyPI tiene listo Trusted Publishing; quedan subir
el commit, comprobar el CI y crear el tag que inicia la publicación. El alta y la
subida al AUR quedan aparte y sin fecha hasta que Arch reabra el registro público de
cuentas nuevas.

### 9.1 Espectro real de cava — HECHO

En esta máquina `cava` no está instalado (en la otra sí lo estaba; ver §8):

```sh
sudo pacman -S cava
cd ~/Documents/workspace/tidalamp && .venv/bin/tidalamp tui
```

Con un sink Bluetooth como el de aquí, cuenta con que las barras vayan un poco por
detrás del sonido: la latencia es del camino de audio, no del analizador.

Reproduce algo y mira la insignia del display, a la derecha del `HI_RES_LOSSLESS`:

- Dice **`FFT`** → cava arrancó y el analizador pinta su espectro. Las bandas graves y
  agudas se mueven por separado.
- Dice **`RMS`** → cava no arrancó y estás viendo el vúmetro repartido en bandas: todas
  suben y bajan a la vez. Si pasa esto, `pgrep -a cava` dice si el proceso vive, y
  `TIDALAMP_DEBUG=1 .venv/bin/tidalamp tui` deja el motivo en
  `~/.local/state/tidalamp/tidalamp.log`.

Qué anotar: si con música sonando las bandas responden a la música de verdad. Es lo
único que valida que cava está capturando el sink y no leyendo silencio.

### 9.2 Carátula en kitty — HECHO

En la misma sesión, la portada va a la izquierda del reloj, en un recuadro que crece
con el terminal (18×9 a 40×20). Tu
terminal es kitty, así que se dibuja con su protocolo gráfico: píxeles de verdad.

```sh
.venv/bin/tidalamp tui                      # kitty, píxeles
TIDALAMP_ART=blocks .venv/bin/tidalamp tui  # medios bloques, para comparar
```

Qué mirar:

1. Que la imagen caiga dentro del recuadro y no se monte sobre el reloj ni el marquee.
2. Que **desaparezca** al abrir `l`, `y` o `e`, y **vuelva** al cerrar la ventana. Es
   deliberado: una imagen de kitty se pinta por encima del texto y si no, el modal se
   abriría por debajo.
3. Que al cambiar de pista se sustituya, sin acumular imágenes ni dejar restos al salir.

Si no aparece nada, la barra de estado lo dice: falta Pillow, `.venv/bin/pip install -e ".[art]"`.

### 9.3 Salida de audio real — HECHO

Todo lo verificado por vía automatizada es con `ao=null`: mpv decodifica de verdad (RMS
−19,2 dBFS sobre una pista hi-res) pero no sale sonido por PipeWire en ninguna sesión
de pruebas. Para repetirlo a mano: reproducir una pista hi-res y una normal, comprobar
que se oyen y que las insignias dicen `24bit … HI_RES_LOSSLESS` en la primera.

**Y mirar el DAC, no sólo la insignia.** Las dos cosas pueden discrepar: si PipeWire
tiene el grafo fijo en un ritmo, la insignia dice la verdad sobre el stream mientras el
DAC recibe 48 kHz. La pantalla de `o` lo detecta y lo arregla; un DAC con pantalla lo
confirma, y si no la tiene, `grep Momentary /proc/asound/card*/stream0` mientras suena.

### 9.4 Decisión pendiente, no comprobación

cava escucha el **sink**, no nuestro mpv: si suena otra cosa a la vez, se cuela en el
analizador. Se arreglaría enrutando mpv a un sink propio de PipeWire, a cambio de un
nodo por ejecución. Sigue sin parecer que compense; la decisión es tuya.

### 9.5 Mirar `retro` y `ascii` — HECHO

**Las cuatro vistas a la vista el 2026-09-10**, en capturas del terminal real del
usuario a su tamaño habitual. La fila del transporte no se sale ni se parte en ninguna,
las barras de título llenan su fila sin cortar el nombre, y la carátula queda dentro de
su recuadro. La revisión encontró defectos reales y se arreglaron en la 0.4.0: la fila
del título de la cola se quedaba corta por un número escrito a mano distinto en cada
disposición, `nova` empezaba en la fila cero contra el borde del terminal, y en
`quattro` el nombre de la app caía justo encima de la carátula.

Lo que sigue sin verse es el extremo pequeño: las capturas son de un terminal ancho, y
la disposición compacta —por debajo de 80x26— sólo está cubierta por pruebas, que miden
celdas y no colores.

Las cuatro estructuras están cubiertas por pruebas Textual, pero una prueba mide
celdas, no colores. Ya mordió una vez: el `retro` de medios bloques pasaba sus
pruebas y en pantalla era una losa gris de lado a lado (§7).

```sh
TIDALAMP_THEME=retro .venv/bin/tidalamp tui
TIDALAMP_THEME=ascii .venv/bin/tidalamp tui
```

Qué mirar en cada una: que la fila del transporte no se salga ni se parta, que las
barras de título llenen su fila sin cortar el nombre, y que la carátula quede dentro
de su recuadro y no encima de la barra de posición. Con `o` se cambia entre las cuatro
sin reiniciar, que es la forma rápida de compararlas.
