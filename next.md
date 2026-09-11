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

## 2. Disposición en dos columnas: reproductor a la izquierda, cola a la derecha

Hoy `compose()` es una pila vertical de once hijos dentro de `MainPanel`: título,
banda de display, seek, los dos sliders, transporte, y debajo el rótulo de la cola, la
lista, la barra de búsqueda y la barra de estado. Todo apilado, todo a lo ancho.

Se quiere poder pasar esa mitad de arriba a una **columna izquierda** y dejar la cola
en una **columna derecha**, y cambiar entre las dos formas **en caliente**, sin
reiniciar la reproducción.

### Lo que hay que hacer

1. **Agrupar las dos mitades en `compose()` desde el principio**, en dos contenedores
   (`#player-half` y `#queue-half`), aunque la disposición apilada siga viéndose
   idéntica. Este paso no cambia nada visible y es el que hace barato todo lo demás.
2. **Cambiar de forma con una clase en `#main`**, no reconstruyendo el árbol. La CSS
   decide si `#main` apila los dos contenedores o los pone en paralelo.
3. **Colgarlo de `_apply_appearance()`**, que ya existe justo para esto: aplica
   estructura y paleta sin tocar mpv.

### Trampas conocidas

- **No reparentar widgets.** Mover hijos de un contenedor a otro en Textual es
  `remove()` más `mount()`, y eso destruye el estado: la fila donde estaba el cursor
  del `RowList`, la imagen ya decodificada del `Artwork`, la fase del `Marquee`.
  Cambiar de forma dejaría la cola saltando al principio y la carátula parpadeando,
  que es exactamente lo contrario de «en tiempo real». Componer las dos mitades una
  vez y que la CSS las coloque evita el problema entero, y es la razón del paso 1.
- **La banda de display está calculada a ancho completo.** `_fit_display_band()`
  dimensiona la carátula por alto y por ancho, `_spread()` mide el encabezado de la
  cola contra el ancho total, y hay constantes duras: `CLOCK_WIDTH = 24`,
  `READOUT_WIDTH = 30`, `MAX_BARS = 64`. Solo el reloj y el readout ya son 54 columnas,
  así que a media pantalla la banda no entra y hay que decidir qué cede. Esto es el
  grueso del trabajo, no el colocar las dos columnas.
- **El umbral de `compact` no sirve.** `_check_size()` pasa a compacto por debajo de
  80x26, y el mínimo de la aplicación es 76x20. Dos columnas necesitan del orden del
  doble de ancho. Hace falta un umbral propio y **volver solo** a la forma apilada
  cuando no quepa, o quien la active en un terminal normal se encuentra la interfaz
  rota sin saber por qué.
- **Multiplica contra el otro eje.** Cuatro disposiciones por dos formas, y con los
  nueve temas de la entrada 1 son veintiséis combinaciones. El prerrequisito que
  compartía con esa entrada, pasar las comparaciones `if config.THEME ==` a una tabla
  de datos, ya está hecho (`layouts.py`).

### Cómo se comprueba

- La suite monta la aplicación en las dos formas y comprueba que ningún widget se
  desmonta al cambiar: el mismo objeto `RowList` antes y después, con el cursor donde
  estaba.
- A un ancho por debajo del umbral, pedir dos columnas deja la forma apilada.
- A mano, en un terminal real y ancho, con la cola llena y una pista sonando: cambiar
  de forma no corta el audio ni mueve el cursor.

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
