"""Runtime colour palette with optional Omarchy theme integration.

Omarchy stages the active theme at
``$XDG_STATE_HOME/omarchy/current/theme/colors.toml``.  Reading that file is
enough to follow stock, overlaid, and user themes without invoking Omarchy or
depending on it.  Everywhere else, and for malformed files, TidalAmp keeps its
classic green-on-black palette.
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

# Portable presets use the same small colour vocabulary as Omarchy's
# ``colors.toml``. They are available on every Linux distribution; ``auto``
# remains the bridge to the active Omarchy theme when that file exists.
_BUILTIN_SOURCES: dict[str, dict[str, str]] = {
    "tokyo-night": {
        "accent": "#7aa2f7",
        "background": "#1a1b26",
        "foreground": "#c0caf5",
        "muted": "#565f89",
        "dark_background": "#16161e",
        "lighter_background": "#24283b",
        "red": "#f7768e",
        "yellow": "#e0af68",
        "green": "#9ece6a",
        "blue": "#7aa2f7",
    },
    "catppuccin": {
        "accent": "#cba6f7",
        "background": "#1e1e2e",
        "foreground": "#cdd6f4",
        "muted": "#6c7086",
        "dark_background": "#11111b",
        "lighter_background": "#313244",
        "red": "#f38ba8",
        "yellow": "#f9e2af",
        "green": "#a6e3a1",
        "blue": "#89b4fa",
    },
    "nord": {
        "accent": "#88c0d0",
        "background": "#2e3440",
        "foreground": "#d8dee9",
        "muted": "#4c566a",
        "dark_background": "#242933",
        "lighter_background": "#3b4252",
        "red": "#bf616a",
        "yellow": "#ebcb8b",
        "green": "#a3be8c",
        "blue": "#81a1c1",
    },
    "gruvbox": {
        "accent": "#d79921",
        "background": "#282828",
        "foreground": "#ebdbb2",
        "muted": "#928374",
        "dark_background": "#1d2021",
        "lighter_background": "#3c3836",
        "red": "#cc241d",
        "yellow": "#d79921",
        "green": "#98971a",
        "blue": "#458588",
    },
    # Black on black, with everything else carried by how light a grey is.
    # It spells out more of the vocabulary than the palettes above, which give
    # only the ten keys they had to: with no `dark_foreground`, the secondary
    # text (status, empty lists, inactive labels, the equaliser's idle bands)
    # falls back to plain `foreground`, and a monochrome palette where the
    # quiet text is as bright as the loud text has nothing left to say with.
    # `red`, `yellow`, `green` and `blue` keep their jobs — danger, warning,
    # playable rows, containers — and become four greys, brightest for the one
    # that matters most, because lightness is the only axis here.
    "black": {
        "accent": "#f5f5f5",
        "background": "#000000",
        "foreground": "#e6e6e6",
        "muted": "#3a3a3a",
        "dark_foreground": "#8a8a8a",
        "light_foreground": "#cfcfcf",
        "bright_foreground": "#ffffff",
        "dark_background": "#000000",
        "lighter_background": "#141414",
        "selection": "#5a5a5a",
        "red": "#ffffff",
        "yellow": "#bdbdbd",
        "green": "#d0d0d0",
        "bright_green": "#ffffff",
        "blue": "#9a9a9a",
    },
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

# The three layouts, listed once so the settings screen, the config template
# and the app itself cannot drift apart. Colour is the other axis and lives in
# the palettes above: any layout works with any palette.
#
#   quattro  a flat, modern TUI treatment; the default
#   retro    the 1997 skin, as far as a terminal can go: square keys, ruled
#            title bars and a centred playlist window heading
#   nova     no frames at all, one flat ground, state carried by colour
#   ascii     a terminal before it had box drawing: `[ z << ]` keys, rules
#             made of `=` and `-`, and no glyph the chrome cannot type
LAYOUTS = ("quattro", "retro", "nova", "ascii")


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


def palette_dir(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """Where portable user palettes live as Omarchy-compatible TOML files."""
    env = os.environ if environ is None else environ
    config_home = env.get("XDG_CONFIG_HOME")
    base = (
        Path(config_home).expanduser()
        if config_home
        else (home or Path.home()) / ".config"
    )
    return base / "tidalamp/palettes"


def _valid_color(value: Any) -> str | None:
    return value if isinstance(value, str) and _HEX_COLOR.fullmatch(value) else None


def _from_source(values: Mapping[str, Any], source: str) -> ThemePalette | None:
    accent = _valid_color(values.get("accent"))
    background = _valid_color(values.get("background"))
    foreground = _valid_color(values.get("foreground"))
    if not (accent and background and foreground):
        return None

    colors: dict[str, str] = {}
    for target, source_names in _OMARCHY_KEYS.items():
        colors[target] = next(
            value
            for source_name in source_names
            if (value := _valid_color(values.get(source_name))) is not None
        )
    return ThemePalette(MappingProxyType(colors), source=source)


def _read_palette(path: Path, source: str) -> ThemePalette | None:
    try:
        with path.open("rb") as handle:
            values = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return _from_source(values, source)


def available_palettes(path: Path | None = None) -> tuple[str, ...]:
    """Built-ins plus safe custom palette slugs, in stable UI order."""
    custom_dir = path or palette_dir()
    try:
        custom = sorted(
            candidate.stem
            for candidate in custom_dir.glob("*.toml")
            if re.fullmatch(r"[A-Za-z0-9_-]+", candidate.stem)
        )
    except OSError:
        custom = []
    base = ("auto", "classic", *_BUILTIN_SOURCES)
    return tuple(dict.fromkeys((*base, *custom)))


def load_palette(
    path: Path | None = None,
    *,
    name: str = "auto",
    custom_dir: Path | None = None,
) -> ThemePalette:
    """Load an automatic, built-in or portable custom semantic palette.

    ``path`` keeps the direct-file API used by probes and tests. With
    ``name='auto'`` the active Omarchy palette wins and classic is the safe
    fallback. Custom files use Omarchy's ``colors.toml`` vocabulary and live
    under ``~/.config/tidalamp/palettes``.
    """
    if path is not None:
        return _read_palette(path, "omarchy") or DEFAULT_PALETTE

    chosen = name.strip().lower()
    if chosen == "auto":
        return _read_palette(omarchy_colors_path(), "omarchy") or DEFAULT_PALETTE
    if chosen == "classic":
        return DEFAULT_PALETTE
    if chosen in _BUILTIN_SOURCES:
        return (
            _from_source(_BUILTIN_SOURCES[chosen], f"builtin:{chosen}") or DEFAULT_PALETTE
        )
    if not re.fullmatch(r"[a-z0-9_-]+", chosen):
        return DEFAULT_PALETTE
    directory = custom_dir or palette_dir()
    return (
        _read_palette(directory / f"{chosen}.toml", f"custom:{chosen}") or DEFAULT_PALETTE
    )


def palette_for(owner: Any) -> ThemePalette:
    """Resolve an app/widget palette while remaining safe for detached widgets."""
    if palette := getattr(owner, "tidalamp_palette", None):
        return palette
    try:
        return getattr(owner.app, "tidalamp_palette", DEFAULT_PALETTE)
    except RuntimeError:
        return DEFAULT_PALETTE
