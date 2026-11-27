"""The cover a track without one gets: one per look, in the palette's colours."""

from __future__ import annotations

import io

import pytest

from tidalamp import artwork, blank_cover
from tidalamp.layouts import LAYOUT_TABLE
from tidalamp.theme import DEFAULT_COLORS

pytest.importorskip("PIL")


def test_the_url_carries_the_look_and_the_colours():
    one = blank_cover.url("nova", DEFAULT_COLORS)
    other = blank_cover.url("nova", {**DEFAULT_COLORS, "accent": "#FF0000"})

    assert blank_cover.is_blank(one)
    assert one.startswith(f"{blank_cover.PREFIX}nova/")
    assert "ff0000" in other and one != other
    assert blank_cover.url("retro", DEFAULT_COLORS) != one


def test_a_palette_missing_a_colour_takes_the_default_one():
    partial = {key: value for key, value in DEFAULT_COLORS.items() if key != "warning"}

    assert blank_cover.url("quattro", partial) == blank_cover.url(
        "quattro", DEFAULT_COLORS
    )


@pytest.mark.parametrize("theme", [*LAYOUT_TABLE, "no-existe"])
def test_every_look_draws_a_square_picture(theme):
    from PIL import Image

    data = blank_cover.draw(blank_cover.url(theme, DEFAULT_COLORS))

    image = Image.open(io.BytesIO(data))
    assert image.format == "PNG"
    assert image.size == (blank_cover.SIZE, blank_cover.SIZE)


def test_the_look_changes_the_picture():
    drawn = {
        theme: blank_cover.draw(blank_cover.url(theme, DEFAULT_COLORS))
        for theme in ("quattro", "retro", "nova", "ascii", "pirata")
    }

    assert len(set(drawn.values())) == len(drawn)


def test_the_palette_changes_the_picture():
    red = {**DEFAULT_COLORS, "accent": "#ff0000"}

    assert blank_cover.draw(blank_cover.url("nova", red)) != blank_cover.draw(
        blank_cover.url("nova", DEFAULT_COLORS)
    )


@pytest.mark.parametrize(
    "address",
    [
        f"{blank_cover.PREFIX}nova/123",
        f"{blank_cover.PREFIX}nova/" + ",".join(["zz"] * 8),
    ],
)
def test_a_url_that_is_not_one_of_ours_is_refused(address):
    with pytest.raises(ValueError):
        blank_cover.draw(address)


def test_fetch_draws_it_instead_of_downloading_it(monkeypatch, tmp_path):
    def no_network(*args, **kwargs):
        raise AssertionError("a blank cover is never downloaded")

    monkeypatch.setattr("requests.get", no_network)
    address = blank_cover.url("retro", DEFAULT_COLORS)

    assert artwork.fetch(address, root=tmp_path) == blank_cover.draw(address)
    assert not any(tmp_path.iterdir()), "nor cached"
