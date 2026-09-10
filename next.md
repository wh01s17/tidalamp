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

## 1. Volver a la pista que suena

Una tecla que devuelve el cursor a lo que se está reproduciendo.

**Por qué.** No existe ninguna. Con 766 favoritos en la cola te vas a mirar el final de
la lista y pierdes dónde estabas, y desde que hay filtro (`ctrl+f`) es todavía más
fácil perderla de vista. Es la función más barata de las tres y la que más se usa.

**Cómo se comporta.**

- Mueve el cursor a `_row_at(self.queue.playing)`.
- Si el filtro la está escondiendo, `_row_at` devuelve `-1`: entonces quita el filtro
  primero con `_clear_queue_filter()` y después mueve. Volver a la pista que suena y
  que no aparezca sería la peor respuesta posible.
- Con `queue.playing < 0` no hay nada a donde ir: no hace nada y lo dice en la línea de
  estado, en lugar de mover el cursor a la primera fila.

**Tecla.** `g`, que está libre y es la convención de «ir a». Rebindeable como el resto,
con la acción `to_playing`.

**Qué toca.** `DEFAULT_KEYS` y `BINDINGS` en `app.py`, la acción nueva, la fila de la
sección «Cola» en `about.py`, el catálogo de `i18n.py`, y la tabla de teclas del README.
La plantilla de configuración se genera desde `DEFAULT_KEYS`, así que sale sola.

**Cómo se comprueba.** Tres pruebas en la app real headless: el cursor lejos y `g` lo
devuelve; con un filtro que esconde la pista que suena, `g` quita el filtro y aterriza
en ella; sin nada sonando no se mueve nada y la línea de estado lo explica.

---

## 2. Guardar la cola como playlist de TIDAL

Una tecla que pregunta un nombre y crea la playlist en la cuenta con las pistas de la
cola, en su orden.

**Por qué.** Hoy se puede añadir a favoritos pero no crear una playlist. Es el cierre de
lo que ya existe: pones una radio, la retocas a mano durante media hora y todo ese
trabajo se pierde en cuanto vacías la cola.

**Cómo se comporta.**

- Pide el nombre en un modal, con la misma forma que `SearchScreen`: un `Input` que
  devuelve una cadena, o `None` si se cancela.
- Con la cola vacía no abre nada y lo dice.
- Manda las pistas en el orden de la cola, no en el del shuffle: lo que se guarda es la
  lista, no la sesión de escucha.
- El spinner lleva el mensaje mientras dura, y al terminar la línea de estado nombra la
  playlist creada.

**Trampas.**

- Es la **primera escritura de creación** contra TIDAL; hasta ahora sólo se favoritea.
  Va en un worker, detrás de `ensure_fresh` y envuelta en `with_retries`, como todo lo
  demás que sale a la red.
- Una cola de 700 pistas no cabe en una sola llamada de `add`. Hay que trocearla, y
  decidir qué se hace si el lote tres falla: la playlist ya existe a medias. Lo honesto
  es dejarla y decir cuántas entraron, no borrarla por detrás.
- La caché de niveles (`_LEVELS` en `library.py`) hace que «Mis playlists» no muestre la
  recién creada hasta pulsar `R`. O se invalida esa clave al crear, o el mensaje dice
  que hay que recargar. Lo primero es mejor y cuesta una línea.
- Comprobar el nombre exacto de la API en la versión de `tidalapi` que está fijada
  antes de escribir nada alrededor.

**Tecla.** Pendiente de elegir entre las libres (`p` encaja con «playlist»).

**Qué toca.** La función de escritura en `library.py`, el modal en `screens.py`, la
acción en `app.py`, y después `about.py`, `i18n.py` y el README.

**Cómo se comprueba.** Con un doble de sesión: que se cree con el nombre escrito, que
se manden todos los ids y en lotes, que el orden sea el de la cola, que un fallo a
mitad llegue a la línea de estado sin romper la cola, y que con la cola vacía no se
llame a nada.

---

## 3. Barra de posición y sliders clicables

Un clic en la barra de posición salta a ese punto de la pista. Un clic en volumen o
balance fija ese valor.

**Por qué.** La app ya sabe manejar clics: `@on(events.Click, "#transport-play")` con
`_transport_hits` hace test de coordenadas sobre los botones del transporte. Pero sólo
los botones responden. Que la barra de posición no reaccione al clic es de las cosas
que se prueban sin pensar y se notan cuando no pasan.

**Trampas.**

- `#seek` tiene `padding: 0 1` en la hoja de estilos, así que la `x` del evento no es la
  `x` dentro de la barra dibujada. Hay que descontar el padding o trabajar sobre la
  región de contenido. Es exactamente el error que se comete aquí.
- El balance tiene centro: el clic en la celda central debe dar `0` exacto, o queda
  descentrado por redondeo y no hay forma de volver al centro con el ratón.
- Sin pista cargada, `total` es `0` y un clic en la barra de posición no debe hacer nada
  en vez de dividir por cero.
- **Alcance: sólo el clic.** Arrastrar es seguir `MouseMove` con el botón pulsado y es
  otra historia; si se quiere, va en otra entrada.

**Qué toca.** `widgets.py` para que `SeekBar` y `Slider` traduzcan una `x` a un valor, y
`app.py` para los manejadores.

**Cómo se comprueba.** Con `pilot.click` y un desplazamiento conocido: que a mitad de la
barra el seek caiga a mitad de la pista, que el clic en el centro del balance dé cero, y
que un clic con la cola parada no llame a mpv.

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
