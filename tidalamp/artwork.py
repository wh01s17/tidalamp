"""Album art: fetch the cover and turn it into something a terminal can draw.

Three targets, in descending fidelity:

* **kitty graphics**, which draws real pixels above the text grid;
* **sixel**, DEC's older pixel format, still spoken by foot, mlterm, contour…;
* **half blocks**, which need no protocol at all: one cell becomes two pixels
  by painting a quadrant glyph in one colour over another, four samples to
  a cell.

Pillow is an optional dependency. Without it there is no decoder, so
:func:`decode` returns ``None``, the cover is simply not drawn, and nothing
else about the player changes — the same bargain as cava in `spectrum.py`.

This module knows nothing about Textual or tidalapi: it takes a URL and a box
measured in cells, and gives back either a pixel matrix or an escape sequence.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .config import CACHE_DIR
from .net import with_retries

log = logging.getLogger(__name__)

ART_CACHE = CACHE_DIR / "art"

# A terminal cell is about twice as tall as it is wide. We only use this to
# pick a pixel size for the box, so being a couple of pixels off costs
# nothing: the terminal scales the image into the cells we ask for.
CELL = (10, 20)

# Half-block rendering gets two vertical pixels per cell and one horizontal.
Pixel = tuple[int, int, int]
Matrix = tuple[tuple[Pixel, ...], ...]


class Protocol(StrEnum):
    """How this terminal can show an image."""

    KITTY = "kitty"
    SIXEL = "sixel"
    BLOCKS = "blocks"
    NONE = "none"


# Terminals that speak the kitty graphics protocol, by $TERM or $TERM_PROGRAM.
_KITTY_TERMS = ("xterm-kitty", "xterm-ghostty")
_KITTY_PROGRAMS = ("ghostty", "WezTerm", "wezterm")
# Terminals that speak sixel but not kitty graphics.
_SIXEL_TERMS = ("foot", "mlterm", "contour", "yaft", "sixel")


def detect_protocol(env: dict[str, str] | None = None, configured: str = "") -> Protocol:
    """Decide how to draw the cover, from the environment alone.

    Querying the terminal is the accurate way, but the reply would land in
    Textual's input stream; guessing from ``$TERM`` costs nothing and the
    half-block fallback is good enough that a wrong guess is not a failure.
    ``configured`` (the ``artwork`` setting, which already accounts for
    ``TIDALAMP_ART``) overrides everything, including ``off``; ``auto`` means
    "guess".
    """
    values: Mapping[str, str] = os.environ if env is None else env

    forced = (configured or values.get("TIDALAMP_ART") or "").strip().lower()
    if forced == "auto":
        forced = ""
    if forced in {"off", "none"}:
        return Protocol.NONE
    if forced in {p.value for p in Protocol}:
        return Protocol(forced)
    if forced:
        log.warning("TIDALAMP_ART=%r no es un protocolo conocido; se ignora", forced)

    term = values.get("TERM", "")
    program = values.get("TERM_PROGRAM", "")
    if (
        values.get("KITTY_WINDOW_ID")
        or term in _KITTY_TERMS
        or program in _KITTY_PROGRAMS
    ):
        return Protocol.KITTY
    if any(name in term for name in _SIXEL_TERMS):
        return Protocol.SIXEL
    return Protocol.BLOCKS


@dataclass(frozen=True, slots=True)
class Cover:
    """A cover already fitted to a box of terminal cells.

    Exactly one of ``pixels`` (half blocks) and ``escape`` (kitty or sixel) is
    set, so the widget never has to ask which protocol produced it.
    """

    cols: int
    rows: int
    protocol: Protocol
    pixels: Matrix | None = None
    escape: str = ""
    # With half blocks, each cell's glyph and two colours, worked out in the
    # worker that rendered the cover (`block_cells`). None where a cover was
    # built without them; the widget works them out from ``pixels`` then.
    cells: tuple[tuple[tuple[str, Pixel, Pixel], ...], ...] | None = None


# --------------------------------------------------------------------- fetching


# TIDAL serves each cover at a handful of square sizes, all at the same path.
_SIZED = re.compile(r"/(80|160|320|640|1280)x\1\.jpg$")


def sized(url: str, px: int) -> str:
    """The same TIDAL cover at ``px`` square, for a box that wants more than
    the 320 the queue asks for. Any other URL comes back as it was."""
    return _SIZED.sub(f"/{px}x{px}.jpg", url)


def cache_path(url: str, *, root: Path | None = None) -> Path:
    """Where a cover URL is cached. The digest keeps the name filesystem-safe."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return (ART_CACHE if root is None else root) / f"{digest}.img"


def fetch(url: str, *, root: Path | None = None) -> bytes:
    """Return the cover bytes, from the cache when we have already seen it.

    Covers never change under a URL — TIDAL puts the image id in the path — so
    the cache needs no expiry.
    """
    path = cache_path(url, root=root)
    try:
        return path.read_bytes()
    except OSError:
        pass

    import requests

    def get() -> bytes:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content

    data = with_retries(get)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as exc:  # A full or read-only cache must not stop playback.
        log.warning("no se pudo cachear la carátula: %s", exc)
    return data


# --------------------------------------------------------------------- decoding


def have_decoder() -> bool:
    """Whether Pillow is importable, i.e. whether a cover can be drawn at all.

    Without it every protocol degrades to nothing, and silently: the widget
    just never becomes visible. The app asks this at startup so it can say so
    once instead of leaving an empty corner unexplained.
    """
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def decode(
    data: bytes,
    cols: int,
    rows: int,
    *,
    cell: tuple[int, int] = CELL,
    upscale: bool = True,
):
    """Decode and fit the cover to ``cols`` × ``rows`` cells.

    Returns a Pillow image, or ``None`` when Pillow is not installed. The
    image is cropped to the box's aspect ratio before scaling, so a square
    cover in a non-square box is centred rather than stretched.
    """
    try:
        from PIL import Image
    except ImportError:
        log.info("Pillow no está instalado; sin carátula")
        return None

    import io

    width = max(1, cols * cell[0])
    height = max(1, rows * cell[1])
    try:
        opened = Image.open(io.BytesIO(data))
        opened.load()
    except Exception as exc:  # A broken download is not worth a traceback.
        log.warning("carátula ilegible: %s", exc)
        return None

    image = opened.convert("RGB")
    # Centre-crop to the target aspect, then scale: covers are square and the
    # box rarely is, and letterboxing would show the panel through the middle.
    src_w, src_h = image.size
    want = width / height
    have = src_w / src_h
    if have > want:
        new_w = max(1, int(src_h * want))
        left = (src_w - new_w) // 2
        image = image.crop((left, 0, left + new_w, src_h))
    elif have < want:
        new_h = max(1, int(src_w / want))
        top = (src_h - new_h) // 2
        image = image.crop((0, top, src_w, top + new_h))
    # kitty scales the image to the cells it is told to fill, so for it the
    # picture is never stretched past its own size: that only multiplies what
    # travels to the terminal (a 320 px cover stretched for a 4K full screen
    # was 8 MB of escape) without adding any detail.
    if not upscale and image.width < width:
        return image
    return image.resize((width, height), Image.Resampling.LANCZOS)


def shape(image, outline: str, ground: Pixel):
    """Cut the fitted cover to `outline`, the corners painted in `ground`.

    Painted rather than left transparent: sixel has no alpha worth trusting,
    and half blocks have none at all, so every protocol gets the same picture.
    The mask is drawn four times over and scaled down, which is what gives the
    disc a smooth edge instead of a staircase.
    """
    if outline == "square":
        return image
    from PIL import Image, ImageDraw

    width, height = image.size
    scale = 4
    mask = Image.new("L", (width * scale, height * scale), 0)
    draw = ImageDraw.Draw(mask)
    box = (0, 0, width * scale - 1, height * scale - 1)
    if outline == "round":
        draw.ellipse(box, fill=255)
    elif outline == "rounded":
        # In proportion to the side, not a fixed number of pixels: in blocks a
        # cell is four pixels, and a radius a kitty cover shows would vanish.
        radius = round(min(width, height) * scale * 0.12)
        draw.rounded_rectangle(box, radius=radius, fill=255)
    else:
        return image
    mask = mask.resize((width, height), Image.Resampling.LANCZOS)
    return Image.composite(image, Image.new("RGB", image.size, ground), mask)


# -------------------------------------------------------------------- blocks

# One glyph per way of splitting a cell's four quadrants between two colours,
# indexed by a bitmask: 8 upper-left, 4 upper-right, 2 lower-left, 1 lower
# right. All sixteen exist in Block Elements, the same ancient range `▀` and
# `█` come from, so this asks nothing of a font that the old rendering did not.
QUADRANTS = " ▗▖▄▝▐▞▟▘▚▌▙▀▜▛█"


# How much each channel counts when two colours are compared: the eye is most
# sensitive to green and least to blue. A cheap stand-in for a perceptual
# distance, and enough to choose between eight ways of splitting a cell.
_WEIGHTS = (3, 4, 2)


def _error(pixels: list[Pixel], colour: Pixel) -> int:
    """How far ``pixels`` are from being drawn all in ``colour``."""
    wr, wg, wb = _WEIGHTS
    return sum(
        wr * (r - colour[0]) ** 2 + wg * (g - colour[1]) ** 2 + wb * (b - colour[2]) ** 2
        for r, g, b in pixels
    )


def _luma(pixel: Pixel) -> float:
    return 0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2]


# The eight ways of splitting a cell's four pixels in two, as (glyph mask,
# the pixels on the glyph side, the rest). The upper-left pixel always stays on
# the ground side: a split and its mirror image are the same split. Mask 0 is
# no split at all, the cell drawn flat.
_SPLITS = tuple(
    (
        mask,
        tuple(i for i in range(4) if mask & (1 << (3 - i))),
        tuple(i for i in range(4) if not mask & (1 << (3 - i))),
    )
    for mask in range(8)
)


def quadrant_cell(quad: tuple[Pixel, Pixel, Pixel, Pixel]) -> tuple[str, Pixel, Pixel]:
    """Turn four pixels into the glyph and two colours that best stand for them.

    A cell can hold two colours and four pixels. Every way of splitting the
    four into two groups is tried (there are eight, one of them no split at
    all) and the one whose two averages sit closest to the pixels wins. It
    used to split by brightness at the midpoint of the range, which is right
    for an edge between light and dark and loses one between two colours of
    about the same brightness, a red against a green.

    The lighter group is the glyph, the darker one its ground, as before, so
    a cell that split well by brightness comes out the same. A flat cell, or
    one that no split draws better, is a space in its own average.

    Each group's error comes from its sums and sums of squares, not from a
    pass over its pixels against its mean: this runs once a cell, and a large
    cover on a 4K terminal is tens of thousands of cells.
    """
    p0, p1, p2, p3 = quad
    if p0 == p1 == p2 == p3:
        return QUADRANTS[0], p0, p0
    wr, wg, wb = _WEIGHTS
    best_error = -1.0
    best: tuple[str, Pixel, Pixel] = (QUADRANTS[0], p0, p0)
    for mask, front_side, back_side in _SPLITS:
        means: list[Pixel] = []
        error = 0.0
        for side in (front_side, back_side):
            if not side:
                means.append((0, 0, 0))
                continue
            n = len(side)
            sr = sg = sb = qr = qg = qb = 0
            for i in side:
                r, g, b = quad[i]
                sr += r
                sg += g
                sb += b
                qr += r * r
                qg += g * g
                qb += b * b
            error += (
                wr * (qr - sr * sr / n)
                + wg * (qg - sg * sg / n)
                + wb * (qb - sb * sb / n)
            )
            means.append((sr // n, sg // n, sb // n))
        if best_error >= 0 and error >= best_error:
            continue
        best_error = error
        front, back = means
        if not front_side:
            best = (QUADRANTS[0], back, back)
        elif _luma(front) >= _luma(back):
            best = (QUADRANTS[mask], front, back)
        else:
            best = (QUADRANTS[15 ^ mask], back, front)
    return best


def block_cells(matrix: Matrix) -> tuple[tuple[tuple[str, Pixel, Pixel], ...], ...]:
    """Every cell of a half-block cover, worked out once.

    Done where the cover is rendered, in a worker thread, so the UI only
    assembles lines: choosing the colours of a full-screen cover on a 4K
    terminal is a second of work the event loop should never wait on.
    """
    rows = []
    for y in range(len(matrix) // 2):
        top, bottom = matrix[y * 2], matrix[y * 2 + 1]
        rows.append(
            tuple(
                quadrant_cell(
                    (top[x * 2], top[x * 2 + 1], bottom[x * 2], bottom[x * 2 + 1])
                )
                for x in range(min(len(top), len(bottom)) // 2)
            )
        )
    return tuple(rows)


def _mean(pixels: list[Pixel]) -> Pixel:
    count = len(pixels)
    return (
        sum(p[0] for p in pixels) // count,
        sum(p[1] for p in pixels) // count,
        sum(p[2] for p in pixels) // count,
    )


def blocks(image, cols: int, rows: int) -> Matrix:
    """Sample the image into ``2 * rows`` rows of ``2 * cols`` pixels.

    Four samples per cell, drawn with the quadrant glyphs: twice the detail
    across that ``▀`` alone could carry, which spent a whole cell's width on
    one pixel. The cost is that a cell still holds only two colours, so where
    its four pixels disagree the two groups are averaged; on a photograph
    neighbouring pixels rarely disagree by much, and the trade buys back the
    horizontal resolution that made covers look stretched.

    The grid's own aspect does not matter: `decode` already cropped the image
    to the box, and whatever grid this samples is mapped back onto that box.
    """
    from PIL import Image

    # LANCZOS rather than the default filter: it is the one downsample from
    # the decoded box to four samples a cell, and the sharpest there is.
    small = image.resize((max(1, cols * 2), max(1, rows * 2)), Image.Resampling.LANCZOS)
    width, height = small.size
    # tobytes() rather than getdata(): three bytes per pixel in RGB, no
    # per-pixel Python objects, and no deprecation to inherit.
    raw = small.tobytes()
    return tuple(
        tuple(
            (raw[i], raw[i + 1], raw[i + 2])
            for i in range(row * width * 3, (row + 1) * width * 3, 3)
        )
        for row in range(height)
    )


# -------------------------------------------------------------------- emblems

# The themed looks' pictures, drawn behind the queue the way a cover is drawn
# in its box: quadrant blocks, real colours. Small PNGs shipped in the package.
EMBLEM_DIR = Path(__file__).parent / "emblems"

# One emblem cell: its column, and the glyph, colours and mean it carries.
EmblemCell = tuple[int, str, Pixel, Pixel, Pixel]


def emblem_path(name: str) -> Path | None:
    """The emblem file called `name`, if the package has it."""
    path = EMBLEM_DIR / name if name else None
    return path if path is not None and path.is_file() else None


@functools.lru_cache(maxsize=16)
def _emblem_image(path: str):
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as opened:
            return opened.convert("RGBA")
    except OSError as exc:
        log.warning("emblema ilegible: %s", exc)
        return None


def _veil(pixel: Pixel, ground: Pixel, amount: float) -> Pixel:
    return (
        round(pixel[0] * amount + ground[0] * (1 - amount)),
        round(pixel[1] * amount + ground[1] * (1 - amount)),
        round(pixel[2] * amount + ground[2] * (1 - amount)),
    )


def emblem_cells(
    path: Path,
    width: int,
    height: int,
    ground: Pixel,
    *,
    amount: float = 0.3,
    size: float = 0.7,
    share: float = 0.55,
    anchor: str = "middle",
    scale: float = 1.0,
) -> dict[int, list[EmblemCell]]:
    """An emblem laid behind a list `width` x `height` cells, line by line.

    Sampled like a cover, four pixels to a cell, and set against the right
    edge: at most `size` of the height and `share` of the width, scaled to
    any size so it grows with a 4K terminal. Every colour goes under a dark
    veil, mixed into `ground` at `amount`, the way a modal's scrim darkens
    what is behind it, so the rows on top keep their contrast.

    Each cell carries both renderings: the quadrant glyph with its two
    colours, for a cell the list leaves empty, and the mean of its four
    pixels, for a cell with a letter in it, where only the ground can change.
    A cell all of whose pixels are transparent is left out. Empty without
    Pillow, as the cover is.
    """
    image = _emblem_image(str(path))
    # `scale` grows the room, never past the list itself.
    cols_room = int((width - 2) * min(1.0, share * scale))
    rows_room = int(height * min(1.0, size * scale))
    if image is None or cols_room < 4 or rows_room < 2:
        return {}
    # A cell is twice as tall as it is wide, so a quadrant pixel is too:
    # the picture takes as many cells across as its width asks for, and half
    # as many rows as its height would at the same scale. Sampling it square
    # squashed every emblem sideways, the moon into an egg.
    cols = min(cols_room, int(rows_room * 2 * image.width / image.height))
    rows = min(rows_room, int(cols * image.height / (2 * image.width)))
    cols = min(cols, int(rows * 2 * image.width / image.height))
    if cols < 2 or rows < 1:
        return {}
    from PIL import Image

    pixels_w, pixels_h = cols * 2, rows * 2
    small = image.resize((pixels_w, pixels_h), Image.Resampling.LANCZOS)
    alpha = small.getchannel("A")
    # The veil and the transparency in one pass, over the whole picture:
    # each pixel goes into the ground by its alpha times `amount`, so a
    # feathered edge melts into the list instead of ending in a square.
    veil = alpha.point(lambda a: round(a * amount))
    veiled = Image.composite(
        small.convert("RGB"), Image.new("RGB", small.size, ground), veil
    )
    raw = veiled.tobytes()
    seen = alpha.tobytes()

    left = width - 2 - cols
    # `bottom` tucks the picture into the lower right corner, a row off the
    # edge; `middle` centres it down the right side.
    top = max(0, height - rows - 1) if anchor == "bottom" else (height - rows) // 2

    lines: dict[int, list[EmblemCell]] = {}
    for row in range(rows):
        cells: list[EmblemCell] = []
        for col in range(cols):
            spots = [
                (row * 2 + dy) * pixels_w + col * 2 + dx for dy in (0, 1) for dx in (0, 1)
            ]
            if all(seen[i] < 8 for i in spots):
                continue
            quad = tuple((raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]) for i in spots)
            glyph, fg, bg = quadrant_cell(quad)  # type: ignore[arg-type]
            mean = _mean(list(quad))
            cells.append((left + col, glyph, fg, bg, mean))
        if cells:
            lines[top + row] = cells
    return lines


# ----------------------------------------------------------------------- kitty


def kitty_escape(png: bytes, cols: int, rows: int, image_id: int) -> str:
    """Transmit and place a PNG with the kitty graphics protocol.

    ``q=2`` is not optional here: without it the terminal answers every chunk
    with an ``OK`` that Textual would read as keyboard input. ``C=1`` keeps
    the cursor where it was, which is what lets us emit this from inside a
    line the compositor is already drawing.
    """
    payload = base64.standard_b64encode(png).decode("ascii")
    # 4096 bytes is the chunk size the protocol asks callers to respect.
    chunks = [payload[i : i + 4096] for i in range(0, len(payload), 4096)] or [""]
    out = []
    for index, chunk in enumerate(chunks):
        more = 1 if index < len(chunks) - 1 else 0
        if index == 0:
            keys = f"a=T,q=2,f=100,i={image_id},c={cols},r={rows},C=1,m={more}"
        else:
            keys = f"m={more}"
        out.append(f"\033_G{keys};{chunk}\033\\")
    return "".join(out)


def kitty_delete(image_id: int) -> str:
    """Remove a transmitted image. Sent before redrawing and on the way out."""
    return f"\033_Ga=d,d=I,i={image_id},q=2\033\\"


def to_png(image) -> bytes:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ----------------------------------------------------------------------- sixel


# For bit ``row`` of a sixel and palette index ``index``, a table that turns a
# row of indices into that bit where the index matches and 0 elsewhere. Built
# once: 256 indices times six rows of 256 bytes.
_BIT_TABLES = tuple(
    tuple(
        bytes((1 << row) if value == index else 0 for value in range(256))
        for row in range(6)
    )
    for index in range(256)
)
# From a sixel's six bits to its character, which is the bits plus 0x3F.
_TO_SIXEL = bytes((value + 0x3F) & 0xFF for value in range(256))
# `!n` costs three characters, so it only pays from four repeats up.
_RUNS = re.compile(rb"(.)\1{3,}", re.DOTALL)


def _run_length(line: bytes) -> bytes:
    return _RUNS.sub(lambda m: b"!%d%c" % (len(m.group(0)), m.group(1)[0]), line)


def sixel_escape(image, colors: int = 255) -> str:
    """Encode an image as sixel.

    Sixel packs six vertical pixels into one character, one colour at a time:
    for every band of six rows we replay the band once per colour present in
    it, separated by ``$`` (return to the start of the band), and end it with
    ``-``. Runs are collapsed with ``!n``, which is what keeps a flat album
    cover from producing hundreds of kilobytes.

    Worked a band and a colour at a time rather than a pixel at a time: each
    row of the band is turned into its bit with ``bytes.translate``, the six
    are joined with one OR of big integers, and the runs are found by a
    regular expression, all of it in C. The pixel-by-pixel version took 29 s
    for a full-screen cover on a 4K terminal, holding the interpreter the
    whole time; the output is the same, byte for byte.
    """

    quantized = image.convert("RGB").quantize(colors=max(2, min(colors, 255)))
    width, height = quantized.size
    palette = quantized.getpalette() or []
    # A quantized image is one palette index per pixel, so the raw buffer is
    # already the index matrix we need.
    data = quantized.tobytes()

    out = [f'\033Pq"1;1;{width};{height}']
    used = sorted(set(data))
    for index in used:
        red, green, blue = palette[index * 3 : index * 3 + 3]
        # Sixel colour components are percentages, not bytes.
        out.append(
            f"#{index};2;{round(red * 100 / 255)};"
            f"{round(green * 100 / 255)};{round(blue * 100 / 255)}"
        )

    for top in range(0, height, 6):
        depth = min(6, height - top)
        rows = [
            data[(top + row) * width : (top + row + 1) * width] for row in range(depth)
        ]
        present = sorted(set(data[top * width : (top + depth) * width]))
        for position, index in enumerate(present):
            if position:
                out.append("$")
            out.append(f"#{index}")
            tables = _BIT_TABLES[index]
            bits = 0
            for row, line in enumerate(rows):
                bits |= int.from_bytes(line.translate(tables[row]), "big")
            sixels = bits.to_bytes(width, "big").translate(_TO_SIXEL)
            # Trailing empties carry no ink; dropping them shrinks the payload.
            out.append(_run_length(sixels.rstrip(b"?")).decode("ascii"))
        out.append("-")
    out.append("\033\\")
    return "".join(out)


# ------------------------------------------------------------------ the façade


def render(
    data: bytes,
    cols: int,
    rows: int,
    protocol: Protocol,
    *,
    image_id: int = 1,
    outline: str = "square",
    ground: Pixel = (0, 0, 0),
) -> Cover | None:
    """Turn raw cover bytes into whatever ``protocol`` needs. ``None`` on failure."""
    if protocol is Protocol.NONE:
        return None
    image = decode(data, cols, rows, upscale=protocol is not Protocol.KITTY)
    if image is None:
        return None
    image = shape(image, outline, ground)
    if protocol is Protocol.KITTY:
        escape = kitty_escape(to_png(image), cols, rows, image_id)
        return Cover(cols, rows, protocol, escape=escape)
    if protocol is Protocol.SIXEL:
        return Cover(cols, rows, protocol, escape=sixel_escape(image))
    matrix = blocks(image, cols, rows)
    return Cover(cols, rows, protocol, pixels=matrix, cells=block_cells(matrix))
