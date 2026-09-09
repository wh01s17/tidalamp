"""Omarchy palette detection with a distro-neutral fallback."""

from __future__ import annotations

from pathlib import Path

from tidalamp.theme import (
    DEFAULT_COLORS,
    DEFAULT_PALETTE,
    available_palettes,
    load_palette,
    omarchy_colors_path,
)


def test_missing_omarchy_theme_uses_the_classic_palette(tmp_path):
    palette = load_palette(tmp_path / "missing.toml")

    assert palette is DEFAULT_PALETTE
    assert palette.colors == DEFAULT_COLORS
    assert palette["accent"] == "#00ff4c"


def test_active_omarchy_colors_map_to_tidalamp_semantics(tmp_path):
    colors = tmp_path / "colors.toml"
    colors.write_text(
        """
accent = "#11aa77"
selection = "#22bb88"
selection_background = "#16352d"
muted = "#445566"
background = "#101820"
dark_background = "#080c10"
darker_background = "#040608"
lighter_background = "#202c36"
foreground = "#d8e0dc"
dark_foreground = "#778880"
light_foreground = "#aabbcc"
bright_foreground = "#ffffff"
red = "#ff5555"
yellow = "#eebb44"
green = "#55dd88"
blue = "#5599ff"
bright_green = "#88ffaa"
""".strip(),
        encoding="utf-8",
    )

    palette = load_palette(colors)

    assert palette.source == "omarchy"
    assert palette["screen"] == "#040608"
    assert palette["panel"] == "#101820"
    assert palette["accent"] == "#11aa77"
    assert palette["active_foreground"] == "#101820"
    assert palette["container"] == "#5599ff"
    assert palette["eq_background"] == "#16352d"


def test_invalid_or_incomplete_omarchy_theme_falls_back_safely(tmp_path):
    malformed = tmp_path / "malformed.toml"
    malformed.write_text('accent = "not-a-colour"\nbackground = "#000000"')

    assert load_palette(malformed) is DEFAULT_PALETTE

    invalid_toml = tmp_path / "invalid.toml"
    invalid_toml.write_text('accent = "#00ff00"\n[')
    assert load_palette(invalid_toml) is DEFAULT_PALETTE


def test_minimal_omarchy_palette_never_mixes_in_classic_colors(tmp_path):
    colors = tmp_path / "colors.toml"
    colors.write_text(
        "\n".join(
            (
                'accent = "#112233"',
                'background = "#223344"',
                'foreground = "#ddeeff"',
            )
        ),
        encoding="utf-8",
    )

    palette = load_palette(colors)

    assert palette.source == "omarchy"
    assert palette["screen"] == "#223344"
    assert palette["input_border"] == "#112233"
    assert palette["danger"] == "#112233"
    assert palette["muted"] == "#ddeeff"
    assert set(palette.colors.values()) <= {"#112233", "#223344", "#ddeeff"}


def test_portable_built_in_palettes_do_not_need_omarchy():
    palette = load_palette(name="tokyo-night")

    assert palette.source == "builtin:tokyo-night"
    assert palette["accent"] == "#7aa2f7"
    assert palette["panel"] == "#1a1b26"


def test_a_custom_palette_uses_the_omarchy_colors_format(tmp_path):
    (tmp_path / "ocean.toml").write_text(
        'accent = "#11aacc"\nbackground = "#102030"\nforeground = "#ddeeff"\n',
        encoding="utf-8",
    )

    palette = load_palette(name="ocean", custom_dir=tmp_path)

    assert palette.source == "custom:ocean"
    assert palette["accent"] == "#11aacc"
    assert "ocean" in available_palettes(tmp_path)


def test_an_invalid_palette_name_falls_back_without_path_traversal(tmp_path):
    assert load_palette(name="../secret", custom_dir=tmp_path) is DEFAULT_PALETTE


def test_omarchy_path_honours_xdg_state_home():
    assert omarchy_colors_path(
        {"XDG_STATE_HOME": "/state"}, home=Path("/ignored")
    ) == Path("/state/omarchy/current/theme/colors.toml")
    assert omarchy_colors_path({}, home=Path("/home/test")) == Path(
        "/home/test/.local/state/omarchy/current/theme/colors.toml"
    )


def test_css_variable_names_are_namespaced():
    variables = DEFAULT_PALETTE.css_variables()

    assert variables["tidalamp-accent"] == "#00ff4c"
    assert variables["tidalamp-title-background"] == "#2b3a4a"
