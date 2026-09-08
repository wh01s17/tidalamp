"""Paths and user configuration.

Settings come from three places, and the first one that has an answer wins:

1. the environment (``TIDALAMP_QUALITY`` and friends), for a one-off run;
2. ``~/.config/tidalamp/config.toml``, for what you always want;
3. the defaults below.

TOML because Python reads it without a dependency, and because a config file
you can comment is worth more than one you cannot. Nothing here writes to it
except ``write_template()``, which the ``tidalamp config`` command calls: the
file belongs to the user, so the app reads it and leaves it alone.
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path

log = logging.getLogger("tidalamp.config")


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "tidalamp"
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "tidalamp"
STATE_DIR = _xdg("XDG_STATE_HOME", ".local/state") / "tidalamp"

SESSION_FILE = CONFIG_DIR / "session.json"
CONFIG_FILE = CONFIG_DIR / "config.toml"
IPC_SOCKET = CACHE_DIR / "mpv.sock"
QUEUE_FILE = STATE_DIR / "queue.json"
LOG_FILE = STATE_DIR / "tidalamp.log"


def read_file(path: Path | None = None) -> dict:
    """The config file as a dict. A missing or broken one is simply empty.

    A typo in the config must not stop the music: it goes to the log and the
    defaults take over.
    """
    path = CONFIG_FILE if path is None else path
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.warning("no se pudo leer %s (%s); se usan los valores por defecto", path, exc)
        return {}


FILE = read_file()


def setting(name: str, env: str, default: str) -> str:
    """Resolve one setting: environment, then file, then default."""
    from_env = os.environ.get(env)
    if from_env:
        return from_env
    value = FILE.get(name)
    return default if value is None else str(value)


def flag(name: str, env: str) -> bool:
    if os.environ.get(env):
        return True
    return bool(FILE.get(name, False))


# TIDAL quality to request. HIGH/LOW come back as plain URLs that mpv plays
# directly; HI_RES_LOSSLESS arrives as a segmented DASH manifest, which we
# translate to HLS before handing it over.
#
# HI_RES_LOSSLESS and not LOSSLESS, which is what this used to be. Measured
# against a real account on 2026-09-08, asking the device-flow client for
# LOSSLESS gets HIGH back — every time, even on a track TIDAL itself tags as
# LOSSLESS. Asking for HI_RES_LOSSLESS gets FLAC 24/96 where the track has it
# and HIGH where it does not, so it is strictly better than the old default,
# which never once produced a lossless stream.
DEFAULT_QUALITY = setting("quality", "TIDALAMP_QUALITY", "HI_RES_LOSSLESS")

# How to draw the cover: auto, kitty, sixel, blocks or off. "auto" means the
# guess in artwork.detect_protocol.
ARTWORK = setting("artwork", "TIDALAMP_ART", "auto")

DEBUG = flag("debug", "TIDALAMP_DEBUG")

# Key overrides, action name to key. Empty means "the defaults in app.py".
KEYS: dict[str, str] = {
    str(action): str(key) for action, key in (FILE.get("keys") or {}).items()
}


TEMPLATE = '''\
# Configuración de tidalamp. Todo es opcional: lo que no esté aquí usa su valor
# por defecto, y una variable de entorno gana siempre sobre este fichero.

# LOW, HIGH, LOSSLESS o HI_RES_LOSSLESS.
# Ojo: pedir LOSSLESS al cliente del device flow devuelve HIGH siempre. Ver el
# README, sección «Calidad».
quality = "HI_RES_LOSSLESS"

# Cómo dibujar la carátula: auto, kitty, sixel, blocks u off.
artwork = "auto"

# Registro en ~/.local/state/tidalamp/tidalamp.log.
debug = false

# Teclas. La izquierda es la acción, la derecha la tecla; varias se separan con
# comas. Las de navegación (flechas, RePág/AvPág, Enter, Esc) no se cambian.
[keys]
%(keys)s
'''


def write_template(path: Path | None = None) -> Path:
    """Write a commented config file. Never overwrites an existing one."""
    from .app import DEFAULT_KEYS

    path = CONFIG_FILE if path is None else path
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = "\n".join(f'# {action} = "{key}"' for action, key in DEFAULT_KEYS.items())
    path.write_text(TEMPLATE % {"keys": keys}, encoding="utf-8")
    return path


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    """Log to ``LOG_FILE`` when debugging is on.

    The TUI owns the terminal, so there is nowhere to print: debugging goes to
    a file or nowhere. Off by default, since a long session would otherwise
    keep writing while nobody reads it.
    """
    if not DEBUG:
        # The package already installs a NullHandler, which is what keeps
        # logging's last-resort handler off the TUI.
        return
    ensure_dirs()
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("tidalamp")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
