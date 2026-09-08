"""Paths and user configuration."""

from __future__ import annotations

import os
from pathlib import Path


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "tidalamp"
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "tidalamp"

SESSION_FILE = CONFIG_DIR / "session.json"
IPC_SOCKET = CACHE_DIR / "mpv.sock"

# TIDAL quality to request. HIGH/LOW come back as plain URLs that mpv plays
# directly; LOSSLESS and HI_RES_LOSSLESS arrive as segmented DASH manifests,
# which we translate to HLS before handing them over.
DEFAULT_QUALITY = os.environ.get("TIDALAMP_QUALITY", "LOSSLESS")


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
