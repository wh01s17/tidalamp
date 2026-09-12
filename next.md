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

## Para la 0.8.1

Salen de una revisión externa (Codex) contrastada con el código el 2026-09-11. Son
baratas y se apoyan unas en otras: los timeouts hacen más probable el caso de las
escrituras duplicadas, así que conviene hacer las dos juntas.

- **Timeouts reales para TIDAL.** Ni tidalamp ni tidalapi ponen `timeout` a las
  peticiones: una petición que TIDAL no contesta deja el worker colgado para siempre y
  `with_retries` (`net.py`) nunca llega a reintentar. Poner uno por defecto (conexión
  y lectura) en `session.request_session` al crear la sesión (`auth._new_session`).
  Trampa: el stream y la resolución de manifiestos pueden tardar más que una lectura
  de la API; medir antes de elegir el número. Se comprueba con un servidor local que
  acepta y no contesta: la llamada tiene que fallar dentro del plazo y reintentar.
- **No reintentar escrituras que no son idempotentes.** `save_queue_playlist` y
  `add_to_playlist` (`library.py`) pasan `create_playlist` y cada lote de
  `playlist.add` por `with_retries`. Si TIDAL aplica la escritura y la respuesta se
  pierde por un timeout, el reintento crea otra playlist o duplica el lote. La misma
  regla que ya sigue quitar de una playlist: la escritura no se reintenta, y el error
  dice cuántas pistas entraron (`PlaylistSaveFailed` ya lo lleva). Las lecturas siguen
  reintentándose. Se comprueba con un doble que aplica la escritura y luego lanza un
  timeout: una sola playlist, sin lotes repetidos.
- **Escritura atómica del estado.** Cola (`queue.py`), ajustes (`settings.py`),
  órdenes de la biblioteca (`library.py`), configuración (`config.py`) y ritmos de
  PipeWire (`audio.py`) usan `write_text` directo, y cola y ajustes además callan el
  `OSError`. Un corte a mitad deja el JSON truncado y se pierde el estado anterior. Un
  helper que escriba a un temporal en la misma carpeta y lo cambie con `os.replace`.
  Trampa: el temporal tiene que estar en el mismo sistema de ficheros para que el
  reemplazo sea atómico. Se comprueba simulando un fallo durante la escritura: el
  fichero anterior queda intacto.
- **`_resolve_worker` no pisa una pista más nueva.** Es un worker de hilo exclusivo,
  pero Textual cancela la tarea que espera al hilo, no el hilo: con «siguiente»
  apretado rápido, la resolución de una pista vieja puede terminar después y ponerse a
  sonar. Al volver del hilo, comprobar que la pista pedida sigue siendo la que toca
  (como ya hacen `_pane_loaded` y la ventana de la letra) y descartarla si no. No hace
  falta tocar los otros veinte workers: casi todos cierran su propia pantalla. Se
  comprueba con un resolve bloqueado a propósito, un segundo «siguiente» y soltar el
  primero: suena la segunda.

## Para la 0.9.0

- **mpv sin congelar la interfaz.** El IPC (`player.py`) espera hasta 2 s por comando,
  el tick consulta varias propiedades y `_recover_mpv` (`app.py`) reinicia el proceso
  en el hilo de la interfaz: un mpv vivo pero bloqueado congela la pantalla unos
  segundos. Los fallos del socket, además, se convierten sin decir nada en `None` o
  cero. Llevar la recuperación a un worker, añadir un estado degradado visible y tests
  de timeout, EOF y líneas partidas del socket. No se ha visto pasar en la práctica.

## Sin fecha

- **Sacar objetos de verdad de `TidalAmp`.** 2635 líneas y 182 métodos en `app.py`;
  `_setting_changed` es de lo más enredado. No en mixins (ver «Descartado»), sino
  objetos con su propio diseño: reproducción, carátula, presentación de la cola y
  aplicación de ajustes, dejando `TidalAmp` como raíz de composición. Es un rediseño
  grande que no arregla ningún fallo, así que solo cuando haya tiempo para hacerlo
  bien.

## Descartado por ahora

No se borran: quedan escritos con el motivo para no volver a discutirlos desde cero.

- **Recordar el segundo de la pista al salir.** `queue.json` guarda el índice pero no la
  posición, así que cerrar a mitad de una canción devuelve a 0:00. **Decidido que no**
  (2026-09-10): ni el cliente oficial de TIDAL lo hace, así que no es una expectativa
  que este reproductor esté defraudando. Si alguna vez se retoma, las trampas son que el
  seek va después de que resuelva el stream, que `_was_idle` lee un mpv en idle como «la
  pista terminó», y que guardar en cada tick reescribiría el fichero diez veces por
  segundo.
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
