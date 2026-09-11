"""Omarchy palette detection with a distro-neutral fallback."""

from __future__ import annotations

from pathlib import Path

from tidalamp.theme import (
    _BUILTIN_SOURCES,
    DEFAULT_COLORS,
    DEFAULT_PALETTE,
    LAYOUTS,
    PAIRED,
    available_palettes,
    contrast_ratio,
    load_palette,
    omarchy_colors_path,
    paired_palette,
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


def test_the_black_palette_is_black_and_grey_all_the_way_down():
    """Black ground, and every other colour a grey: hue is not the axis here,
    lightness is, so a stray blue would be the only coloured thing on screen."""
    palette = load_palette(name="black")

    assert palette.source == "builtin:black"
    assert palette["screen"] == "#000000"
    assert palette["panel"] == "#000000"
    assert palette["display_background"] == "#000000"
    for name, value in palette.colors.items():
        red, green, blue = value[1:3], value[3:5], value[5:7]
        assert red == green == blue, f"{name} = {value} no es un gris"

    # The quiet text has to be quieter than the loud text, which is the only
    # thing left to say it with. Without a `dark_foreground` in the source,
    # both would come out as plain `foreground`.
    def level(name: str) -> int:
        return int(palette[name][1:3], 16)

    assert level("status") < level("body") < level("accent")
    assert level("border") < level("body")
    assert "black" in available_palettes()


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


def test_a_layout_and_a_palette_share_a_name_only_when_declared():
    """Pairing is by name, so a shared name means something.

    A palette called `nova` added one day would recolour the `nova` layout for
    everyone who picks it. Every shared name has to be in `PAIRED`, and every
    pair has to exist on both sides.
    """
    assert set(LAYOUTS) & set(_BUILTIN_SOURCES) == PAIRED
    for name in PAIRED:
        assert paired_palette(name) == name
    for name in set(LAYOUTS) - PAIRED:
        assert paired_palette(name) is None


def test_contrast_ratio_matches_the_wcag_endpoints():
    assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert contrast_ratio("#777777", "#777777") == 1.0
    # Order does not matter, and an alpha byte is ignored.
    assert contrast_ratio("#ffffff", "#000000cc") == contrast_ratio("#000000", "#ffffff")


def test_every_shipped_palette_stays_readable():
    """Half the themes people ask for lean black on black.

    The body text against the ground is held to WCAG AA for text (4.5), and
    the accent, which lights buttons and the cursor, to AA for interface
    elements (3.0). A palette that fails is pretty in a screenshot and
    useless in a terminal.
    """
    for name in ("classic", *_BUILTIN_SOURCES):
        palette = load_palette(name=name)
        assert len(palette.colors) == len(DEFAULT_COLORS), name
        screen = palette["screen"]
        assert contrast_ratio(palette["body"], screen) >= 4.5, f"{name}: body"
        assert contrast_ratio(palette["accent"], screen) >= 3.0, f"{name}: accent"
