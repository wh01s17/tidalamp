"""Paths and user configuration.

Settings come from three places, and the first one that has an answer wins:

1. the environment (``TIDALAMP_QUALITY`` and friends), for a one-off run;
2. ``~/.config/tidalamp/config.toml``, for what you always want;
3. the defaults below.

TOML because Python reads it without a dependency, and because a config file
you can comment is worth more than one you cannot. That is also why writing is
done a line at a time by ``set_option()`` rather than by dumping a dict back:
a round trip through a parser would return the settings and throw away every
comment the user put around them.

An environment variable still wins over the file, so a setting the config
screen writes can be shadowed by one. ``overridden()`` reports that, because
a screen that showed a value the app is not using would be lying.
"""

from __future__ import annotations

import logging
import os
import re
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


# Every setting the file carries: its name, the variable that overrides it,
# and what it falls back to. The config screen renders this, `set_option`
# validates against it, and the template is generated from it, so a setting
# added here shows up in all three at once.
ENV_VARS: dict[str, str] = {
    "quality": "TIDALAMP_QUALITY",
    "artwork": "TIDALAMP_ART",
    "language": "TIDALAMP_LANG",
    "columns": "TIDALAMP_COLUMNS",
    "theme": "TIDALAMP_THEME",
    "palette": "TIDALAMP_PALETTE",
    "debug": "TIDALAMP_DEBUG",
}


def overridden(name: str) -> str | None:
    """The environment variable shadowing ``name``, or None.

    The file is not the last word: `TIDALAMP_QUALITY=LOW tidalamp` beats
    whatever is written down, and a screen that did not say so would show a
    value the app is not using.
    """
    variable = ENV_VARS.get(name)
    if variable and os.environ.get(variable):
        return variable
    return None


def setting(name: str, env: str, default: str) -> str:
    """Resolve one setting: environment, then file, then default."""
    from_env = os.environ.get(env)
    if from_env:
        return from_env
    value = FILE.get(name)
    return default if value is None else str(value)


def columns() -> tuple[str, ...]:
    """The queue's column list, split and cleaned.

    Unknown names are dropped rather than raising: this comes from a file the
    user edits by hand, and a typo should cost that one column, not the app.
    """
    # Absolute, not relative: tests load this file as a standalone module to
    # get a private copy, and a relative import has no package to resolve.
    from tidalamp.columns import NAMES

    raw = setting("columns", "TIDALAMP_COLUMNS", DEFAULT_COLUMNS)
    wanted = [part.strip().lower() for part in raw.split(",")]
    return tuple(dict.fromkeys(name for name in wanted if name in NAMES))


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

# "auto" follows the locale; "es" or "en" pin it. Until now the language was
# only ever read from $LANG, which is ambient rather than chosen: it made the
# one setting a user could not write down.
LANGUAGE = setting("language", "TIDALAMP_LANG", "auto")

# Layout and colour are deliberately independent. Quattro is a flatter,
# modern TUI treatment; winamp retains the framed transport. ``auto`` follows
# an active Omarchy palette and falls back to the built-in classic colours.
THEME = setting("theme", "TIDALAMP_THEME", "quattro")
PALETTE = setting("palette", "TIDALAMP_PALETTE", "auto")

# Which metadata columns the queue draws, in the order they were chosen. A
# comma-separated string rather than a TOML array so that it reads and writes
# through the same three functions as every other setting, and so that
# TIDALAMP_COLUMNS="artist,year" works from a shell without quoting a list.
DEFAULT_COLUMNS = ",".join(("artist", "album", "year", "duration"))
COLUMNS = columns()

DEBUG = flag("debug", "TIDALAMP_DEBUG")

# Key overrides, action name to key. Empty means "the defaults in app.py".
KEYS: dict[str, str] = {
    str(action): str(key) for action, key in (FILE.get("keys") or {}).items()
}


def write_template(path: Path | None = None) -> Path:
    """Write a commented config file. Never overwrites an existing one."""
    from .app import DEFAULT_KEYS
    from .i18n import config_template

    path = CONFIG_FILE if path is None else path
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = "\n".join(f'# {action} = "{key}"' for action, key in DEFAULT_KEYS.items())
    path.write_text(config_template() % {"keys": keys}, encoding="utf-8")
    return path


# Everything above [keys] is a plain `name = value` line; the writer only ever
# touches that part, so a key override is never mistaken for a setting.
_SECTION = re.compile(r"^\s*\[")


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_option(name: str, value: object, path: Path | None = None) -> Path:
    """Persist one setting, leaving every comment in the file where it was.

    The template ships each setting commented out, so an existing `# quality =`
    line is uncommented in place rather than a second one being appended: the
    user keeps the explanation that was written above it.
    """
    path = CONFIG_FILE if path is None else path
    write_template(path)
    lines = path.read_text(encoding="utf-8").splitlines()

    written = f"{name} = {_toml(value)}"
    pattern = re.compile(rf"^\s*#?\s*{re.escape(name)}\s*=")
    for index, line in enumerate(lines):
        if _SECTION.match(line):
            # Past the first section header; settings do not live down here.
            lines[index:index] = [written, ""]
            break
        if pattern.match(line):
            lines[index] = written
            break
    else:
        lines.append(written)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if path == CONFIG_FILE:
        reload()
    return path


def reload() -> None:
    """Re-read the file into the module globals, after `set_option` wrote it.

    The settings are module attributes rather than a dict so that reading one
    stays a plain name lookup; the cost is this function, and that a consumer
    doing `from .config import DEFAULT_QUALITY` keeps the value it imported.
    Those consumers read `config.DEFAULT_QUALITY` instead — see stream.py.
    """
    global FILE, DEFAULT_QUALITY, ARTWORK, LANGUAGE, THEME, PALETTE, COLUMNS
    global DEBUG, KEYS
    FILE = read_file()
    DEFAULT_QUALITY = setting("quality", "TIDALAMP_QUALITY", "HI_RES_LOSSLESS")
    ARTWORK = setting("artwork", "TIDALAMP_ART", "auto")
    LANGUAGE = setting("language", "TIDALAMP_LANG", "auto")
    THEME = setting("theme", "TIDALAMP_THEME", "quattro")
    PALETTE = setting("palette", "TIDALAMP_PALETTE", "auto")
    COLUMNS = columns()
    DEBUG = flag("debug", "TIDALAMP_DEBUG")
    KEYS = {str(action): str(key) for action, key in (FILE.get("keys") or {}).items()}


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
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger = logging.getLogger("tidalamp")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
