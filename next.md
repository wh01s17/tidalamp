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

## 1. Ambientes: un tema que cambia estructura, color y rótulos a la vez

Hoy hay **dos ejes deliberadamente ortogonales**. `LAYOUTS` en `theme.py` da la
estructura (`quattro`, `retro`, `nova`, `ascii`) y la paleta da el color (`auto`,
`classic`, cuatro incorporadas y las de usuario en `~/.config/tidalamp/palettes`). El
docstring lo dice sin rodeos: cualquier disposición funciona con cualquier paleta. Eso
da color, pero no identidad: elegir `gruvbox` no hace que el reproductor *se sienta*
de otra cosa.

Un **ambiente** es un nombre que fija los dos ejes de una vez y además cambia los
rótulos del chrome. Una sola elección en config y el reproductor entero cambia de
carácter.

**Decidido el 2026-09-10: un ambiente elige, no encierra.** No es un tercer eje, es un
*preset*: un punto con nombre dentro del espacio (disposición x paleta) más un puñado
de cadenas. Elegirlo deja la paleta que le pega a la temática, y a partir de ahí la
paleta **sigue siendo libre**: quien quiera el ambiente gótico con `nord` puede
tenerlo, y el ambiente no lo revierte ni se queja.

Esto fija dos reglas de implementación:

- **El ambiente escribe en `theme` y `palette`, no los sustituye.** Aplicarlo es
  asignar esos dos ajustes y los rótulos; no hay un tercer valor que arbitrar en el
  config ni una precedencia que documentar. La pregunta «¿qué gana si pido
  `ambiente = gotico` y `palette = nord`?» deja de existir, que es la mitad del valor
  de haberlo decidido así.
- **Cambiar la paleta después no desactiva el ambiente.** Los rótulos y la disposición
  se quedan. Un ambiente al que se le cambió el color sigue siendo ese ambiente.

### Lo que hay que hacer

1. **Primero, quitar el `if config.THEME ==` de en medio.** Hoy la disposición se
   decide con comparaciones de cadena repartidas por `app.py`: `_title_text()`,
   el diccionario de `_transport_*`, y dos sitios más alrededor de las líneas 1006 y
   1018. Con cuatro disposiciones se aguanta; con cuatro más nueve ambientes se
   convierte en el sitio donde viven los fallos. Antes de añadir nada, esas ramas
   tienen que pasar a una tabla de datos: una `Layout` con los campos que hoy son
   ramas (rótulo del título, regla, constructor del transporte, presupuesto de
   glifos).
2. **Un `Ambience`** con: disposición base, paleta, rótulo del título y poco más.
   Guardado como datos, no como código.
3. **Una paleta nueva por ambiente**, porque ninguna de las cuatro actuales evoca nada
   de la lista. Entran en `_BUILTIN_SOURCES` como las demás, lo que las vuelve
   **elegibles por su cuenta**: se puede tener la paleta del ambiente gótico con la
   disposición `retro` y sin sus rótulos, igual que hoy se elige `nord`. El ambiente
   es quien la pone por omisión, no quien la posee.
4. **Exponerlo en config y en la pantalla de ajustes**, junto a `theme` y `palette`,
   diciendo que los sobrescribe.

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
  caja. Un ambiente que le meta un rótulo con caracteres raros la rompe justo para
  quien la eligió. El presupuesto de glifos es parte de la disposición y manda sobre
  el ambiente.
- **Legibilidad.** La mitad de la lista tira a negro sobre negro. Hace falta una
  comprobación de contraste mínimo entre `body` y `screen`, y entre `accent` y
  `screen`, o habrá ambientes bonitos en la captura e inservibles en uso.
- **Cada rótulo nuevo es una entrada de catálogo.** Todo literal `_()` necesita su
  pareja en `i18n.ENGLISH` y el test que recorre el AST exige igualdad exacta. Si los
  nombres de ambiente son propios, no pasarlos por `_()`.
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

- La suite recorre todos los ambientes y comprueba que cada uno nombra una disposición
  que existe y una paleta que `available_palettes()` lista, y que esa paleta produce
  una `ThemePalette` con los veinticinco colores válidos.
- Cambiar la paleta con un ambiente puesto no toca la disposición ni los rótulos.
- Un test de contraste mínimo sobre cada ambiente.
- El ambiente `ascii` de turno no emite ningún carácter fuera de ASCII.
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
- **Multiplica contra los otros ejes.** Cuatro disposiciones por dos formas, y con los
  ambientes de la entrada 1 la cuenta se dispara. Comparte prerrequisito con esa
  entrada: **las comparaciones `if config.THEME ==` repartidas por `app.py` tienen que
  pasar a una tabla de datos antes**, o cada forma nueva se paga en cuatro sitios
  distintos.

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
