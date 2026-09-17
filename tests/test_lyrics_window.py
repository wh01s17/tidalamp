"""The lyrics window with lines wider than it: they wrap, and the window
counts rows, not lines."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime, settle

from tidalamp.app import TidalAmp
from tidalamp.lyrics import LyricLine, LyricsDocument
from tidalamp.queue import Entry
from tidalamp.screens import LyricsScreen

LONG = "palabra " * 18  # about 144 cells: two or three rows at any width here


def _document(synced: bool, count: int = 40) -> LyricsDocument:
    return LyricsDocument(
        tuple(
            LyricLine(float(i * 5) if synced else None, f"{LONG}VERSO-{i:02d}")
            for i in range(count)
        )
    )


def _drawn(document: LyricsDocument, position: float, keys: tuple[str, ...] = ()):
    entry = Entry(id=1, title="t", artist="a")
    seen: dict[str, object] = {}

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = LyricsScreen(lambda: entry, lambda _e: document, lambda: position)
            application.push_screen(screen)
            await settle(pilot, lambda: screen._document is not None)
            for key in keys:
                await pilot.press(key)
            screen._refresh_lyrics()
            await pilot.pause()
            body = screen.query_one("#lyrics-body")
            seen["rows"] = [
                body.render_line(y).text.rstrip() for y in range(body.size.height)
            ]
            seen["width"] = body.content_size.width

    asyncio.run(scenario())
    return seen


def test_the_sung_line_stays_on_screen_when_the_lines_wrap(monkeypatch):
    """`window()` counted lines: with every line two rows tall, the sung one
    was pushed below the bottom of the window."""
    isolate_runtime(monkeypatch)

    seen = _drawn(_document(synced=True), position=20 * 5 + 1)

    text = "\n".join(seen["rows"])
    assert "VERSO-20" in text
    active = next(row for row in seen["rows"] if "▶" in row)
    assert "palabra" in active


def test_a_wrapped_line_keeps_its_indent(monkeypatch):
    """The second row of a line comes back under its text, not under the marker."""
    isolate_runtime(monkeypatch)

    seen = _drawn(_document(synced=True), position=1)

    rows = [row for row in seen["rows"] if row.strip()]
    continuation = next(row for row in rows if "VERSO-00" in row)
    # Under the text, two cells in: where the marker is on the first row.
    assert continuation.startswith(("  palabra", "  VERSO"))


def test_plain_lyrics_scroll_to_their_last_line_even_when_it_wraps(monkeypatch):
    """The scroll stopped at `len(lines) - height`, which with wrapped lines
    left the end of the song below the window."""
    isolate_runtime(monkeypatch)

    seen = _drawn(_document(synced=False), position=0, keys=("pagedown",) * 10)

    assert "VERSO-39" in "\n".join(seen["rows"])
