"""Sextant cells: six pixels a cell, for the grid's covers where the terminal
draws the glyphs itself."""

from __future__ import annotations

import pytest

from tidalamp import artwork
from tidalamp.artwork import draws_sextants, sextant_cell, sextant_glyph

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (200, 30, 30)


@pytest.mark.parametrize(
    ("mask", "glyph"),
    [
        (0, " "),
        (1, "\U0001fb00"),  # BLOCK SEXTANT-1, the first of the range.
        (3, "\U0001fb02"),  # SEXTANT-12, the top pair.
        (20, "\U0001fb13"),
        (21, "▌"),  # The left half: older than the range, left out of it.
        (22, "\U0001fb14"),
        (41, "\U0001fb27"),
        (42, "▐"),
        (43, "\U0001fb28"),
        (62, "\U0001fb3b"),  # The last of the range.
        (63, "█"),
    ],
)
def test_every_pattern_has_its_glyph(mask, glyph):
    assert sextant_glyph(mask) == glyph


def test_the_sixty_two_glyphs_of_the_range_are_all_used_once():
    glyphs = {sextant_glyph(mask) for mask in range(64)}
    assert len(glyphs) == 64
    in_range = {g for g in glyphs if 0x1FB00 <= ord(g) <= 0x1FB3B}
    assert len(in_range) == 60


def test_two_colours_split_exactly_where_they_meet():
    """A white top row over black: the top pair lit, in white on black."""
    six = (WHITE, WHITE, BLACK, BLACK, BLACK, BLACK)
    assert sextant_cell(six) == ("\U0001fb02", WHITE, BLACK)


def test_the_lighter_side_is_the_glyph_whichever_pixel_starts():
    """Pixel 0 is always ground in the search; a light pixel 0 has to come
    out as the glyph all the same."""
    six = (WHITE, BLACK, BLACK, BLACK, BLACK, BLACK)
    assert sextant_cell(six) == ("\U0001fb00", WHITE, BLACK)


def test_a_flat_cell_is_a_space_in_its_colour():
    assert sextant_cell((RED,) * 6) == (" ", RED, RED)


def test_the_sampled_cover_has_one_cell_per_place():
    pytest.importorskip("PIL")
    from PIL import Image

    image = Image.new("RGB", (160, 160), RED)
    cells = artwork.sextant_cells(image, 16, 8)
    assert len(cells) == 8 and all(len(line) == 16 for line in cells)
    assert cells[0][0] == (" ", RED, RED)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"TERM": "xterm-kitty"}, True),
        ({"KITTY_WINDOW_ID": "1", "TERM": "xterm-256color"}, True),
        ({"TERM": "xterm-ghostty"}, True),
        ({"TERM_PROGRAM": "WezTerm", "TERM": "xterm-256color"}, True),
        ({"TERM": "foot"}, True),
        ({"TERM": "xterm-256color"}, False),
        ({"TERM": "alacritty"}, False),
        ({"TERM": "alacritty", "TIDALAMP_SEXTANTS": "1"}, True),
        ({"TERM": "xterm-kitty", "TIDALAMP_SEXTANTS": "0"}, False),
    ],
)
def test_sextants_only_where_the_terminal_draws_them(env, expected):
    assert draws_sextants(env) is expected
