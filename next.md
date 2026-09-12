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

- **Ir al artista y al álbum desde el menú de la pista.** Dos entradas más en el menú
  que abren `m` y `↵` en todos sus sitios (navegador, búsqueda, cola y la cola de la
  pantalla completa): «ir al artista» e «ir al álbum», que abren el navegador en ese
  nivel. Hoy, desde una pista de la cola, no hay forma de llegar a su disco o a su
  artista sin buscarlos a mano. Trampas: `Entry` guarda `album_id` pero **no el id
  del artista**, sólo su nombre; hay que añadir `artist_id`, y una cola guardada antes
  no lo trae, así que sale de `entry.resolve()` (el `Track` de tidalapi lleva
  `artist.id`), en un worker, porque es una petición. Una pista con varios artistas:
  ir al principal o preguntar cuál, por decidir. Desde la cola y la pantalla completa
  el navegador no está abierto: tiene que abrirse con ese nivel ya apilado, y `⌫`
  volver a la raíz de la biblioteca en vez de cerrar. Se comprueba con una sesión
  simulada: el menú ofrece las dos entradas en los cuatro sitios, y cada una abre el
  nivel correcto, también desde una cola restaurada sin `artist_id`.
- **Un artista con sus discos, no sólo sus canciones sugeridas.** Hoy abrir un artista
  trae sus pistas más escuchadas (`get_top_tracks`). Que abra a secciones: populares,
  álbumes, EPs y sencillos, y otros (recopilatorios y en los que aparece), cada una un
  nivel paginado como los demás y cada disco un nivel de pistas como el álbum de
  siempre. Las secciones son las que trae la API y ninguna más: tidalapi da
  `get_albums`, `get_ep_singles` y `get_other`, y los discos en vivo van donde TIDAL
  los ponga, entre los álbumes (decidido por el mantenedor el 2026-09-12: separarlos
  por el título sería adivinar). Trampas: una sección vacía (un artista sin EPs) no
  aparece. `s` tiene que seguir ordenando donde TIDAL ordene, y `m` sobre un
  artista hoy reproduce las populares: decidir si sigue así. Se comprueba con una
  sesión simulada con álbumes, EPs y nada en «otros»: salen tres secciones y no
  cuatro, y abrir un disco trae sus pistas.

Lo de la 0.9.0 (mpv sin congelar la interfaz, sin corte entre pistas, volumen
normalizado, tus mixes, la insignia `RG`, la carátula y la letra de la siguiente por
adelantado, y el segundo recordado tras un reinicio de mpv y al salir, que estaba
descartado y se retomó) está hecho, probado a mano contra TIDAL real y cerrado en `CHANGELOG.md`
bajo `[0.9.0]`; el detalle, en `plan.md` §4 y §5.

## Sin fecha

- **Sacar objetos de verdad de `TidalAmp`.** 2635 líneas y 182 métodos en `app.py`;
  `_setting_changed` es de lo más enredado. No en mixins (ver «Descartado»), sino
  objetos con su propio diseño: reproducción, carátula, presentación de la cola y
  aplicación de ajustes, dejando `TidalAmp` como raíz de composición. Es un rediseño
  grande que no arregla ningún fallo, así que solo cuando haya tiempo para hacerlo
  bien.

- **Seleccionar varias pistas en la cola** para quitarlas o moverlas juntas; hoy se
  hace de a una. Interesa, pero sin versión decidida.

## Descartado por ahora

No se borran: quedan escritos con el motivo para no volver a discutirlos desde cero.

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
