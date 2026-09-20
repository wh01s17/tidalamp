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

Descubrir, la vista de cuadrícula, la gestión de playlists propias y las páginas que
llegan solas entraron en la `0.11.0` (publicada el 2026-09-15): ver
`CHANGELOG.md` y `plan.md` §4. La `0.11.1` (publicada el 2026-09-16) sólo arregla
el título de la ventana de letras, y la `0.11.2` (publicada el 2026-09-17) que el DAC
siga el rate de cada pista y no sólo el de la primera. La `0.12.0` (publicada el
2026-09-17) ofrece añadir tidalamp al menú de aplicaciones, la `0.13.0` (publicada el
2026-09-17) trae cerrar sesión desde `o`, la `0.14.0` (publicada el 2026-09-19) la
letra al lado de la carátula en pantalla completa, y la `0.15.0` (publicada el
2026-09-20) «Lofi sin copyright», sus créditos en `k`, los nombres que se deslizan en
la cola de pantalla completa y el arreglo de las cargas que fallan. Las escrituras en tus playlists
se comprobaron contra TIDAL real ese mismo día. Queda por comprobar a mano:

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
  - *Por mirar:* los otros tres temas.
  - *Comprobación:* capturas entre 60x18 y 79x25 (por ejemplo 72x20 y 79x25) en los
    cuatro temas. Qué mirar: lo mismo que §9.5, que la fila del transporte no se salga
    ni se parta y que las barras de título llenen su fila.

- **Escuchar «Lofi sin copyright» de verdad, un rato largo.** Es lo único de la
  `0.15.0` que ninguna máquina puede comprobar: que mpv decodifica las URLs está
  medido, que *suene* a lofi no. El mantenedor ya rechazó la primera selección
  (`chillout` traía ambient de netlabel de 2006) y el arreglo fue pedir `chillhop` con
  suelo de fecha en 2016, pero eso se validó **leyendo títulos y años**, no oyendo.
  - *Qué mirar:* si se cuela alguna voz —Jamendo dice cuáles son instrumentales, pero
    es una casilla que marca el artista—, si algún artista cansa aunque el tope sean
    cuatro pistas, y si la mezcla del día aguanta dos horas de fondo sin distraer.
  - *La cura si algo no encaja:* una palabra más en `archive.JUNK` o `archive.VOCALS`,
    o retocar `jamendo.TAGS` y `jamendo.SINCE`. No una lista de identificadores: los
    catálogos crecen y esa lista sólo describiría el día en que se escribió.
  - *Lo que no tiene cura:* el sonido de «lofi hip hop radio» es el catálogo de un
    sello y nada de eso es Creative Commons. Por eso la fila dice **experimental**.

- **Ver deslizarse la cola de pantalla completa.** Los tests miden celdas: que una
  fila que no cabe enseñe su final, que la que cabe no se mueva, que el número y la
  duración no se vayan, y que el ancho no cambie nunca. Lo que no miden es el ritmo.
  - *Qué mirar:* que a 0,3 s por celda se lea mientras se mueve y no maree con treinta
    filas a la vez, y que las cortas esperando a las largas no se note raro.
  - *Dónde:* `w`, luego `tab` para abrir la cola, con una cola larga de nombres largos.

## Sin fecha

- **«más…» en las categorías de Inicio.** Una categoría de la página de inicio trae
  los diez primeros que TIDAL pone en la página, y la lista completa está detrás de
  su «view all». `tidalapi` 0.8.11 lo tiene roto: `PageCategoryV2.view_all` llama a
  un `session.view_all` que no existe. Habría que pedir la ruta de `_more.api_path`
  a mano, como ya se hace con los enlaces de Explorar (`library._page_at`).

- **Sacar objetos de verdad de `TidalAmp`.** **3393 líneas y 214 métodos** en `app.py`
  a 2026-09-20, y la cuenta sube en cada versión: eran 2635 y 182 cuando se escribió
  esta entrada, y la `0.15.0` le sumó `_gave_up`, `action_credits` y el reparto de
  `_now_playing`. `_setting_changed` sigue siendo lo más enredado. No en mixins (ver
  «Descartado»), sino objetos con su propio diseño: reproducción, carátula,
  presentación de la cola y aplicación de ajustes, dejando `TidalAmp` como raíz de
  composición. Es un rediseño grande que no arregla ningún fallo, así que solo cuando
  haya tiempo para hacerlo bien — pero cada versión que pasa lo encarece.

- **Una guarda común para los workers al cerrar.** Un worker de hilo que termina
  después de salir llama a `call_from_thread` contra un loop que se cierra: en la app
  cuesta una excepción dentro de ese hilo, sin efecto visible, y en los tests es la
  carrera por la que `app_helpers.isolate_runtime` desactiva el worker del sink.
  Señalado por Codex (2026-09-12). Razonable y pequeño, pero sin un fallo que lo
  pida: cuando aparezca uno.
- La separación de `TidalAmp` (arriba) la señaló también Codex (2026-09-12), con la
  misma conclusión: objetos con diseño propio. Vigilar además que `Mpv._request` (53
  líneas, cada rama con su test) no crezca hasta ser otro núcleo.

- **Seleccionar varias pistas en la cola** para quitarlas o moverlas juntas; hoy se
  hace de a una. Interesa, pero sin versión decidida.

## Descartado por ahora

No se borran: quedan escritos con el motivo para no volver a discutirlos desde cero.

- **Emisoras lofi en vivo** (2026-09-20), de Radio Browser, como segunda fila de
  «Lofi sin copyright». La API responde sin clave y tiene emisoras lofi de sobra, pero
  no hay forma de verificar qué emiten, así que la fila dejaría de merecer su nombre.
  Además una emisora no tiene duración ni portada: habría que tocar el transporte, la
  barra de posición y la cola para una fila que no se puede prometer. El mantenedor
  eligió quedarse sólo con el Internet Archive.
- **Otras fuentes para «Lofi sin copyright»** (2026-09-20), miradas al rediseñarla como
  emisora. **Jamendo** tiene taxonomía de géneros de verdad y URLs de stream, pero pide
  registrar un `client_id`, que es la misma puerta que §2 cierra para TIDAL, y ataría el
  proyecto a la cuenta de una persona. **Free Music Archive** tiene la API muerta: su
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
