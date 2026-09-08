# Registro de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el
versionado es [semántico](https://semver.org/lang/es/).

## [Sin publicar]

Todavía no hay ninguna versión publicada en PyPI ni en el AUR. Cuando la haya, esta
sección se cierra con su número y su fecha; el procedimiento completo está en
[`publish.md`](publish.md).

### Añadido

- Interfaz TUI con la estética de Winamp 2.x: reloj de siete segmentos, marquesina,
  analizador de 19 bandas, barra de posición y sliders de volumen y balance.
- Reproducción con `mpv` de larga vida por socket IPC, con reinicio automático si el
  proceso muere.
- Autenticación por *device flow* de TIDAL, sin registrar ninguna app, con refresco del
  token al arrancar y a media sesión.
- Cola con shuffle, repetición en tres modos, reordenado y persistencia entre sesiones.
- Navegador de la biblioteca: playlists, favoritos, álbumes y artistas, paginado y con
  caché de niveles en memoria.
- Búsqueda de pistas, álbumes, artistas y playlists.
- Favoritos de TIDAL con `f` y `F`.
- Servicio MPRIS2 completo, incluida la interfaz `TrackList`.
- Carátula en el terminal por protocolo de kitty, sixel o medios bloques.
- Letras sincronizadas (LRC) con respaldo a texto plano.
- Ecualizador de diez bandas y balance, como filtros de mpv, con persistencia.
- Espectro real con `cava` cuando está instalado, y vúmetro RMS cuando no.
- Paleta tomada del tema Omarchy activo, con cambio en vivo.
- Fichero de configuración `config.toml` y teclas rebindables.
- Entrada de escritorio e icono, y aviso cuando el terminal es más pequeño de 76×20.
- Empaquetado para el AUR y para PyPI, con publicación por *Trusted Publishing*.
- Interfaz y CLI bilingües español/inglés según el locale, con fallback al español.
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
