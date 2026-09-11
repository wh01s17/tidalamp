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

## 1. Temas temáticos: una disposición propia y una paleta que la acompaña

Hoy hay **dos ejes ortogonales**. `LAYOUTS` en `theme.py` da la estructura (`quattro`,
`retro`, `nova`, `ascii`) y la paleta da el color (`auto`, `classic`, y las
incorporadas `tokyo-night`, `catppuccin`, `nord`, `gruvbox`, `black`). Cualquier
disposición funciona con cualquier paleta.

No hace falta un tercer concepto. Un tema temático es **una entrada más en cada uno de
los dos ejes, con el mismo nombre**:

- `eva-01` entra en `LAYOUTS`: su propia estructura, tan distinta como haga falta.
- `eva-01` entra en `_BUILTIN_SOURCES`: sus propios colores.
- Elegir el tema `eva-01` deja puesta la paleta `eva-01`, y desde ahí **la paleta sigue
  siendo libre**: quien quiera `eva-01` con `nord` lo tiene, y el tema no lo revierte.

**Decidido el 2026-09-10.** Se descartó la idea previa de un «ambiente» como tercer
ajuste que agrupara los otros dos. Con el emparejamiento por nombre no hay nada que
arbitrar: no existe la pregunta «¿qué gana si pido `ambiente = eva-01` y
`palette = nord`?», porque no hay un tercer valor. Menos código, menos config y menos
documentación para el mismo resultado.

**Esto es compatible hacia atrás por construcción.** Ningún nombre de disposición
actual existe como paleta ni al revés, así que la regla del emparejamiento no cambia
el comportamiento de nadie que ya use `quattro`, `retro`, `nova` o `ascii`.

### Lo que hay que hacer

Ya hecho el 2026-09-10 (ver `plan.md` «Disposiciones como datos»): la tabla
`layouts.LAYOUT_TABLE` que sustituye a los `if config.THEME ==`, la regla de
emparejamiento (elegir el tema escribe su paleta una vez, `theme.PAIRED`), el test
que impide que una disposición y una paleta compartan nombre sin declararlo, el test
de presupuesto ASCII y el de contraste mínimo. `load_palette(name="auto")` no se tocó,
como estaba decidido. Queda, por tema:

1. **Una `Layout` en `LAYOUT_TABLE`**, con su estructura: título, encabezado de la
   cola, un `_transport_<nombre>` si no reutiliza uno, y su bloque de TCSS.
2. **Una entrada en `_BUILTIN_SOURCES` con el mismo nombre.** Queda elegible por su
   cuenta, como las demás: la paleta `eva-01` con disposición `retro` es una
   combinación válida y nadie tiene que impedirla.
3. **Su nombre en `theme.PAIRED`.** Sin eso el test de choque de nombres falla, que es
   justo lo que tiene que hacer.

### Trampas conocidas

- **Las paletas nuevas se quedan dentro del vocabulario de diez.** `_from_source()`
  acepta `accent`, `background`, `foreground`, `muted`, `dark_background`,
  `lighter_background`, `red`, `yellow`, `green` y `blue`, y de ahí deriva los
  veinticinco semánticos con `_OMARCHY_KEYS`. Es lo que mantiene compatibles las
  paletas de Omarchy y las de usuario, y **no hay que romperlo**: una paleta escrita
  en esos diez es además copiable tal cual a
  `~/.config/tidalamp/palettes/loquesea.toml`, que es media documentación gratis. Si
  alguna necesitara de verdad control fino de algo como `eq_background`, la salida es
  construirle la `ThemePalette` desde los veinticinco saltándose `_from_source()`,
  nunca ampliar el vocabulario compartido. Que sea la excepción y no la norma.
- **`ascii` no puede dibujar.** Esa disposición existe para terminales sin glifos de
  caja, y el presupuesto de glifos es parte de la disposición (`Layout.ascii_only`,
  con test). Los temas nuevos son libres de usar lo que quieran, pero ninguno debe
  empujar sus rótulos a `ascii`.
- **Cada rótulo nuevo es una entrada de catálogo.** Todo literal `_()` necesita su
  pareja en `i18n.ENGLISH` y el test que recorre el AST exige igualdad exacta. Los
  nombres propios de tema no se pasan por `_()`.
- **Verlos en un terminal de verdad.** `plan.md` §9.5 ya mordió una vez por dar por
  buena una disposición que solo se había visto en un test.

### La lista propuesta

Nueve, de la conversación del 2026-09-10: eva-01, One Piece, Death Note, Cyberpunk
2077, El Señor de los Anillos, reggae, el Joker de *El caballero oscuro*, gótico y
death metal.

**Antes de fijar los nombres hay que resolver lo de las marcas.** Seis de los nueve son
marcas registradas y muy defendidas. Una paleta de colores no es registrable y nadie
puede reclamar el morado con verde y naranja; el **nombre** y el **logotipo** sí lo son,
y tidalamp se publica en PyPI a nombre propio del mantenedor. Lo barato es evocar sin
nombrar: `eva-01` pasa a `unidad-morada`, Cyberpunk 2077 a `neon-noir`, Death Note a
`cuaderno`, y así. Los tres de género (reggae, gótico, death metal) no tienen ese
problema y pueden entrar tal cual. Esto es decisión del mantenedor, no técnica; queda
escrito para que no se decida por descuido al teclear el primer nombre.

### Cómo se comprueba

- Ninguna disposición y ninguna paleta comparten nombre salvo a propósito: la lista de
  parejas declaradas es explícita y el test falla ante una coincidencia nueva.
- Elegir un tema con pareja escribe esa paleta en el config; cambiar la paleta después
  no toca la disposición ni los rótulos.
- `palette = "auto"` sigue resolviendo Omarchy y luego `classic`, con tema emparejado
  o sin él, exactamente como hoy.
- Cada paleta nueva produce una `ThemePalette` con los veinticinco colores válidos y
  pasa el contraste mínimo.
- A mano, en un terminal real y a dos tamaños: los nueve, con captura.

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
