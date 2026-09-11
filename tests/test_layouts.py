"""The layout table: every entry complete and drawable."""

from __future__ import annotations

import unicodedata

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
