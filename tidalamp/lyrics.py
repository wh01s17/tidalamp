"""Lyrics loading and LRC parsing.

TIDAL may return both plain lyrics and timestamped ``subtitles``.  Keep this
module independent from Textual so parsing and synchronization can be tested
without a terminal or a real account.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any

from .net import with_retries

_TIMESTAMP = re.compile(
    r"\[(?P<minutes>\d{1,3}):(?P<seconds>\d{2})(?:[\.:](?P<fraction>\d{1,3}))?\]"
)


class LyricsUnavailable(RuntimeError):
    """The current track has no usable lyrics."""


@dataclass(frozen=True)
class LyricLine:
    at: float | None
    text: str


@dataclass(frozen=True)
class LyricsDocument:
    lines: tuple[LyricLine, ...]
    provider: str = ""

    @property
    def synced(self) -> bool:
        return bool(self.lines) and all(line.at is not None for line in self.lines)

    def active_index(self, position: float) -> int | None:
        """Return the line active at ``position``, or None for plain lyrics."""
        if not self.synced:
            return None
        timestamps = [line.at for line in self.lines if line.at is not None]
        index = bisect_right(timestamps, max(0.0, position)) - 1
        return index if index >= 0 else None

    def window(
        self, position: float, height: int
    ) -> tuple[int, tuple[LyricLine, ...], int | None]:
        """Return a viewport centred around the active synchronized line."""
        height = max(1, height)
        active = self.active_index(position)
        if active is None:
            return 0, self.lines[:height], None
        start = max(0, min(active - height // 2, len(self.lines) - height))
        return start, self.lines[start : start + height], active


def _seconds(match: re.Match[str]) -> float:
    fraction = match.group("fraction") or ""
    decimal = int(fraction) / (10 ** len(fraction)) if fraction else 0.0
    return int(match.group("minutes")) * 60 + int(match.group("seconds")) + decimal


def _plain_lines(text: str) -> tuple[LyricLine, ...]:
    raw = [line.rstrip() for line in text.strip("\n").splitlines()]
    if not any(line.strip() for line in raw):
        return ()
    return tuple(LyricLine(None, line) for line in raw)


def parse_lyrics(text: str = "", subtitles: str = "", provider: str = "") -> LyricsDocument:
    """Parse TIDAL's LRC subtitles, falling back to its plain lyric text."""
    timed: list[LyricLine] = []
    for raw in subtitles.splitlines():
        matches = list(_TIMESTAMP.finditer(raw))
        if not matches:
            # LRC metadata such as [ar:...] and unknown subtitle formats are
            # ignored; the plain text field remains the safe fallback.
            continue
        content = _TIMESTAMP.sub("", raw).strip() or "♪"
        timed.extend(LyricLine(_seconds(match), content) for match in matches)

    if timed:
        timed.sort(key=lambda line: line.at if line.at is not None else -1.0)
        return LyricsDocument(tuple(timed), provider)
    return LyricsDocument(_plain_lines(text), provider)


def load_lyrics(track: Any) -> LyricsDocument:
    """Fetch and parse lyrics for ``track`` without leaking API exceptions."""
    name = getattr(track, "name", "esta pista")
    try:
        raw = with_retries(track.lyrics)
    except Exception as exc:
        raise LyricsUnavailable(f"Letra no disponible para «{name}»: {exc}") from exc

    document = parse_lyrics(
        text=getattr(raw, "text", "") or "",
        subtitles=getattr(raw, "subtitles", "") or "",
        provider=getattr(raw, "provider", "") or "",
    )
    if not document.lines:
        raise LyricsUnavailable(f"Letra no disponible para «{name}»")
    return document
