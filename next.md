# next.md — lo que entra en la próxima versión

Cola de trabajo comprometido, no una lista de deseos. Cada entrada trae lo que hay que
hacer, por qué, las trampas que ya se conocen y cómo se comprueba, para que se pueda
retomar sin releer el hilo en el que se decidió.

**Cómo se usa este fichero.** Cuando algo de aquí queda hecho, **se borra de aquí** y
pasa a dos sitios: la línea de usuario a `CHANGELOG.md`, bajo `[Unreleased]`, y el
detalle de diseño y las decisiones a la sección que le corresponda de `plan.md`. Un
fichero que acumula entradas tachadas deja de decir qué falta, que es lo único para lo
que existe. Si algo se descarta, no se borra sin más: baja a «Descartado por ahora» con
el motivo.

Lo de aquí no bloquea publicar. `plan.md` §5 y §6 mandan sobre el estado general.

---

## Para la próxima versión

- **Terminar de probar Windows en una máquina real**, siguiendo `windows.md` §12 paso
  a paso: cada apartado dice qué comando lanzar, qué mirar y en qué fichero está el
  código si falla. Empezó el 2026-09-24 en Windows 10 con Windows Terminal: suena por
  el named pipe con un mpv de verdad, y lo que salió mal se arregló en la `0.17.0`
  (`windows.md`, trampas 20 a 24). La `0.18.0` trajo el dispositivo de salida, visto
  funcionar con un FiiO BTR15 y un JBL: elegirlo, arrancar con él apagado,
  desenchufarlo en plena pista y volver a enchufarlo (§12.5), y el margen de Windows
  Terminal (§12.6). El 2026-09-24 se automatizó lo que no pide ojos ni oídos y el
  mantenedor vio el resto; salieron y se arreglaron las teclas multimedia (trampa
  27), cava (trampa 28) y la salida silenciada en Windows (trampa 29), publicados en
  la `0.19.0`. §12.9, la sesión normal en Linux, quedó vista el 2026-09-24, y de ella
  salió el espectro que no volvía tras reiniciar PipeWire, también en la `0.19.0`.
  **De Windows sólo queda** §12.7: repetir §12.3 y §12.4 con el `.exe` de la
  `0.21.0` (la `0.19.0` fue la primera con esos arreglos), y después «Después de §12».
  Lo que se compruebe se marca allí mismo con la fecha; lo que falle, con el log de
  `TIDALAMP_DEBUG=1`. El entorno para arreglar cosas desde Windows está en
  `CONTRIBUTING.md` («Setting up», «Windows»).
  - *Después de §12:* el clasificador de Windows en PyPI, quitar «preview» del README,
    y una captura en Windows Terminal (`windows.md`, «Después de §12»).

La última publicada es la `0.21.0` (2026-09-26), en PyPI y en GitHub con el zip de
Windows; su checksum del AUR está en `7c5dc46`, `makepkg -Csi` y `namcap` están sin
hacer (piden instalar con `sudo` las dependencias del paquete), y lo demás del AUR
espera al registro (`plan.md` §6). Lo que trae cada versión está en
`CHANGELOG.md`.

## El siguiente gran cambio: varias fuentes

Decidido el 2026-10-02. Va **después** de cerrar Windows (arriba), no a la vez: los dos
tocan `app.py`, `config.py` y la ventana `o`, y se pisarían.

Hoy tidalamp es un cliente de TIDAL con una sola fila ajena («Lofi sin copyright»). La
idea es que pase a ser un reproductor de varias fuentes: TIDAL, música local, YouTube
Music y, si se encuentra la forma, Spotify. **Cada fuente tiene su biblioteca y sus
playlists, y la cola es lo único que las mezcla.**

- **Panel de fuentes a la izquierda de la biblioteca.** Hoy `BrowserScreen` es una
  sola `RowList`, y `library.root()` devuelve las filas de TIDAL más la de lofi. Pasa a
  dos columnas: a la izquierda las fuentes (TIDAL, Música local, YouTube Music, Spotify
  si entra, y «Lofi sin copyright», que deja de colgar de la raíz de TIDAL), y a la
  derecha la raíz de la fuente elegida, con todo lo que el navegador ya sabe hacer
  (filtro `/`, orden, cuadrícula, «más…», menú `m`, ratón).
  - Una fuente sin vincular sale igual en el panel, atenuada, y su raíz es una sola
    fila, «Vincular cuenta», que abre su pestaña de configuración.
  - La búsqueda busca en la fuente seleccionada. Buscar en todas a la vez se decide
    después: mezcla resultados con calidades y licencias distintas.
  - *Trampa, el ancho:* a 60 columnas el panel se come la lista. Por debajo de cierto
    ancho tiene que plegarse (a una fila de pestañas arriba, o ocultarse tras una
    tecla). Decidirlo con capturas a 60x18 y 80x26, como en `plan.md` §9.5.
  - *Trampa, el foco:* hoy las flechas son de la lista. Tab pasa entre panel y lista,
    y ⌫ en la raíz de una fuente vuelve al panel.

- **Arrancar sin TIDAL.** `cli.tui` sale con error si `load_session()` lanza
  `NotLoggedIn`. Con varias fuentes se arranca igual, y TIDAL sale sin vincular. Lo que
  hoy pregunta `entry.is_tidal` (letras, radio, favoritos, año del disco, en `app.py`,
  `library.py`, `stream.py` y `screens/tracks.py`) pasa a preguntarle a la fuente qué
  sabe hacer, en vez de sumar un `if` por fuente.

- **Una costura `Source`**, como `music.py` lo es hoy para la sección libre: un
  Protocol con la raíz, la búsqueda, resolver una pista a algo que mpv reproduzca, sus
  playlists, y lo demás declarado como capacidades (favoritos, radio, letras, escribir
  playlists, vincular cuenta). `library.py` (1542 líneas, casi todo TIDAL) se reparte:
  lo de TIDAL a su fuente; `Row`, `matches`, la caché de niveles y el paginado quedan
  comunes. Es el momento natural de «Sacar objetos de verdad de `TidalAmp`» (Sin
  fecha): mejor una vez y bien que a medias en los dos sitios.

- **`Entry` con identidad por fuente.** `Entry.id` es un `int` de TIDAL; un videoId de
  YouTube es un texto y una pista local es una ruta. Pasa a (`source`, `id` como
  texto), y `queue.json` necesita migración: una cola guardada con la versión anterior
  tiene que volver entera. `Entry.source` ya existe (`tidal` / `free`) y `Entry.url` ya
  sirve para lo que mpv reproduce sin resolver, así que lo local encaja casi sin tocar.

- **Música local.**
  - Pestaña «Música local» en la configuración: añadir y quitar carpetas del equipo
    (`local_folders` en `config.toml`) y reescanear. Añadir necesita un selector de
    carpetas dentro de la TUI (Textual trae `DirectoryTree`), además de poder escribir
    la ruta.
  - El escaneo va en un worker y deja un índice en `CACHE_DIR` (ruta, mtime, tamaño,
    tags), para que el segundo arranque no relea miles de ficheros. Tags y carátula
    embebida con `mutagen` como extra opcional, igual que Pillow con `[art]`; sin él,
    el título sale del nombre del fichero. `cover.jpg` o `folder.jpg` de la carpeta
    como respaldo de la carátula.
  - Raíz: Artistas, Álbumes, Pistas, Carpetas y Playlists.
  - mpv reproduce el fichero tal cual, así que rates, hi-res, cava, ecualizador y
    gapless siguen valiendo. Es la fuente que mejor casa con lo que tidalamp promete:
    un FLAC 24/192 del disco sale bit-perfect sin depender de nadie.
  - Playlists locales en `.m3u8` bajo `STATE_DIR/playlists/`, y además se leen los
    `.m3u` y `.m3u8` que haya dentro de las carpetas añadidas.
  - *Trampa, Windows:* rutas con `\`, letras de unidad, mayúsculas que no distinguen,
    y mtime poco fiable en unidades de red. Probar con una carpeta en otra unidad.

- **YouTube Music.**
  - Catálogo y biblioteca con `ytmusicapi` (no oficial, MIT): búsqueda, biblioteca,
    playlists propias y editarlas, likes, radio (la «watch playlist») y letras.
  - El audio, con `yt-dlp`, que mpv ya sabe usar por su `ytdl_hook`. El audio normal
    de YouTube no lleva DRM, así que no choca con «No cruzar la línea del DRM»
    (`plan.md` §2); si algo llegara cifrado, se rechaza como hace `stream.py` con
    TIDAL.
  - *Vincular la cuenta:* el OAuth de `ytmusicapi` pide hoy credenciales propias de
    Google Cloud (client id y secret de la YouTube Data API), y la alternativa es
    pegar las cabeceras de una sesión del navegador. Ninguna es tan limpia como el
    device flow de TIDAL. Verificar cómo está antes de diseñar la pantalla.
  - *Trampa, yt-dlp se rompe:* cada pocas semanas YouTube cambia algo (PO tokens, y
    últimamente un runtime de JavaScript). Tiene que poder actualizarse sin esperar a
    una versión de tidalamp, y el error tiene que decir «actualiza yt-dlp», no «pista
    no disponible».
  - *Trampa, la calidad:* el máximo ronda los 256 kbps en AAC u Opus. La insignia de
    calidad y los rates tienen que decirlo tal cual, sin aparentar hi-res.
  - Igual que TIDAL por `tidalapi`, es un cliente no oficial: el README lo dice.

- **Spotify: analizar antes de comprometer nada.** El problema no es el catálogo, es
  el audio.
  - La Web API no entrega audio y nunca lo ha hecho. Además Spotify la viene cerrando:
    en noviembre de 2024 quitó endpoints (recomendaciones, audio features y otros) a
    las apps nuevas, y en 2025 el «extended quota» quedó para organizaciones grandes;
    una app en modo desarrollo sólo la usan unas pocas cuentas dadas de alta a mano.
    Para algo que cualquiera instala desde PyPI, cada usuario tendría que registrar su
    propia app y pegar su client id. Verificar las condiciones vigentes al retomarlo.
  - Reproducir dentro de tidalamp (librespot y similares) es descifrar el audio de
    Spotify: cruza la línea del DRM. **Descartado** por la misma regla de `plan.md` §2.
  - Lo que queda, de más barato a más caro:
    1. **Importar.** Leer playlists y favoritos de Spotify, con el client id del
       usuario, y emparejarlos por ISRC con TIDAL, YouTube Music o la música local
       para crear la playlist en esa fuente. No reproduce Spotify, pero resuelve «tengo
       mis listas allí», que es casi siempre lo que se quiere.
    2. **Mando a distancia por Spotify Connect.** tidalamp controla un dispositivo
       Connect (la app oficial, spotifyd) por la Web API. Pide Premium, y el audio no
       pasa por mpv: sin rates, sin ecualizador, sin cava, sin gapless. Y una pista de
       Spotify en la cola obliga a cambiar de motor a mitad de cola. Mucho coste para
       la mitad de las funciones.
    3. No hacerlo.
  - *Propuesta para discutir:* si se hace algo, empezar por 1 y medir después si 2
    vale la pena. Decidirlo antes de diseñar el panel, para saber si Spotify ocupa
    sitio en él o sólo una acción de «importar» en la configuración.

- **Playlists separadas, cola mezclada.** Cada playlist pertenece a una fuente y sólo
  lleva pistas de esa fuente. La cola acepta de todas.
  - «Añadir a una playlist» (menú de la pista) ofrece sólo las playlists de la fuente
    de esa pista.
  - Guardar la cola como playlist (`p`) con una cola mezclada, *por decidir:*
    preguntar la fuente y guardar sólo sus pistas, diciendo cuántas quedan fuera; o
    guardarla como playlist local `.m3u8`, que puede apuntar a varias fuentes. Lo que
    no se hace es meter en TIDAL lo que no es de TIDAL buscándolo por ISRC sin
    preguntar.
  - En la cola, la fuente de cada fila como columna opcional de `columns.py`, igual
    que la licencia de las pistas libres.
  - Cada pista se resuelve con su fuente al sonar. Si esa fuente está sin vincular o
    no contesta, se salta con el mensaje de la fuente y no con uno genérico (ver «Una
    carga que falla no es una pista que acaba», `plan.md` §4).

- **La configuración en pestañas**, con la barra de título como selector, igual que
  la ayuda (`screens/help.py`, `plan.md` §4 «Ayuda y acerca de»): General, Audio,
  Apariencia, y una por fuente (TIDAL, Música local, YouTube Music, Spotify si entra).
  - Cada pestaña de streaming lleva el estado (vinculada, con qué cuenta), «Vincular
    cuenta», «Cerrar sesión» y sus ajustes: en TIDAL la calidad y el volumen
    normalizado, en YouTube Music la calidad y dónde está `yt-dlp`, etcétera. La fila
    «Cerrar sesión» de General y la calidad de Audio se mudan a la de TIDAL.
  - *Vincular TIDAL desde la TUI:* hoy sólo existe `tidalamp login` en la terminal. El
    device flow ya es un enlace y un código, así que cabe en una ventana con el enlace
    y un spinner hasta que se autoriza.
  - *Cerrar sesión por fuente:* hoy `auth.forgotten` y `auth.logout` borran la sesión
    de TIDAL y, con la casilla, todo tidalamp, y después la app se cierra. Pasa a que
    cerrar la sesión de una fuente borra sólo su sesión y su caché, y **no** cierra la
    app, porque las otras fuentes siguen sonando. Borrar todos los datos se queda en
    General. Qué pasa con las pistas de esa fuente que ya están en la cola (quitarlas
    o dejarlas marcadas) está por decidir.
  - *Trampa, las teclas:* en la ventana `o` las flechas izquierda y derecha ya cambian
    el valor de la fila (`advance` y `back`), así que las pestañas no pueden usarlas
    como en la ayuda. Tab y shift+tab, dichos en el pie. Mirar si la ayuda debería
    aceptar tab también, por coherencia.
  - El desplazamiento a mano alrededor del cursor (`CHROME`, alto del terminal) pasa a
    ser por pestaña, como `_offsets` en la ayuda.

- **Cambiarle el nombre.** Con varias fuentes, «tidalamp» y «TIDAL AMP» dicen algo que
  ya no es cierto, y llevar la marca TIDAL en el nombre de un reproductor que no es
  sólo de TIDAL es buscarse un problema. El nombre se decide **antes** de publicar la
  primera versión con varias fuentes, porque el renombrado toca:
  - El paquete de PyPI (nombre nuevo; la última `tidalamp` avisa o depende del nuevo),
    el AUR, el `.exe` y el zip de Windows.
  - Las rutas `~/.config/tidalamp`, `~/.local/state/tidalamp`, `~/.cache/tidalamp` y
    las de `%APPDATA%` y `%LOCALAPPDATA%`: migrarlas una vez al arrancar, sin perder
    sesión, cola ni ajustes.
  - Las variables `TIDALAMP_*` (aceptar las viejas un tiempo), el nombre MPRIS, el
    `.desktop` y el `.lnk` (los viejos que encuentra `desktop.user_launchers` se
    reemplazan), el banner, los títulos («TIDAL AMP» en `layouts.py` y en `i18n.py`),
    el repo de GitHub (redirige solo) y los docs.
  - En un commit de sólo renombrado, que va a `.git-blame-ignore-revs` como el reparto
    de `app.py`.

- **Orden propuesto**, una versión por paso y cada una publicable:
  1. Decidir el nombre y renombrar. Antes que lo demás, para que el índice local, las
     sesiones nuevas y las pestañas nazcan ya en las rutas buenas.
  2. Costura `Source`, `Entry` con id por fuente y migración de `queue.json`; arrancar
     sin TIDAL. Sin cambios a la vista.
  3. Configuración en pestañas; vincular y cerrar sesión de TIDAL desde la TUI.
  4. Panel de fuentes en la biblioteca, con TIDAL y Lofi.
  5. Música local.
  6. YouTube Music.
  7. Spotify, si la decisión de arriba dice que sí.

- *Comprobación:* fuentes falsas en los tests, como `fake_mpv.py`, para que la suite
  no dependa de cuentas. Una `queue.json` de la `0.21.0` vuelve entera tras la
  migración. Una cola con TIDAL, local y YouTube Music suena en orden y sin corte entre
  pistas de la misma fuente. Cerrar la sesión de una fuente deja las otras sonando.
  Capturas del panel y de las pestañas a 60x18 y 80x26 en los cuatro temas. Las
  carpetas locales, también en Windows (§12 de `windows.md` gana un apartado).

## Sin fecha

- **Ver la disposición compacta en un terminal real.** Por debajo de 80x26 la
  interfaz quita la carátula y la fila de balance, y hasta ahora solo lo cubren tests
  que miden celdas y no colores (`plan.md` §9.5).
  - *Lo que ya se ha visto (2026-09-14):* una captura a 72x17, que está por debajo del
    mínimo de 60x18 por la altura. Sale bien el aviso («The window is 72×17. TIDAL AMP
    needs at least 60×18.»), en el color de acento y sin cortes. **La disposición
    compacta en sí no sale**, porque a esa altura la tapa el aviso.
  - La forma tenue que se ve detrás del aviso en esa captura es el fondo de pantalla
    del mantenedor, que se transparenta a través de kitty. No es un fallo.
  - *Visto el 2026-09-14:* el aviso, bien de 48x11 a 72x17, sin cortes (a 48 columnas
    la línea más larga cabe justa). Y la disposición compacta con el reproductor en
    marcha, en un tema: el transporte cabe entero, la barra de título está completa,
    no hay carátula ni fila de balance, y la cola recorta sus columnas. En la captura
    la insignia decía «C  FLAC…»: era el `Glide` desplazando la línea, que no cabe, a
    mitad de camino. No es un fallo.
  - El cuadradito oscuro que se veía a la izquierda de la línea de estado, en esa
    captura y también a tamaño normal, era el spinner `#busy` parado: su relleno
    dibujaba dos celdas de su propio fondo. Arreglado (clase `-idle`, sin relleno).
  - *Por mirar:* los otros tres temas. Pasó a «Sin fecha» el 2026-09-23: el
    mantenedor lo deja para otro día. Si llega antes la fase F3 de Windows, que toca
    carátulas, temas y sextantes, conviene tener estas capturas de Linux antes.
  - *Comprobación:* capturas entre 60x18 y 79x25 (por ejemplo 72x20 y 79x25) en los
    cuatro temas. Qué mirar: lo mismo que §9.5, que la fila del transporte no se salga
    ni se parta y que las barras de título llenen su fila.

- **«más…» en las categorías de Inicio.** Una categoría de la página de inicio trae
  los diez primeros que TIDAL pone en la página, y la lista completa está detrás de
  su «view all». `tidalapi` 0.8.11 lo tiene roto: `PageCategoryV2.view_all` llama a
  un `session.view_all` que no existe. Habría que pedir la ruta de `_more.api_path`
  a mano, como ya se hace con los enlaces de Explorar (`library._page_at`).

- **Sacar objetos de verdad de `TidalAmp`.** **3665 líneas y 226 métodos** en `app.py`
  a 2026-09-24, y la cuenta sube en cada versión: eran 2635 y 182 cuando se escribió
  esta entrada y 3393 y 214 el 2026-09-20; la `0.15.0` le sumó `_gave_up`,
  `action_credits` y el reparto de `_now_playing`, y Windows, el dispositivo de salida
  y a qué oye cava (`_cava_hears_mpv`, `_pick_spectrum`). `_setting_changed` sigue siendo lo más enredado. No en mixins (ver
  «Descartado»), sino objetos con su propio diseño: reproducción, carátula,
  presentación de la cola y aplicación de ajustes, dejando `TidalAmp` como raíz de
  composición. Es un rediseño grande que no arregla ningún fallo, así que solo cuando
  haya tiempo para hacerlo bien — pero cada versión que pasa lo encarece.
  - Codex llegó a la misma conclusión (2026-09-12): objetos con diseño propio. Vigilar
    además que `Mpv._request` (53 líneas, cada rama con su test) no crezca hasta ser
    otro núcleo.
  - *Después de Windows, no antes.* `windows.md` está pensado para que `app.py` apenas
    cambie, y las fachadas de su fase F0 (MPRIS y audio como backends) ya son un primer
    paso en esta dirección. Hacer las dos cosas a la vez se pisaría.

- **Seleccionar varias pistas en la cola** para quitarlas o moverlas juntas; hoy se
  hace de a una. Interesa, pero sin versión decidida.

## Descartado por ahora

No se borran: quedan escritos con el motivo para no volver a discutirlos desde cero.

- **Emisoras lofi en vivo** (2026-09-20), de Radio Browser, como segunda fila de
  «Lofi sin copyright». La API responde sin clave y tiene emisoras lofi de sobra, pero
  no hay forma de verificar qué emiten, así que la fila dejaría de merecer su nombre.
  Además una emisora no tiene duración ni portada: habría que tocar el transporte, la
  barra de posición y la cola para una fila que no se puede prometer. La fila se quedó
  con pistas de catálogo: Jamendo, y el Internet Archive de respaldo.
- **Otras fuentes para «Lofi sin copyright»** (2026-09-20), miradas al rediseñarla como
  emisora. Jamendo, que al principio se descartó por pedir un `client_id`, acabó
  entrando en la `0.15.0` como fuente principal. **Free Music Archive** tiene la API muerta: su
  `/api/get/tracks.json` contesta 404. **ccMixter** sí responde y tiene metadatos CC
  buenos, pero es una comunidad de remixes —sus lofi son casi todos BY-NC, que el filtro
  de licencia no deja pasar— y manda cabeceras tan grandes que `undici` se atraganta
  (`requests` no). **Pixabay** pide clave.
- **Distribuir por pacman mientras el AUR siga cerrado** (2026-09-12). Los repos
  oficiales no son una opción: los mantienen los Package Maintainers de Arch, y la vía
  para entrar pasa por el AUR. Quedaban dos caminos, los dos viables porque todas las
  dependencias están en `extra`: adjuntar el `.pkg.tar.zst` a cada GitHub Release
  (`pacman -U`, sin actualizaciones) o un repositorio propio firmado con `repo-add`
  (actualiza con `-Syu`, pero pide una clave de firma en los secretos de Actions y que
  el usuario confíe en ella). El mantenedor prefirió quedarse en PyPI. Cuando reabra el
  AUR, el PKGBUILD está listo.
- **Radio de un artista o de una playlist** (2026-09-11), para completar el menú de la
  `m`, que no tiene radio porque la de TIDAL nace de una pista. Al mantenedor no le
  interesó: la radio de pista ya cubre lo que busca.
- **Temporizador de apagado.** Un `set_timer` que llame a `action_stop` y un indicador
  en el transporte. Barato, pero no lo pidió nadie todavía.
- **Enrutar mpv a un sink propio de PipeWire** para que cava no oiga el resto del
  sistema. Cuesta un nodo por ejecución para arreglar un caso raro. Ver `plan.md` §9.4.
- **`app.py` en mixins por tema** (2026-09-11). Probado y revertido: mypy no acepta
  `self: TidalAmp` en un mixin (el tipo de `self` tiene que ser supertipo de la clase),
  así que las ~1100 líneas movidas quedan sin comprobar o piden un stub con las ~170
  firmas duplicadas. Además los `@on` solo cuentan en clases que construye Textual, y
  seis métodos tienen que quedarse porque los tests parchean nombres en
  `tidalamp.app`. Si se retoma, que sea extrayendo objetos de verdad (MPRIS, carátula,
  cola), con su propio diseño. El resto del reparto (`screens/`, `styles/`,
  `widgets.py`, los tests de la app) está hecho y en `.git-blame-ignore-revs`.
