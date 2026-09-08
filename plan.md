# plan.md — estado del proyecto `tidalamp`

Documento de traspaso. Describe qué existe, qué está verificado, qué falta y con qué
criterio se tomaron las decisiones, para que cualquiera (humano o modelo) pueda
retomar el trabajo sin contexto previo.

**Última actualización:** 2026-09-08 (refresco del token verificado contra TIDAL: la
app se negaba a arrancar con un access token caducado; antes, el hi-res, el rendimiento
de la biblioteca, el indicador de carga, `TrackList`, carátula y empaquetado)

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
  config.py     Rutas XDG y calidad por defecto. Sin dependencias internas.
  auth.py       Device flow y persistencia de sesión. Lanza NotLoggedIn.
  stream.py     Track -> Playable (URL o playlist HLS local). Lanza StreamUnavailable.
  player.py     Clase Mpv: spawn del proceso, socket IPC, transporte, medición RMS.
  widgets.py    TimeDisplay, Marquee, Analyzer, SeekBar, Slider. Sin lógica de negocio.
  app.py        TidalAmp y sus modales de búsqueda, biblioteca, letras y ecualizador.
  winamp.tcss   Paleta y layout.
  queue.py      Entry (metadatos serializables + Track perezoso) y Queue (orden,
                shuffle, repeat, persistencia). No conoce la UI.
  library.py    Navegación de la biblioteca. Devuelve listas de Row, paginadas.
  net.py        with_retries(): reintentos con backoff para las llamadas a TIDAL.
  spectrum.py   Cava: proceso cava + lector de frames. Opcional por diseño.
  settings.py   Balance y ecualizador: grafos de filtro y persistencia.
  lyrics.py     Carga de letras, parseo LRC y modelo de sincronización. Sin Textual.
  theme.py      Paleta semántica: tema Omarchy activo o fallback clásico validado.
  artwork.py    Carátula: descarga con cache, y codificación kitty / sixel /
                medios bloques. Sin Textual ni tidalapi.
  mpris.py      Servicio MPRIS2 en D-Bus. Habla con la app por el Protocol
                PlayerBackend, así que no conoce Textual ni tidalapi.
  cli.py        Entrypoint typer: login / tui / search.

packaging/
  README.md     Procedimiento de publicación en PyPI y en el AUR.
  aur/PKGBUILD  Receta de Arch; `.SRCINFO` se regenera con makepkg.
.github/workflows/
  ci.yml        pytest en 3.11–3.14.
  release.yml   tag v* -> build -> twine check -> PyPI por OIDC.
```

Dependencia en un solo sentido:

```text
cli -> app -> {player, stream, widgets, mpris, library, lyrics, spectrum, settings}
       app -> {queue, net, artwork} -> {auth, config}
       widgets -> artwork  (sólo los tipos Cover/Protocol y el borrado de kitty)
```

`widgets.py` no conoce TIDAL ni mpv; recibe valores por reactives. Mantener esa
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

### Interfaz — `app.py`, `widgets.py`, `winamp.tcss`

- [x] Reloj de siete segmentos, con alternancia transcurrido/restante (`t`).
- [x] Marquee del título con scroll.
- [x] Analizador de 19 bandas con balística ataque rápido / caída lenta y marcas de pico.
- [x] Barra de posición y slider de volumen.
- [x] Playlist con cursor, marcador de pista en curso y scroll centrado.
- [x] Búsqueda en TIDAL en modal, ejecutada en hilo para no bloquear la UI.
- [x] Avance automático al terminar la pista (se detecta por `idle-active` de mpv).
- [x] Teclas de Winamp: `z` `x` `c` `v` `b`, más `/` `l` `y` `e`, navegación,
      balance, volumen, shuffle/repeat y salida.
- [x] Indicadores persistentes `SHUF ON/OFF` y `REP OFF/ALL/1`, con resaltado para el
      modo activo y actualización inmediata por teclado o MPRIS.
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
- [x] Paginación: `_paged()` pide `PAGE` (100) elementos y, si la página vuelve llena,
      cuelga una fila `más…` al final. `↵` sobre ella carga la siguiente página **en el
      mismo nivel** (`RowList.extend_at`), sin perder el scroll. Una página que vuelve
      corta es el final; un total múltiplo exacto de 100 ofrece una página vacía, que es
      preferible a mentir sobre el recuento.
- [x] La búsqueda también pagina.
- [x] **«Mis playlists» costaba 20 s con 110 playlists.** `session.user.playlists()`
      parece una llamada y no lo es: al parsear cada elemento lo pasa por
      `Playlist.factory()`, que para una playlist propia construye un `UserPlaylist`,
      y ese constructor **vuelve a pedir la playlist entera para leer el ETag**. Medido
      con cProfile contra la cuenta real: 111 peticiones HTTP, 19,87 s, de las cuales
      la red útil eran 0,25 s. Como no editamos playlists, `_playlists_level()` parsea
      el listado con `Playlist.parse()` (que no pide nada) y se salta la factoría.
      Además ahora pagina como el resto. Resultado en la app real: **0,39 s**.
- [x] Caché de niveles en memoria (`library.cached` / `library.forget`): volver a
      entrar en un nivel ya visitado es instantáneo. Sólo en memoria, porque una
      biblioteca cambia desde otros dispositivos; `R` en el navegador olvida el nivel y
      lo vuelve a pedir. La lista cacheada se entrega tal cual, no copiada, para que
      las páginas que el usuario ya cargó con «más…» sigan ahí al volver.

### Robustez — `net.py`, `player.py`, `auth.py`

- [x] `net.with_retries()`: 3 intentos con backoff 0.6s→1.2s. Reintenta lo transitorio
      (conexión, timeout, 408/429/5xx) y propaga de inmediato lo que no va a cambiar
      (401, 404). Envuelve `track.get_stream()`, `entry.resolve()` y los niveles de la
      biblioteca.
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

### Espectro — `spectrum.py`, `widgets.py`

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
- [x] Pillow es opcional: sin él `decode()` devuelve `None`, no hay carátula y no
      cambia nada más. Mismo trato que cava.
- [x] Las imágenes de kitty y sixel se pintan por encima del texto, en una capa que el
      compositor de Textual desconoce: la carátula se retira al apilar una pantalla
      modal y se restaura desde el tick lento al desapilarla, y se borra por id al
      desmontar el widget.

### Tests — `tests/`

- [x] `pytest`, 174 pruebas, sin red y sin TIDAL. `pip install -e ".[dev]"`.
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
      shuffle/repeat y la garantía de que el tick lento no reinstala filtros.

### Navegador y cola en la UI — `app.py`

- [x] `BrowserScreen` con pila de niveles, `⌫` para volver y carga en worker.
- [x] `↵` reproduce y encola el nivel entero; `a` añade uno (o el contenedor completo);
      `A` añade todo el nivel, y si el nivel sólo tiene contenedores cae en `a`.
- [x] `RowList` es un único widget compartido por la cola y por el navegador.
- [x] `s` shuffle, `r` repeat, `d` quitar, `C` vaciar; indicadores `[SHUF REP:ALL]`.
- [x] La cola se restaura al arrancar.
- [x] `alt+↑` / `alt+↓` reordenan la cola. `Queue.move()` remapea la permutación de
      shuffle en vez de regenerarla, así que reordenar no vuelve a barajar lo que suena
      después, y el cursor y la marca de «sonando» siguen a la pista movida.

### CLI — `cli.py`

- [x] `tidalamp login`, `tidalamp tui`, `tidalamp search <query>`.

## 5. Estado de verificación

Distinguir esto importa: parte del código nunca se ha ejecutado contra TIDAL real.

| Área                               | Estado                            | Cómo se comprobó                                                                                                                                                                |
| ---------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| IPC de mpv                         | **Verificado**                    | Script directo: get/set de volumen, `idle`, `paused`.                                                                                                                           |
| Medición RMS                       | **Verificado**                    | Tono de 440 Hz generado con ffmpeg; devuelve −21 dBFS estable.                                                                                                                  |
| Layout y render de la TUI          | **Verificado**                    | La app real corriendo en un pty, con `pyte` emulando el terminal y datos stub.                                                                                                  |
| MPRIS: registro y propiedades      | **Verificado con `dbus-fast`**    | Integración automatizada contra un `dbus-daemon` temporal más la comprobación manual previa con `gdbus`.                                                                        |
| MPRIS: controles                   | **Verificado con `dbus-fast`**    | Play y Volume cruzan el bus real; todos los transportes y setters están cubiertos con backend falso.                                                                            |
| MPRIS: señales                     | **Verificado con `dbus-fast`**    | El bus aislado recibe un solo `PropertiesChanged`, ninguno si no cambia el estado, y `Seeked` conserva microsegundos.                                                           |
| MPRIS: LoopStatus / Shuffle        | **Verificado con `dbus-fast`**    | Lectura/escritura del adaptador, más la integración Textual de sus indicadores persistentes.                                                                                    |
| MPRIS: colisión de nombre          | **Verificado con `dbus-fast`**    | Dos conexiones reales al bus aislado: la segunda reclama `.instance<pid>`.                                                                                                     |
| MPRIS: TrackList                   | **Verificado con `dbus-fast`**    | `Tracks`, `GetTracksMetadata`, `GoTo` y `CanEditTracks` contra el bus aislado, con `TrackListReplaced` recibido por un cliente real; más unitarias de identidad de fila (dos veces la misma canción, reordenado, ida y vuelta a disco) y una que fija que el tick no construye metadata. |
| Cola: shuffle / repeat             | **Verificado**                    | Unitarias de recorrido en los tres modos y prueba Textual de indicadores persistentes por teclado y setters MPRIS.                                                             |
| Cola: persistencia                 | **Verificado**                    | Ida y vuelta a disco, y dos sesiones reales de la app encadenadas.                                                                                                              |
| Navegador de biblioteca            | **Verificado**                    | Drill-down, `↵`, `a` y `A` con una sesión simulada.                                                                                                                             |
| Paginación de la biblioteca        | **Verificado**                    | Unitarias sobre `_paged`, y la app real headless: nivel de 103 pistas → 101 filas con `más…`, `↵` sobre ella → 103 filas sin `más…`.                                            |
| Reordenar la cola                  | **Verificado**                    | Unitarias de `Queue.move` (bordes, cursor, shuffle intacto) y `alt+↓` en la app real.                                                                                           |
| Reinicio de mpv                    | **Verificado**                    | SIGKILL a mpv con la app corriendo: el tick lo relanza con otro PID y la pista vuelve a sonar.                                                                                  |
| Espectro con cava                  | **Parcial con cava real**         | Unitarias con frames normalizados y muerte del doble. El binario real está instalado y produjo un proceso vivo con 19 bandas; falta observar señal mientras suena audio.       |
| Balance y ecualizador              | **Verificado**                    | Grafos validados con `ffmpeg -af` de verdad; en la app real los filtros llegan a mpv, se guardan, y se reaplican tras reiniciar mpv.                                            |
| Reintentos de red                  | **Verificado**                    | Unitarias: reintenta conexión/timeout/503, no reintenta 404, se rinde al tercer intento.                                                                                        |
| Letras sincronizadas               | **Verificado con dobles**         | 9 pruebas de LRC, texto plano, ventanas, carga y fallos transitorios; el trabajo de red queda fuera del loop. Falta probar una letra real de TIDAL.                             |
| Tema Omarchy / fallback             | **Verificado**                    | Unitarias con paletas temporales y montaje Textual; la máquina cambió de Wh01s17 a Tokyo Night y el lector tomó el nuevo acento.                                               |
| Refresco del token                 | **VERIFICADO CONTRA TIDAL REAL**  | Copia de la sesión real con el access token invalidado a mano: la app arranca, reescribe el token, completa el handshake (user id y país) y la API responde. El fichero real quedó intacto. Además 10 unitarias con dobles, incluida la del 401 que tidalapi deja escapar. |
| **`login` y reproducción real**    | **VERIFICADO POR EL USUARIO**     | El usuario ejecutó `tidalamp tui` con su cuenta y reprodujo TOOL - Schism (Lateralus) el 2026-09-08. Login, búsqueda, `stream.resolve()` y salida de audio funcionan de verdad. |
| Reproducción real (`ao` de verdad) | **Verificado sólo con `ao=null`** | Nunca se ha sacado sonido por PipeWire en esta sesión.                                                                                                                          |
| Ruta MPD -> HLS                    | **PARCIAL**                       | Ambas ramas están cubiertas por tests con manifiestos fijados, y `stream.resolve()` ya registra cuál toma. Falta una reproducción real con `TIDALAMP_DEBUG=1` para leerlo.      |
| Ruta MPD -> HLS (hi-res)           | **VERIFICADO CONTRA TIDAL REAL**  | Matriz de las cuatro calidades sobre dos pistas reales; con `HI_RES_LOSSLESS` la rama es MPD, FLAC 24 bit/96 kHz, 69 segmentos. `ffprobe` sobre la playlist reescrita da flac/96000/24 y `ffmpeg` decodifica 3 s a un WAV de 1.152.102 bytes (exactamente 96000×3×2×2). La app real con mpv de verdad: insignias `24bit 96kHz HI_RES_LOSSLESS`, posición 12,3 s de 266 s, RMS −19,2 dBFS. La playlist sin reescribir falla con *error reading header* en el mismo ffmpeg. |
| Empaquetado (sdist / wheel / AUR)  | **Verificado salvo la publicación** | `python -m build` + `twine check` en ambos artefactos; 89 pruebas desde el sdist extraído; `bash -n` y `makepkg --printsrcinfo` sobre el PKGBUILD; `pacman -Si` confirma que todas las dependencias están en `extra`. No se ha ejecutado `makepkg -si` ni se ha publicado nada: el tag no existe todavía. |
| Carátula                           | **Verificado salvo la vista** | Unidades sobre los tres codificadores, incluida una vuelta completa de sixel a píxeles; la app real bajo un pty con `TERM=xterm-kitty` emite el APC gráfico anclado en la esquina del widget, y en medios bloques pyte muestra el recuadro de 18×9 con el resto del display intacto. Nadie ha mirado todavía una portada real en una ventana de kitty. |
| Indicador de carga y barra de estado | **Verificado**                  | Unitarias del `Spinner` y de los tres momentos del navegador (raíz, abrir un nivel, volver atrás) con un loader bloqueado a propósito; la app real bajo pty midió `#statusbar` dentro de la pantalla y pintó `⠦ resolviendo «Schism»…` en la última fila. |
| «Mis playlists» y caché de niveles | **Verificado contra TIDAL real**  | cProfile sobre la cuenta del usuario localizó las 111 peticiones; tras el cambio, la app real bajo un pty abre «Mis playlists» en 0,39 s (antes 19,87 s) y en 0,13 s la segunda vez. Unitarias: una petición por página, paginación, claves de caché y `R`. |

**Ojo con la sesión:** `~/.config/tidalamp/session.json` **ya no existe** (comprobado
el 2026-09-08, después de la sesión en la que el usuario reprodujo música). Todo lo que
diga «contra TIDAL real» en esta tabla empieza, hoy, por `tidalamp login`, que es
interactivo por definición: el device flow pide abrir una URL y autorizar.

Con la sesión rehecha, la instrumentación de la rama de manifiesto ya está puesta:
`TIDALAMP_DEBUG=1 tidalamp tui`, reproducir una pista en cada calidad y leer
`~/.local/state/tidalamp/tidalamp.log`. Es lo primero que debería hacer quien retome
esto delante de un terminal de verdad.

## 6. Pendiente

P1–P4 están cerradas: lo que queda no es funcionalidad que falte para que el
reproductor sirva, sino acabado, distribución y confirmar contra TIDAL real cosas hoy
probadas sólo con dobles.

**Orden propuesto (2026-09-08):** ~~P5 empaquetado~~ y ~~carátula~~ ✅ hechos. Lo que
queda pide credenciales o un par de ojos: el alta en PyPI y el AUR, y las
verificaciones contra TIDAL real.

**Aviso para quien retome esto:** ya no hay sesión guardada. `~/.config/tidalamp/`
está vacío, así que las comprobaciones «contra TIDAL real» de §5 empiezan por
`tidalamp login`, que es interactivo por definición (device flow) y no se puede
automatizar.

### ~~P1 — Exponer MPRIS en D-Bus~~ ✅ HECHO

Implementado en `mpris.py` con `dbus-fast`. Ver §4 y §5.

### ~~P2 — Colas y biblioteca~~ ✅ HECHO

Ver §4. Paginación y reordenado con `Alt+↑/↓` incluidos. Queda uno menor:

- [x] `TrackList` de MPRIS. Hecho: ver §4 y §5.

### ~~P3 — Espectro real~~ ✅ HECHO

`spectrum.py` lanza cava contra el sink y el analizador dibuja sus frames; sin cava
sigue el vúmetro RMS y la insignia `FFT`/`RMS` dice cuál es cuál. Pendientes:

- [x] Arrancar el cava real instalado: proceso vivo y frame de 19 bandas.
- [ ] Observar el frame con señal de audio real para validar la captura del sink.
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

- [x] Slider de balance (`,` `.` `\`), como filtro `pan`.
- [x] Ventana de ecualizador de 10 bandas (`e`) sobre el filtro `equalizer`.
- [x] Carátula en el terminal vía protocolo Kitty/sixel, con medios bloques como
      fallback universal. Ver §4. Queda por mirar con los ojos en un kitty de verdad,
      y por decidir si el recuadro debe seguir el tamaño del terminal en vez de ser
      18×9 fijo.
- [x] Letras sincronizadas y fallback a texto plano (`y`).
- [x] Colores adaptados al tema Omarchy activo, con cambio en vivo y fallback clásico.
- [x] Empaquetado, dos canales que se complementan. El procedimiento completo de
      publicación está en `packaging/README.md`; aquí sólo el estado.
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
      - [ ] **Pendiente y no automatizable desde aquí:** dar de alta el *pending
            publisher* en PyPI y crear el entorno `pypi` en GitHub (sin eso el job
            `publish` falla con un error de OIDC), y subir el PKGBUILD al AUR. Ambos
            piden credenciales del usuario. Además `sha256sums` sigue en `SKIP` hasta
            que exista el tag: se rellena con `updpkgsums`.

## 7. Trampas conocidas

Cosas que ya costaron tiempo una vez:

- **Sintaxis de la etiqueta de filtro en mpv**: es `--af=@etiqueta:lavfi=[...]`, con la
  etiqueta **delante**. Ponerla detrás (`lavfi=[...]@etiqueta`) hace que mpv aborte al
  arrancar y el socket IPC nunca aparece.
- **`box-sizing` de Textual es `border-box`**: el `padding` come de la altura
  declarada. Un widget con `height: 3` y `padding-top: 1` sólo pinta 2 filas.
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
- **Textual captura stdout mientras la app corre**: un `print` dentro de `run_test()`
  no aparece hasta que el bloque termina. Para sacar datos de una app que sigue viva,
  escribe a un fichero.

## 8. Entorno

- Arch Linux, Hyprland (Omarchy). Python 3.14, mpv y ffmpeg en el sistema.
- Venv en `.venv/`, rehecho tras el renombrado; `.venv/bin/tidalamp` funciona de nuevo.
  Lleva el paquete en editable más `pytest` y `pyte`.
- Tests: `.venv/bin/python -m pytest` (174 pruebas, ~8 s, sin red ni bus de usuario).
  El extra `dev` arrastra Pillow, así que las pruebas de carátula corren de verdad; si
  falta, se saltan solas.
- `cava` está instalado en `/usr/bin/cava`; arranca con la configuración real de 19
  bandas. Las pruebas automatizadas siguen usando `tests/fake_cava.py` y falta validar
  visualmente una señal de audio del sink.
- Para ver el layout sin terminal interactivo hay un atajo más corto que pyte:
  `app.export_screenshot()` dentro de `run_test()` da un SVG del que se saca el texto.
- Smoke headless de la app entera (mpv falso + sesión doble) en el scratchpad de la
  sesión: ejerce paginación, reordenado y muerte/reinicio de mpv sobre la app real.
- MPRIS tiene una integración reproducible en `tests/test_mpris.py`: levanta un bus de
  sesión temporal, conecta dos servicios y un cliente, y lo destruye al terminar.
- Para verificar la TUI sin terminal interactivo: correr la app bajo `pty.fork()` y
  emular la pantalla con `pyte`. Es como se generaron las capturas de este repo.
