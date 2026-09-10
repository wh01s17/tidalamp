# Registro de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el
versionado es [semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Cambiado

- **La identidad de la pista baja bajo el reloj.** La marquesina llevaba número, artista,
  título y duración en una sola línea, y debajo del reloj había cinco filas vacías. Ahora
  la marquesina es sólo el número y el título, y el artista, el álbum, el año y la
  duración van en la columna del reloj, cada uno en su línea. El año se calla cuando el
  catálogo no lo da. En la disposición compacta el bloque desaparece y el reloj se queda
  con la banda entera, como antes.

### Añadido

- **`g` vuelve a la pista que suena**. Si el buscador de la cola la está escondiendo,
  quita primero el filtro; si no suena nada, deja el cursor donde está y lo explica en
  la línea de estado.
- **`p` guarda la cola como playlist de TIDAL**. Pide el nombre, toma una instantánea
  en el orden real de la cola, envía las pistas en lotes de 100 e invalida «Mis
  playlists». Si un lote falla, conserva la playlist parcial y dice cuántas pistas
  llegaron en vez de borrar trabajo a espaldas del usuario.
- **Barras clicables**: la de posición salta al punto pulsado, y volumen y balance
  fijan su valor; la celda central del balance queda en cero exacto.

### Corregido

- **Los límites 429 de TIDAL vuelven a intentarse.** `tidalapi` convierte el error HTTP
  en `TooManyRequests`, un tipo que el reintentador no reconocía. Ahora respeta
  `Retry-After`, usa el backoff normal cuando la cabecera falta y abandona sin congelar
  la interfaz cuando la espera indicada supera un minuto.

## [0.3.0] - 2026-09-10

### Añadido

- **Formas para el analizador**, elegibles en la ventana de ajustes (`o`, en
  Apariencia), en `config.toml` o con `TIDALAMP_VISUALIZER`: `bars` son las barras de
  siempre, `mirror` las hace crecer hacia arriba y hacia abajo desde una línea central,
  `curve` dibuja el contorno del espectro como una línea de un glifo por columna, y
  `fine` dibuja esa misma línea sobre la rejilla de puntos del Braille, con el doble de
  resolución horizontal y los puntos entre muestra y muestra encendidos, así que sale
  un trazo continuo en vez de una fila de marcas sueltas. `fine` necesita una fuente
  que traiga Braille: casi todas lo hacen, pero una que no dibuja cuadraditos y a un
  terminal no se le puede preguntar de antemano, por eso es una forma que se elige y no
  una a la que nada cae solo. Las cuatro se dibujan donde el analizador ha estado
  siempre —al lado de la carátula, bajo los datos de la pista— y las cuatro llegan
  hasta el borde derecho de la ventana; antes las barras se paraban a las 19 y dejaban
  vacíos dos tercios de la columna. Las cuatro leen el mismo frame de cava, que ahora
  se pide con más bandas de las que dibuja ninguna y cada forma remuestrea, así que
  cambiar de una a otra cuesta un repintado y no reinicia el FFT.

- **Buscador en la cola**, con `ctrl+f`. Abre una barra bajo la lista, al estilo del
  filtro `/` del navegador de la biblioteca: no tapa la cola, la estrecha debajo
  mientras se escribe, y a la derecha dice cuántas pistas quedan de cuántas. Ignora
  mayúsculas y acentos, exige que cada palabra aparezca en algún sitio y busca también
  por el álbum de la pista. Las filas conservan **el número que tienen de verdad en la
  cola**: una coincidencia que sale como `47` dice dónde está en el orden de
  reproducción en vez de fingir que es la primera. `↵` devuelve las flechas a la lista
  con el filtro puesto y `esc` lo quita dejando el cursor en la pista a la que se había
  llegado. Todo lo que actúa sobre la fila seleccionada —`↵`, `d`, `alt+↑`, `alt+↓`,
  `f`— actúa sobre esa pista y no sobre el sitio que ocupa en la pantalla. La tecla es
  rebindeable como cualquier otra, con la acción `filter_queue`.

- **`tidalamp -v` / `tidalamp --version`**: imprime `tidalamp <versión>` en el terminal
  y sale. El número estaba sólo dentro de la interfaz, y quien lo necesita suele
  necesitarlo justo cuando la interfaz no arranca. Responde antes de que nada pida
  sesión, `mpv` ni un terminal de cierto tamaño, y lee la misma versión que enseña la
  pantalla de ayuda.

### Cambiado

- **El analizador es mucho más barato en pantallas grandes.** Las barras se topan en 64
  bandas y se ensanchan para cubrir el ancho, en vez de multiplicarse y adelgazar según
  crece el terminal, y los tramos de un mismo color se mandan al terminal en una sola
  secuencia de escape en lugar de una por celda. A 380x50 —un 4K— eso baja el coste de
  la app de **55% de un núcleo a 8%** a diez frames por segundo. También sale ganando el
  analizador de siempre en un terminal normal: pinta menos tramos que antes.

- **La ayuda pasa a dos pestañas**: «Ayuda» son los atajos y `→` lleva a «Acerca de»,
  con los créditos, la licencia y los cambios por versión; `←` vuelve. Antes era un
  documento seguido en el que todo eso quedaba tres pantallas por debajo de lo único
  que se abre la ventana a mirar. Cada pestaña recuerda por dónde iba, la barra de
  título marca en cuál estás, y el pie dice a dónde lleva la flecha que queda.

## [0.2.0] - 2026-09-10

### Añadido

- **Paleta `black`**: negro puro de fondo y todo lo demás en grises y blancos. Es la
  primera monocroma, así que declara más vocabulario que las otras: sin
  `dark_foreground`, el texto secundario —estado, listas vacías, etiquetas inactivas,
  las bandas apagadas del ecualizador— caía en el `foreground` de siempre, y una paleta
  sin color donde lo callado brilla igual que lo importante no tiene con qué decirlo.
  `red`, `yellow`, `green` y `blue` conservan su papel (error, aviso, pistas
  reproducibles, contenedores) y se vuelven cuatro grises, porque aquí el único eje es
  cuánta luz tiene cada cosa. Una prueba fija que ningún color de la paleta tiene tono.

- **Filtro dentro del navegador de la biblioteca**, con `/`. Abre una barra al pie de
  la ventana, al estilo del buscador de un navegador web: no tapa el nivel, lo estrecha
  debajo mientras se escribe, y a la derecha dice cuántas filas quedan de cuántas. Filtra
  lo que el nivel tenga —pistas en favoritas, playlists en «Mis playlists», álbumes,
  artistas o una categoría de resultados—, ignora mayúsculas y acentos (`sinfonia`
  encuentra *Sinfonía*), exige que cada palabra escrita aparezca en algún sitio y busca
  también por el álbum de la pista, que no está en la línea salvo que se active esa
  columna. `↵` aplica el filtro y devuelve las flechas a la lista; `esc` lo quita y deja
  el navegador abierto sobre la fila a la que se había llegado. La fila «más…» nunca se
  filtra: un nivel sólo tiene una página hasta que alguien pide el resto, y esconder la
  única forma de pedirlo convertiría el filtro en una mentira sobre 766 favoritos.

- El README explica cómo actualizar una instalación con `pipx upgrade`, incluido
  que el extra `art` se conserva y que justo después de publicar una versión pip
  puede responder «already at latest version» por su caché del índice.

### Cambiado

- **La carátula cambia de protocolo en vivo**, sin reiniciar. Era tolerable pedir un
  reinicio mientras esto era un detalle del display; dejó de serlo cuando la
  transparencia empezó a mover ese ajuste por su cuenta, porque quien la encendía se
  quedaba con el hueco de la carátula hasta el siguiente arranque de lo mismo que estaba
  configurando. `_reload_art()` baja la imagen vieja —una carátula de kitty la sostiene
  el terminal y sobrevive a las celdas donde se pintó hasta que algo la borra—, cambia
  el protocolo y vuelve a pedirla.
- **Una carátula que llega con una ventana abierta ya no se pinta encima de ella.** Pasa
  con cualquier cambio de pista hecho desde el navegador, no sólo al cambiar el
  protocolo: una imagen de píxeles se dibuja sobre el texto llegue cuando llegue. Ahora
  aterriza y se retira sola si hay un modal delante. Las de medios bloques se quedan.
- **Con la transparencia encendida, la carátula sólo ofrece `blocks` y `off`.** Las
  demás dejan de estar en la lista mientras dure, porque `kitty` y `sixel` pintarían la
  imagen sobre la ventana y `auto` promete justamente eso en un terminal que las sabe
  hacer. Al apagarla vuelven los cinco modos. El aviso sale sólo cuando el cambio quita
  una imagen de verdad: pasar de `auto` a `blocks` donde `auto` ya era `blocks` cambia
  la palabra de la fila y nada de la pantalla.
- **La transparencia es una opción, no una imposición.** Nueva fila
  «Transparencia» en la pantalla de `o` (`transparency` en el fichero,
  `TIDALAMP_TRANSPARENCY` en el entorno), apagada por defecto. Al encenderla, la
  carátula pasa automáticamente a `blocks` y la pantalla lo dice en vez de mover
  un ajuste a espaldas de nadie: kitty y sixel hacen que el terminal pinte la
  imagen por encima del texto, así que la ventana se abriría debajo de la
  carátula. El aviso enlaza la especificación del protocolo de kitty, que es
  donde está documentado ese orden de dibujo.
- **La pantalla de configuración va agrupada por temática**: Audio, Apariencia y
  General. Diez ajustes en una sola columna se leían como diez interruptores sin
  relación, con la calidad del stream pegada al color de los bordes. La lista se
  desplaza sola cuando el terminal es pequeño, así que las filas de abajo ya no
  quedan seleccionables e invisibles a la vez, que es lo que pasaba al añadir las
  cabeceras. La ventana crece con su propio texto en vez de quedarse en once
  filas en medio de una pantalla 4K.
- `winamp.tcss` pasa a llamarse `styles.tcss`. Aloja el layout entero y los
  cuatro estilos visuales, de los cuales «retro» es sólo uno; el nombre viejo
  describía una skin que hace tiempo dejó de ser todo lo que hay dentro.

- **Las ventanas superpuestas ocupan la pantalla que hay.** Eran 84x26 fijas, así que
  en 4K quedaban como un sello en medio de un campo vacío. Ahora la biblioteca, la
  letra y la ayuda toman el 85% del terminal (con un tope de 160 columnas, pasadas las
  cuales una línea de pista es casi todo hueco) y los diálogos —buscar, configuración,
  columnas, ecualizador, menú de la pista— crecen con él dentro de lo que pide su
  contenido. En el terminal mínimo de 60x18 siguen cabiendo.
- **El reproductor se ve detrás.** El fondo de los modales dejó de ser opaco: ahora es
  un velo translúcido, y el marco de cada ventana es de cristal esmerilado en vez de un
  bisel macizo. Un terminal no sabe desenfocar, así que el velo es lo que hace de
  desenfoque. La regla `Screen` del proyecto pisaba sin querer el 60% que Textual ya
  aplica a `ModalScreen`, y por eso hasta ahora el reproductor desaparecía del todo.
- **Con un modal abierto, el reproductor deja de repintarse.** Es lo que hace que lo
  anterior salga gratis: con la pantalla translúcida, cada fotograma del analizador
  repintaba el reproductor *y* volvía a mezclar el terminal entero, diez veces por
  segundo. Medido en 240x62 con la biblioteca abierta: **37,7% de un núcleo animándose
  contra 0,5% con el fondo quieto** —menos que el 8,8% que costaba antes de todo esto,
  cuando el modal era opaco. Lo que no es cosmético sigue corriendo detrás: fin de
  pista, salud de mpv, MPRIS y la línea de estado, que es donde informa un favorito
  añadido desde el navegador. La carátula dibujada con medios bloques ya no se retira
  al abrir un modal; la de kitty o sixel sigue haciéndolo porque el terminal la pinta
  por encima del texto y taparía la ventana.
- La línea de estado sólo se reescribe cuando cambia. Se refrescaba cuatro veces por
  segundo dijera lo que dijera, y `Static.update()` repinta igual.

### Corregido

- La barra de ayuda del navegador cabe en la ventana. Era un único literal de 97
  celdas dentro de un recuadro de 84, así que el terminal la cortaba a mitad de
  palabra y dejaba una «R» suelta contra el borde, con `R recargar` y `esc cerrar`
  perdidos. Ahora se arma por piezas y suelta entradas enteras, de la menos esencial
  a la más, hasta que la línea entra: se va antes `R recargar` que `esc cerrar`, y
  `f/F favorito` aguanta más que `A añadir todo` porque `A` se adivina desde `a` y
  los favoritos no se adivinan de ninguna parte.

## [0.1.1] - 2026-09-09

Versión de documentación y de primer contacto: lo que veía quien instalaba tidalamp
fuera de Arch estaba escrito para Arch. Ningún cambio en la reproducción.

### Añadido

- **Paleta `black`**: negro puro de fondo y todo lo demás en grises y blancos. Es la
  primera monocroma, así que declara más vocabulario que las otras: sin
  `dark_foreground`, el texto secundario —estado, listas vacías, etiquetas inactivas,
  las bandas apagadas del ecualizador— caía en el `foreground` de siempre, y una paleta
  sin color donde lo callado brilla igual que lo importante no tiene con qué decirlo.
  `red`, `yellow`, `green` y `blue` conservan su papel (error, aviso, pistas
  reproducibles, contenedores) y se vuelven cuatro grises, porque aquí el único eje es
  cuánta luz tiene cada cosa. Una prueba fija que ningún color de la paleta tiene tono.

- Cuando falta `mpv` o `cava`, el mensaje nombra la orden de instalación de la
  distribución que se está ejecutando, leída de `/etc/os-release`. Antes decía
  `pacman -S mpv` en todas partes, así que lo primero que veía quien lo instalaba
  en Debian o Fedora era una orden que su sistema no tiene. Las derivadas
  —Mint, Pop!_OS, Nobara— se resuelven por `ID_LIKE`, y una distribución que no
  se reconoce se queda sin sugerencia en vez de recibir una equivocada.

### Cambiado

- La descripción del proyecto deja de definirse por comparación con Winamp. El
  README, la descripción del paquete, la entrada de escritorio, el `PKGBUILD`, la
  ayuda de la CLI y la pantalla «Acerca de» hablan ahora de una interfaz retro de
  reproductor. Winamp sigue nombrado donde es un dato y no una etiqueta: el origen
  de las teclas del transporte, las diez bandas del ecualizador y el descargo de
  marcas.
- El README documenta los requisitos por distribución: la orden de `mpv` y de
  `cava` en apt, dnf, zypper y pacman, y que el suelo de Python 3.11 deja fuera
  Ubuntu 22.04 y Debian 11.
- El README se reescribe para quien usa el programa: un arranque rápido y la
  instalación al principio —estaban a mitad de página— y fuera unas cien líneas
  que justificaban decisiones de diseño ante un revisor de código.
- Las imágenes del README pasan a URL absolutas. Con rutas relativas no se veía
  ninguna en la página de PyPI, que es la primera impresión del proyecto.

### Corregido

- La página de PyPI de 0.1.0 describía la interfaz como «estilo Winamp». Una
  versión publicada es inmutable, así que la descripción corregida —y el README
  nuevo, y las imágenes— sólo podían llegar con esta versión.

## [0.1.0] - 2026-09-09

Primera versión pública de tidalamp, distribuida mediante PyPI y GitHub Releases. El
paquete del AUR está preparado, pero su publicación queda aplazada mientras siga
cerrado el registro público de cuentas nuevas por el endurecimiento de seguridad del
servicio. El procedimiento y el estado completo están en [`publish.md`](publish.md).

### Añadido

- **Paleta `black`**: negro puro de fondo y todo lo demás en grises y blancos. Es la
  primera monocroma, así que declara más vocabulario que las otras: sin
  `dark_foreground`, el texto secundario —estado, listas vacías, etiquetas inactivas,
  las bandas apagadas del ecualizador— caía en el `foreground` de siempre, y una paleta
  sin color donde lo callado brilla igual que lo importante no tiene con qué decirlo.
  `red`, `yellow`, `green` y `blue` conservan su papel (error, aviso, pistas
  reproducibles, contenedores) y se vuelven cuatro grises, porque aquí el único eje es
  cuánta luz tiene cada cosa. Una prueba fija que ningún color de la paleta tiene tono.

- `tidalamp` sin subcomando abre directamente el reproductor; `tidalamp tui` se
  conserva como forma explícita equivalente.
- Interfaz TUI retro de reproductor de escritorio: reloj de siete segmentos, marquesina,
  analizador de 19 bandas, barra de posición y sliders de volumen y balance.
- Play y pausa comparten un único botón y una única tecla (`x`), cuyo icono es la
  acción que hará al pulsarlo: `▶` parado o en pausa, `‖` sonando.
- El transporte ocupa cuatro teclas contiguas, en el orden de los botones:
  `z` anterior, `x` play/pausa, `c` parar, `v` siguiente. Los rótulos de los
  botones salen de los bindings efectivos, así que siguen a `config.toml`.
- El transporte se dibuja como botones de tres filas, en dos grupos: el transporte por
  un lado y shuffle/repetición por otro.
- La cola se dibuja en columnas cuando el terminal da para ello, en vez de meter el
  artista dentro del título. **Cuáles se ven se elige** desde la ventana de `o`, que
  abre un selector con las once que la API de TIDAL rellena: número de pista, versión,
  artista, álbum, año, calidad, explícito, popularidad, disco, ISRC y duración. El
  cambio se aplica a la cola que ya está en pantalla, no a la siguiente que cargues.
  Se van cayendo solas al estrecharse la ventana, en el orden en que se pueden perder,
  y al final queda `artista - título` en una línea con la duración a la derecha.
- **Cuatro estructuras visuales, elegibles con `theme`**, independientes del color:
  `quattro` (por defecto, plana y moderna), `retro` (barras de título dibujadas como
  una regla con el nombre centrado, teclas cuadradas pegadas y los conmutadores con las
  palabras `SHUFFLE` y `REPEAT`) y `nova` (sin marcos, un solo fondo, y una regla del
  acento bajo el conmutador encendido) y `ascii` (un terminal de antes del dibujo de
  cajas: botones `[ z << ]`, reglas de `=` y `-`, y ningún glifo en el cromado que no
  se pueda teclear). Se cambian desde la ventana de `o` sin parar la reproducción.
- **Paletas portables** además de seguir a Omarchy: `classic`, `tokyo-night`,
  `catppuccin`, `nord`, `gruvbox`, o un TOML propio en
  `~/.config/tidalamp/palettes/`, con el mismo formato que el `colors.toml` de
  Omarchy. Cualquier paleta funciona con cualquiera de las tres estructuras.
- La ventana de configuración avisa en su propia línea, y en el color de aviso, cuando
  el grafo de PipeWire está fijo en un ritmo y remuestrea todo: la insignia dice la
  verdad sobre el stream mientras el DAC recibe otra cosa, y no había nada en pantalla
  que lo delatara sin mover el cursor.
- **`v` (parar) rearrancaba la lista desde el principio**: dejaba mpv en idle y el
  tick lo leía como «la pista acabó», así que avanzaba a la siguiente — que desde
  una cola parada es la primera.
- Reproducción con `mpv` de larga vida por socket IPC, con reinicio automático si el
  proceso muere.
- Autenticación por *device flow* de TIDAL, sin registrar ninguna app, con refresco del
  token al arrancar y a media sesión.
- Cola con shuffle, repetición en tres modos, reordenado y persistencia entre sesiones.
  Ambos viven en la barra de transporte como botones `s ⇄` y `r ↻`, encendidos con
  el acento del tema; la barra separa transporte y ventanas con `·` y alinea las
  ventanas a la derecha.
- Navegador de la biblioteca: playlists, favoritos, álbumes y artistas, paginado y con
  caché de niveles en memoria.
- Búsqueda de pistas, álbumes, artistas y playlists.
- Menú de acciones al pulsar `↵` sobre una canción: reproducir ahora (`a`),
  reproducir a continuación (`c`), reproducir la radio que TIDAL genera para esa
  pista (`d`) y añadir a favoritos (`v`), cada uno con su icono.
- Favoritos de TIDAL con `f` y `F`.
- Servicio MPRIS2 completo, incluida la interfaz `TrackList`.
- Carátula en el terminal por protocolo de kitty, sixel o medios bloques, en un
  recuadro que crece con el terminal (de 18×9 a 40×20) junto con el analizador.
- Letras sincronizadas (LRC) con respaldo a texto plano.
- Ecualizador de diez bandas y balance, como filtros de mpv, con persistencia.
- Espectro real con `cava` cuando está instalado, y vúmetro RMS cuando no.
- Paleta tomada del tema Omarchy activo, con cambio en vivo.
- Fichero de configuración `config.toml` y teclas rebindables.
- Ventana de configuración (`o`) que escribe ese fichero: calidad, carátula,
  idioma y registro, avisando cuando una variable de entorno los pisa. Incluye
  el estado de la salida de audio, y activa los ritmos hi-res de PipeWire —sin
  los cuales un 24/96 llega al DAC remuestreado a 48 kHz— y su reinicio.
- El idioma pasa a ser un ajuste del fichero; antes sólo salía de `$LANG`.
- Entrada de escritorio e icono, y aviso cuando el terminal es más pequeño de 76×20.
- Empaquetado para el AUR y para PyPI, con publicación por *Trusted Publishing*.
- Interfaz y CLI bilingües español/inglés según el locale, con fallback al español.
- Ventana de ayuda (`?` o `h`) con todos los atajos agrupados y leídos de los
  bindings efectivos, así que una tecla rebindeada en `config.toml` aparece como
  la que hay que pulsar. Incluye «Acerca de» —versión, autor, repositorio y
  licencia— y el resumen de cambios de cada versión.
- README público en inglés.

### Corregido

- **El hi-res no sonaba.** La playlist HLS que genera `tidalapi` lista el segmento de
  inicialización como si fuera audio y no emite `#EXT-X-MAP`; además ffmpeg bloquea
  `https` desde una playlist local. Las dos cosas están resueltas.
- **La calidad por defecto no producía lossless nunca.** Pedir `LOSSLESS` al cliente del
  device flow devuelve `HIGH` siempre; el valor por defecto es `HI_RES_LOSSLESS`.
- **Una página corta de TIDAL no es el final de la lista.** La biblioteca dejaba fuera
  676 de 766 pistas favoritas.
- **«Mis playlists» tardaba 20 segundos** con 110 playlists, porque `tidalapi` pedía
  cada una por separado. Ahora tarda 0,4 s.
- **La app no arrancaba con un access token caducado**, que es el caso normal al abrirla
  al día siguiente.
- **La barra de estado quedaba fuera de la pantalla**, así que todo lo que la aplicación
  tenía que decir se escribía donde nadie lo veía.
- La insignia mostraba «16bit» sobre audio con pérdida.
- **La barra de volumen se rompía por encima de 100.** El relleno no estaba
  acotado al ancho de la pista, así que a 105 el número se corría, a 115 salía
  del widget y a 130 la línea era tan larga que no se dibujaba nada: quedaba
  «VOL» y una fila vacía. El widget ya no deja que ningún valor le deforme la
  pista, y el volumen tiene tope en 100 —por encima mpv aplica ganancia digital
  sobre una señal ya normalizada, que satura—, tanto por teclado como por MPRIS.
- **Sin Pillow no había carátula y no se decía por qué**: el widget se quedaba
  oculto y el único rastro era un `log.info` en un fichero. Ahora la barra de
  estado nombra el extra que lo arregla al arrancar, y las instrucciones de
  instalación desde el repositorio incluyen `".[art]"`, que era donde faltaba.
- **Los corchetes desaparecían del texto que no escribimos nosotros.**
  `Static.update` interpreta un `str` como marcado de Rich: un álbum llamado
  «Lateralus [Deluxe Edition]» se dibujaba como «Lateralus », y un nombre con
  una etiqueta de cierre (`[/]`) lanzaba `MarkupError` en pleno render. Los
  cuatro `Static` que reciben nombres de TIDAL, títulos de pista o mensajes de
  excepción se construyen ahora con `markup=False`.
