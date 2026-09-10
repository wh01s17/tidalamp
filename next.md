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

## 1. La columna «Año» siempre sale vacía

Está en el catálogo, se puede activar en la ventana de columnas, ocupa su sitio en la
fila y no muestra nada. Bajo el reloj, lo mismo.

**Qué pasa.** `Entry.year` sale de `album.year` de tidalapi, que lo deduce de
`releaseDate` o `streamStartDate` del JSON del álbum. Pero cuando una pista llega en un
listado —favoritos, un álbum, una búsqueda, una radio— el álbum que viene anidado
dentro de la pista es la versión corta: id, título y portada, **sin fecha**. Así que
`album.year` es `None` siempre y `int(... or 0)` lo convierte en `0`, que es el valor
que la columna trata como «no hay dato».

Medido sobre la cola guardada del usuario: 100 entradas, 15 álbumes distintos, **0 con
año**. No es que a esos discos les falte la fecha en TIDAL; es que no viaja en esa
respuesta.

**Lo que esto le hace a una promesa del plan.** §4 dice que las once columnas no cuestan
una petición extra porque «vienen rellenas en un listado normal». Es cierto para diez.
El año lo cumple sólo porque llega vacío, que no es cumplirlo.

**Opción elegida: pedir el álbum una vez por álbum distinto.** Para una cola de 100
pistas son 15 peticiones, no 100, en segundo plano y cacheadas por id durante la sesión.
Sólo cuando la columna esté activada o el bloque del reloj a la vista: quien no mire el
año no paga nada.

**Descartado: el `streamStartDate` de la pista.** Sí viaja en el listado y costaría cero
peticiones, pero es la fecha en que TIDAL empezó a emitirla, no la de publicación. Para
un disco de 1997 subido al catálogo en 2011 pintaría 2011. Un dato equivocado con cara
de dato bueno es peor que una celda vacía; es lo mismo que la insignia `FFT`/`RMS`
existe para no hacer.

**Trampas.**

- La cola persistida ya tiene `year: 0` escrito en `queue.json`. Hay que decidir si al
  restaurar se rellena o si sólo se pide para lo que entra nuevo. Rellenar al restaurar
  son 15 peticiones al arrancar, que no es gratis.
- Un álbum sin fecha en TIDAL seguirá dando `0`, y eso está bien: la celda vacía
  entonces sí dice la verdad.
- La caché va por id de álbum, no por pista: 100 pistas de 15 discos son 15 peticiones,
  y ese es todo el ahorro.

**Qué toca.** `queue.py` para el relleno, `library.py` para la caché por álbum, y el
punto de §4 de `plan.md` que hay que corregir cuando esté hecho.

**Cómo se comprueba.** Con un doble de sesión: que se pida un álbum por id distinto y no
uno por pista, que una segunda pista del mismo álbum no dispare petición, que un álbum
sin fecha deje la celda vacía sin reintentar en bucle, y que con la columna apagada no
se pida nada.

---

## Descartado por ahora

No se borran: quedan escritos con el motivo para no volver a discutirlos desde cero.

- **Recordar el segundo de la pista al salir.** `queue.json` guarda el índice pero no la
  posición, así que cerrar a mitad de una canción devuelve a 0:00. Es la que más se
  echa de menos, pero también la que más cuidado pide: el seek va después de que el
  stream resuelva, `_was_idle` lee un mpv en idle como «la pista terminó», y guardar en
  cada tick reescribiría `queue.json` diez veces por segundo. Se queda fuera de esta
  tanda por eso, no porque no valga.
- **Temporizador de apagado.** Un `set_timer` que llame a `action_stop` y un indicador
  en el transporte. Barato, pero no lo pidió nadie todavía.
- **Enrutar mpv a un sink propio de PipeWire** para que cava no oiga el resto del
  sistema. Cuesta un nodo por ejecución para arreglar un caso raro. Ver `plan.md` §9.4.
