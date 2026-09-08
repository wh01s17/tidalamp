"""Runtime colour palette with optional Omarchy theme integration.

Omarchy stages the active theme at
``$XDG_STATE_HOME/omarchy/current/theme/colors.toml``.  Reading that file is
enough to follow stock, overlaid, and user themes without invoking Omarchy or
depending on it.  Everywhere else, and for malformed files, TidalAmp keeps its
classic Winamp-inspired palette.
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z")

DEFAULT_COLORS = MappingProxyType(
    {
        "screen": "#000000",
        "panel": "#1c1c22",
        "border": "#4a4a55",
        "title_background": "#2b3a4a",
        "title_foreground": "#b8c8d8",
        "display_background": "#000000",
        "muted": "#7f9f87",
        "track_background": "#14141a",
        "transport_background": "#2a2a33",
        "transport_foreground": "#9fb8a7",
        "inactive": "#718078",
        "status": "#6f8f77",
        "accent": "#00ff4c",
        "active_foreground": "#000000",
        "input_border": "#3f5f47",
        "body": "#9fcfa7",
        "empty": "#5f7f67",
        "container": "#9fd8ff",
        "playable": "#7fbf8f",
        "danger": "#ff3b3b",
        "warning": "#ffd500",
        "peak": "#8fd8a0",
        "bar_empty": "#2f3f35",
        "eq_background": "#123a1c",
        "eq_inactive": "#4f6f57",
    }
)

_OMARCHY_KEYS = {
    "screen": ("darker_background", "dark_background", "background"),
    "panel": ("background",),
    "border": ("muted", "dark_foreground", "foreground"),
    "title_background": ("lighter_background", "background"),
    "title_foreground": ("bright_foreground", "foreground"),
    "display_background": ("dark_background", "background"),
    "muted": ("dark_foreground", "foreground"),
    "track_background": ("dark_background", "background"),
    "transport_background": ("lighter_background", "background"),
    "transport_foreground": ("light_foreground", "foreground"),
    "inactive": ("dark_foreground", "foreground"),
    "status": ("dark_foreground", "foreground"),
    "accent": ("accent",),
    "active_foreground": ("background",),
    "input_border": ("selection", "accent"),
    "body": ("foreground",),
    "empty": ("dark_foreground", "foreground"),
    "container": ("blue", "cyan", "accent"),
    "playable": ("green", "foreground"),
    "danger": ("red", "accent"),
    "warning": ("yellow", "accent"),
    "peak": ("bright_green", "green", "accent"),
    "bar_empty": ("muted", "dark_foreground", "foreground"),
    "eq_background": (
        "selection_background",
        "lighter_background",
        "dark_background",
        "background",
    ),
    "eq_inactive": ("dark_foreground", "foreground"),
}


@dataclass(frozen=True)
class ThemePalette:
    colors: Mapping[str, str]
    source: str = "classic"

    def __getitem__(self, name: str) -> str:
        return self.colors[name]

    def css_variables(self) -> dict[str, str]:
        return {
            f"tidalamp-{name.replace('_', '-')}": value
            for name, value in self.colors.items()
        }


DEFAULT_PALETTE = ThemePalette(DEFAULT_COLORS)


def omarchy_colors_path(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    env = os.environ if environ is None else environ
    state_home = env.get("XDG_STATE_HOME")
    base = (
        Path(state_home).expanduser()
        if state_home
        else (home or Path.home()) / ".local/state"
    )
    return base / "omarchy/current/theme/colors.toml"


def _valid_color(value: Any) -> str | None:
    return value if isinstance(value, str) and _HEX_COLOR.fullmatch(value) else None


def load_palette(path: Path | None = None) -> ThemePalette:
    """Load the active Omarchy palette, or return the exact classic fallback."""
    colors_path = path or omarchy_colors_path()
    try:
        with colors_path.open("rb") as source:
            omarchy = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT_PALETTE

    accent = _valid_color(omarchy.get("accent"))
    background = _valid_color(omarchy.get("background"))
    foreground = _valid_color(omarchy.get("foreground"))
    if not (accent and background and foreground):
        return DEFAULT_PALETTE

    colors: dict[str, str] = {}
    for target, source_names in _OMARCHY_KEYS.items():
        colors[target] = next(
            value
            for source_name in source_names
            if (value := _valid_color(omarchy.get(source_name))) is not None
        )
    return ThemePalette(MappingProxyType(colors), source="omarchy")


def palette_for(owner: Any) -> ThemePalette:
    """Resolve an app/widget palette while remaining safe for detached widgets."""
    if palette := getattr(owner, "tidalamp_palette", None):
        return palette
    try:
        return getattr(owner.app, "tidalamp_palette", DEFAULT_PALETTE)
    except RuntimeError:
        return DEFAULT_PALETTE
