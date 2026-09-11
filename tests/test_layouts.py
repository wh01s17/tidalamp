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


def test_every_themed_look_has_an_emblem_that_fits_the_cover_box():
    """Up to forty pixels a side, shrunk to the cover box when drawn; every
    letter must be a palette role or see-through, and every row as wide."""
    from tidalamp.theme import PAIRED
    from tidalamp.widgets import EMBLEM_ROLES

    for layout in LAYOUT_TABLE.values():
        if layout.name not in PAIRED:
            assert not layout.emblem and layout.tagline is None, layout.name
            continue
        rows = layout.emblem
        assert rows and len(rows) <= 40, layout.name
        assert len({len(row) for row in rows}) == 1, layout.name
        assert len(rows[0]) <= 40, layout.name
        assert set("".join(rows)) <= set(EMBLEM_ROLES) | {"."}, layout.name
        assert layout.tagline and layout.tagline(), layout.name


def test_a_large_emblem_shrinks_to_the_cover_box_and_keeps_its_details():
    """A 40-pixel drawing in the smallest box: eighteen pixels square, with
    the thin eye of the unit still there after the reduction."""
    from tidalamp.widgets import shrink

    eva = LAYOUT_TABLE["unidad-morada"].emblem
    small = shrink(eva, 18, 18)
    assert len(small) <= 18 and len(small[0]) <= 18
    assert "A" in "".join(small), "el ojo sobrevive"
