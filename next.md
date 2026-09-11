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

## 1. Más formas de carátula

`cover_shape` tiene `square` y `round`. Añadir al menos `rounded`, esquinas
redondeadas, con `ImageDraw.rounded_rectangle` en `artwork.shape`, sobre la misma
máscara dibujada a 4x.

Trampas:

- En `blocks` una celda son cuatro píxeles: un radio pequeño desaparece. Radio en
  proporción al lado (alrededor de un 12 %) y mirarlo en `blocks`, no solo en kitty.
- Las formas viven en `ConfigScreen.COVER_SHAPES`, en las tres copias de la plantilla
  de `i18n.py`, en el README (tabla de ajustes y sección de la carátula) y en el test
  de `artwork.shape`.

Cómo se comprueba: test de que la esquina queda en el fondo de la banda y un píxel
algo hacia dentro ya es la carátula; captura en `blocks` y a la vista en kitty.

## 2. Reproducción automática al terminar la cola

Un ajuste nuevo, «Reproducción automática» (`autoplay`, sí o no, apagado por
defecto para no cambiar lo que hace hoy): al acabarse la cola sigue con la radio de
TIDAL de la última pista en vez de detenerse.

Dónde engancha: el tick ve a mpv en reposo tras haber sonado algo y llama a
`action_next`; si `queue.next_index()` devuelve `None`, hoy se llama a `action_stop`.
Con el ajuste encendido, ahí se pide la radio.

Trampas:

- **No reutilizar `_radio_ready` tal cual:** reemplaza la cola y empieza por la pista
  semilla, que es la que acaba de sonar. Aquí la radio se **añade** al final, sin la
  semilla ni pistas que ya estén en la cola, y suena la primera añadida. La cola que
  había se conserva.
- La radio llega de un worker: entre el fin de la pista y la respuesta mpv está en
  reposo. Que eso no dispare otro `action_next` ni otra petición (una sola en vuelo).
- Radio vacía o fallida: detenerse como hoy y decirlo en la barra de estado.
- Con repetición de cola nunca se llega al final; con aleatorio, lo añadido tiene que
  entrar en el orden de `Queue`, y la cola se guarda como siempre.
- El ajuste es booleano como `debug`: va en `_FLAGS`, en las tres plantillas y en
  `conftest`.

Cómo se comprueba: tests con una cola de dos pistas y la radio simulada. Apagado, al
acabar se detiene; encendido, se añaden las pistas sin la semilla ni repetidas, suena
la primera nueva y la cola anterior sigue ahí; la radio vacía o con error detiene y
avisa.

## 3. Modo pantalla completa, como el de TIDAL

Pedido el 2026-09-11, con una captura del cliente de TIDAL como referencia. Una vista
que solo se abre con una tecla (sin fila en ajustes ni botón que la abra): la
carátula grande y centrada sobre un fondo liso, y abajo una barra de una fila con la
pista a la izquierda (título, artista, álbum), el transporte y la barra de posición
con sus tiempos en el centro, y a la derecha un botón que abre la cola en un panel
lateral, como en la captura. `esc` vuelve al reproductor normal.

Adaptada a la paleta y al tema en uso: el fondo, la barra y el panel salen de los
roles de la paleta (no del color de la carátula, como hace TIDAL), y el marco y los
glifos de las teclas, del `Layout` activo.

Qué hacer:

- La tecla: por decidir. Hoy están libres `a`, `i`, `j`, `k`, `n` y `w`; F11 no
  sirve, porque casi todos los emuladores la usan para su propia pantalla completa.
  Va en `DEFAULT_KEYS`, en la ayuda y en el README, y se puede cambiar en `[keys]`.
- Una `Screen` propia (no modal) con la carátula, la barra de abajo y el panel de la
  cola, que se abre y se cierra con su botón y con una tecla; `esc` la cierra.
- La carátula ocupa el alto que deja la barra, centrada; con el panel abierto se
  encoge para dejarle sitio en vez de quedar tapada.

Trampas:

- **La carátula kitty/sixel y las ventanas:** hoy toda pantalla por encima de la
  principal cuenta como ventana, y `_art_ready`, `_hide_art` y `push_screen`
  esconden la carátula de píxeles mientras hay una encima (`len(screen_stack) > 1`).
  Esta pantalla tiene que ser la excepción: la carátula se dibuja en ella, y las
  ventanas que se abran encima (ayuda, velocidad) sí la esconden.
- **El tamaño:** `Artwork.MAX_ROWS` limita hoy la carátula a 20 filas. Aquí quiere
  todo el alto, y en 4K eso son muchas celdas: medir el coste en `blocks` como se
  midió el fondo de la cola, y volver a pedirla a TIDAL al tamaño nuevo.
- **El tick:** hoy actualiza los widgets del reproductor por su id. La barra de
  abajo y el panel de la cola de esta pantalla necesitan los mismos datos (posición,
  estado, cola) sin que el tick sepa qué pantalla está delante.
- **La cola lateral:** reutilizar `RowList` con el fondo de su tema, y que sus
  teclas (cursor, ↵, `d`) sean las de la cola de siempre.
- Terminales pequeñas: por debajo de un tamaño mínimo la vista no se abre, y lo dice.
- Transparencia y `cover_shape` se respetan igual que en el reproductor.

Cómo se comprueba: tests de que la tecla abre la vista y `esc` vuelve con la cola y
la reproducción intactas, de que el botón y su tecla abren y cierran el panel, de que
la carátula no se esconde en esta pantalla pero sí bajo una ventana abierta encima, y
de que en todas las disposiciones y paletas cabe en el mínimo. Capturas en varios
temas, y a la vista en kitty.

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
