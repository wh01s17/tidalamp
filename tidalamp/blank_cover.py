"""The cover for a track that has none, drawn for the look in use.

A local file without art in its folder or inside it used to leave the cover
band showing whatever was there before: the last TIDAL record stayed over a
demo recorded at home (seen 2026-11-27). Now such a track gets a cover of
its own, and it belongs to the look: the themed looks set their emblem in a
frame, and the four plain ones each get a picture in their own manner. The
colours are the palette's, so it changes with it.

The picture goes by a URL like any other cover, one that says everything
needed to draw it (`url`). `artwork.fetch` draws it instead of downloading
it, so the player, the full-screen view and the cover cache all take it the
way they take a record's.
"""

from __future__ import annotations

import functools
import io
import math
from collections.abc import Mapping

from . import artwork
from .layouts import layout_for
from .theme import DEFAULT_COLORS

PREFIX = "tidalamp:blank-cover/"

# The palette entries a drawing uses, in the order the URL carries them.
COLOURS = (
    "display_background",
    "panel",
    "track_background",
    "transport_background",
    "accent",
    "muted",
    "body",
    "warning",
)

SIZE = 512

Rgb = tuple[int, int, int]


def url(theme: str, colors: Mapping[str, str]) -> str:
    """The blank cover of ``theme`` in ``colors``. Two looks or two palettes
    give two URLs, so a change of either draws it again."""
    values = [
        str(colors.get(name) or DEFAULT_COLORS[name]).lstrip("#").lower()
        for name in COLOURS
    ]
    return f"{PREFIX}{theme}/{','.join(values)}"


def is_blank(address: str) -> bool:
    return address.startswith(PREFIX)


@functools.lru_cache(maxsize=8)
def draw(address: str) -> bytes:
    """The PNG behind a blank cover's URL. Empty without Pillow, where no
    cover is drawn at all."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return b""
    theme, _slash, encoded = address.removeprefix(PREFIX).partition("/")
    values = encoded.split(",")
    if len(values) != len(COLOURS):
        raise ValueError(address)
    colors = {name: _rgb(value) for name, value in zip(COLOURS, values, strict=True)}
    layout = layout_for(theme)
    emblem = artwork.emblem_path(layout.emblem)
    if emblem is not None:
        image = _emblem(colors, emblem)
    else:
        painter = {"retro": _retro, "nova": _nova, "ascii": _ascii}.get(
            layout.name, _quattro
        )
        image = painter(colors)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


# ------------------------------------------------------------------- colours


def _rgb(value: str) -> Rgb:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(value)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _mix(one: Rgb, other: Rgb, amount: float) -> Rgb:
    """``one`` moved ``amount`` of the way towards ``other``."""
    return (
        round(one[0] + (other[0] - one[0]) * amount),
        round(one[1] + (other[1] - one[1]) * amount),
        round(one[2] + (other[2] - one[2]) * amount),
    )


BLACK: Rgb = (0, 0, 0)
WHITE: Rgb = (255, 255, 255)


# ------------------------------------------------------------------ drawings


def _record(draw, centre: float, radius: float, colors: dict[str, Rgb], *, ring: Rgb):
    """A record seen from above: grooves, a label in the accent, the hole."""
    disc = _mix(colors["display_background"], BLACK, 0.35)
    groove = _mix(disc, colors["muted"], 0.35)

    def circle(r: float, **style) -> None:
        draw.ellipse((centre - r, centre - r, centre + r, centre + r), **style)

    circle(radius, fill=disc, outline=ring, width=max(1, round(radius * 0.02)))
    for step in range(9):
        circle(radius * (0.9 - step * 0.055), outline=groove, width=1)
    # The shine a lamp leaves across the grooves.
    reach = radius * 0.8
    box = (centre - reach, centre - reach, centre + reach, centre + reach)
    shine = _mix(disc, WHITE, 0.18)
    draw.arc(box, 200, 250, fill=shine, width=max(1, round(radius * 0.05)))
    draw.arc(box, 20, 70, fill=shine, width=max(1, round(radius * 0.05)))
    circle(radius * 0.34, fill=colors["accent"])
    circle(radius * 0.05, fill=colors["panel"])


def _quattro(colors: dict[str, Rgb]):
    """The default look's: flat, a record and its four squares."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (SIZE, SIZE), colors["panel"])
    draw = ImageDraw.Draw(image)
    _record(draw, SIZE / 2, SIZE * 0.4, colors, ring=colors["track_background"])
    side, gap, left = SIZE * 0.05, SIZE * 0.015, SIZE * 0.05
    for index in range(4):
        x = left + (index % 2) * (side + gap)
        y = left + (index // 2) * (side + gap)
        fill = (
            colors["accent"]
            if index == 0
            else _mix(colors["panel"], colors["muted"], 0.6)
        )
        draw.rectangle((x, y, x + side, y + side), fill=fill)
    return image


def _nova(colors: dict[str, Rgb]):
    """No frames, one flat ground: a ring and a point, nothing else."""
    from PIL import Image, ImageDraw

    ground = colors["track_background"]
    image = Image.new("RGB", (SIZE, SIZE), ground)
    draw = ImageDraw.Draw(image)
    centre = SIZE / 2

    def ring(radius: float, colour: Rgb, width: float) -> None:
        draw.ellipse(
            (centre - radius, centre - radius, centre + radius, centre + radius),
            outline=colour,
            width=max(1, round(width)),
        )

    ring(SIZE * 0.36, _mix(ground, colors["muted"], 0.35), SIZE * 0.006)
    ring(SIZE * 0.3, colors["accent"], SIZE * 0.014)
    dot = SIZE * 0.03
    draw.ellipse(
        (centre - dot, centre - dot, centre + dot, centre + dot), fill=colors["accent"]
    )
    return image


# The bars of the retro look's analyser, as fractions of the screen.
_BARS = (0.42, 0.7, 0.88, 0.64, 0.8, 0.56, 0.74, 0.5, 0.62, 0.38, 0.46, 0.28)


def _retro(colors: dict[str, Rgb]):
    """The 1997 skin's: a bevelled panel round a screen with an analyser."""
    from PIL import Image, ImageDraw

    face = colors["transport_background"]
    image = Image.new("RGB", (SIZE, SIZE), face)
    draw = ImageDraw.Draw(image)
    light, dark = _mix(face, WHITE, 0.35), _mix(face, BLACK, 0.5)
    edge = round(SIZE * 0.012)
    for offset in range(edge):
        end = SIZE - 1 - offset
        draw.line((offset, offset, end, offset), fill=light)
        draw.line((offset, offset, offset, end), fill=light)
        draw.line((offset, end, end, end), fill=dark)
        draw.line((end, offset, end, end), fill=dark)
    left, top = round(SIZE * 0.12), round(SIZE * 0.16)
    right, bottom = SIZE - left, SIZE - round(SIZE * 0.12)
    screen = colors["display_background"]
    # The screen sits into the panel: dark above, light below.
    draw.rectangle((left - edge, top - edge, right + edge, bottom + edge), fill=dark)
    draw.rectangle((left, top, right + edge, bottom + edge), fill=light)
    draw.rectangle((left, top, right, bottom), fill=screen)
    inner = SIZE * 0.03
    width = (right - left - 2 * inner) / len(_BARS)
    segment = max(3, round(SIZE * 0.022))
    floor = bottom - inner
    room = bottom - top - 2 * inner
    for index, height in enumerate(_BARS):
        x0 = left + inner + index * width + width * 0.12
        x1 = x0 + width * 0.76
        y = floor
        while y > floor - room * height:
            rise = (floor - y) / room
            colour = colors["warning"] if rise > 0.72 else colors["accent"]
            draw.rectangle((x0, y - segment + 1, x1, y), fill=colour)
            y -= segment + 1
        peak = y - segment * 0.6
        draw.rectangle((x0, peak - 2, x1, peak), fill=colors["body"])
    # Scanlines, faint, over the whole screen.
    line = _mix(screen, BLACK, 0.45)
    for y in range(top, bottom, 4):
        draw.line((left, y, right, y), fill=line)
    # The title strip above the screen.
    stripe = top - round(SIZE * 0.07)
    for y in range(stripe, stripe + round(SIZE * 0.03), 3):
        draw.line((left, y, right, y), fill=_mix(face, colors["accent"], 0.35))
    return image


def _ascii(colors: dict[str, Rgb]):
    """A terminal before box drawing: the record, in pixels you can count."""
    from PIL import Image, ImageDraw

    cells = 32
    small = Image.new("RGB", (cells, cells), colors["display_background"])
    draw = ImageDraw.Draw(small)
    disc = _mix(colors["display_background"], colors["body"], 0.12)
    centre = (cells - 1) / 2
    for y in range(cells):
        for x in range(cells):
            distance = math.hypot(x - centre, y - centre)
            if distance <= 13.5:
                colour = disc
                if distance <= 1.2:
                    colour = colors["display_background"]
                elif distance <= 4.5:
                    colour = colors["accent"]
                elif round(distance) % 3 == 0:
                    colour = colors["muted"]
                draw.point((x, y), fill=colour)
    # A border of `=` the way the look rules its titles: every other cell.
    for x in range(0, cells, 2):
        draw.point((x, 0), fill=colors["muted"])
        draw.point((x, cells - 1), fill=colors["muted"])
    return small.resize((SIZE, SIZE), Image.Resampling.NEAREST)


def _emblem(colors: dict[str, Rgb], path):
    """A themed look's emblem in a frame, on a ground that fades downwards."""
    from PIL import Image, ImageDraw

    top, bottom = colors["panel"], colors["display_background"]
    ground = Image.new("RGB", (1, SIZE))
    for y in range(SIZE):
        ground.putpixel((0, y), _mix(top, bottom, y / (SIZE - 1)))
    image = ground.resize((SIZE, SIZE))
    draw = ImageDraw.Draw(image)
    inset, width = round(SIZE * 0.06), max(2, round(SIZE * 0.012))
    draw.rectangle(
        (inset, inset, SIZE - inset, SIZE - inset), outline=colors["accent"], width=width
    )
    emblem = artwork.emblem_image(path)
    if emblem is None:
        return image
    room = SIZE * 0.7
    scale = min(room / emblem.width, room / emblem.height)
    fitted = emblem.resize(
        (max(1, round(emblem.width * scale)), max(1, round(emblem.height * scale))),
        Image.Resampling.LANCZOS,
    )
    image.paste(
        fitted,
        ((SIZE - fitted.width) // 2, (SIZE - fitted.height) // 2),
        fitted,
    )
    return image
