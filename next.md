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

## Para la 0.9.0

- **mpv sin congelar la interfaz.** El IPC (`player.py`) espera hasta 2 s por comando,
  el tick consulta varias propiedades y `_recover_mpv` (`app.py`) reinicia el proceso
  en el hilo de la interfaz: un mpv vivo pero bloqueado congela la pantalla unos
  segundos. Los fallos del socket, además, se convierten sin decir nada en `None` o
  cero. Llevar la recuperación a un worker, añadir un estado degradado visible y tests
  de timeout, EOF y líneas partidas del socket. No se ha visto pasar en la práctica.

- **Sin corte entre pistas.** Hoy la pista siguiente se resuelve cuando termina la
  anterior (`_play_index` llama a `_resolve_worker`), así que entre canciones queda el
  silencio de pedir el stream a TIDAL. Resolverla por adelantado mientras suena la
  actual y dejársela preparada a mpv; en discos en vivo o conceptuales el corte se
  nota. Trampas: la URL del stream caduca, así que no se puede resolver con demasiada
  antelación; shuffle, repeat y la cola editada cambian cuál es «la siguiente», y un
  resultado preparado para otra pista no debe sonar (el mismo cuidado que
  `_resolving`). Se comprueba con un mpv falso: al terminar una pista, la siguiente
  arranca sin volver a resolver, y si la cola cambió en medio se resuelve la correcta.
- **Volumen normalizado (ReplayGain).** Un ajuste con tres modos, apagado, por pista y
  por disco, para que una playlist no salte de volumen entre canciones. TIDAL publica
  la ganancia de cada pista y de su disco; **por confirmar** que tidalapi la expone en
  lo que ya pedimos al resolver el stream (`stream.py`), y en qué forma. mpv la aplica
  como un filtro de volumen más, junto al balance y el ecualizador (`settings.py`,
  `_apply_audio`). Trampa: no recortar si la ganancia sube una pista ya fuerte; el
  pico, si TIDAL lo da, marca el límite. Se comprueba con valores fijados: el filtro
  que llega a mpv cambia con el modo y desaparece al apagarlo.
- **Tus Mixes de TIDAL en la biblioteca.** Una sección con los mixes personales, como
  el diario y el de descubrimiento, que se abren como una playlist más. **Por
  confirmar** qué ofrece tidalapi y lo estable que es: esa parte de TIDAL cambia más
  que favoritos o playlists. Trampa: un mix no se ordena ni se modifica, así que no
  debe ofrecer `s` ni `d`. Se comprueba con una sesión simulada que devuelve dos
  mixes: la sección los lista y abrir uno trae sus pistas.

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

- **Radio de un artista o de una playlist** (2026-09-11), para completar el menú de la
  `m`, que no tiene radio porque la de TIDAL nace de una pista. Al mantenedor no le
  interesó: la radio de pista ya cubre lo que busca.
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
