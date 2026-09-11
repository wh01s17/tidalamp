"""The layout table: every entry complete and drawable."""

from __future__ import annotations

import unicodedata

import pytest

from tidalamp.app import TidalAmp
from tidalamp.layouts import DEFAULT_LAYOUT, LAYOUT_TABLE, layout_for
from tidalamp.theme import LAYOUTS

HINTS = "↵ reproducir"


def test_the_names_the_settings_offer_are_the_table_itself():
    assert tuple(LAYOUT_TABLE) == LAYOUTS
    assert LAYOUTS[0] == "quattro" == DEFAULT_LAYOUT.name
    for name, layout in LAYOUT_TABLE.items():
        assert layout.name == name


def test_an_unknown_layout_name_falls_back_to_the_default():
    assert layout_for("no-existe") is DEFAULT_LAYOUT


def test_every_layout_names_a_transport_the_app_can_draw():
    for layout in LAYOUT_TABLE.values():
        assert callable(getattr(TidalAmp, f"_transport_{layout.transport}", None)), (
            layout.name
        )


def test_every_heading_draws_at_any_width():
    for layout in LAYOUT_TABLE.values():
        for width in (10, 60, 200):
            assert layout.title(width), layout.name
            assert layout.queue_heading(width, HINTS), layout.name


def test_no_layout_draws_its_chrome_with_a_wide_glyph():
    """An emoji-presentation glyph (an anchor, say) takes two cells in most
    terminals while the heading is measured as one, and the hints behind it
    were pushed off the edge of the frame."""
    for layout in LAYOUT_TABLE.values():
        for text in (layout.title(80), layout.queue_heading(80, "")):
            wide = [c for c in text if unicodedata.east_asian_width(c) in ("W", "F")]
            assert not wide, f"{layout.name}: {wide}"


def test_every_themed_look_has_an_emblem_the_package_ships():
    """A small PNG in `tidalamp/emblems`, readable and at most 192 px a side;
    the looks without a theme have none, and every themed one has a line."""
    pil_image = pytest.importorskip("PIL.Image")

    from tidalamp.artwork import emblem_path
    from tidalamp.theme import PAIRED

    for layout in LAYOUT_TABLE.values():
        if layout.name not in PAIRED:
            assert not layout.emblem and layout.tagline is None, layout.name
            continue
        path = emblem_path(layout.emblem)
        assert path is not None, layout.name
        with pil_image.open(path) as image:
            assert max(image.size) <= 192, layout.name
            assert image.mode in ("RGBA", "RGB", "P"), layout.name
        assert layout.tagline and layout.tagline(), layout.name


def test_theme_names_are_shown_in_the_language_in_use():
    """The file keeps the name it always had; only the label follows the
    language, so a config written under one works under the other."""
    from tidalamp import i18n
    from tidalamp.layouts import label

    try:
        i18n.use("en")
        assert label("bosque") == "forest"
        assert label("unidad-morada") == "purple-unit"
        assert label("reggae") == "reggae"
        assert label("quattro") == "quattro"
        assert label("auto") == "auto"
        i18n.use("es")
        assert label("bosque") == "bosque"
        assert label("comodin") == "comodin"
    finally:
        i18n.refresh()
    assert LAYOUT_TABLE["bosque"].name == "bosque"
