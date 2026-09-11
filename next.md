# next.md — lo que entra en la próxima versión

Cola de trabajo comprometido, no una lista de deseos. Cada entrada trae lo que hay que
hacer, por qué, las trampas que ya se conocen y cómo se comprueba, para que se pueda
retomar sin releer el hilo en el que se decidió.

**Cómo se usa este fichero.** Cuando algo de aquí queda hecho, **se borra de aquí** y
pasa a dos sitios: la línea de usuario a `CHANGELOG.md`, bajo `[Sin publicar]`, y el
detalle de diseño y las decisiones a la sección que le corresponda de `plan.md`. Un
fichero que acumula entradas tachadas deja de decir qué falta, que es lo único para lo
que existe. Si algo se descarta, no se borra sin más: baja a «Descartado por ahora» con
el motivo.

Lo de aquí no bloquea publicar. `plan.md` §5 y §6 mandan sobre el estado general.

---

## 1. Partir los ficheros que han crecido demasiado

Decidido el 2026-09-11, aplazado hasta cerrar los emblemas. Hoy: `tests/test_app.py`
~5000 líneas, `tidalamp/app.py` ~2300 (una sola clase con ~170 métodos),
`tidalamp/screens.py` ~2200 (once pantallas), `tidalamp/styles.tcss` ~1300 y
`tidalamp/widgets.py` ~1000. Es seguro si cada paso **solo mueve código**, sin cambiar
comportamiento, y la suite pasa después de cada uno.

Orden, de menos a más riesgo:

1. `screens.py` a paquete `screens/`, un módulo por pantalla; `__init__.py` reexporta
   todo para que `from tidalamp.screens import ConfigScreen` siga valiendo.
2. `tests/test_app.py` partido por tema (transporte, cola, split, temas, ajustes, ayuda),
   con los helpers (`FakeMpv`, `isolate_runtime`, `use_theme`...) en `conftest.py` o en
   un módulo propio: `tests/` no es un paquete y un test no puede importar de otro.
3. `widgets.py`: el analizador a su módulo, los de texto (`Glide`, `Marquee`,
   `LyricsPane`) a otro.
4. `styles.tcss` en varios ficheros (`CSS_PATH` acepta una lista) **en el mismo orden**:
   a igual especificidad gana la regla posterior, y varias dependen de eso.
5. `app.py`, lo último: primero mixins por tema (apariencia, transporte, cola, carátula
   y letra, MPRIS), que reparten sin cambiar nada; extraer objetos de verdad sería otro
   trabajo, con su propio diseño.

Trampas:

- **Los `monkeypatch` de los tests** parchean nombres en un módulo concreto
  (`screens_module.paired_palette`, `app_module.config`): si la función se muda, el
  parche sigue en el sitio viejo y el test pasa sin probar nada. Hay que moverlos con
  el código.
- **El test del catálogo i18n** recorre `tidalamp/*.py` con `glob`: con subpaquetes
  dejaría de ver sus textos sin fallar. Pasarlo a `rglob` antes de mover nada.
- Un commit por fichero, sin funcionalidad mezclada, y un `.git-blame-ignore-revs` con
  esos commits para que `git blame` siga apuntando al autor real.

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
