"""Paths and user configuration."""

from __future__ import annotations

import os
from pathlib import Path


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "tidalamp"
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "tidalamp"
STATE_DIR = _xdg("XDG_STATE_HOME", ".local/state") / "tidalamp"

SESSION_FILE = CONFIG_DIR / "session.json"
IPC_SOCKET = CACHE_DIR / "mpv.sock"
QUEUE_FILE = STATE_DIR / "queue.json"
LOG_FILE = STATE_DIR / "tidalamp.log"

# TIDAL quality to request. HIGH/LOW come back as plain URLs that mpv plays
# directly; LOSSLESS and HI_RES_LOSSLESS arrive as segmented DASH manifests,
# which we translate to HLS before handing them over.
DEFAULT_QUALITY = os.environ.get("TIDALAMP_QUALITY", "LOSSLESS")


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    """Log to ``LOG_FILE`` when TIDALAMP_DEBUG is set.

    The TUI owns the terminal, so there is nowhere to print: debugging goes to
    a file or nowhere. Off by default, since a long session would otherwise
    keep writing while nobody reads it.
    """
    import logging

    if not os.environ.get("TIDALAMP_DEBUG"):
        # The package already installs a NullHandler, which is what keeps
        # logging's last-resort handler off the TUI.
        return
    ensure_dirs()
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("tidalamp")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
