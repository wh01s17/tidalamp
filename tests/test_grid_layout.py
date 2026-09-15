"""How the grid's tiles share a line: the slack in the gaps, not at the end."""

from __future__ import annotations

from tidalamp.screens.grid import spread


def test_the_slack_goes_into_the_gaps_and_the_last_tile_meets_the_edge():
    """Seen on a real terminal: eight tiles to the left and a column's worth
    of empty band on the right."""
    lead, gaps = spread(width=150, columns=8, tile=16, gap=2)

    assert lead == 0
    assert len(gaps) == 7
    assert 8 * 16 + sum(gaps) == 150
    assert max(gaps) - min(gaps) <= 1


def test_a_line_that_fits_exactly_keeps_the_plain_gap():
    assert spread(width=16 * 3 + 2 * 2, columns=3, tile=16, gap=2) == (0, [2, 2])


def test_a_single_tile_is_centred():
    assert spread(width=30, columns=1, tile=16, gap=2) == (7, [])


def test_a_window_narrower_than_a_tile_does_not_go_negative():
    assert spread(width=10, columns=1, tile=16, gap=2) == (0, [])
