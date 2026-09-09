"""The queue's columns: what exists, how wide it is, and how to read it.

A module of its own because both ends need it and neither can import the
other: `config` validates the names a user wrote in the file, and `screens`
draws them. Nothing internal is imported here beyond a type, so it can sit
underneath both.

Every field below comes filled in on a plain track listing — checked against
the real API — so turning a column on never costs an extra request. The two
that TIDAL does not always answer (`version`, and `year` on an album with no
release date) leave their cell blank rather than inventing a value.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle, and only a type
    from .queue import Entry


@dataclass(frozen=True)
class Column:
    """One optional column.

    ``width`` is in terminal cells, or 0 for the columns that share whatever
    the title does not need. ``drop`` orders them for a narrow list: the
    highest goes first, so a small window keeps the ones worth keeping.
    """

    name: str
    width: int
    align: str
    drop: int
    read: Callable[[Entry], str]


# TIDAL's own names, shortened to something that fits a badge or a column.
# Shared with the display band so the two never disagree.
QUALITY_LABELS = {
    "HI_RES_LOSSLESS": "HI-RES",
    "LOSSLESS": "LOSSLESS",
    "HIGH": "HIGH",
    "LOW": "LOW",
}


def _quality(entry: Entry) -> str:
    return QUALITY_LABELS.get(entry.quality, entry.quality)


def _year(entry: Entry) -> str:
    return str(entry.year) if entry.year else ""


def _number(value: int) -> str:
    return str(value) if value else ""


# In display order, left to right. Two things are not here because there is
# nothing to choose about them: the title, and the queue position drawn at the
# far left. `track` is the number the song carries on its own album, which is
# a different number and was read as that one until it was renamed.
ALL: tuple[Column, ...] = (
    Column("track", 3, "right", 40, lambda e: _number(e.track_num)),
    Column("version", 0, "left", 50, lambda e: e.version),
    Column("artist", 0, "left", 10, lambda e: e.artist),
    Column("album", 0, "left", 20, lambda e: e.album),
    Column("year", 4, "right", 30, _year),
    Column("quality", 8, "left", 60, _quality),
    Column("explicit", 1, "left", 70, lambda e: "E" if e.explicit else ""),
    Column("popularity", 3, "right", 80, lambda e: _number(e.popularity)),
    Column("disc", 2, "right", 90, lambda e: _number(e.disc)),
    Column("isrc", 12, "left", 100, lambda e: e.isrc),
    # Special: its text is the row's own `detail`, because a browser row that
    # is not a track puts «101 pistas» there instead of a running time. The
    # renderer measures it over the whole list, so it is width 0 here.
    Column("duration", 0, "right", 5, lambda e: e.length),
)

BY_NAME = {column.name: column for column in ALL}
NAMES = tuple(BY_NAME)

# What the queue drew before any of this was configurable.
DEFAULT = ("artist", "album", "year", "duration")
