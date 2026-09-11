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

from .layouts import LAYOUT_TABLE

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
    # The themed palettes, one per themed layout of the same name (see
    # `layouts.py` and `PAIRED` below). Each also spells `dark_foreground`,
    # for the reason `black` gives above: quiet text needs its own grey.
    # A purple giant: lime for what is lit, orange for warnings.
    "unidad-morada": {
        "accent": "#9bff4d",
        "background": "#1c1128",
        "foreground": "#e6dcf7",
        "dark_foreground": "#a896c4",
        "muted": "#6a4f8a",
        "dark_background": "#120a1a",
        "lighter_background": "#2e1d44",
        "red": "#ff6a1f",
        "yellow": "#ffb000",
        "green": "#9bff4d",
        "blue": "#a07de0",
    },
    # Straw yellow on open sea.
    "pirata": {
        "accent": "#ffd23f",
        "background": "#0e2a3f",
        "foreground": "#f4ecd8",
        "dark_foreground": "#a9bccb",
        "muted": "#4a7391",
        "dark_background": "#081c2b",
        "lighter_background": "#173e5c",
        "red": "#ef4f5a",
        "yellow": "#ffd23f",
        "green": "#57cc99",
        "blue": "#4cc9f0",
    },
    # A black notebook: white pages, one red that matters.
    "cuaderno": {
        "accent": "#e5383b",
        "background": "#0b0b0b",
        "foreground": "#ededed",
        "dark_foreground": "#8a8a8a",
        "muted": "#444444",
        "dark_background": "#000000",
        "lighter_background": "#1a1a1a",
        "red": "#e5383b",
        "yellow": "#cfcfcf",
        "green": "#bdbdbd",
        "blue": "#8f8f8f",
    },
    # Night city neon: yellow, cyan and a hard red.
    "neon-noir": {
        "accent": "#fcee0a",
        "background": "#0b0b14",
        "foreground": "#e4f6f8",
        "dark_foreground": "#7fa3aa",
        "muted": "#3a3f5c",
        "dark_background": "#05050a",
        "lighter_background": "#1a1a2e",
        "red": "#ff2a55",
        "yellow": "#fcee0a",
        "green": "#00f0c8",
        "blue": "#00e0ff",
    },
    # Old gold on a dark forest.
    "runas": {
        "accent": "#d4a93a",
        "background": "#15170f",
        "foreground": "#e8dcc0",
        "dark_foreground": "#a89d80",
        "muted": "#5c5540",
        "dark_background": "#0c0d08",
        "lighter_background": "#27291c",
        "red": "#c0503a",
        "yellow": "#e0b84c",
        "green": "#8aab62",
        "blue": "#7d9ab4",
    },
    # Red, gold and green on black.
    "reggae": {
        "accent": "#f7d117",
        "background": "#10100a",
        "foreground": "#f2efe0",
        "dark_foreground": "#aaa68c",
        "muted": "#4f4a2a",
        "dark_background": "#080805",
        "lighter_background": "#1f1f14",
        "red": "#e8412c",
        "yellow": "#f7d117",
        "green": "#2fbf5a",
        "blue": "#6fc98a",
    },
    # The wild card: a purple suit and green hair.
    "comodin": {
        "accent": "#b77cff",
        "background": "#150e1d",
        "foreground": "#ebe4d4",
        "dark_foreground": "#a99bb8",
        "muted": "#5a3f73",
        "dark_background": "#0c0712",
        "lighter_background": "#2a1a3a",
        "red": "#ef4444",
        "yellow": "#f0a830",
        "green": "#46d974",
        "blue": "#b77cff",
    },
    # Crimson and violet under a pointed arch.
    "gotico": {
        "accent": "#d63a5c",
        "background": "#0e0a0f",
        "foreground": "#dcd2de",
        "dark_foreground": "#9a8c9e",
        "muted": "#4a3a4d",
        "dark_background": "#070507",
        "lighter_background": "#1e1522",
        "red": "#d63a5c",
        "yellow": "#c2a472",
        "green": "#a08fb3",
        "blue": "#8a74b8",
    },
    # Bone on black, and blood red.
    "death-metal": {
        "accent": "#e0102a",
        "background": "#070707",
        "foreground": "#ddd6c6",
        "dark_foreground": "#8f887a",
        "muted": "#3d3a35",
        "dark_background": "#000000",
        "lighter_background": "#171513",
        "red": "#ff2a3d",
        "yellow": "#a69c86",
        "green": "#c2baa8",
        "blue": "#847e72",
    },
    # Leaf green on moss, sun for warnings, earth red, and a clear sky.
    "bosque": {
        "accent": "#86cc5a",
        "background": "#0f1a12",
        "foreground": "#e4ecd6",
        "dark_foreground": "#9bab8e",
        "muted": "#3f5a3a",
        "dark_background": "#09110b",
        "lighter_background": "#1b2c1e",
        "red": "#d0683f",
        "yellow": "#e8c547",
        "green": "#86cc5a",
        "blue": "#6fb7d6",
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

# The layout names, listed once so the settings screen, the config template
# and the app itself cannot drift apart. What each one looks like is data in
# `layouts.py`. Colour is the other axis and lives in the palettes above: any
# layout works with any palette.
LAYOUTS = tuple(LAYOUT_TABLE)

# A themed look is a layout and a built-in palette with the same name, and
# choosing the layout in the settings writes that palette once. From then on
# the palette is free again. Pairs are declared here and not inferred, because
# a name shared by accident would recolour a layout for everyone: a `nova`
# palette added one day must not quietly change what `theme = "nova"` looks
# like. A test holds the shared names to exactly this set.
PAIRED: frozenset[str] = frozenset(
    {
        "unidad-morada",
        "pirata",
        "cuaderno",
        "neon-noir",
        "runas",
        "reggae",
        "comodin",
        "gotico",
        "death-metal",
        "bosque",
    }
)


def paired_palette(layout: str) -> str | None:
    """The palette that comes with `layout`, if it was declared with one."""
    return layout if layout in PAIRED else None


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast between two `#rrggbb` colours, from 1 to 21.

    The alpha byte an eight-digit colour may carry is ignored: the terminal
    draws the ground opaque whatever the palette says.
    """

    def luminance(color: str) -> float:
        channels = (int(color[index : index + 2], 16) / 255 for index in (1, 3, 5))
        r, g, b = (
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        )
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


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
