"""Album art: fetch the cover and turn it into something a terminal can draw.

Three targets, in descending fidelity:

* **kitty graphics**, which draws real pixels above the text grid;
* **sixel**, DEC's older pixel format, still spoken by foot, mlterm, contour…;
* **half blocks**, which need no protocol at all: one cell becomes two pixels
  by painting ``▀`` in the top colour over the bottom colour as background.

Pillow is an optional dependency. Without it there is no decoder, so
:func:`decode` returns ``None``, the cover is simply not drawn, and nothing
else about the player changes — the same bargain as cava in `spectrum.py`.

This module knows nothing about Textual or tidalapi: it takes a URL and a box
measured in cells, and gives back either a pixel matrix or an escape sequence.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from dataclasses import dataclass
from enum import Enum
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


class Protocol(str, Enum):
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


def detect_protocol(env: dict[str, str] | None = None) -> Protocol:
    """Decide how to draw the cover, from the environment alone.

    Querying the terminal is the accurate way, but the reply would land in
    Textual's input stream; guessing from ``$TERM`` costs nothing and the
    half-block fallback is good enough that a wrong guess is not a failure.
    ``TIDALAMP_ART`` overrides everything, including ``off``.
    """
    env = os.environ if env is None else env

    forced = (env.get("TIDALAMP_ART") or "").strip().lower()
    if forced in {"off", "none"}:
        return Protocol.NONE
    if forced in {p.value for p in Protocol}:
        return Protocol(forced)
    if forced:
        log.warning("TIDALAMP_ART=%r no es un protocolo conocido; se ignora", forced)

    term = env.get("TERM", "")
    program = env.get("TERM_PROGRAM", "")
    if env.get("KITTY_WINDOW_ID") or term in _KITTY_TERMS or program in _KITTY_PROGRAMS:
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


# --------------------------------------------------------------------- fetching


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


def decode(data: bytes, cols: int, rows: int, *, cell: tuple[int, int] = CELL):
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
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:  # A broken download is not worth a traceback.
        log.warning("carátula ilegible: %s", exc)
        return None

    image = image.convert("RGB")
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
    return image.resize((width, height), Image.LANCZOS)


# ------------------------------------------------------------------ half blocks


def half_blocks(image, cols: int, rows: int) -> Matrix:
    """Sample the image into ``2 * rows`` rows of ``cols`` pixels.

    The widget paints each cell as ``▀``: the upper half takes the foreground
    colour and the lower half the background, which doubles vertical
    resolution for free.
    """
    small = image.resize((max(1, cols), max(1, rows * 2)))
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


def sixel_escape(image, colors: int = 255) -> str:
    """Encode an image as sixel.

    Sixel packs six vertical pixels into one character, one colour at a time:
    for every band of six rows we replay the band once per colour present in
    it, separated by ``$`` (return to the start of the band), and end it with
    ``-``. Runs are collapsed with ``!n``, which is what keeps a flat album
    cover from producing hundreds of kilobytes.
    """
    from PIL import Image

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
        band = data[top * width : min(top + 6, height) * width]
        depth = len(band) // width
        present = sorted(set(band))
        for position, index in enumerate(present):
            if position:
                out.append("$")
            out.append(f"#{index}")
            out.append(_sixel_row(band, width, depth, index))
        out.append("-")
    out.append("\033\\")
    return "".join(out)


def _sixel_row(band: bytes, width: int, depth: int, index: int) -> str:
    """One colour's contribution to one six-pixel-tall band, run-length coded."""
    pieces: list[str] = []
    run_char = ""
    run_length = 0
    for column in range(width):
        bits = 0
        for row in range(depth):
            if band[row * width + column] == index:
                bits |= 1 << row
        char = chr(0x3F + bits)
        if char == run_char:
            run_length += 1
            continue
        if run_char:
            pieces.append(_run(run_char, run_length))
        run_char, run_length = char, 1
    if run_char:
        pieces.append(_run(run_char, run_length))
    # Trailing empties carry no ink; dropping them shrinks the payload.
    while pieces and pieces[-1].endswith("?"):
        pieces.pop()
    return "".join(pieces)


def _run(char: str, length: int) -> str:
    # `!n` costs three characters, so it only pays from four repeats up.
    return char * length if length < 4 else f"!{length}{char}"


# ------------------------------------------------------------------ the façade


def render(
    data: bytes,
    cols: int,
    rows: int,
    protocol: Protocol,
    *,
    image_id: int = 1,
) -> Cover | None:
    """Turn raw cover bytes into whatever ``protocol`` needs. ``None`` on failure."""
    if protocol is Protocol.NONE:
        return None
    image = decode(data, cols, rows)
    if image is None:
        return None
    if protocol is Protocol.KITTY:
        escape = kitty_escape(to_png(image), cols, rows, image_id)
        return Cover(cols, rows, protocol, escape=escape)
    if protocol is Protocol.SIXEL:
        return Cover(cols, rows, protocol, escape=sixel_escape(image))
    return Cover(cols, rows, protocol, pixels=half_blocks(image, cols, rows))
