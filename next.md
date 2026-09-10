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

## 1. `C` vacía la cola sin red de seguridad

`action_clear` llama a `action_stop()` y a `queue.clear()`, y ahí acaba: ni pregunta ni
se puede deshacer.

**Por qué importa ahora.** `c` es detener y `C` es vaciar. Un resbalón con la tecla
shift borra una cola que puede haber costado media hora de armar. Y desde la 0.4.0 duele
más, porque una cola vale más: se puede guardar en TIDAL con `p`, pero sólo si te
acordaste **antes** de pulsar `C`.

**Deshacer, no confirmar.** Una confirmación molesta las cien veces que sí querías
vaciar y sólo sirve la que no. Deshacer no cuesta nada las veces que no hace falta.

**Cómo se comporta.**

- `C` sigue vaciando de inmediato, sin diálogo.
- La cola vaciada se guarda en memoria: las entradas, el orden y dónde estaba el cursor.
- Una tecla la restaura, y lo dice en la línea de estado con cuántas pistas volvieron.
- **No reanuda la reproducción.** Vaciar detuvo, y deshacer devuelve la lista, no el
  sonido: arrancar solo una canción que el usuario paró sería peor que el fallo.
- Sin nada que deshacer, lo dice y no toca la cola.
- **Un solo nivel.** Dos serían un historial que nadie ha pedido.

**Trampas.**

- `_sync_queue` guarda `queue.json` en cuanto se vacía, así que el fichero ya está
  sobrescrito cuando se pulsa deshacer: lo que se restaura vive en memoria y sólo en
  memoria. Cerrar la app entre medias pierde la cola, y eso está bien: deshacer es para
  el resbalón de hace dos segundos, no para ayer.
- Un segundo `C` reemplaza lo que deshacer tiene guardado. Es lo esperable, pero hay que
  escribirlo o alguien lo tratará como una pila.
- Restaurar debe devolver el cursor donde estaba, no a la fila uno. Es la misma razón
  por la que el filtro de la cola lo conserva.

**Tecla.** `u`, libre, y la convención de deshacer. Rebindeable como `undo_clear`.

**Qué toca.** `app.py` y `queue.py`, más `about.py`, `i18n.py` y la tabla del README.

**Cómo se comprueba.** En la app real: vaciar y deshacer devuelve el orden y el cursor;
deshacer sin nada previo lo dice y no rompe; un segundo vaciado reemplaza lo guardado;
y deshacer no vuelve a poner música sonando.

---

## 2. Presets del ecualizador

El ecualizador ya está: diez bandas, ganancias persistidas en `settings.json` y
aplicadas mientras se mueven. Falta lo que Winamp sí tenía, que es una lista de
conjuntos con nombre.

**Cómo se comporta.**

- Un puñado de presets, no los treinta del original: plano, rock, pop, jazz, clásica,
  voz, graves y agudos. Ocho caben en la ventana y cubren lo que se usa.
- Una tecla los recorre dentro de la ventana del ecualizador, y el nombre del que está
  puesto se ve.
- Se aplican en vivo, como ya se aplica mover una banda: un ecualizador que no se oye
  hasta pulsar «OK» no sirve, y esa decisión ya está tomada.

**Trampas.**

- Tocar una banda después de aplicar un preset lo deja de ser. Hace falta un estado
  «manual» que sostenga las ganancias editadas, o recorrer los presets pisará en
  silencio un ajuste hecho a mano y no habrá forma de volver.
- Los presets son **datos**, y van en `settings.py`, que no importa Textual y por tanto
  se prueba sin levantar una app. El mismo motivo por el que las notas de versión están
  en `about.py`.
- Las ganancias siguen topadas en ±12 dB; un preset que se pase se recorta al aplicarse
  y no al escribirse, para que el catálogo se lea como lo que es.

**Qué toca.** `settings.py` para el catálogo y el estado manual, `screens.py` para la
ventana, y `i18n.py` para los nombres.

**Cómo se comprueba.** Sin app: aplicar un preset deja exactamente sus ganancias,
recorrer da la vuelta al final, uno que se pase queda recortado, y editar una banda
después marca el estado manual sin perder lo editado.

---

## 3. Añadir a una playlist de TIDAL que ya existe

La 0.4.0 sabe crear una playlist desde la cola. No sabe añadir a una que ya tienes, que
es lo que se quiere la mayoría de las veces.

**Lo que ya está hecho y se reusa.** El troceado en lotes de 100, conservar lo que sí
entró cuando falla un lote a mitad, contar cuántas llegaron y olvidar la caché del nivel.
Todo eso vive en `save_queue_playlist` y no hay que reescribirlo.

**Va en el menú de la pista**, junto a «reproducir ahora», «a continuación», la radio y
favoritos. Es el sitio donde ya se pregunta qué hacer con una canción, y desde la 0.4.0
ese menú se abre en los dos lados: con ↵ en la biblioteca y con `m` en la cola.

**Lo nuevo es elegir el destino**, que es una lista que el navegador ya sabe pintar.

**Trampas.**

- **La biblioteca lista también playlists que sigues, no sólo las tuyas.** Escribir en
  una ajena devuelve un 403. Hay que filtrar por propietario antes de enseñar la lista,
  no después de que TIDAL diga que no.
- Hay que olvidar la caché **del nivel de esa playlist**, no sólo la de «Mis
  playlists». Si no, abrirla después de añadir la enseña como estaba.
- TIDAL acepta duplicados. Añadir la misma cola dos veces mete todo dos veces, y eso es
  lo que el usuario pidió: no hay que ponerse a deduplicar por su cuenta.

**Qué toca.** `library.py` para la escritura y el filtro de propietario, `screens.py`
para el selector, `app.py` para la acción.

**Cómo se comprueba.** Con un doble de sesión: que sólo se ofrezcan las playlists
propias, que se manden todos los ids en lotes, que un fallo a mitad diga cuántas
entraron, y que la caché olvidada sea la del destino y no sólo la del listado.

---

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
