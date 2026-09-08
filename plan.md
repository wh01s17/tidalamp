# plan.md — estado del proyecto `tidalamp`

Documento de traspaso. Describe qué existe, qué está verificado, qué falta y con qué  
criterio se tomaron las decisiones, para que cualquiera (humano o modelo) pueda  
retomar el trabajo sin contexto previo.

**Última actualización:** 2026-09-08 (P3 espectro con cava, y balance + ecualizador de P5)

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
| **Usar el device flow vía `tidalapi**`                   | Es el mismo OAuth que los clientes oficiales de TV/escritorio. No requiere registrar nada: el usuario abre un enlace, autoriza, y la sesión refrescable se cachea.                                                                                               |
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
  app.py        TidalAmp (App de Textual), Playlist, SearchScreen, Entry.
  winamp.tcss   Paleta y layout.
  queue.py      Entry (metadatos serializables + Track perezoso) y Queue (orden,
                shuffle, repeat, persistencia). No conoce la UI.
  library.py    Navegación de la biblioteca. Devuelve listas de Row, paginadas.
  net.py        with_retries(): reintentos con backoff para las llamadas a TIDAL.
  spectrum.py   Cava: proceso cava + lector de frames. Opcional por diseño.
  settings.py   Balance y ecualizador: grafos de filtro y persistencia.
  mpris.py      Servicio MPRIS2 en D-Bus. Habla con la app por el Protocol
                PlayerBackend, así que no conoce Textual ni tidalapi.
  cli.py        Entrypoint typer: login / tui / search.
```

Dependencia en un solo sentido:  
`cli -> app -> {player, stream, widgets, mpris, library, spectrum, settings}        -> {queue, net} -> {auth, config}`.  
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
- [x] Detección de manifiestos cifrados -> `StreamUnavailable` con mensaje explicando
      el DRM, en vez de dejar que mpv falle con un error de códec.
- [x] `Playable` expone `kbps`/`khz` para las insignias del display.
- [x] `cleanup_playlists()` borra los `.m3u8` temporales al salir.

### Reproducción — `player.py`

- [x] Spawn de `mpv --idle --no-video` con `--input-ipc-server`.
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
- [x] Teclas de Winamp: `z` `x` `c` `v` `b`, más `/` `↑` `↓` `Enter` `←` `→` `+` `-` `t` `q`.

### MPRIS — `mpris.py`

- [x] Publica `org.mpris.MediaPlayer2.tidalamp` en el bus de sesión.
- [x] Interfaz raíz `org.mpris.MediaPlayer2`: Identity, CanQuit, Quit, etc.
- [x] Interfaz `Player`: Play, Pause, PlayPause, Stop, Next, Previous, Seek,
      SetPosition; propiedades PlaybackStatus, Metadata, Position, Volume (lectura y
      escritura), CanGoNext/CanGoPrevious.
- [x] Metadata completa incluida `mpris:artUrl` (carátula, que Waybar muestra).
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

### Tests — `tests/`

- [x] `pytest`, 64 pruebas, sin red y sin TIDAL. `pip install -e ".[dev]"`.
- [x] `tests/fake_mpv.py`: un mpv falso que habla el IPC JSON real y **emite eventos
      asíncronos antes de cada respuesta**, que es justo la trampa del §7. Lleva la
      cuenta de los filtros con etiqueta y rechaza la sintaxis con la etiqueta detrás.
- [x] `tests/fake_cava.py`: emite frames binarios como cava, leyendo el número de
      bandas de la config que generamos.
- [x] Cubren: cola (traversal, shuffle, repeat, mover, persistencia), paginación de la
      biblioteca, las dos ramas de `stream.resolve()` más DRM y manifiesto vacío,
      política de reintentos, `player` contra el mpv falso incluida la muerte y el
      reinicio del proceso y los filtros con etiqueta, `spectrum` contra el cava falso,
      y `settings` (recortes, grafos y persistencia).

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
| MPRIS: registro y propiedades      | **Verificado**                    | `busctl --user list` y `gdbus call` contra la app headless.                                                                                                                     |
| MPRIS: controles                   | **Verificado**                    | Pause, Play, Next, Previous y Volume por `gdbus`, comprobando el efecto en el estado.                                                                                           |
| MPRIS: señales                     | **Verificado**                    | `gdbus monitor`: 5 `PropertiesChanged` para 5 cambios reales, ninguna de más.                                                                                                   |
| MPRIS: LoopStatus / Shuffle        | **Verificado**                    | Lectura, escritura y señales contra una instancia aislada.                                                                                                                      |
| MPRIS: colisión de nombre          | **Verificado**                    | Dos instancias a la vez: la segunda cae a `.instance<pid>`.                                                                                                                     |
| Cola: shuffle / repeat             | **Verificado**                    | Pruebas unitarias de `next_index`/`prev_index` en los tres modos.                                                                                                               |
| Cola: persistencia                 | **Verificado**                    | Ida y vuelta a disco, y dos sesiones reales de la app encadenadas.                                                                                                              |
| Navegador de biblioteca            | **Verificado**                    | Drill-down, `↵`, `a` y `A` con una sesión simulada.                                                                                                                             |
| Paginación de la biblioteca        | **Verificado**                    | Unitarias sobre `_paged`, y la app real headless: nivel de 103 pistas → 101 filas con `más…`, `↵` sobre ella → 103 filas sin `más…`.                                            |
| Reordenar la cola                  | **Verificado**                    | Unitarias de `Queue.move` (bordes, cursor, shuffle intacto) y `alt+↓` en la app real.                                                                                           |
| Reinicio de mpv                    | **Verificado**                    | SIGKILL a mpv con la app corriendo: el tick lo relanza con otro PID y la pista vuelve a sonar.                                                                                  |
| Espectro con cava                  | **Verificado con cava falso**     | Frames normalizados, config generada, muerte del proceso → vuelta a RMS. En esta máquina **cava no está instalado**, así que nunca se ha visto contra el binario real.          |
| Balance y ecualizador              | **Verificado**                    | Grafos validados con `ffmpeg -af` de verdad; en la app real los filtros llegan a mpv, se guardan, y se reaplican tras reiniciar mpv.                                            |
| Reintentos de red                  | **Verificado**                    | Unitarias: reintenta conexión/timeout/503, no reintenta 404, se rinde al tercer intento.                                                                                        |
| Refresco del token                 | **Sin verificar contra TIDAL**    | La ruta se ejerce con dobles; nunca se ha dejado caducar un token real.                                                                                                         |
| **`login` y reproducción real**    | **VERIFICADO POR EL USUARIO**     | El usuario ejecutó `tidalamp tui` con su cuenta y reprodujo TOOL - Schism (Lateralus) el 2026-09-08. Login, búsqueda, `stream.resolve()` y salida de audio funcionan de verdad. |
| Reproducción real (`ao` de verdad) | **Verificado sólo con `ao=null**` | Nunca se ha sacado sonido por PipeWire en esta sesión.                                                                                                                          |
| Ruta MPD -> HLS                    | **PARCIAL**                       | Ambas ramas están cubiertas por tests con manifiestos fijados, y `stream.resolve()` ya registra cuál toma. Falta una reproducción real con `TIDALAMP_DEBUG=1` para leerlo.      |

**Ya no hay ningún bloqueo de credenciales:** la sesión está guardada y la  
reproducción real está confirmada. La instrumentación de la rama de manifiesto ya está  
puesta: queda ejecutar `TIDALAMP_DEBUG=1 tidalamp tui`, reproducir una pista en cada  
calidad y leer `~/.local/state/tidalamp/tidalamp.log`. Es lo primero que debería hacer  
quien retome esto delante de un terminal de verdad.

## 6. Pendiente

Ordenado por valor. Los tres primeros son los que de verdad cambian el producto.

### ~~P1 — Exponer MPRIS en D-Bus~~ ✅ HECHO

Implementado en `mpris.py` con `dbus-next`. Ver §4 y §5.  
Pendiente menor: `LoopStatus` y `Shuffle` sólo tendrán sentido cuando exista P2.

### ~~P2 — Colas y biblioteca~~ ✅ HECHO

Ver §4. Paginación y reordenado con `Alt+↑/↓` incluidos. Queda uno menor:

- [ ] `TrackList` de MPRIS (`HasTrackList` sigue en False). Es la interfaz
      `org.mpris.MediaPlayer2.TrackList`: exponer la cola como lista de trackids y
      permitir `GoTo`. Poco cliente la consume; por eso sigue abajo del todo.

### ~~P3 — Espectro real~~ ✅ HECHO

`spectrum.py` lanza cava contra el sink y el analizador dibuja sus frames; sin cava  
sigue el vúmetro RMS y la insignia `FFT`/`RMS` dice cuál es cuál. Pendientes:

- [x] Probarlo con el cava real (`pacman -S cava`); aquí sólo se ha visto contra el
      doble.
- [ ] cava escucha el sink, no nuestro mpv: si suena otra cosa a la vez, se cuela. Se
      arreglaría enrutando mpv a un sink propio de PipeWire, a cambio de un nodo por
      ejecución. No parece que compense todavía.

### ~~P4 — Robustez~~ ✅ HECHO

Ver §4: reinicio de mpv, refresco del token, reintentos con backoff y suite de  
`pytest` con mpv falso y manifiestos fijados. Queda menor:

- [ ] Dejar caducar un token real para verificar `ensure_fresh` contra TIDAL.

### P5 — Acabado

- [x] Slider de balance (`,` `.` `\`), como filtro `pan`.
- [x] Ventana de ecualizador de 10 bandas (`e`) sobre el filtro `equalizer`.
- [ ] Carátula en el terminal vía protocolo Kitty/sixel.
- [ ] Letras sincronizadas (`track.lyrics()` existe en tidalapi).
- [ ] Empaquetado: PKGBUILD para AUR.

## 7. Trampas conocidas

Cosas que ya costaron tiempo una vez:

- **Sintaxis de la etiqueta de filtro en mpv**: es `--af=@etiqueta:lavfi=[...]`, con la  
  etiqueta **delante**. Ponerla detrás (`lavfi=[...]@etiqueta`) hace que mpv aborte al  
  arrancar y el socket IPC nunca aparece.
- **`box-sizing` de Textual es `border-box**`: el `padding`come de la altura  
declarada. Un widget con`height: 3`y`padding-top: 1` sólo pinta 2 filas.
- **El socket IPC comparte stream con los eventos async de mpv**: hay que leer líneas  
  hasta encontrar la que lleva nuestro `request_id`, no asumir que la primera respuesta  
  es la nuestra.
- **Un selector CSS agrupado (`#a, #b {}`) editado con sed** puede dejar reglas  
  aplicadas al widget equivocado. Pasó con `#seek, #volume`.
- **dbus-next exige anotaciones de tipo que sean constantes de cadena.** Un método  
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
- **Las rutas de socket unix se cortan en ~108 bytes.** El directorio de scratchpad de  
  la sesión ya gasta casi todo el presupuesto, así que un `--input-ipc-server` ahí  
  falla con `AF_UNIX path too long`. Los scripts de prueba crean el socket en un  
  `mkdtemp()` corto.
- **`logging` tiene un handler de último recurso que escribe a stderr.** Un  
  `log.warning` sin handlers propios pinta encima de la TUI. Por eso `__init__.py`  
  registra un `NullHandler` en el logger `tidalamp`: basta con que exista uno en la  
  cadena para que el de último recurso no entre.
- **Textual captura stdout mientras la app corre**: un `print` dentro de `run_test()`  
  no aparece hasta que el bloque termina. Para sacar datos de una app que sigue viva,  
  escribe a un fichero.

## 8. Entorno

- Arch Linux, Hyprland (Omarchy). Python 3.14, mpv y ffmpeg en el sistema.
- Venv en `.venv/`, rehecho tras el renombrado; `.venv/bin/tidalamp` funciona de nuevo.  
  Lleva el paquete en editable más `pytest` y `pyte`.
- Tests: `.venv/bin/python -m pytest` (64 pruebas, ~1,5 s, sin red).
- `cava` **no** está instalado en esta máquina; el espectro sólo se ha probado contra  
  `tests/fake_cava.py`.
- Para ver el layout sin terminal interactivo hay un atajo más corto que pyte:  
  `app.export_screenshot()` dentro de `run_test()` da un SVG del que se saca el texto.
- Smoke headless de la app entera (mpv falso + sesión doble) en el scratchpad de la  
  sesión: ejerce paginación, reordenado y muerte/reinicio de mpv sobre la app real.
- Para probar MPRIS sin terminal interactivo: `app.run_test()` de Textual levanta la  
  app headless en el mismo proceso, y desde fuera se interroga con `gdbus call` /  
  `gdbus monitor`. El script usado está en el scratchpad de la sesión.
- Para verificar la TUI sin terminal interactivo: correr la app bajo `pty.fork()` y  
  emular la pantalla con `pyte`. Es como se generaron las capturas de este repo.
