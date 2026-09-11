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

## 1. Calidad, ritmos hi-res y reiniciar PipeWire se eligen de una lista

Pedido el 2026-09-11. Hoy en la ventana de ajustes Enter, espacio y la flecha derecha
llaman a `_change(1)` y la izquierda a `_change(-1)`, así que una flecha de más cambia
la calidad, escribe o borra el drop-in de ritmos de PipeWire (`_toggle_rates`) o
**reinicia PipeWire** (`_restart`), que corta el audio. Son las tres filas donde un
toque sin querer cuesta caro.

Qué hacer: en esas tres filas las flechas no hacen nada y Enter abre una ventana con
una lista para elegir una opción (no casillas, como las columnas de la cola):

- Calidad: `LOW`, `HIGH`, `LOSSLESS`, `HI_RES_LOSSLESS`, con la actual marcada y la
  nota de siempre (`LOSSLESS` por device flow devuelve `HIGH`).
- Ritmos hi-res: configurar o quitar, con lo que hace cada una.
- Reiniciar PipeWire: reiniciar ahora o cancelar, diciendo que corta el audio.

Trampas:

- `SpeedScreen` (`screens/speed.py`) ya es casi esa ventana: sacar de ahí una lista
  genérica de elegir uno (título, opciones, actual, pie) y que la usen las cuatro, en
  vez de copiarla tres veces. Ojo con los nombres: `#picker-box` ya es de
  `PlaylistPickerScreen`.
- Enter en la fila tiene que seguir funcionando igual para las demás filas; lo que
  cambia es solo qué hacen las flechas en estas tres.
- Con transparencia activa, la ventana nueva va en la lista de cajas esmeriladas de
  `styles/base.tcss`, como `#speed-box`.

Cómo se comprueba: tests que pulsan izquierda y derecha sobre cada una de las tres
filas y comprueban que no cambia nada (ni `config`, ni el drop-in, ni se llama a
`_restart`), y que Enter abre la lista y elegir escribe lo mismo que hoy.

## 2. Velocidad por MPRIS

`mpris.py` publica `Rate`, `MinimumRate` y `MaximumRate` fijos en 1.0 y de solo
lectura. Qué hacer: `Rate` de lectura y escritura con la velocidad de mpv,
`MinimumRate` 0.25 y `MaximumRate` 2.0 (los extremos de `Mpv.SPEEDS`), y avisar con
`PropertiesChanged` cuando la velocidad cambia desde la ventana de `b`.

Trampas:

- Un escritorio puede pedir cualquier número. Redondear al cuarto más cercano dentro
  del rango, para que el botón y la ventana sigan diciendo una de las ocho.
- La especificación dice que `Rate` no debe ser 0: si llega, ignorarlo.
- `mpris.py` no lo revisa mypy (`ignore_errors`, por las firmas de dbus-fast): lo
  cubren los tests de contrato de `tests/test_mpris.py`, contra un bus real. El
  método nuevo del backend va en el `Protocol` `PlayerBackend` y en el doble.

Cómo se comprueba: en `tests/test_mpris.py`, leer los tres valores, escribir `Rate`
0.5 y ver la velocidad de la app, escribir 0.6 y ver 0.5, escribir 0 y ver que no
cambia. A mano: `playerctl` o el widget del escritorio.

## 3. Más formas de carátula

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

## 4. Reproducción automática al terminar la cola

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
