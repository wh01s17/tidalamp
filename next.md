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

## 1. Temas temáticos: verlos en un terminal real

Implementados el 2026-09-10 (ver `plan.md` «Disposiciones como datos» y el CHANGELOG):
los nueve temas, con nombres que evocan sin nombrar marcas. Lo único que queda es la
comprobación a mano que ningún test sustituye, porque `plan.md` §9.5 ya mordió una vez
por dar por buena una disposición vista solo en un test:

- A mano, en un terminal real y a dos tamaños (el mínimo y uno ancho): los nueve, con
  su paleta y con otra, y con captura para el README.
- Mirar en particular los glifos de cromo que dependen de la fuente: `▚ ▰ ☠ ⎈ ✎ ♫ ♠ ♥
  ♦ ♣ ✠ ⟦ ⟧ ◆`. Si alguno sale como tofu o a dos celdas, se cambia en `layouts.py`; el
  test de ancho solo cubre lo que Unicode declara ancho, no lo que la fuente decide.

---

## 2. Dos columnas: lo que queda por mirar

Implementado el 2026-09-10 (`arrangement = "split"`, ver `plan.md` «Dos columnas»), y
ya usado en un terminal real con audio y letra. Queda:

- Achicar la ventana por debajo de 160 con split puesto y una carátula kitty: vuelve a
  apilada sin dejar restos de la imagen pintados encima de la cola.
- La letra sin sincronizar se enseña desde arriba y no se puede desplazar en el panel
  (en la ventana de `y` sí). Si molesta, el panel necesita su propio desplazamiento, y
  decidir qué teclas lo mueven sin pisar las de la cola.

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
