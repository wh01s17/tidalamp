# plan.md — estado del proyecto `tidalamp`

Documento de traspaso. Describe qué existe, qué está verificado, qué falta y con qué
criterio se tomaron las decisiones, para que cualquiera (humano o modelo) pueda
retomar el trabajo sin contexto previo.

**Última actualización:** 2026-09-08 (MPRIS implementado)

---

## 1. Qué es esto

Cliente de TIDAL para terminal con interfaz estilo Winamp 2.x (TUI). Reproduce audio
con `mpv` y obtiene catálogo y streams con `tidalapi`.

Antes se llamaba `tidal-cli-omarchy` porque se pensó como plugin de Omarchy. Se
renombró a `tidalamp` al decidir que el producto es una TUI autónoma. **El directorio
del repositorio sigue llamándose `tidal-cli-omarchy`**; renombrarlo es seguro y queda
pendiente:

```sh
mv ~/workspace/tidal-cli-omarchy ~/workspace/tidalamp
```

## 2. Decisiones de arquitectura (y por qué)

Estas son las decisiones que **no** hay que volver a litigar sin motivo nuevo:

| Decisión | Motivo |
|---|---|
| **No usar la API oficial** (`developer.tidal.com`) | Exige registrar una app, y aun así no entrega URLs de stream. Sólo sirve para metadata. |
| **Usar el device flow vía `tidalapi`** | Es el mismo OAuth que los clientes oficiales de TV/escritorio. No requiere registrar nada: el usuario abre un enlace, autoriza, y la sesión refrescable se cachea. |
| **mpv como motor, no un player embebido** | Maneja HLS/DASH/FLAC sin que nosotros toquemos códecs. Un solo proceso `--idle` de larga vida sobrevive a los cambios de pista. |
| **IPC por socket unix con JSON**, no `python-mpv`/libmpv | Cero dependencias nativas, y da acceso directo a las propiedades (`time-pos`, `volume`, `af-metadata`) que necesita el display. |
| **Textual para la TUI** | Tiene CSS, que hace tratable clonar la estética de Winamp. |

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
  mpris.py      Servicio MPRIS2 en D-Bus. Habla con la app por el Protocol
                PlayerBackend, así que no conoce Textual ni tidalapi.
  cli.py        Entrypoint typer: login / tui / search.
```

Dependencia en un solo sentido: `cli -> app -> {player, stream, widgets, mpris} -> {auth, config}`.
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

### CLI — `cli.py`
- [x] `tidalamp login`, `tidalamp tui`, `tidalamp search <query>`.

## 5. Estado de verificación

Distinguir esto importa: parte del código nunca se ha ejecutado contra TIDAL real.

| Área | Estado | Cómo se comprobó |
|---|---|---|
| IPC de mpv | **Verificado** | Script directo: get/set de volumen, `idle`, `paused`. |
| Medición RMS | **Verificado** | Tono de 440 Hz generado con ffmpeg; devuelve −21 dBFS estable. |
| Layout y render de la TUI | **Verificado** | La app real corriendo en un pty, con `pyte` emulando el terminal y datos stub. |
| MPRIS: registro y propiedades | **Verificado** | `busctl --user list` y `gdbus call` contra la app headless. |
| MPRIS: controles | **Verificado** | Pause, Play, Next, Previous y Volume por `gdbus`, comprobando el efecto en el estado. |
| MPRIS: señales | **Verificado** | `gdbus monitor`: 5 `PropertiesChanged` para 5 cambios reales, ninguna de más. |
| Reproducción real (`ao` de verdad) | **Verificado sólo con `ao=null`** | Nunca se ha sacado sonido por PipeWire en esta sesión. |
| `login` (device flow) | **SIN VERIFICAR** | Requiere una cuenta TIDAL. |
| `stream.resolve()` con pistas reales | **SIN VERIFICAR** | Depende del login. **Es el punto de mayor riesgo.** |
| Ruta MPD -> HLS | **SIN VERIFICAR** | `manifest.get_hls()` de tidalapi no se ha probado contra mpv. |

**Primer paso para quien retome:** ejecutar `tidalamp login`, luego `tidalamp tui`,
buscar algo y darle a Enter. Ahí se sabrá si §5 filas 5-7 funcionan.

## 6. Pendiente

Ordenado por valor. Los tres primeros son los que de verdad cambian el producto.

### ~~P1 — Exponer MPRIS en D-Bus~~ ✅ HECHO
Implementado en `mpris.py` con `dbus-next`. Ver §4 y §5.
Pendiente menor: `LoopStatus` y `Shuffle` sólo tendrán sentido cuando exista P2.

### P2 — Colas y biblioteca
- [ ] Playlists del usuario, favoritos, álbumes y artistas (`session.user.playlists()`,
      `session.user.favorites`). La API ya está disponible; falta UI para navegarla.
- [ ] Añadir a la cola sin reemplazarla (hoy la búsqueda pisa la playlist entera).
- [ ] Guardar y restaurar la playlist entre sesiones.
- [ ] Shuffle y repeat.

### P3 — Espectro real
El analizador actual es un vúmetro repartido en bandas, no una FFT: `astats` da nivel,
no espectro. Para un espectro auténtico, lanzar `cava` contra el sink de PipeWire y
leer su stdout en crudo. Documentado honestamente en README y en el docstring de
`Analyzer`; no presentarlo como FFT.

### P4 — Robustez
- [ ] Reconexión si el proceso mpv muere (hoy la UI se queda congelada sin avisar).
- [ ] Refresco del token cuando caduca a mitad de sesión.
- [ ] Reintentos con backoff en los errores de red de tidalapi.
- [ ] Tests: `pytest` con un mpv falso y manifiestos de TIDAL fijados en fixtures.

### P5 — Acabado
- [ ] Slider de balance (Winamp lo tenía; hoy sólo hay volumen).
- [ ] Ventana de ecualizador de 10 bandas conectada al filtro `equalizer` de mpv.
- [ ] Carátula en el terminal vía protocolo Kitty/sixel.
- [ ] Letras sincronizadas (`track.lyrics()` existe en tidalapi).
- [ ] Empaquetado: PKGBUILD para AUR.

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
- **dbus-next exige anotaciones de tipo que sean constantes de cadena.** Un método
  D-Bus que devuelve void no lleva anotación **ninguna**: poner `-> None` hace que
  falle al importar el módulo, porque intenta leerlo como firma de salida.
- **zsh no hace word-splitting de variables sin comillas.** Guardar flags en una
  variable (`D="-d foo -o /bar"`) y pasarla como `$D` los entrega como un único
  argumento. Usar arrays de bash en los scripts de prueba.
- **Cuidado con `pkill -f <patrón>` en estos scripts**: el patrón suele aparecer en la
  propia línea de comandos del shell que lo ejecuta, y el shell se mata a sí mismo.
  Matar por PID.

## 8. Entorno

- Arch Linux, Hyprland (Omarchy). Python 3.14, mpv y ffmpeg en el sistema.
- Venv en `.venv/`, paquete instalado en editable (`pip install -e .`).
- Para probar MPRIS sin terminal interactivo: `app.run_test()` de Textual levanta la
  app headless en el mismo proceso, y desde fuera se interroga con `gdbus call` /
  `gdbus monitor`. El script usado está en el scratchpad de la sesión.
- Para verificar la TUI sin terminal interactivo: correr la app bajo `pty.fork()` y
  emular la pantalla con `pyte`. Es como se generaron las capturas de este repo.
