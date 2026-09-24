# windows.md — compatibilidad con Windows en el repo principal

Documento de traspaso para quien ejecute el trabajo: qué ata hoy el proyecto a Linux,
cómo desatarlo **sin tocar el comportamiento en Linux**, en qué orden, y cómo se
comprueba cada paso. Está escrito para poder ejecutarse sin haber leído el hilo en el
que se decidió, y en español porque lo lee el mantenedor (ver `CONTRIBUTING.md`,
«Documentation»).

**Punto de partida:** `tidalamp` v0.15.0 (`02dc6ea`). Ni una línea de Windows todavía.

**Estado (2026-09-24):** publicada la **0.17.0**, en vista previa:
`pipx install "tidalamp[art]"` desde PyPI, o el zip con `tidalamp.exe` en
<https://github.com/wh01s17/tidalamp/releases/tag/v0.17.0>. Las siete fases están
escritas. La suite pasa en
`windows-latest` (3.11 y 3.14) y el `.exe` se construye y pasa su prueba de humo en
CI. **La primera prueba en una máquina real** (Windows 10, Windows Terminal 1.24, con
el zip de la 0.16.0 y desde el checkout) reprodujo música por el named pipe, y lo que
salió mal se arregló en la 0.17.0: trampas 20 a 24 y §10.2. El resto de §12 sigue
abierto —SMTC, modo exclusivo, conhost— y sus casillas sin marcar. Quien lo haga y quiera arreglar algo desde Windows tiene el entorno en
`CONTRIBUTING.md` («Setting up», «Windows») y, en §12, qué fichero mirar para cada
fallo. El estado fase a fase está en §15.

**Qué sustituye:** el fork `wh01s17/tidalamp-win` (copia de la v0.13.0 con un plan de
migración propio). Buena parte de este documento reutiliza su plan, pero su premisa —un
fork duro— se descartó; §1 explica por qué. **El fork ya no existe**: el mantenedor lo
borró de GitHub y del disco el 2026-09-23. Lo que tenía de útil está aquí.

---

## Índice

0. [Resumen](#0-resumen)
1. [La decisión: un solo repo](#1-la-decisión-un-solo-repo)
2. [Reglas de trabajo](#2-reglas-de-trabajo)
3. [Skills de referencia](#3-skills-de-referencia)
4. [Inventario: qué ata el proyecto a Linux](#4-inventario-qué-ata-el-proyecto-a-linux)
5. [Arquitectura: backends y fachadas](#5-arquitectura-backends-y-fachadas)
6. [Fases](#6-fases)
7. [Cambios fichero a fichero](#7-cambios-fichero-a-fichero)
8. [La suite de tests](#8-la-suite-de-tests)
9. [CI](#9-ci)
10. [Empaquetado y el `.exe`](#10-empaquetado-y-el-exe)
11. [Documentación y skills que hay que actualizar](#11-documentación-y-skills-que-hay-que-actualizar)
12. [Probar en Windows, paso a paso](#12-probar-en-windows-paso-a-paso)
13. [Trampas conocidas](#13-trampas-conocidas)
14. [Qué hacer con `tidalamp-win`](#14-qué-hacer-con-tidalamp-win)
15. [Estado](#15-estado)

---

## 0. Resumen

- De las ~17 000 líneas de `tidalamp/`, el código atado a Linux son seis módulos
  (`player.py`, `mpris.py`, `audio.py`, `desktop.py`, `spectrum.py`, `distro.py`, unas
  1 580 líneas) más ajustes puntuales en `config.py`, `auth.py`, `i18n.py`,
  `artwork.py`, `stream.py` y `cli.py`. Todo lo demás (Textual, tidalapi, cola,
  biblioteca, pantallas, catálogo de idiomas, las fuentes libres nuevas) ya es
  multiplataforma.
- La plataforma se elige **en un solo sitio por módulo** (una fachada), nunca con
  `if sys.platform` repartidos por `app.py` o las pantallas.
- El transporte IPC de mpv (socket Unix contra named pipe) se aísla detrás de una
  interfaz pequeña dentro de `player.py`. Es el cambio con más riesgo y el primero que
  desbloquea todo lo demás.
- MPRIS pasa a ser «integración de medios del sistema»: D-Bus en Linux y SMTC
  (System Media Transport Controls) en Windows, detrás de la misma API.
- CI con matriz `ubuntu-latest` + `windows-latest`. El `.exe` lo genera `release.yml`
  con PyInstaller al publicar un tag y lo sube al GitHub Release, junto al wheel de
  PyPI que ya existe.
- Condición que no se negocia: **la suite de Linux actual pasa sin cambios de
  comportamiento en cada PR**. Si un paso obliga a cambiar lo que hace la app en Linux,
  ese paso está mal planteado.

---

## 1. La decisión: un solo repo

Se valoró mantener `tidalamp-win` como fork aparte. Se descarta por lo que el propio fork
ya ha demostrado:

1. **Se desfasó antes de empezar.** Se copió de la v0.13.0 y, sin una sola línea
   migrada, upstream ya lleva 20 commits más, cinco módulos nuevos (`archive.py`,
   `freemusic.py`, `jamendo.py`, `music.py`, `screens/credits.py`) y más de veinte
   ficheros «que no había que tocar» ya difieren. Cada arreglo en `library.py` o en
   `screens/` habría que portarlo con cherry-pick, para siempre.
2. **El código específico es poco y está concentrado.** Un 9 % del paquete. Mantener
   dos repos, dos changelogs, dos PyPI y dos CI para eso es desproporcionado.
3. **La regla de oro del fork funciona aún mejor en un solo repo.** «Cambiar el cuerpo,
   no el contrato» (mismos nombres de clase y firmas públicas) es exactamente lo que
   hace falta para que una fachada elija el backend sin que `app.py` se entere. En el
   fork servía para que los diffs aplicaran; aquí sirve para que no haga falta aplicarlos.

Cuándo volvería a tener sentido un fork: si Windows necesitara otra UI, otro reproductor
o un ciclo de releases independiente. Nada de eso está planteado.

---

## 2. Reglas de trabajo

Son las reglas que resuelven los casos dudosos. Cada una sale de una skill del repo
(§3) o de cómo ya está escrito el proyecto.

1. **Linux no cambia.** Mismas rutas XDG, mismos argumentos de mpv, mismos mensajes,
   misma política de lanzador, mismos tests. Un usuario de Linux que actualiza no puede
   notar nada. Los refactors de extracción (mover código a un backend, sacar el
   transporte de `Mpv`) van en **commits propios, sin cambios de lógica**, para que la
   revisión sea «¿es idéntico?» y no «¿qué cambió?».
2. **La plataforma se decide en un solo sitio.** Una fachada por módulo (§5). Fuera de
   las fachadas y de los backends no debería aparecer `sys.platform` salvo en casos
   justificados en el propio fuente (hoy: `artwork.py`, `i18n.py`, `config.py`).
3. **Se comprueba `sys.platform` literal, no una constante propia.** mypy solo entiende
   `sys.platform == "win32"` y `sys.platform.startswith("linux")` para descartar ramas.
   Un `IS_WINDOWS = ...` global rompe esa detección y mypy comprobará en Linux código
   que usa `winreg` o `_winapi` (y fallará) o lo dará por inalcanzable sin revisarlo.
4. **Contratos explícitos.** Lo que un backend promete se escribe como `Protocol` o, para
   módulos de funciones, como un test de paridad que compara nombres y firmas (§8.3).
   *Explicit is better than implicit* (skill `python-patterns`).
5. **Degradar, no romper.** Lo que no existe en Windows (cava, Omarchy, forzar la tasa
   del grafo de PipeWire) devuelve el valor neutro que el llamante ya sabe tratar
   (`""`, `None`, `False`, tupla vacía) y lo dice en el docstring. El proyecto ya está
   escrito así: la falta de cava, de carátula o de bus de sesión no para la música.
6. **Las dependencias nativas son opcionales o van con marcador.** Nada de Windows se
   instala en Linux y al revés (`; sys_platform == "win32"`). El job `bare` de CI existe
   para esto (§9).
7. **Los tests no tocan hardware, red, TIDAL ni el escritorio del desarrollador.** Igual
   que hoy: dobles para mpv, para cava y un bus privado para MPRIS. En Windows lo mismo:
   un named pipe falso en lugar de un mpv real.
8. **Cada decisión de arquitectura va a `plan.md` con su porqué**, cada trampa en su §7,
   y `CHANGELOG.md` se actualiza en el mismo commit que el cambio (`CONTRIBUTING.md`).

---

## 3. Skills de referencia

Las skills de `.agents/skills/` son la guía de estilo de este trabajo. Qué aporta cada
una y dónde se aplica:

| Skill | Qué exige | Dónde se aplica aquí |
|---|---|---|
| `tidalamp-mpv-ipc` | Casar respuestas por `request_id`; fallo de socket, timeout y proceso muerto son un estado degradado **explícito**; `restart()` limpia socket y búfer; tests con un mpv falso que cubra eventos intercalados, líneas partidas, timeouts, EOF y proceso muerto | §7.1 (`player.py`), §8.2 (`fake_mpv.py`) |
| `tidalamp-mpris-contract` | Adaptador pequeño y testeable sin escritorio; conversión de unidades en la frontera; emitir solo lo que cambió; fallos del bus nunca fatales para el TUI | §7.2 (MPRIS/SMTC) |
| `tidalamp-textual-workflows` | Trabajo bloqueante en *workers*; volver al hilo de la UI solo por los mecanismos seguros de Textual; dobles en las fronteras | §7.2 (callbacks de SMTC), §7.3 (bucle de tasa de audio) |
| `tidalamp-tidalapi-resilience` | Resolución de streams fuera del bucle de eventos; limpieza que no rompa | §7.10 (`stream.py`) |
| `python-patterns` | `Protocol` para duck typing; EAFP; explícito antes que implícito; type hints modernos; organización de paquete con `__init__` que exporta; gestores de contexto para recursos | §5 (fachadas y `Protocol`), §7.1 (transporte), en todo el código nuevo |
| `python-testing-patterns` | Patrón AAA; un comportamiento por test; nombres `test_<unidad>_<escenario>_<resultado>`; fixtures para montar/desmontar; `parametrize`; `mock`/`monkeypatch` en las fronteras; *markers* para clasificar | §8 entero |

Dos de esas skills (`tidalamp-mpv-ipc`, `tidalamp-mpris-contract`) describen hoy solo la
arquitectura Linux. Hay que actualizarlas en la misma fase que el código (§11): un agente
las lee y se las cree.

---

## 4. Inventario: qué ata el proyecto a Linux

Estado a la v0.15.0.

| Dependencia del sistema | Dónde | En Windows | Fase |
|---|---|---|---|
| socket Unix (`AF_UNIX`) para el IPC de mpv | `player.py`, `config.IPC_SOCKET`, `tests/fake_mpv.py` | No existe. Named pipe `\\.\pipe\...` | F1 |
| Localizar y lanzar `mpv` | `player.py` (`shutil.which("mpv")`, `Popen(["mpv", ...])`) | Existe, pero rara vez en el `PATH`; `mpv.com` frente a `mpv.exe`; ventana de consola | F1 |
| XDG Base Directories | `config.py` (`_xdg`), usado por `audio.py`, `desktop.py`, `theme.py` | `%APPDATA%` / `%LOCALAPPDATA%` | F1 |
| `os.replace` sobre un fichero abierto | `config.write_atomically` | Falla con `PermissionError` | F1 |
| D-Bus + MPRIS (`dbus-fast`) | `mpris.py`, `app.py` (`_start_mpris`) | No existe. SMTC | F1 (neutro), F5 (SMTC) |
| `/etc/os-release` | `distro.py` | No existe. winget / scoop / choco | F1 |
| `locale.LC_MESSAGES` | `i18n._language` | No existe; hoy cae **en silencio** a español | F1 |
| fd de `mkstemp` sin cerrar | `stream.py:144` | En Windows impide borrar el `.m3u8` | F1 |
| PipeWire / PulseAudio (`pactl`, `systemctl --user`, `/proc/asound`) | `audio.py`, `app.py` (bucle de tasa), `screens/config_window.py` | No existe. WASAPI vía mpv | F4 |
| `chmod 0600/0700` | `auth.py`, `config.py` | Casi no-op; la protección la da la ACL heredada | F4 |
| freedesktop `.desktop`, `XDG_DATA_DIRS`, Omarchy | `desktop.py` | Acceso directo `.lnk` en el menú Inicio | F4 |
| `cava` | `spectrum.py` | Hay build de Windows desde cava 0.10 (entrada `winscap`); **hay que comprobar** el modo raw | F3 |
| Detección de terminal por `$TERM` / kitty | `artwork.py` | `$TERM` no suele existir; Windows Terminal soporta sixel desde 1.22 | F3 |
| Paleta de Omarchy | `theme.py` | El fichero no existe y ya se cae a la paleta por defecto; solo hay que ocultar la opción | F3 |
| Codificación de la consola | `cli.py` | Con salida redirigida, página de códigos ANSI | F1 |
| AUR | `packaging/aur/` | No aplica; se queda para Linux | — |

Módulos que **no** hay que tocar: `library.py`, `queue.py`, `net.py`, `lyrics.py`,
`analyzer.py`, `settings.py`, `widgets.py`, `layouts.py`, `scrolling.py`, `columns.py`,
`about.py`, `archive.py`, `music.py`, `freemusic.py`, `jamendo.py` y todo `screens/`
salvo `config_window.py`. Se ha comprobado con grep que ninguno usa sockets, `chmod`,
`/proc`, `/etc`, XDG, señales ni subprocesos.

---

## 5. Arquitectura: backends y fachadas

### 5.1 Estructura

```
tidalamp/
  audio.py          ← fachada (antes: implementación PipeWire)
  mpris.py          ← fachada (antes: implementación D-Bus)
  desktop.py        ← fachada
  distro.py         ← fachada
  spectrum.py       ← se queda como está, parametrizado (§7.8)
  player.py         ← se queda; el transporte se inyecta (§7.1)
  backends/
    __init__.py     ← vacío, o solo un docstring que explica el esquema
    linux/
      __init__.py
      audio.py      ← git mv de tidalamp/audio.py, sin cambios
      mpris.py      ← git mv de tidalamp/mpris.py, sin cambios
      desktop.py    ← git mv
      distro.py     ← git mv
    windows/
      __init__.py
      audio.py      ← nuevo: WASAPI vía mpv
      media.py      ← nuevo: SMTC (misma API que linux/mpris.py)
      desktop.py    ← nuevo: acceso directo .lnk
      distro.py     ← nuevo: winget / scoop / choco
      pipe.py       ← nuevo: transporte de named pipe para player.py
```

¿Por qué `backends/` y no `platform/`? `platform` es un módulo de la stdlib. Con imports
relativos no hay colisión real, pero `from .platform import ...` al lado de
`import platform` confunde a quien lee, y ahorrarse esa duda es gratis.

¿Por qué no se mueve `player.py`? Porque lo específico de plataforma no es el
reproductor, es cómo llega el byte al proceso. El 95 % de `Mpv` (protocolo JSON,
`request_id`, detección de cuelgue, `restart()`, propiedades) es común. Duplicarlo en dos
backends sería duplicar la parte más delicada del proyecto.

### 5.2 La fachada

Cada fachada elige el backend con un `if sys.platform` **literal** (regla 3) y reexporta
explícitamente lo que forma la API pública. Nada de `import *`: la lista explícita es
el contrato que ven `app.py` y las pantallas, y la herramienta que lo comprueba.

```python
"""Audio output: which device mpv plays to and at what rate.

The implementation depends on the audio stack: PipeWire/PulseAudio on Linux,
WASAPI (through mpv) on Windows. Both expose the same names; see
tests/test_backend_parity.py.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .backends.windows.audio import (
        MANAGES_RATES,
        Sink,
        allowed_rates,
        clamped,
        force_rate,
        hardware_rates,
        rate_to_force,
        rates_configured,
        remove_rates,
        restart,
        sink,
        streams_on,
        write_rates,
    )
else:
    from .backends.linux.audio import (
        MANAGES_RATES,
        Sink,
        ...
    )

__all__ = ["MANAGES_RATES", "Sink", "allowed_rates", ...]
```

Consecuencias que hay que asumir:

- **Los tests que hacen `monkeypatch` sobre funciones privadas** (p. ej.
  `audio._run`) pasan a importar el backend concreto:
  `from tidalamp.backends.linux import audio`. Parchear la fachada no afecta al código
  del backend, porque la fachada solo tiene copias de las referencias.
- **`git blame`** sigue la historia a través del `git mv` con `git log --follow` y
  `git blame -C`. El commit del movimiento no debe contener ni una línea cambiada: así
  la detección de renombrado de git es exacta.

### 5.3 Contratos con `Protocol`

Donde el contrato es una clase, se escribe como `Protocol` (skill `python-patterns`,
«Protocol-Based Duck Typing»). Ya hay un precedente: `mpris.PlayerBackend` documenta qué
lee el adaptador de la app. Se mueve a un sitio neutro (`tidalamp/media.py` o se queda
en la fachada `mpris.py`) porque lo van a usar los dos backends:

```python
class MediaService(Protocol):
    """What the app needs from the desktop's media integration."""

    async def start(self) -> str: ...
    async def stop(self) -> None: ...
    def publish(self) -> None: ...
    def publish_tracks(self) -> None: ...
    def seeked(self, position: float) -> None: ...
```

Y el transporte de mpv (§7.1):

```python
class Transport(Protocol):
    """One connection to mpv's JSON IPC. Semantics mirror a blocking socket."""

    address: str

    def prepare(self) -> None:
        """Before spawning mpv: remove leftovers, check limits."""

    def connect(self, timeout: float) -> None:
        """Wait until mpv accepts; MpvNotFound if it never does."""

    def recv(self, timeout: float) -> bytes:
        """Up to 64 KiB. TimeoutError if nothing arrived, b"" on EOF,
        OSError if the connection is broken."""

    def sendall(self, data: bytes) -> None: ...

    def close(self) -> None:
        """Idempotent. Also removes whatever `prepare` would clean up."""
```

La semántica de `recv` es **la de `socket.recv`** a propósito: así `Mpv._readline` no
cambia de lógica, solo de objeto, y la distinción `_TIMED_OUT` / `None` que sostiene la
recuperación de un mpv colgado queda exactamente donde está (§13, trampa 1).

### 5.4 mypy en dos plataformas

`[tool.mypy]` no fija `platform`. CI corre mypy dos veces:

```sh
mypy --platform linux
mypy --platform win32
```

Cada pasada descarta las ramas del otro sistema y comprueba las suyas. Sin la segunda,
el código de Windows no se revisa nunca en un runner Linux. El override que hoy excluye
`tidalamp.mpris` pasa a apuntar a `tidalamp.backends.linux.mpris` (las anotaciones de
`dbus-fast` son firmas D-Bus, no tipos Python; `CONTRIBUTING.md` lo explica).

---

## 6. Fases

Cada fase es uno o varios PR que dejan `main` publicable. No se pasa a la siguiente sin
cumplir el criterio de hecho. El orden importa: F0 y F1 hacen que la app arranque, F2
hace que la suite diga la verdad, y sin eso lo demás se hace a ciegas.

| Fase | Qué entrega | Criterio de hecho |
|---|---|---|
| **F0** | Refactors sin cambio de comportamiento: `backends/linux/`, fachadas, transporte extraído, comando de mpv inyectable | Suite de Linux verde **sin tocar un solo assert**; `mypy --platform linux` limpio |
| **F1** | Arranque en Windows: rutas, named pipe, lanzamiento de mpv, MPRIS neutro, `distro`, idioma, `mkstemp`, consola | `tidalamp tui` abre en Windows y reproduce una pista; matar `mpv.exe` hace que la app lo relance |
| **F2** | Suite en Windows y CI con matriz | `pytest -q` verde en `windows-latest`; `mypy --platform win32` limpio |
| **F3** | Terminal: carátulas, sextantes, espectro, paleta | Portada visible en Windows Terminal y en conhost; el visualizador degrada sin error |
| **F4** | Audio WASAPI, permisos de sesión, lanzador `.lnk` | 24/96 bit-perfect con `exclusive`; acceso directo ofrecido una vez |
| **F5** | SMTC (teclas multimedia, panel de Windows) | Título/artista visibles en el panel; play/pause/siguiente desde el teclado |
| **F6** | `.exe` en el release | Un tag genera `tidalamp-<versión>-windows-x64.zip` en el GitHub Release |
| **F7** | Documentación, skills, capturas | README, CONTRIBUTING, plan.md, CHANGELOG y skills coherentes |

F5 va después de F4 a propósito: SMTC es la pieza con más incertidumbre técnica y la
que menos bloquea. Una versión que reproduce bien sin teclas multimedia es publicable;
lo contrario no.

---

## 7. Cambios fichero a fichero

### 7.1 `player.py` — el transporte IPC · F0 + F1

**Hoy:** `Mpv` lanza un `mpv --idle` de larga vida y le habla JSON por un socket Unix
(`socket.AF_UNIX`), que no existe en Windows. mpv en Windows expone **el mismo
protocolo** sobre un named pipe: `--input-ipc-server=\\.\pipe\<nombre>`.

**F0 — extraer, sin cambiar nada:**

1. Crear `_UnixSocket` (en `player.py`, no hace falta módulo propio) que implemente el
   `Transport` de §5.3 con el código que hay hoy:
   - `prepare()`: la comprobación de `SOCKET_PATH_MAX` (que lanza `MpvNotFound` con el
     mensaje traducido actual) y `IPC_SOCKET.unlink(missing_ok=True)`.
   - `connect()`: el bucle actual de `_connect` (espera a que exista el fichero, conecta,
     `settimeout`).
   - `recv()`: `settimeout(timeout)` + `recv(65536)`.
   - `close()`: cierra y hace `unlink`.
2. `Mpv.__init__` acepta dos parámetros opcionales, con valores por defecto que
   reproducen lo de hoy:

   ```python
   def __init__(
       self,
       command: Sequence[str] | None = None,
       transport: Transport | None = None,
   ) -> None:
   ```

   `command` es el ejecutable (y argumentos previos) que se lanza. Hoy los tests
   fabrican un script `mpv` con shebang y `chmod 0o755` y lo meten en el `PATH`; eso
   no funciona en Windows (§8.2). Con `command=[sys.executable, FAKE]` el test es el
   mismo en los dos sistemas. Es inyección de dependencias en la frontera, que es lo que
   piden `tidalamp-mpv-ipc` y `python-testing-patterns`.
3. `_readline` cambia `self._sock.recv(...)` por `self._transport.recv(...)` y nada más.
   Las ramas `TimeoutError → _TIMED_OUT`, `OSError → None` y `b"" → None` se quedan
   **literalmente iguales**.

Criterio: `tests/test_player.py` pasa sin cambiar asserts. Solo cambia la fixture `mpv`
para usar `command=`, y eso puede ir en el mismo PR.

**F1 — el named pipe:**

1. **Dirección.** `config.IPC_SOCKET` (una `Path`) se queda para Linux. En Windows:

   ```python
   rf"\\.\pipe\tidalamp-mpv-{os.getpid()}"
   ```

   El PID evita que dos instancias choquen por el mismo pipe, con el mismo razonamiento
   que ya aplica `mpris.py` al pedir un nombre de bus con sufijo.

2. **Transporte `backends/windows/pipe.py` con E/S solapada, no con `open()` + hilo.**
   Esto contradice al plan del fork, y es deliberado. `open(r"\\.\pipe\...", "r+b")`
   abre un handle **síncrono**, y Windows serializa las operaciones sobre un handle
   síncrono: mientras un hilo está bloqueado en `ReadFile` esperando un evento de mpv,
   el `WriteFile` del hilo de la UI **espera a que termine esa lectura**. Justo lo que
   pasa en cuanto mpv se queda callado, que es cuando más importa poder mandarle algo.
   **Verificarlo con un test** antes de descartarlo del todo, pero no construir sobre
   esa base.

   Lo correcto es E/S solapada, con `FILE_FLAG_OVERLAPPED`. Hay dos formas:

   | Opción | A favor | En contra |
   |---|---|---|
   | `_winapi` (stdlib) | Sin dependencias; es lo que usan `multiprocessing.connection.PipeConnection` y `asyncio` en Windows, así que se mantiene | Módulo privado, sin documentación oficial |
   | `pywin32` (`win32file`, `win32event`) | API pública y documentada | Dependencia binaria pesada |

   **Recomendación: `_winapi`**, encapsulado en ese único fichero y cubierto por los
   tests de §8.2. Si una versión de Python lo rompe, el daño se queda en un fichero y la
   CI lo detecta el mismo día.

   Esquema (orientativo, no copiar sin probar):

   ```python
   import _winapi


   class NamedPipe:
       """mpv's JSON IPC over a Windows named pipe, with real timeouts."""

       def __init__(self, address: str) -> None:
           self.address = address
           self._handle: int | None = None
           self._pending: Any = None  # the overlapped read still in flight

       def prepare(self) -> None:
           """Nothing to clean: the system destroys a pipe with its last handle."""

       def connect(self, timeout: float) -> None:
           deadline = time.monotonic() + timeout
           while time.monotonic() < deadline:
               try:
                   self._handle = _winapi.CreateFile(
                       self.address,
                       _winapi.GENERIC_READ | _winapi.GENERIC_WRITE,
                       0,
                       _winapi.NULL,
                       _winapi.OPEN_EXISTING,
                       _winapi.FILE_FLAG_OVERLAPPED,
                       _winapi.NULL,
                   )
                   return
               except FileNotFoundError:
                   pass  # mpv has not created the pipe yet
               except OSError as exc:
                   if exc.winerror != _winapi.ERROR_PIPE_BUSY:
                       raise
                   _winapi.WaitNamedPipe(self.address, 50)
               time.sleep(0.05)
           raise MpvNotFound(_("mpv no abrió el socket IPC a tiempo"))

       def recv(self, timeout: float) -> bytes:
           if self._pending is None:
               self._pending = _winapi.ReadFile(self._handle, 65536, overlapped=True)
           waited = _winapi.WaitForMultipleObjects(
               [self._pending.event], False, int(timeout * 1000)
           )
           if waited == _winapi.WAIT_TIMEOUT:
               raise TimeoutError  # the read stays pending for the next call
           read, self._pending = self._pending, None
           try:
               data, _error = read.GetOverlappedResult(True)
           except BrokenPipeError:
               return b""  # mpv closed its end: EOF, like socket.recv
           return data

       ...
   ```

   El detalle que más importa: **ante un timeout, la lectura solapada no se cancela, se
   guarda** en `_pending` y la siguiente llamada espera sobre la misma. Si se cancelara,
   los bytes que llegasen entre la cancelación y la siguiente lectura podrían perderse, y
   perder media línea de JSON desincroniza el casado por `request_id`, que es
   exactamente el fallo que `tidalamp-mpv-ipc` pide no reintroducir.

   `close()` cancela la lectura pendiente (`CancelIoEx` vía `self._pending.cancel()`),
   espera su resultado ignorando `ERROR_OPERATION_ABORTED` y cierra el handle con
   `_winapi.CloseHandle`. Tiene que ser idempotente, porque `restart()` y `close()`
   pueden llegar los dos.

3. **Localizar el binario.** Probar en este orden:
   1. el ajuste nuevo `mpv_path` / `TIDALAMP_MPV_PATH` (añadirlo a `ENV_VARS` en
      `config.py`, siguiendo el patrón de los demás);
   2. `shutil.which("mpv.exe")`, **con la extensión**. `shutil.which("mpv")` en Windows
      recorre `PATHEXT`, donde `.COM` va antes que `.EXE`, y los builds oficiales de mpv
      traen los dos. `mpv.com` es el envoltorio de consola;
   3. `%LOCALAPPDATA%\Microsoft\WinGet\Links\mpv.exe`, `%USERPROFILE%\scoop\shims\mpv.exe`,
      `%ProgramFiles%\mpv\mpv.exe`.

   Solo si todo falla, `MpvNotFound` con el mensaje de `distro.missing("mpv")`.
   El `Popen` recibe **la ruta resuelta**, no `"mpv"`: `CreateProcess` no consulta
   `PATHEXT`, así que un `"mpv"` suelto puede fallar aunque `which` lo encuentre. En
   Linux usar también la ruta resuelta es inocuo.

4. **Sin ventana de consola**, solo en Windows:

   ```python
   creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
   ```

   Sin esto parpadea una consola en cada arranque y en cada `restart()`.

5. **Argumentos de mpv que no se tocan:** `--af=@astats...`,
   `--demuxer-lavf-o=protocol_whitelist=%NN%...`, `--cache=yes`,
   `--demuxer-readahead-secs`, `--prefetch-playlist=yes`, `--load-scripts=no`. Cada
   uno explica en el fuente el problema que resuelve y ninguno es de Linux (§13).

6. **Argumento nuevo, solo con el ajuste activo:** `--audio-exclusive=yes` (§7.3).

**Criterio de hecho F1:** `tidalamp tui` arranca en Windows; `x` reproduce; la posición
avanza; `z` `c` `v` responden; matar `mpv.exe` desde el Administrador de tareas hace que
la app lo relance conservando el volumen (es la ruta de `restart()` que describe
`tidalamp-mpv-ipc`).

### 7.2 `mpris.py` — integración de medios · F1 (neutro) + F5 (SMTC)

**Hoy:** 419 líneas que publican `org.mpris.MediaPlayer2.tidalamp` en D-Bus con
`dbus-fast`. `app.py` crea `MprisService(self)`, arranca `start()` en un worker, publica
con `publish()`/`publish_tracks()`/`seeked()` y expone 30 métodos `mpris_*` que forman
el `PlayerBackend`.

**Lo que no se toca:** los nombres `mpris_*` de `app.py` y `PlayerBackend`. Sí, en
Windows «mpris» es un nombre histórico, pero es el contrato del adaptador y renombrarlo
son 30 métodos, todos sus tests y cero beneficio. Se documenta en el docstring de la
fachada.

**F0:** `git mv tidalamp/mpris.py tidalamp/backends/linux/mpris.py` y fachada
`tidalamp/mpris.py` que reexporta `MprisService` y `PlayerBackend`.

**Un cambio en `app.py`, el único de esta fase.** `_start_mpris` compara el nombre
devuelto con el literal `"org.mpris.MediaPlayer2.tidalamp"` para avisar de que hay otra
instancia. Eso filtra un detalle de D-Bus a la app. Sustituirlo por un atributo del
servicio:

```python
name = await self.mpris.start()
...
if self.mpris.shared:  # another tidalamp already held the plain name
```

En Linux `shared` es `True` cuando se pidió el nombre con sufijo; en Windows siempre
`False`. Mismo mensaje, mismo comportamiento, sin literal de D-Bus fuera del backend.

**F1 — neutro en Windows.** `backends/windows/media.py` con la API completa que no hace
nada: `start()` devuelve `""` y `shared = False`, y el resto `return None`. La app
arranca, `_mpris_ready` queda en `True`, y nadie ve un aviso falso.

**F5 — SMTC de verdad.**

- **El obstáculo conocido:** `SystemMediaTransportControls.GetForCurrentView()` exige un
  `CoreWindow` y `ISystemMediaTransportControlsInterop.GetForWindow(hwnd)` exige un
  `HWND`. Un TUI no tiene ninguno.
- **La salida que hay que probar primero:** crear un
  `Windows.Media.Playback.MediaPlayer`, desactivar su `CommandManager`
  (`player.CommandManager.IsEnabled = False`) y usar su
  `player.SystemMediaTransportControls`. Es la vía que usan apps de escritorio sin
  ventana propia. **Hacer un spike de una tarde antes de comprometerse**: si no
  funciona desde una app sin empaquetar lanzada desde un terminal, el plan B es la
  ventana oculta con su bucle de mensajes, que es bastante más caro.
- **Paquetes:** los módulares de pywinrt (`winrt-Windows.Media`,
  `winrt-Windows.Media.Playback`, `winrt-Windows.Foundation`, …). `winsdk` está
  abandonado a favor de estos. Comprobar en PyPI los nombres y versiones exactos antes
  de fijarlos.
- **Hilos (skill `tidalamp-textual-workflows`):** el evento `ButtonPressed` de SMTC llega
  en un hilo del pool de WinRT, no en el de Textual. El manejador **solo** hace
  `app.call_from_thread(app.mpris_play_pause)` (o el que toque). Nunca toca la cola ni
  el reproductor directamente.
- **Unidades (skill `tidalamp-mpris-contract`):** la app trabaja en segundos; MPRIS usaba
  microsegundos en la frontera; SMTC usa `TimeSpan`, en unidades de 100 ns. La
  conversión se hace **en el backend** y se documenta en el fuente, igual que la
  documenta hoy `mpris.py`. SMTC no expone volumen: `mpris_volume` simplemente no se
  usa en Windows.
- **Emitir solo lo que cambió:** igual que `publish()` hoy compara con lo último
  publicado antes de emitir `PropertiesChanged`, el backend SMTC compara antes de llamar
  a `DisplayUpdater.Update()`. Actualizar el panel en cada tick de la UI es trabajo
  inútil, y en algunos sistemas hace que el panel parpadee.
- **Fallos nunca fatales:** si falta el paquete, falla la importación o WinRT lanza,
  `start()` lanza y `_start_mpris` ya lo convierte en «MPRIS no disponible (...)». Hay
  que cambiar ese texto a algo neutral («controles multimedia no disponibles») en
  `i18n.py`, con su par en inglés.

### 7.3 `audio.py` — la pila de audio · F4

**Hoy:** PipeWire/PulseAudio. `pactl` para el dispositivo y los streams,
`/proc/asound/cardN/stream0` para las tasas del DAC, un fichero en
`~/.config/pipewire/pipewire.conf.d` para permitir tasas, `systemctl --user restart`
para aplicarlo. `app.py` tiene un worker que sigue la tasa del stream y la fuerza en el
grafo; `screens/config_window.py` muestra el dispositivo y ofrece escribir las tasas.

**Lo que sobrevive es el problema, no el código:** que una pista de 24/96 llegue al DAC a
24/96. En Windows:

- En **modo compartido** (el normal), el motor de audio remuestrea todo al «formato
  predeterminado» del dispositivo (Sonido → Propiedades → Opciones avanzadas). Nada
  dentro de la app lo evita.
- En **modo exclusivo** WASAPI, mpv toma el dispositivo y lo abre a la tasa de la fuente.
  Es el equivalente exacto a lo que hace hoy el módulo con PipeWire:
  `--audio-exclusive=yes`.

**`backends/windows/audio.py`** con la misma API que el de Linux (el test de paridad de
§8.3 lo vigila):

| Función | En Windows |
|---|---|
| `sink()` | `Sink` a partir de las propiedades de mpv `audio-device` y `audio-out-params` (tasa efectiva). Si hace falta el nombre legible, `audio-device-list` |
| `allowed_rates()`, `hardware_rates()` | `()`: no se gestionan. Leer el `WAVEFORMATEX` del registro (`winreg`) es posible pero frágil; **no** hacerlo en esta fase |
| `streams_on()` | `0` |
| `rate_to_force()` | La función pura de Linux, que se puede importar tal cual o devolver `0` |
| `force_rate()` | `False` |
| `rates_configured()`, `clamped()` | `False` |
| `write_rates()`, `remove_rates()` | No se llaman en Windows (ver `MANAGES_RATES`); si llegan a llamarse, `NotImplementedError` con mensaje claro |
| `restart()` | No se llama en Windows |
| `MANAGES_RATES` | **Nuevo**, en los dos backends: `True` en Linux, `False` en Windows |

`sink()` en Windows necesita hablar con mpv, y hoy `audio.sink()` no recibe el
reproductor. Dos opciones: pasarle un `Mpv` opcional (`sink(mpv=None)`, que en Linux se
ignora) o que el bucle de `app.py` construya el `Sink` desde el reproductor en Windows.
**Preferir el parámetro opcional**: mantiene el bucle de `app.py` idéntico.

Con esos valores neutros, el bucle de `app.py` (el worker que sigue la tasa) **no
necesita cambios**: `force_rate` nunca se llama porque `rate_to_force` devuelve 0, y
`force_rate(0)` en el `finally` es un no-op. Solo sigue refrescando la línea de salida,
que es lo que queremos.

**`screens/config_window.py`:** la sección de tasas de PipeWire y el botón de reinicio se
ocultan con `if audio.MANAGES_RATES`. En su lugar, en Windows, un conmutador para el
ajuste nuevo **`exclusive`** (`TIDALAMP_EXCLUSIVE`, en `ENV_VARS`), **apagado por
defecto**: en exclusivo no suena ningún otro programa, y una app de música que silencia
las notificaciones sin avisar es un informe de bug esperando a llegar. El texto de ayuda
tiene que decirlo.

**`i18n.py`:** las cadenas de PipeWire siguen existiendo (Linux las usa). Las nuevas
(«modo exclusivo», su ayuda) se añaden con su par en inglés.

**Criterio de hecho:** con `exclusive` activo y una pista de 24/96, `audio-out-params`
de mpv marca 96 000 Hz y el panel de sonido de Windows muestra el dispositivo en uso
exclusivo.

### 7.4 `config.py` — rutas y escritura atómica · F1

1. **Rutas.** `_xdg()` conserva nombre y firma (lo importan `audio.py`, `desktop.py` y
   `theme.py`). En Linux, idéntico. En Windows:

   | Constante | Windows |
   |---|---|
   | `CONFIG_DIR` | `%APPDATA%\tidalamp` |
   | `CACHE_DIR` | `%LOCALAPPDATA%\tidalamp\cache` |
   | `STATE_DIR` | `%LOCALAPPDATA%\tidalamp\state` |

   Si `XDG_CONFIG_HOME` y compañía están definidas en Windows, se respetan: quien las
   pone lo hace a propósito (WSL, dotfiles portables) y los tests las usan para aislarse.
   Si `APPDATA` no existe (servicios, sesiones raras), `Path.home() / "AppData/Roaming"`.

   **No** meter `platformdirs` como dependencia: son tres rutas y quedan más claras
   escritas.

2. **`IPC_SOCKET`** se queda como `Path` para Linux y se añade la dirección del pipe
   para Windows (§7.1). Quien la consume es solo el transporte.

3. **`write_atomically()`**:
   - `os.replace()` en Windows lanza `PermissionError` si el destino está abierto por
     otro proceso, y un antivirus escaneando el fichero basta. Reintentar 3 veces con
     50 ms de espera **solo en Windows** y solo ante `PermissionError`; después,
     propagar. En Linux el comportamiento no cambia.
   - La conservación del modo (`st_mode & 0o777` + `chmod`) en Windows solo mueve el
     bit de solo lectura. No hace daño; ajustar el docstring para que no prometa un
     «0644» que en Windows no significa nada.

### 7.5 `auth.py` — permisos del fichero de sesión · F4

**Hoy:** `_tighten()` y `_private()` dejan el directorio en `0700` y la sesión en `0600`,
porque guarda los tokens de acceso y de refresco.

En Windows esas llamadas no protegen nada. `%APPDATA%` ya hereda una ACL que solo da
acceso al usuario, a SYSTEM y a Administradores, que es el equivalente práctico a lo que
hay en Linux (donde root también lo lee).

**Qué hacer:** en Windows, `_tighten()` y `_private()` no hacen nada y lo dicen en el
docstring, explicando **por qué** es suficiente la ACL heredada. **No** ejecutar
`icacls` por defecto: añade un subproceso al arranque, puede fallar en entornos
gestionados y no mejora el modelo de amenaza real. Si algún día se quiere endurecer, que
sea una fase propia con `pywin32` (`win32security`) y sus tests.

Mantener la garantía actual: ningún fallo aquí impide abrir el reproductor.

### 7.6 `desktop.py` — el lanzador · F4

**Hoy:** escribe un `.desktop` en `~/.local/share/applications`, busca uno existente en
`XDG_DATA_DIRS` para no duplicarlo, instala el icono SVG y trata Omarchy como caso
especial.

**F0:** `git mv` a `backends/linux/desktop.py` y fachada.

**`backends/windows/desktop.py`** con la **misma política**, que es la parte valiosa: se
pregunta una vez, un «no» no se vuelve a preguntar (`MARKER`), un lanzador borrado a
mano no se reescribe, respeta `TIDALAMP_NO_DESKTOP_ENTRY` (lo pone
`tests/conftest.py` para no escribir en el menú del desarrollador) y **ningún fallo
aquí impide abrir el reproductor**.

1. `data_dirs()` → `%APPDATA%\Microsoft\Windows\Start Menu\Programs` y
   `%ProgramData%\Microsoft\Windows\Start Menu\Programs`.
2. `existing()` → busca `TidalAmp.lnk` por nombre. Un `.lnk` es binario: no se puede
   leer con la regex de `Exec=` que usa el backend de Linux.
3. `create()` → crea el acceso directo vía COM (`WScript.Shell`), con PowerShell y
   `CREATE_NO_WINDOW`, para no añadir dependencias:

   ```powershell
   $s = (New-Object -ComObject WScript.Shell).CreateShortcut($ruta)
   $s.TargetPath = "wt.exe"; $s.Arguments = '-- "<ruta a tidalamp.exe>" tui'
   $s.IconLocation = "<ruta a tidalamp.ico>"; $s.Save()
   ```

   Los valores se pasan como argumentos de PowerShell (`-ArgumentList` / parámetros del
   script), **no interpolados en el texto del comando**: una ruta con una comilla simple
   no puede convertirse en código.
4. **Objetivo:** Windows Terminal si existe (`shutil.which("wt.exe")`), que es donde el
   TUI se ve bien; si no, `tidalamp.exe tui` directamente (conhost). Es el análogo de la
   rama Omarchy: el escritorio abre las apps de terminal a su manera.
5. **Icono:** los `.lnk` no leen SVG. Generar `tidalamp.ico` (16, 32, 48, 256) a partir
   de `tidalamp/tidalamp.svg`, versionarlo dentro del paquete (`tidalamp/tidalamp.ico`)
   para que `importlib.resources` lo encuentre también desde el `.exe` de PyInstaller.
6. **Cerrar sesión con borrado** (`test_app_logout.py`) tiene que borrar también el
   `.lnk`, igual que hoy borra el `.desktop`.

### 7.7 `distro.py` — cómo se instala mpv · F1

**Hoy:** lee `/etc/os-release` y devuelve `sudo pacman -S mpv` o equivalente. Existe
porque pip no puede instalar mpv y el mensaje de error tiene que decir cómo conseguirlo.

**F0:** `git mv` a `backends/linux/distro.py` y fachada con `install_command(package)` y
`missing(package)`.

**`backends/windows/distro.py`:** detectar `winget`, `scoop` o `choco` con
`shutil.which`, en ese orden (winget viene de serie en Windows 10 actualizado y en 11).
Si no hay ninguno, `""`, y `missing()` cae en la forma sin paréntesis, igual que en una
distro no reconocida.

⚠️ **No escribir de memoria los identificadores de paquete.** Comprobar en una máquina
real `winget search mpv`, `scoop search mpv` (probablemente en el bucket `extras`) y
`choco search mpv`, y escribir lo que devuelvan. `mpv.net` es otra aplicación. Dejar en
el fuente un comentario con la fecha en que se comprobó.

### 7.8 `spectrum.py` — cava · F3

**Hoy:** lanza `cava -p <config>` con `method = pulse` y salida raw por stdout. Si cava
falta o muere, lanza `SpectrumUnavailable` y el llamante conserva el medidor RMS.

cava tiene build para Windows desde la 0.10, con la entrada `winscap` (captura loopback
de WASAPI). **Hay que comprobar** que el modo `raw` a stdout funciona igual ahí. Según
lo que salga:

- **Si funciona:** `method` pasa a elegirse por plataforma (`"pulse"` en Linux,
  `"winscap"` en Windows) y nada más cambia. Es el mejor resultado posible.
- **Si no:** en Windows `Cava.__init__` lanza `SpectrumUnavailable` con un mensaje que
  lo explique, y `config_window.py` marca `visualizer = "spectrum"` como no disponible
  en lugar de dejar que falle. `analyzer.py` y `app.py` ya degradan solos.

`tests/fake_cava.py` usa `chmod` para el script falso: mismo tratamiento que el mpv
falso (§8.2).

### 7.9 `i18n.py` — idioma por defecto · F1

**El fallo:** `_language()` acaba con `locale.getlocale(locale.LC_MESSAGES)`, y
`LC_MESSAGES` no existe en Windows. El `except (ValueError, AttributeError)` lo captura,
así que no hay error: **un usuario con Windows en inglés ve la interfaz en español**
porque se llega al `return "es"` final. Es un fallo silencioso de cara al usuario.

**Arreglo**, solo en la rama de respaldo y solo en Windows:

```python
if sys.platform == "win32":
    import ctypes

    lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    code = locale.windows_locale.get(lcid, "")  # e.g. "en_US"
```

No usar `locale.getlocale()[0]` sin más: en Windows devuelve cosas como
`'Spanish_Spain'` y el `split("_")[0].lower()` daría `'spanish'`.

Se mantiene intacta la precedencia de `LANGUAGE`/`LC_ALL`/`LC_MESSAGES`/`LANG` y de
`TIDALAMP_LANG` (que `tests/conftest.py` fija a `"es"`).

Test: `monkeypatch` de `ctypes.windll...` no es portable. Separar la consulta en una
función pequeña (`_windows_ui_language() -> str`) y parchear esa. El test de la
traducción LCID → código corre en cualquier sistema, porque `locale.windows_locale` es
un diccionario que existe en todas las plataformas.

### 7.10 `stream.py` — un fd que se escapa · F1 (y es un bug también en Linux)

```python
path = Path(tempfile.mkstemp(dir=CACHE_DIR, prefix=..., suffix=".m3u8")[1])
```

`mkstemp` devuelve `(fd, ruta)` y aquí el `fd` se descarta **sin cerrarlo**. En Linux es
una fuga de descriptores por cada pista hi-res. En Windows además `cleanup()` no puede
borrar un fichero que el propio proceso tiene abierto: `PermissionError`, y los `.m3u8`
se acumulan en la caché para siempre.

```python
fd, name = tempfile.mkstemp(dir=CACHE_DIR, prefix=f"track-{track_id}-", suffix=".m3u8")
os.close(fd)
path = Path(name)
```

Y el `stale.unlink(missing_ok=True)` de la limpieza, dentro de
`contextlib.suppress(OSError)`: si mpv todavía tiene abierta la playlist de la pista en
curso, Windows no deja borrarla y eso no es motivo para romper nada (skill
`tidalamp-tidalapi-resilience`: la limpieza no puede dejar el estado ambiguo).

Este arreglo **puede ir en un PR propio antes que todo lo demás**, con su test y su línea
en el CHANGELOG, porque corrige Linux también.

### 7.11 `cli.py` — codificación · F1

Desde Python 3.6 la consola de Windows escribe UTF-8 bien **cuando la salida es la
consola**. El problema aparece al redirigir (`tidalamp login > log.txt`, o dentro de
algunos terminales integrados), donde se usa la página de códigos ANSI y los `«»`, `ñ` o
`—` de los mensajes de error salen rotos. Al principio de `main()`:

```python
for stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, OSError):
        stream.reconfigure(encoding="utf-8")
```

Es inocuo en Linux. `[project.scripts]` genera `tidalamp.exe` sin cambios; **no** pasarlo
a `gui-scripts`, que le quitaría la consola a un TUI.

### 7.12 `artwork.py` — carátulas en el terminal · F3

| Protocolo | Windows |
|---|---|
| kitty graphics | Solo WezTerm |
| sixel | Windows Terminal ≥ 1.22; WezTerm |
| medios bloques | Siempre |

`$TERM` normalmente no existe en Windows, así que hoy la detección cae en medios bloques:
correcto, pero por casualidad. Hacerlo a propósito:

1. `detect_protocol()` conserva la firma y el respeto a `configured` (`TIDALAMP_ART`, que
   debe poder forzar cualquier protocolo). Señales nuevas: `WT_SESSION` (Windows
   Terminal), `TERM_PROGRAM == "WezTerm"`.
2. Por defecto, **medios bloques**. Sixel en Windows Terminal solo tras verlo funcionar
   en una máquina real, y aun así primero detrás del ajuste explícito. Un sixel enviado a
   un terminal que no lo entiende llena la pantalla de basura; los medios bloques no
   fallan nunca.
3. **Sextantes** (U+1FB00–U+1FBFF): dependen de la fuente. Comprobar la versión actual de
   Cascadia Code/Mono. Hasta entonces, en Windows solo con `TIDALAMP_SEXTANTS=1`; si no,
   el usuario ve una rejilla de cuadros vacíos donde iba la portada.
4. Tests con `detect_protocol(env={...})`, que ya acepta el entorno como parámetro:
   parametrizar los casos nuevos (`WT_SESSION`, WezTerm, sin variables) sin depender del
   sistema en el que se ejecuten.

### 7.13 `theme.py` — Omarchy · F3

`omarchy_colors_path()` apunta a un fichero que en Windows no existe, y
`_read_palette(...) or DEFAULT_PALETTE` ya cae a la paleta por defecto. **No hay que
borrar nada.** Solo ocultar la opción «omarchy» en la ventana de ajustes cuando no se
está en Linux, para no ofrecer algo que nunca va a funcionar.

`palette_dir()` usa `_xdg()` y queda corregida con §7.4. El formato TOML de las paletas
no cambia: así un usuario puede llevarse sus paletas de Linux a Windows.

### 7.14 `pyproject.toml` · F0–F2

```toml
dependencies = [
    "tidalapi>=0.8.11",
    "textual>=0.80",
    "typer>=0.12",
    "dbus-fast>=5.0.22; sys_platform == 'linux'",
    "requests>=2.31",
    # F5, cuando exista el backend SMTC. Nombres por comprobar en PyPI:
    # "winrt-Windows.Media.Playback>=...; sys_platform == 'win32'",
]
```

- **Clasificadores:** añadir `"Operating System :: Microsoft :: Windows"` y
  `"Environment :: Win32 (MS Windows)"` junto a los de Linux, **solo cuando F2 esté
  verde**. Un clasificador es una promesa.
- **Nombre y script:** no cambian. Un solo paquete `tidalamp` en PyPI; `tidalamp.exe` lo
  crea pip en Windows.
- **mypy:** el override de `tidalamp.mpris` pasa a `tidalamp.backends.linux.mpris` (§5.4).
- **`[tool.hatch.build.targets.sdist]`:** `packaging/` sigue dentro; se añade
  `packaging/windows/` (§10).

---

## 8. La suite de tests

Aplicando `python-testing-patterns` y las secciones «Verification» de las skills del
proyecto.

### 8.1 Principios

- **AAA y un comportamiento por test.** Un test que prueba «el pipe conecta, lee y
  reinicia» son tres tests.
- **Nombres que dicen el síntoma.** El repo ya lo hace (`CONTRIBUTING.md`: «the test
  should say what was breaking»). Ejemplos para esta migración:
  `test_named_pipe_timeout_keeps_pending_read`,
  `test_language_on_english_windows_is_english`,
  `test_m3u8_cleanup_survives_file_in_use`.
- **Marcadores** en `pyproject.toml` (`[tool.pytest.ini_options] markers`), mejor que
  `skipif` sueltos con la condición repetida:

  ```python
  # tests/conftest.py
  linux_only = pytest.mark.skipif(
      not sys.platform.startswith("linux"), reason="Linux-only backend"
  )
  windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only backend")
  ```

  `skipif` y no borrar: si algún día hay implementación, el test vuelve gratis.
- **Dobles en las fronteras, nunca en el medio.** Se falsifica mpv, cava, el bus, SMTC y
  el registro; no se falsifican `Mpv`, la cola ni la app.
- **Cada test de Linux sigue pasando en Linux.** Los cambios en tests existentes son de
  montaje (fixtures), no de asserts, salvo donde se indica.

### 8.2 `fake_mpv.py` y la fixture `mpv`

`fake_mpv.py` es el doble más valioso del repo: responde el subconjunto del JSON IPC que
usa `Mpv`, intercala eventos asíncronos con las respuestas (lo que ya causó bugs) y tiene
tres variables para portarse mal: `FAKE_MPV_HANG_ON`, `FAKE_MPV_EOF_ON`,
`FAKE_MPV_SPLIT`. Todo eso se conserva.

1. **Servidor según plataforma.** Separar en el fake la lógica del protocolo (que no
   cambia) del servidor. En Linux, el `AF_UNIX` de hoy. En Windows, un servidor de named
   pipe con `_winapi.CreateNamedPipe` + `ConnectNamedPipe`, las mismas primitivas que el
   cliente. **Así el transporte de producción queda cubierto en CI**, que es la
   diferencia con el plan del fork (TCP en tests y pipe solo en producción dejaba sin
   probar justo la parte nueva).
2. **La fixture `mpv`** deja de fabricar un script con shebang y `chmod 0o755` en el
   `PATH` y usa `Mpv(command=[sys.executable, str(FAKE)], transport=...)` (§7.1). Queda
   igual en los dos sistemas.
3. **`signal.SIGKILL`** (`test_player.py:117,126`) no existe en Windows → `proc.kill()`,
   que en Linux envía SIGKILL igualmente. Cambio sin pérdida.
4. **`test_a_socket_path_too_long_...`** pasa a `@linux_only`: el límite de 108 bytes es
   de `sun_path` y no existe en un pipe.
5. **Casos nuevos para el pipe** (`@windows_only`), los que pide `tidalamp-mpv-ipc`:
   respuesta con eventos intercalados, línea partida en dos lecturas, timeout seguido de
   la respuesta que llega tarde (la lectura pendiente **no** pierde bytes), EOF, proceso
   muerto, `restart()` y `close()` dos veces.
6. **Test de integración con un mpv real**, marcado `@pytest.mark.integration` y con
   `skipif` si no hay `mpv.exe`: arranca, `loadfile` de un WAV corto generado en
   `tmp_path`, lee `audio-out-params`, cierra. No corre en la CI por defecto; es el que
   se lanza a mano en la máquina Windows de F1.

### 8.3 Test de paridad de backends

Nuevo, `tests/test_backend_parity.py`. Es lo que convierte «misma API» de promesa en
comprobación:

```python
import inspect

import pytest

from tidalamp.backends.linux import audio as linux_audio
from tidalamp.backends.windows import audio as windows_audio


@pytest.mark.parametrize("name", sorted(linux_audio.__all__))
def test_windows_audio_exposes_the_linux_api(name):
    linux, windows = getattr(linux_audio, name), getattr(windows_audio, name)
    if callable(linux):
        assert inspect.signature(windows) == inspect.signature(linux)
```

Uno por módulo con fachada (`audio`, `mpris`/`media`, `desktop`, `distro`). Para que
corra en cualquier sistema, **los backends tienen que poder importarse en los dos**:
nada de `import winreg`, `_winapi` o `dbus_fast` a nivel de módulo en un backend que
luego se importe en el otro sistema. Se importan dentro de las funciones que los usan o
tras un `if sys.platform`. Donde no se pueda (el backend D-Bus hereda de
`ServiceInterface`), ese caso concreto se marca `@linux_only` y se compara solo la clase
pública `MprisService`.

### 8.4 `chmod` como forma de simular fallos

Hay tests que hacen `chmod(0o500)` o parecidos para simular «no se puede escribir»:
`test_settings.py:156,162`, `test_app_logout.py:72`, `test_queue.py:300,306`,
`test_library.py:970,977`, `test_config.py:96,100,322`, `test_auth.py:197,198,273,279`.
En Windows **pasan sin probar nada**, porque `chmod` solo cambia el bit de solo lectura.
Y en Linux fallan si la suite corre como root (en un contenedor, por ejemplo).

Hay dos tipos y cada uno se trata distinto:

- **Los que simulan un fallo de escritura** → sustituir por un `monkeypatch` que haga
  lanzar `PermissionError` a la función concreta (`Path.write_text`, `os.replace`, lo
  que toque). Mejor en los dos sistemas: determinista y sin depender del usuario.
- **Los que comprueban que el fichero queda en `0600`** (`test_auth.py`) → `@linux_only`.
  En Windows se añade uno propio que compruebe que `_tighten` no lanza.

### 8.5 Resto de ficheros

| Fichero | Tratamiento |
|---|---|
| `test_audio.py` | Importa `tidalamp.backends.linux.audio`; `@linux_only` a nivel de módulo (`pytestmark`). Nuevo `test_audio_windows.py` con `mpv` falso |
| `test_mpris.py` | Ya se salta sin `dbus-daemon`; además `@linux_only`. Nuevo `test_media_windows.py` contra un `SystemMediaTransportControls` falso |
| `test_desktop.py` | Los casos de `/usr/bin` y `xdg-terminal-exec` → `@linux_only`. Nuevo para el `.lnk`: se falsifica el `subprocess.run` de PowerShell y se comprueba la política (una vez, «no» persiste, borrado a mano no se reescribe) |
| `test_distro.py` | `@linux_only`; nuevo parametrizado por gestor para Windows, con `shutil.which` falso |
| `test_spectrum.py`, `fake_cava.py` | Según §7.8 |
| `test_theme.py:150` | `XDG_STATE_HOME` sigue valiendo en los dos (se respeta en Windows si está definida, §7.4) |
| `test_config.py:23`, `test_player.py:53`, `test_auth.py:240`, `conftest.py:147` | Idem: siguen aislando con variables XDG, que ahora también se respetan en Windows |
| `test_i18n.py` | Casos nuevos para `_windows_ui_language` y la traducción LCID |
| `test_stream.py` | Caso nuevo: `cleanup()` con un `.m3u8` que no se puede borrar no lanza |

**Rutas largas:** `tmp_path` más `track-<id>-XXXX.m3u8` puede rozar los 260 caracteres de
`MAX_PATH`. Si aparecen `FileNotFoundError` sin sentido, es eso. Documentarlo en
`CONTRIBUTING.md` (§11).

---

## 9. CI

### 9.1 `ci.yml`

```yaml
jobs:
  pytest:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ["3.11", "3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}

      - name: Install dbus-daemon
        if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y dbus

      - name: Install the package
        run: python -m pip install -e ".[dev]"

      - name: Run the suite
        run: python -m pytest -q --cov
```

- **mpv no hace falta en CI**: la suite usa `fake_mpv.py`. El test de integración con
  mpv real (§8.2) queda fuera por el marcador.
- **Coste:** la matriz pasa de 4 a 8 trabajos. Si molesta, Windows puede ir solo con
  3.11 y 3.14 (los extremos).

### 9.2 El job `bare` y el heredoc

El job `bare` existe porque una dependencia dura sobre una opcional rompió la instalación
documentada sin que nadie se enterara (así desaparecieron las carátulas en un clon
limpio). Hay que conservarlo **y** correrlo en Windows, porque allí es donde un
`import dbus_fast` de más rompería la instalación.

Problema: usa un heredoc de bash (`python - <<'PY'`) y en `windows-latest` la shell por
defecto es PowerShell. Solución: mover el script a `tools/import_all.py` y llamarlo con
`python tools/import_all.py` en los dos sistemas. Además se puede lanzar a mano.

El paso `tidalamp --help > /dev/null` pasa a `tidalamp --help` sin redirección (o
`shell: bash`, que existe en los runners de Windows).

### 9.3 `lint`

Se queda en `ubuntu-latest` (ruff y mypy son estáticos), pero mypy corre dos veces:

```yaml
      - name: Types (Linux)
        run: mypy --platform linux
      - name: Types (Windows)
        run: mypy --platform win32
```

---

## 10. Empaquetado y el `.exe`

### 10.1 Dos formas de instalar, en este orden de preferencia

1. **Con Python:** `uv tool install tidalamp` o `pipx install tidalamp`, más
   `winget install <id de mpv>`. Funciona en cuanto F1 esté publicada, no requiere nada
   nuevo en el release y es lo que se documenta primero.
2. **Sin Python:** un zip con `tidalamp.exe` generado con PyInstaller y subido al GitHub
   Release.

### 10.2 PyInstaller

`packaging/windows/tidalamp.spec` (versionado, no generado en cada build):

- **`onedir`, no `onefile`.** `onefile` descomprime todo en `%TEMP%` en cada arranque (un
  segundo o más antes de ver el TUI) y es lo que más falsos positivos de antivirus
  provoca. `onedir` comprimido en zip arranca al momento.
- **`console=True`.** Es un TUI; sin consola no hay nada que ver.
- **Datos del paquete:** `collect_data_files("tidalamp")` para `styles/*.tcss`,
  `emblems/`, `tidalamp.svg` y el `.ico` nuevo. Textual y certifi traen sus propios hooks.
  Comprobar en el `.exe` que las hojas de estilo cargan: si falta una, Textual no falla
  al empaquetar, falla al abrir.
- **Icono del ejecutable:** `icon="tidalamp/tidalamp.ico"`.
- **Resolución de rutas:** cualquier código que use `__file__` para encontrar un recurso
  hay que revisarlo; en el `.exe` debe usarse `importlib.resources`.
- **mpv no va dentro: se instala con winget al primer arranque** (decidido el
  2026-09-24, probando el zip de la 0.16.0). Es GPL, pesa ~30 MB y se actualiza por su
  cuenta; meterlo en el zip obliga a fijar un build de shinchiro (nocturnos, que
  caducan) y a acompañarlo de licencia y fuentes. En su lugar, `cli._offer_installs`
  pregunta en la consola, antes de abrir la interfaz, y lanza
  `winget install --id shinchiro.mpv --exact` a la vista (su instalador pide UAC).
  mpv se pregunta en cada arranque hasta que esté; cava (`karlstav.cava`) **una sola
  vez**, diga lo que diga, apuntado en `%LOCALAPPDATA%\tidalamp\state\offered`. Al
  principio era «hasta el primer no», y un «sí» cuyo cava no se encontraba después
  volvía a preguntar en cada arranque (trampa 24). Sin winget,
  o sin consola, lo de siempre: `distro.missing("mpv")` dice el comando. Mecanismo en
  `backends/windows/winget.py`. Si algún día se quiere un zip «todo incluido», que sea
  un segundo zip (`-with-mpv`) y que `Mpv` busque primero junto a `sys.executable`.
- **Pillow va dentro.** El zip de la 0.16.0 se construyó con `pip install .`, sin
  `[art]`: sin decodificador no hay carátula en ningún modo y ningún error lo dice.
  `release.yml` instala `.[art]` y `smoke.py` falla si falta `PIL/_imaging*`.

### 10.3 `release.yml`

El job actual (tag → comprobar versión → wheel/sdist → PyPI con Trusted Publishing) no se
toca. Se añade uno en paralelo:

```yaml
  windows-exe:
    runs-on: windows-latest
    needs: build            # el que comprueba que el tag coincide con la versión
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: python -m pip install ".[art]" pyinstaller
      - run: pyinstaller packaging/windows/tidalamp.spec --noconfirm
      - name: Smoke test
        run: dist/tidalamp/tidalamp.exe --version
      - name: Zip
        run: Compress-Archive dist/tidalamp "tidalamp-${{ github.ref_name }}-windows-x64.zip"
      - uses: softprops/action-gh-release@v2
        with:
          files: tidalamp-*-windows-x64.zip
```

- El **smoke test** es obligatorio: un `.exe` que no arranca porque falta un módulo
  oculto es el fallo típico de PyInstaller y solo se ve ejecutándolo.
- Publicar también el **SHA-256** del zip en las notas del release (lo necesitará el
  manifiesto de winget).
- **Firma de código:** sin firma, SmartScreen avisará en las primeras descargas. No
  bloquea; se documenta en el README. Firmar es un coste recurrente (certificado) que se
  decide aparte.
- **`permissions: contents: write`** en ese job para poder subir al release.

### 10.4 Después (no bloquea)

- **Manifiesto de winget** (`wh01s17.TidalAmp`), cuando haya un zip con SHA-256 estable,
  con `mpv` como dependencia del manifiesto.
- **Bucket de scoop**: más fácil que winget y apto para apps de terminal.
- **Instalador (Inno Setup)** que cree el acceso directo; entonces `desktop.py` pasa a
  ser el camino para quien instala con pip.

---

## 11. Documentación y skills que hay que actualizar

| Fichero | Qué cambiar | Fase |
|---|---|---|
| `README.md` | «Requirements» y «Quick start» con una pestaña/sección Windows (`winget install mpv`, `uv tool install tidalamp`, el zip). Terminal recomendado: Windows Terminal. Qué no hay en Windows (MPRIS hasta F5, tasas de PipeWire, espectro según §7.8). Aviso de SmartScreen | F6–F7 |
| `CONTRIBUTING.md` | Preparar el entorno en Windows (`python -m venv .venv`, `.venv\Scripts\pip`, rutas largas, mpv opcional para el test de integración). Explicar los marcadores `linux_only`/`windows_only` y el test de paridad | F2 |
| `plan.md` | La decisión de un solo repo (§1) y la arquitectura de backends (§5) **con su porqué**. En §7, las trampas de §13 que se confirmen | F0 en adelante |
| `next.md` | Las fases de §6 como cola comprometida; se borran al completarse | F0 |
| `CHANGELOG.md` | Una línea por cambio visible, en el mismo commit. El arreglo de `mkstemp` y el del idioma son entradas propias | cada PR |
| `publish.md`, `packaging/README.md` | El job del `.exe`, la comprobación del zip y el SHA-256 | F6 |
| `.agents/skills/tidalamp-mpv-ipc/SKILL.md` | Hoy dice «Unix IPC socket». Pasar a «IPC de mpv sobre un transporte (socket Unix o named pipe)», con el contrato de `Transport`, la regla de la lectura pendiente (§7.1) y que el fake sirve los dos | F1 |
| `.agents/skills/tidalamp-mpris-contract/SKILL.md` | Añadir el backend SMTC: unidades `TimeSpan`, callbacks en hilo ajeno → `call_from_thread`, y que la fachada decide | F5 |
| `.agents/skills/tidalamp-textual-workflows/SKILL.md` | Nada obligatorio; opcional mencionar los callbacks de SMTC como otro origen fuera del hilo de la UI | — |

Las skills están en `.gitignore` (`.agents/`, `.claude/`): no viajan por git, **pero
están en el disco y un agente se las va a creer**. Una skill que describe solo la
arquitectura anterior es peor que no tener skill.

Capturas (`img/*.webp`): una en Windows Terminal para el README. No bloquea nada.

---

## 12. Probar en Windows, paso a paso

La suite verde no demuestra ninguno de estos puntos. Se hace en una máquina Windows real
con audio, en este orden: cada paso da por bueno el anterior. Marca cada casilla aquí
mismo al comprobarla, con la fecha, y apunta lo que no salió como se esperaba.

**Qué recoger cuando algo falla.** Lanza con el registro de depuración y adjunta el log:

```powershell
$env:TIDALAMP_DEBUG = "1"; tidalamp
# el log: %LOCALAPPDATA%\tidalamp\state\tidalamp.log
```

Más una captura de la ventana y el texto exacto de la línea de estado. La versión de
Windows (`winver`), la de Python (`python --version`) y la terminal (Windows Terminal o
conhost) van en cada informe.

### 12.1 Instalar

```powershell
winget install shinchiro.mpv
winget install karlstav.cava                 # opcional: el espectro
pipx install "tidalamp[art]"                 # o: uv tool install "tidalamp[art]"
```

- [ ] Instala sin errores. `pip` baja los paquetes `winrt-*` y **no** `dbus-fast`
- [ ] `tidalamp --version` dice `tidalamp 0.16.0` sin sesión y sin mpv
- [ ] En una terminal **nueva**, `tidalamp tui` sin haber hecho login dice cómo hacerlo
- [ ] Sin mpv (antes de instalarlo, o renombrando `Program Files\MPV Player`), el aviso
      dice `winget install shinchiro.mpv`. Si mpv no aparece estando instalado:
      `backends/windows/mpv.py` (`PLACES`), y el ajuste `mpv_path` como salida

### 12.2 Primer arranque

```powershell
tidalamp login
tidalamp
```

- [ ] `tidalamp login` muestra la URL, y los acentos y `«»` salen bien. También con la
      salida redirigida: `tidalamp login > login.txt` y abrir el fichero
      (`cli._utf8_output`)
- [ ] Abre sin que parpadee una consola negra, ni al arrancar ni al relanzar mpv
      (`CREATE_NO_WINDOW` en `player.py` y `spectrum.py`)
- [ ] La interfaz está en el idioma de Windows (`i18n._windows_ui_language`)
- [ ] Se ofrece el acceso directo **una vez**. «Sí» crea
      `%APPDATA%\Microsoft\Windows\Start Menu\Programs\TidalAmp.lnk`, aparece en el
      menú Inicio con el icono y abre en Windows Terminal. Un «no» no vuelve a
      preguntarse (`backends/windows/desktop.py`)
- [ ] `tidalamp config` crea `%APPDATA%\tidalamp\config.toml`

### 12.3 Reproducir: mpv por el named pipe

- [ ] `/`, buscar, `↵`: suena. La posición avanza; `z` `x` `c` `v` responden
- [ ] El paso de una pista a otra no tiene corte (gapless)
- [ ] **Matar `mpv.exe`** en el Administrador de tareas: en unos segundos vuelve a
      sonar desde donde iba y con el mismo volumen. Es el camino de `Mpv.restart()`
- [ ] Dos tidalamp a la vez: cada uno suena y ninguno se lleva el pipe del otro
      (`config.IPC_PIPE` lleva el pid)
- [ ] Tras varias sesiones con pistas hi-res, `%LOCALAPPDATA%\tidalamp\cache` no
      acumula ficheros `.m3u8`

Si mpv no responde o la app lo relanza sin parar: `backends/windows/pipe.py`, y las
trampas 1 a 3 y 18 de §13. `tests/test_player.py` corre contra el pipe de verdad en
Windows: `.venv\Scripts\python -m pytest tests/test_player.py -q`.

### 12.4 Teclas multimedia y panel de Windows (SMTC)

La pieza con más incertidumbre del plan (§7.2).

- [ ] Con algo sonando, el panel multimedia (el que sale sobre el control de volumen,
      o `Win+A`) muestra título, artista, álbum y portada
- [ ] Las teclas multimedia del teclado: reproducir/pausa, siguiente, anterior
- [ ] Los botones del panel hacen lo mismo, y su barra de posición mueve la pista
- [ ] La línea de estado **no** dice «controles multimedia no disponibles». Si lo dice,
      apunta el texto entre paréntesis: es el error de WinRT

Si no aparece nada: el problema conocido es que SMTC pide una ventana, y la salida que
usa `backends/windows/media.py` (los controles de un `MediaPlayer`) podría no valer
para un programa lanzado desde una terminal y sin empaquetar. El plan B es una ventana
oculta con su propio bucle de mensajes (§7.2), bastante más trabajo. Prueba antes con
el `.exe` del zip (§12.7), que es un programa «de verdad» para Windows.

### 12.5 Audio: modo exclusivo

Con una pista 24/96 (se ve en la insignia `SRC`) y un DAC que enseñe la frecuencia en
su pantalla, como el FiiO BTR15:

- [ ] Sin modo exclusivo (`o`, Audio): suena, la insignia `OUT` dice la frecuencia del
      formato del dispositivo en Windows (Sonido → Propiedades → Opciones avanzadas), y
      las notificaciones del sistema **siguen sonando** a la vez
- [ ] Activar **Modo exclusivo** en `o`: la pista sigue sin cortarse, `OUT` pasa a
      96 kHz y el DAC marca 96K. Las notificaciones ya no suenan
- [ ] Desactivarlo devuelve lo anterior sin reiniciar nada
- [ ] Con `exclusive = true` en el fichero, arranca ya en exclusivo
- [ ] La ventana `o` no ofrece las filas de PipeWire

Código: `player._exclusive_option`, `Mpv.set_exclusive`, `app._setting_changed`
(«exclusive») y `backends/windows/audio.py`.

### 12.6 La terminal

- [ ] En **Windows Terminal**: la portada se ve en medios bloques, sin cuadros vacíos, y
      los colores del tema son los de siempre
- [ ] Con `TIDALAMP_ART=sixel` en Windows Terminal (1.22 o más nueva): la portada con
      sixel. Si se ve bien, se puede proponer como opción por defecto ahí
- [ ] Con `TIDALAMP_SEXTANTS=1`: si la fuente los trae, la portada con más detalle; si
      salen cuadros vacíos, la fuente no los tiene y el valor por defecto acierta
- [ ] En **conhost** (la consola clásica, `conhost.exe` desde Ejecutar): abre, se ve y
      responde, aunque con peores colores
- [ ] El espectro: con cava instalado, la fila del analizador se mueve con la música; sin
      él, el medidor RMS, y ningún error a la vista (`spectrum.py`, método `winscap`)

Código: `artwork.detect_protocol` y `artwork.draws_sextants`.

### 12.7 El `.exe` sin Python

En una máquina, o un usuario, sin Python instalado:

- [ ] El zip del Release de la 0.16.0 se descomprime y `tidalamp.exe` abre la interfaz
- [ ] SmartScreen avisa la primera vez (no está firmado) y deja seguir
- [ ] Todo §12.3 y §12.4 vuelve a funcionar desde el `.exe`

### 12.8 Cerrar sesión

- [ ] `o`, Cerrar sesión, con la casilla de borrar los datos: desaparecen
      `%APPDATA%\tidalamp`, las carpetas `cache` y `state` de
      `%LOCALAPPDATA%\tidalamp` (la carpeta en sí puede quedar, vacía) y el acceso
      directo, y **nada** más (`auth.forgotten`)

### 12.9 Y en Linux, nada ha cambiado

- [ ] De vuelta en Omarchy/Arch: una sesión normal con MPRIS, espectro, tasas de
      PipeWire y el lanzador, como antes de la 0.16.0

### Después de §12

Con todo marcado: el clasificador `Operating System :: Microsoft :: Windows` en
`pyproject.toml`, quitar «preview» del README (frase de entrada, «Windows (preview)» y
la tabla de plataformas) y del CHANGELOG de la versión siguiente, una captura en
Windows Terminal para el README.

---

## 13. Trampas conocidas

Cada una puede costar una tarde si no se conoce de antemano.

1. **`_TIMED_OUT` (`b""`) no es `None`.** En `Mpv._readline`, timeout y conexión muerta
   son estados distintos y el segundo dispara `restart()`. Un transporte que los
   confunda hace que la app reinicie mpv cada vez que tarda un segundo en contestar, o
   que se quede colgada contra un mpv muerto. Es lo primero que hay que mirar si algo «va
   raro».
2. **Un handle síncrono de pipe serializa lectura y escritura** (§7.1). Leer en un hilo y
   escribir en otro sobre el mismo `open()` se bloquea justo cuando mpv está callado.
3. **Cancelar una lectura solapada puede perder bytes.** Se deja pendiente (§7.1).
4. **`shutil.which("mpv")` devuelve `mpv.com`** si está al lado de `mpv.exe`, y
   `Popen(["mpv"])` no consulta `PATHEXT`. Resolver `mpv.exe` y pasar la ruta completa.
5. **`if IS_WINDOWS:` no lo entiende mypy.** Solo `sys.platform` literal (regla 3).
6. **La lista blanca de protocolos necesita el escape `%NN%`.** mpv parte las opciones
   por comas; sin `%<longitud>%` la lista no llega a ffmpeg y todos los segmentos
   hi-res fallan con «Protocol 'https' not on whitelist». Es cosa de mpv, no de Linux.
7. **`--cache=yes` es obligatorio.** La pista hi-res es un `.m3u8` *local* con segmentos
   https; mpv la cree local y apaga la caché. Medido: 1,02 s de buffer sin la opción,
   29,8 s con ella.
8. **`os.replace()` falla si el destino está abierto** (antivirus incluido). Afecta a la
   config, la cola y el ecualizador (§7.4).
9. **`chmod` es una ilusión en Windows.** Los tests que lo usan pasan sin probar nada
   (§8.4).
10. **`locale.LC_MESSAGES` no existe** y el `except` lo esconde: el síntoma no es un
    error, es el idioma equivocado (§7.9).
11. **Parchear la fachada no parchea el backend.** `monkeypatch.setattr(audio, "_run", ...)`
    sobre `tidalamp.audio` no hace nada tras el F0: hay que parchear
    `tidalamp.backends.linux.audio` (§5.2).
12. **SMTC exige una ventana**, salvo el truco del `MediaPlayer` (§7.2). Presupuestarlo
    como trabajo propio, con un spike primero.
13. **Callbacks de WinRT en otro hilo.** Tocar la app desde ahí sin `call_from_thread`
    corrompe el estado de Textual de forma intermitente.
14. **`MAX_PATH` = 260.** Aparece como `FileNotFoundError` sin sentido en los tests.
19. **cava en Windows sí saca el raw por stdout.** `raw_target = /dev/stdout` no es una
    ruta allí, pero su código lo trata aparte y usa `GetStdHandle(STD_OUTPUT_HANDLE)`.
    El método de entrada es `winscap` (loopback de WASAPI): oye lo mismo que `pulse`
    en Linux, todo lo que suena, no sólo mpv.
15. **conhost no es Windows Terminal.** Colores, redimensionado y sixel se comportan
    distinto. Probar en los dos antes de cerrar F3.
16. **PyInstaller no falla al empaquetar si falta un `.tcss`**: falla al abrir. Por eso el
    smoke test del release (§10.3).
17. **winget no pone mpv en el `PATH`.** El paquete `shinchiro.mpv` (0.41.0, un Inno
    Setup reempaquetado por `0GMou/mpv2winget`) instala en
    `%ProgramFiles%\MPV Player\mpv.exe` y no toca el `PATH`: con solo
    `shutil.which`, quien siguiera el mensaje de «instala mpv» vería el mismo mensaje
    otra vez. `backends/windows/mpv.py` mira ahí. Comprobado leyendo el `.iss`
    (2026-09-23); §7.1 decía `%ProgramFiles%\mpv` y `WinGet\Links`, que no son de
    este paquete.
18. **`GetOverlappedResult` de una lectura no lanza con `ERROR_BROKEN_PIPE` ni con
    `ERROR_MORE_DATA`**: los devuelve como código, igual que los trata
    `multiprocessing.connection`. El esquema de §7.1 los esperaba como excepción.
20. **Cerrar la terminal no cierra mpv.** En Linux el SIGHUP llega a todo el grupo de
    procesos; en Windows el `CTRL_CLOSE_EVENT` sólo a los procesos de *esa* consola, y
    mpv, lanzado con `CREATE_NO_WINDOW`, tiene una oculta propia. Python muere sin
    limpiar nada (ni `close()` ni `atexit`) y mpv sigue sonando. Arreglo:
    `backends/windows/job.py` mete mpv y cava en un *job object* con
    `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; el kernel cierra nuestro handle al morir el
    proceso, sea como sea, y se lleva a los hijos. tidalamp **no** entra en el job: lo
    heredaría todo lo que lance, incluido el navegador del login. El test
    (`tests/test_job_windows.py`) necesita `FAKE_MPV_LINGER`: el mpv falso sale solo
    al perder al cliente y ocultaba el fallo.
21. **`⏸` sale como emoji azul en Windows Terminal.** La fuente del terminal no lo
    tiene y el respaldo que encuentra Windows es Segoe UI Emoji, en color.
    `about.pause_glyph` pone `‖` en Windows: una celda, como `▶`. Comprobado que
    Consolas trae `‖` y no `⏸` (2026-09-24); la Cascadia de Windows Terminal está en
    `WindowsApps` y no se deja leer.
22. **Un sixel en Windows Terminal se ve sólo como una franja.** WT guarda el sixel en
    la rejilla de texto, como el VT340: escribir en una celda borra su trozo de imagen.
    `Artwork` mandaba la imagen en la primera línea y Textual pintaba después las
    líneas en blanco de debajo, que la borraban. En Windows
    (`artwork.sixel_erased_by_text`) va al final de la última línea, tras sus
    blancos, subiendo el cursor al origen de la caja y devolviéndolo con DECSC/DECRC
    (`artwork.sixel_from_below`). kitty no lo necesita: pinta por encima del texto.
    En Linux sigue como estaba; si foot o mlterm hacen lo mismo, el arreglo vale igual.
    En el menú de ajustes, Windows no ofrece `kitty` (`config_window._artworks`).
23. **Con eso, la carátula sixel parpadeaba a cada tecla.** Cada repintado de la caja
    son blancos (que borran la imagen) y luego la imagen, y Windows Terminal enseñaba
    el estado de en medio. Textual envuelve cada frame en la salida sincronizada
    (modo 2026) sólo si el terminal dice que la tiene, y **sólo lo pregunta en el
    driver de Linux**. `TidalAmp._ask_for_synchronized_output` hace la pregunta en
    Windows; la respuesta entra por el mismo `XTermParser` (el driver de Windows lee
    con `ENABLE_VIRTUAL_TERMINAL_INPUT`) y Textual la activa solo. Con
    `TIDALAMP_DEBUG=1`, el log dice «el terminal acepta frames enteros (modo 2026)»
    si contestó que sí: es lo primero que mirar si vuelve a parpadear.
24. **`karlstav.cava` no es portable.** Es un instalador: deja `cava.exe` en
    `%LOCALAPPDATA%\cava` y añade esa carpeta al PATH del usuario, que sólo ven los
    procesos que arrancan después (un terminal abierto antes no la ve). Se buscaba en
    `WinGet\Links`, donde no está, y la oferta de instalarlo salía en cada arranque.
    `backends/windows/cava.py` mira en las dos, como `mpv.py` para mpv. Comprobado
    en una instalación real (2026-09-24).

---

## 14. Qué hacer con `tidalamp-win`

**Hecho, de otra manera** (2026-09-23): el mantenedor borró el repositorio de GitHub y
la copia del disco, en lugar de archivarlo como proponía este apartado. No queda nada
que enlazar ni que mantener.

- Su `windows.md` fue la fuente de muchos detalles de este documento; no había nada en
  ese repo que no esté aquí o que no estuviera desfasado.
- No reservar el nombre `tidalamp-win` en PyPI: el paquete es `tidalamp` en todas las
  plataformas.

---

## 15. Estado

- [x] F0 · backends y fachadas, transporte extraído, `command` inyectable (Linux idéntico)
- [x] `stream.py` · `mkstemp` (PR aparte, arregla Linux también)
- [~] F1 · arranque en Windows. **Código escrito y comprobado desde Linux**
  (2026-09-23): rutas en `AppData`, `NamedPipe` con E/S solapada, búsqueda de
  `mpv.exe`, `CREATE_NO_WINDOW`, `mpris` y `desktop` neutros, `distro` con
  winget/scoop/choco, idioma por LCID, UTF-8 en la CLI, `dbus-fast` solo en Linux.
  `mypy --platform win32` limpio y la paridad de backends en tests. **Falta el
  criterio de hecho**, que solo se cumple en Windows: arrancar, reproducir y relanzar
  un `mpv.exe` matado. El pipe no ha corrido nunca; su primera prueba es F2.
- [x] F2 · suite en Windows y matriz de CI. **Verde en `windows-latest`** en 3.11 y
  3.14 y en el job `bare`, el 2026-09-23, al cuarto run (`462146d`). El named pipe
  funcionó a la primera; lo que fallaba eran tiempos de los tests, que en Linux
  pasaban por suerte: `settle` sin esperar a los workers, el navegador leído antes de
  cargar sus filas, un `pause` tras `resize_terminal`, y un `WaitForMultipleObjects`
  que vuelve unos ms antes. Los seis tests que simulaban con `chmod` un fallo de
  escritura hacen ahora que la escritura lance, y corren en los dos sistemas; con
  `@linux_only` quedan los que miran modos de fichero y el lanzador `.desktop`.
- [~] F3 · terminal: carátulas, sextantes, espectro, paleta. **Código y tests hechos**
  (2026-09-23). La detección de carátula y sextantes ya se portaba bien en Windows
  (medios bloques y cuadrantes en Windows Terminal y conhost; kitty y sextantes en
  WezTerm), y ahora lo fijan tests. cava: su build de Windows acepta `winscap` y manda
  el raw a stdout igual que en Linux (leído en su código), así que sólo cambia el
  método; sin consola, y `winget install karlstav.cava` en el aviso. La nota de la
  paleta no promete Omarchy en Windows. **Falta verlo**: portada y colores en Windows
  Terminal y en conhost, y el espectro de cava real (checklist §12).
- [~] F4 · audio WASAPI, permisos, acceso directo. **Código y tests hechos**
  (2026-09-23). `backends/windows/audio.py` pregunta a mpv (`audio-device`,
  `audio-out-params`) a través de `audio.use_player`, que en Linux no hace nada;
  `MANAGES_RATES` quita las filas de PipeWire y pone «Modo exclusivo» (`exclusive`,
  apagado por defecto, `--audio-exclusive=yes` al lanzar y `ao-reload` en caliente,
  sólo en Windows). `auth._tighten` no toca nada en Windows. El acceso directo
  `TidalAmp.lnk` en el menú Inicio, con la misma política que el `.desktop`, abre
  Windows Terminal si lo hay; PowerShell lo escribe con un script fijo que lee los
  valores del entorno. **Falta verlo**: 24/96 a 96 kHz con `exclusive`, las
  notificaciones sin él, y que el acceso directo aparezca y abra (checklist §12).
  - *Límite conocido:* en modo compartido, la línea OUT dice la frecuencia a la que
    mpv entrega (la del formato del dispositivo), no la de la pista, así que no
    avisa del remuestreo como en Linux.
- [~] F5 · SMTC. **Código y tests hechos, sin el spike** (2026-09-23).
  `backends/windows/media.py`: un `MediaPlayer` con su `CommandManager` apagado presta
  sus controles; título, artista, álbum, portada, estado y línea de tiempo al panel,
  sólo cuando cambian; teclas multimedia y la barra del panel vuelven al bucle de la app
  con `call_soon_threadsafe`. Paquetes modulares de pywinrt 3.2 (`winrt-runtime`,
  `winrt-Windows.Foundation`, `.Media`, `.Media.Playback`, `.Storage.Streams`), con
  wheels de 3.9 a 3.14, sólo en Windows. Sin ellos, o si WinRT falla, «controles
  multimedia no disponibles» y la música sigue. Los tests usan un WinRT falso. **Falta
  lo que el plan pedía primero**: ver en una máquina real que los controles de un
  `MediaPlayer` aparecen desde una app lanzada en un terminal y sin empaquetar. Si no,
  el plan B es la ventana oculta (§7.2).
- [x] F6 · `.exe` en el release. Construido en `windows-latest` y con la prueba de
  humo en verde (run `35947336411`, `1984aad`, 2026-09-24): `tidalamp.exe tui` sin
  sesión importa el reproductor entero y acaba en «login», y las hojas de estilo y los
  emblemas están. Zip de 18,6 MB. El primer intento falló porque el `.gitignore`
  excluía `*.spec` y la receta nunca había entrado en git. **Falta abrirlo** en una
  máquina sin Python (checklist §12).
- [~] F7 · documentación, skills, capturas. README («Windows (preview)», la pila de
  audio, SMTC, el acceso directo, la tabla de plataformas), CHANGELOG, CONTRIBUTING,
  `plan.md`, `next.md`, `publish.md`, `packaging/README.md` y las skills
  `tidalamp-mpv-ipc` y `tidalamp-mpris-contract` al día (2026-09-23). **Falta la
  captura** en Windows Terminal, que pide una máquina real.
- [x] `tidalamp-win` retirado: borrado de GitHub y del disco por el mantenedor
  (2026-09-23)
