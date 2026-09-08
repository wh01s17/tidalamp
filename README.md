# tidalamp

Un cliente de TIDAL para terminal con la estética de Winamp 2.x. Sin registrar apps
en la API oficial y sin navegador de por medio: device flow + mpv.

```
 ░▒▓ TIDAL AMP ▓▒░
   _   _       _   _      3. Burial - Archangel (3:51)
  | | | |  .  | |  _|     16bit  44kHz  LOSSLESS
  |_| |_|  .  |_| |_
                          ▁ ▄ ▅     ▄ ▁ ▁ ▁   ▁
                          ▇ █ █ ▆ ▅ █ █ ▃ █ ▃ ▆ ▁ ▅ ▂ ▆ ▄ ▁ ▂ ▂
 ──────────────▓───────────────────────────────────────────────
 VOL █████████████████████████████████ 100
  z ◀◀   x ▶   c ‖   v ■   b ▶▶      / buscar   t tiempo   q salir
```

## Cómo funciona

Tres capas independientes:

| Capa | Qué hace | Módulo |
|---|---|---|
| Auth | Device flow de TIDAL, sin registrar ninguna app | `auth.py` |
| Stream | Resuelve una pista a algo que mpv pueda abrir | `stream.py` |
| Playback | Un `mpv --idle` de larga vida controlado por socket IPC | `player.py` |
| UI | TUI en Textual con la estética de Winamp | `app.py`, `widgets.py` |
| MPRIS | Servicio D-Bus para el resto del escritorio | `mpris.py` |

**Autenticación**: no usa la API oficial de `developer.tidal.com` (que exige registrar
una app y ni siquiera entrega URLs de stream). Usa el mismo *device authorization
flow* que los clientes oficiales de TV/escritorio, vía `tidalapi`. Abres un enlace una
vez, autorizas, y la sesión refrescable queda en `~/.config/tidalamp/session.json`.

**Streaming**: TIDAL devuelve dos formas de manifiesto. `BTS` es una lista de URLs
progresivas que mpv abre directamente. `MPD` es DASH segmentado (típico en
LOSSLESS / HI_RES); `tidalapi` ya parsea los segmentos, así que los volcamos como una
playlist HLS local y le pasamos ese fichero a mpv.

## Integración con el escritorio (MPRIS)

Al arrancar, `tidalamp` publica `org.mpris.MediaPlayer2.tidalamp` en el bus de sesión.
Eso lo hace visible para todo lo que hable MPRIS, sin configuración adicional:

```sh
playerctl -p tidalamp play-pause
playerctl -p tidalamp metadata
```

Con ello funcionan las teclas multimedia de Hyprland, el módulo `mpris` de Waybar
(que además muestra la carátula, porque exportamos `mpris:artUrl`), y cualquier widget
externo — un frontend en Quickshell lo consume con `Quickshell.Services.Mpris` sin
necesidad de IPC propio.

Se exportan `PlaybackStatus`, `Metadata`, `Position`, `Volume` y las capacidades, y se
emite `PropertiesChanged` sólo cuando algo cambia de verdad. Si no hay bus de sesión,
la aplicación arranca igual y lo indica en la barra de estado.

Nota: lanzamos mpv con `--load-scripts=no` a propósito. Si tienes `mpv-mpris` instalado
en el sistema, sin esa opción mpv publicaría un segundo reproductor duplicado en el bus.

## Limitación importante: DRM

Las pistas cuyo manifiesto viene cifrado (Widevine) **no se pueden reproducir con
mpv** — no hay CDM que las descifre. El cliente lo detecta y te lo dice en la barra de
estado en vez de fallar con un error de códec. Si te topas con muchas, baja la calidad:

```sh
TIDALAMP_QUALITY=HIGH tidalamp tui
```

Los valores válidos son `LOW`, `HIGH`, `LOSSLESS` y `HI_RES_LOSSLESS`.

## Instalación

Requiere `mpv` y Python 3.11+.

```sh
python -m venv .venv && .venv/bin/pip install -e .
.venv/bin/tidalamp login
.venv/bin/tidalamp tui
```

## Teclas

Son las de Winamp, a propósito.

| Tecla | Acción |
|---|---|
| `z` `x` `c` `v` `b` | anterior / play / pausa / stop / siguiente |
| `/` | buscar en TIDAL |
| `↑` `↓` `Enter` | navegar y reproducir |
| `←` `→` | ±5 segundos |
| `+` `-` | volumen |
| `t` | alternar tiempo transcurrido / restante |
| `q` | salir |

## Sobre el analizador

mpv expone niveles RMS por el filtro `astats`, no un espectro. El analizador es por
tanto un vúmetro repartido en bandas con balística de ataque rápido y caída lenta:
reacciona de verdad a la música, pero no es una FFT real. Para un espectro auténtico
habría que enchufar `cava` a la salida de PipeWire y leer su stdout.
