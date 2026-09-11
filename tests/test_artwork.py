"""Cover art: protocol detection, caching, and the two pixel encoders."""

from __future__ import annotations

import base64
import io
import re

import pytest

from tidalamp import artwork
from tidalamp.artwork import Protocol

PIL = pytest.importorskip("PIL.Image", reason="Pillow es opcional")


def solid(size: tuple[int, int], colour: tuple[int, int, int]) -> bytes:
    image = PIL.new("RGB", size, colour)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ------------------------------------------------------------------- detection


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"KITTY_WINDOW_ID": "3", "TERM": "xterm-256color"}, Protocol.KITTY),
        ({"TERM": "xterm-kitty"}, Protocol.KITTY),
        ({"TERM": "xterm-256color", "TERM_PROGRAM": "WezTerm"}, Protocol.KITTY),
        ({"TERM": "foot"}, Protocol.SIXEL),
        ({"TERM": "mlterm"}, Protocol.SIXEL),
        ({"TERM": "xterm-256color"}, Protocol.BLOCKS),
        ({}, Protocol.BLOCKS),
    ],
)
def test_protocol_is_guessed_from_the_environment(env, expected):
    assert artwork.detect_protocol(env) is expected


def test_the_override_wins_over_the_terminal():
    env = {"TERM": "xterm-kitty", "TIDALAMP_ART": "blocks"}
    assert artwork.detect_protocol(env) is Protocol.BLOCKS
    assert artwork.detect_protocol({"TIDALAMP_ART": "off"}) is Protocol.NONE


def test_a_nonsense_override_falls_back_instead_of_failing():
    env = {"TERM": "xterm-kitty", "TIDALAMP_ART": "vector"}
    assert artwork.detect_protocol(env) is Protocol.KITTY


# --------------------------------------------------------------------- fetching


def test_the_cover_is_cached_and_only_downloaded_once(tmp_path, monkeypatch):
    calls: list[str] = []

    class Response:
        content = b"payload"

        def raise_for_status(self) -> None:
            pass

    def get(url, timeout=None):
        calls.append(url)
        return Response()

    monkeypatch.setattr("requests.get", get)

    url = "https://resources.tidal.com/images/abc/320x320.jpg"
    assert artwork.fetch(url, root=tmp_path) == b"payload"
    assert artwork.fetch(url, root=tmp_path) == b"payload"
    assert calls == [url]
    assert artwork.cache_path(url, root=tmp_path).read_bytes() == b"payload"


def test_an_unwritable_cache_still_returns_the_cover(tmp_path, monkeypatch):
    class Response:
        content = b"payload"

        def raise_for_status(self) -> None:
            pass

    monkeypatch.setattr("requests.get", lambda url, timeout=None: Response())
    monkeypatch.setattr(
        artwork.Path, "write_bytes", lambda self, data: (_ for _ in ()).throw(OSError())
    )
    assert artwork.fetch("https://x/y.jpg", root=tmp_path) == b"payload"


# --------------------------------------------------------------------- decoding


def test_decode_fits_the_box_in_pixels():
    image = artwork.decode(solid((640, 640), (10, 20, 30)), 18, 9, cell=(10, 20))
    assert image.size == (180, 180)


def test_a_wide_cover_is_centre_cropped_rather_than_squashed():
    # Red | green | red, so a centred crop keeps green and drops both reds.
    source = PIL.new("RGB", (300, 100), (255, 0, 0))
    source.paste(PIL.new("RGB", (100, 100), (0, 255, 0)), (100, 0))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")

    image = artwork.decode(buffer.getvalue(), 10, 5, cell=(10, 20))
    assert image.size == (100, 100)
    assert image.getpixel((50, 50)) == (0, 255, 0)
    assert image.getpixel((2, 50)) == (0, 255, 0)


def test_broken_bytes_decode_to_nothing_instead_of_raising():
    assert artwork.decode(b"not an image", 4, 2) is None


def test_without_pillow_there_is_simply_no_cover(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_pillow(name, *args, **kwargs):
        if name.startswith("PIL"):
            raise ImportError("no PIL")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pillow)
    assert artwork.decode(solid((32, 32), (1, 2, 3)), 4, 2) is None
    assert artwork.render(solid((32, 32), (1, 2, 3)), 4, 2, Protocol.BLOCKS) is None
    # And the app can ask beforehand, so the empty corner gets an explanation.
    assert artwork.have_decoder() is False


def test_have_decoder_is_true_when_pillow_is_installed():
    assert artwork.have_decoder() is True


# ---------------------------------------------------------------------- blocks


def test_blocks_give_four_samples_per_cell():
    """Two rows and two columns, where `▀` alone took one column and two rows."""
    image = artwork.decode(solid((64, 64), (12, 34, 56)), 6, 3, cell=(10, 20))
    matrix = artwork.blocks(image, 6, 3)
    assert len(matrix) == 6
    assert all(len(row) == 12 for row in matrix)
    assert matrix[0][0] == (12, 34, 56)


def test_a_cell_splits_its_four_pixels_into_a_light_group_and_a_dark_one():
    white, black = (255, 255, 255), (0, 0, 0)
    assert artwork.quadrant_cell((white, black, black, black))[0] == "▘"
    assert artwork.quadrant_cell((black, white, black, black))[0] == "▝"
    assert artwork.quadrant_cell((white, white, black, black))[0] == "▀"
    assert artwork.quadrant_cell((white, black, black, white))[0] == "▚"
    assert artwork.quadrant_cell((white, white, white, white))[0] == " "


def test_a_flat_cell_paints_as_its_own_colour():
    grey = (10, 20, 30)
    glyph, foreground, background = artwork.quadrant_cell((grey, grey, grey, grey))
    assert glyph == " "
    assert foreground == background == grey


def test_the_split_follows_the_range_and_not_the_majority():
    """A mean would follow the three dark pixels and flatten the edge the
    bright one makes, which is the detail this exists to keep."""
    dark, bright = (0, 0, 0), (255, 255, 255)
    glyph, foreground, background = artwork.quadrant_cell((bright, dark, dark, dark))
    assert glyph == "▘"
    assert foreground == bright
    assert background == dark


def test_every_split_of_four_pixels_has_a_glyph():
    assert len(artwork.QUADRANTS) == 16
    assert len(set(artwork.QUADRANTS)) == 16


# ------------------------------------------------------------------------ kitty


def noisy(size: tuple[int, int]) -> bytes:
    """An incompressible cover, so the payload really needs several chunks."""
    import random

    random.seed(0)
    image = PIL.frombytes(
        "RGB", size, bytes(random.randrange(256) for _ in range(size[0] * size[1] * 3))
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_kitty_transmits_the_png_in_chunks_that_reassemble():
    png = noisy((120, 120))
    escape = artwork.kitty_escape(png, 18, 9, image_id=7)

    chunks = re.findall(r"\033_G([^;]*);([^\033]*)\033\\\\?", escape)
    assert len(chunks) > 1, "una carátula de verdad no cabe en un solo trozo"

    head = chunks[0][0]
    assert "a=T" in head and "f=100" in head and "i=7" in head
    assert "c=18" in head and "r=9" in head
    # Without q=2 the terminal answers every chunk and Textual reads the
    # answer as keystrokes; without C=1 the cursor moves under the compositor.
    assert "q=2" in head and "C=1" in head

    assert all(keys == "m=1" for keys, _ in chunks[1:-1])
    assert chunks[-1][0] in ("m=0", head.replace("m=1", "m=0"))
    assert base64.standard_b64decode("".join(body for _, body in chunks)) == png


def test_a_tiny_image_still_produces_a_single_terminated_chunk():
    escape = artwork.kitty_escape(b"x", 2, 1, image_id=1)
    assert escape.count("\033_G") == 1
    assert "m=0" in escape and escape.endswith("\033\\")


def test_kitty_delete_names_the_image_by_id():
    assert artwork.kitty_delete(4) == "\033_Ga=d,d=I,i=4,q=2\033\\"


# ------------------------------------------------------------------------ sixel


def decode_sixel(text: str) -> tuple[dict[int, tuple[int, int, int]], dict]:
    """A minimal sixel reader, so the encoder is checked against pixels."""
    assert text.startswith("\033Pq"), text[:10]
    assert text.endswith("\033\\")
    body = text[3:-2]
    body = re.sub(r'^"[\d;]+', "", body)

    palette: dict[int, tuple[int, int, int]] = {}
    pixels: dict[tuple[int, int], int] = {}
    colour = 0
    x = 0
    band = 0
    i = 0
    while i < len(body):
        char = body[i]
        if char == "#":
            match = re.match(r"#(\d+)(?:;2;(\d+);(\d+);(\d+))?", body[i:])
            colour = int(match.group(1))
            if match.group(2) is not None:
                palette[colour] = tuple(
                    round(int(match.group(n)) * 255 / 100) for n in (2, 3, 4)
                )
            i += match.end()
            x = 0
            continue
        if char == "$":
            x = 0
            i += 1
            continue
        if char == "-":
            x = 0
            band += 1
            i += 1
            continue
        if char == "!":
            match = re.match(r"!(\d+)(.)", body[i:])
            count, sixel = int(match.group(1)), match.group(2)
            i += match.end()
        else:
            count, sixel = 1, char
            i += 1
        bits = ord(sixel) - 0x3F
        for _ in range(count):
            for row in range(6):
                if bits & (1 << row):
                    pixels[(x, band * 6 + row)] = colour
            x += 1
    return palette, pixels


def test_sixel_round_trips_a_solid_colour():
    image = PIL.new("RGB", (12, 12), (255, 0, 0))
    palette, pixels = decode_sixel(artwork.sixel_escape(image))

    assert len(pixels) == 12 * 12
    colour = palette[next(iter(pixels.values()))]
    assert colour == (255, 0, 0)


def test_sixel_round_trips_two_bands_of_different_colours():
    image = PIL.new("RGB", (8, 12), (0, 0, 255))
    image.paste(PIL.new("RGB", (8, 6), (255, 255, 0)), (0, 6))
    palette, pixels = decode_sixel(artwork.sixel_escape(image))

    assert palette[pixels[(0, 0)]] == (0, 0, 255)
    assert palette[pixels[(0, 11)]] == (255, 255, 0)
    assert palette[pixels[(7, 5)]] == (0, 0, 255)


def test_sixel_collapses_runs():
    wide = artwork.sixel_escape(PIL.new("RGB", (200, 6), (0, 128, 0)))
    assert "!" in wide, "200 celdas iguales tienen que ir codificadas por longitud"
    assert len(wide) < 200


# ---------------------------------------------------------------------- façade


@pytest.mark.parametrize(
    "protocol, attribute",
    [(Protocol.KITTY, "escape"), (Protocol.SIXEL, "escape"), (Protocol.BLOCKS, "pixels")],
)
def test_render_produces_what_each_protocol_needs(protocol, attribute):
    cover = artwork.render(solid((64, 64), (9, 9, 9)), 6, 3, protocol)
    assert cover is not None
    assert cover.protocol is protocol
    assert getattr(cover, attribute)
    assert cover.cols == 6 and cover.rows == 3


def test_render_does_nothing_when_artwork_is_off():
    assert artwork.render(solid((8, 8), (0, 0, 0)), 4, 2, Protocol.NONE) is None


def test_an_emblem_keeps_its_shape_behind_the_queue():
    """A cell is twice as tall as it is wide, and so is a quadrant pixel: a
    round moon has to take twice as many cells across as rows down. Sampled
    square, every emblem came out squashed sideways."""
    from tidalamp.artwork import emblem_cells, emblem_path

    path = emblem_path("cuaderno.png")
    lines = emblem_cells(path, 120, 60, (0, 0, 0), size=0.7, share=0.9)
    rows = len(lines)
    xs = [cell[0] for cells in lines.values() for cell in cells]
    cols = max(xs) - min(xs) + 1
    with __import__("PIL.Image").Image.open(path) as image:
        want = 2 * image.width / image.height
    assert abs(cols / rows - want) < 0.25, (cols, rows, want)


def test_an_emblem_can_sit_in_the_lower_right_corner_and_grow():
    """`bottom` ends the picture a row above the list's lower edge, against
    the right; `middle` centres it. A larger scale takes more of the room."""
    from tidalamp.artwork import emblem_cells, emblem_path

    path = emblem_path("pirata.png")
    middle = emblem_cells(path, 120, 60, (0, 0, 0))
    bottom = emblem_cells(path, 120, 60, (0, 0, 0), anchor="bottom")
    bigger = emblem_cells(path, 120, 60, (0, 0, 0), anchor="bottom", scale=1.3)

    assert max(bottom) == 60 - 2
    assert abs((min(middle) + max(middle)) / 2 - 30) <= 1
    assert max(x for cells in bottom.values() for x, *_ in cells) == 120 - 3
    assert len(bigger) > len(bottom)


def test_a_round_cover_is_a_disc_on_the_band_s_ground():
    """The corners take the band's ground, whatever the protocol: sixel has
    no alpha worth trusting and half blocks none at all. The middle is the
    cover, untouched."""
    pil_image = pytest.importorskip("PIL.Image")
    red = pil_image.new("RGB", (80, 80), (200, 20, 20))
    ground = (10, 30, 12)
    assert artwork.shape(red, "square", ground) is red
    disc = artwork.shape(red, "round", ground)
    assert disc.size == red.size
    for corner in ((0, 0), (79, 0), (0, 79), (79, 79)):
        assert disc.getpixel(corner) == ground
    assert disc.getpixel((40, 40)) == (200, 20, 20)
    # The edge is blended, not stepped: some pixel sits between the two.
    diagonal = [disc.getpixel((x, x)) for x in range(5, 20)]
    assert any(ground[0] < pixel[0] < 200 for pixel in diagonal)


def test_render_cuts_the_cover_before_any_protocol_sees_it():
    pil_image = pytest.importorskip("PIL.Image")
    buffer = io.BytesIO()
    pil_image.new("RGB", (64, 64), (250, 250, 250)).save(buffer, "PNG")
    cover = artwork.render(
        buffer.getvalue(), 8, 4, Protocol.BLOCKS, outline="round", ground=(0, 0, 0)
    )
    assert cover is not None and cover.pixels is not None
    assert cover.pixels[0][0] == (0, 0, 0)
    middle = cover.pixels[len(cover.pixels) // 2][len(cover.pixels[0]) // 2]
    assert middle == (250, 250, 250)


def test_rounded_corners_keep_the_edges_straight():
    """The corners take the band's ground; the middle of each edge is still
    the cover, which is what tells `rounded` from `round`."""
    pil_image = pytest.importorskip("PIL.Image")
    red = pil_image.new("RGB", (80, 80), (200, 20, 20))
    ground = (10, 30, 12)
    card = artwork.shape(red, "rounded", ground)
    for corner in ((0, 0), (79, 0), (0, 79), (79, 79)):
        assert card.getpixel(corner) == ground, corner
    # One pixel in, the smoothed edge: still all but the ground.
    assert all(
        abs(a - b) <= 8 for a, b in zip(card.getpixel((1, 1)), ground, strict=True)
    )
    for edge in ((40, 0), (0, 40), (79, 40), (40, 79)):
        assert card.getpixel(edge) == (200, 20, 20), edge


def test_rounded_corners_survive_the_blocks_protocol():
    """Four pixels a cell: a radius in proportion to the side still shows."""
    pil_image = pytest.importorskip("PIL.Image")
    buffer = io.BytesIO()
    pil_image.new("RGB", (64, 64), (250, 250, 250)).save(buffer, "PNG")
    cover = artwork.render(
        buffer.getvalue(), 18, 9, Protocol.BLOCKS, outline="rounded", ground=(0, 0, 0)
    )
    assert cover is not None and cover.pixels is not None
    # The corner cell averages its four pixels: mostly ground, a trace of edge.
    assert max(cover.pixels[0][0]) < 64
    middle_of_top = cover.pixels[0][len(cover.pixels[0]) // 2]
    assert middle_of_top == (250, 250, 250)
