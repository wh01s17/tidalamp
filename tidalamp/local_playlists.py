"""Playlists of «Música local»: `.m3u8` files tidalamp writes and reads.

**A playlist is a file, not a record in some database.** Each one is an
extended M3U in UTF-8 under `PLAYLIST_DIR`, one absolute path a line, so any
other player opens it, and a playlist copied in from elsewhere shows up the
next time the level opens. The name is the `#PLAYLIST:` line when there is
one, and the file's name when there is not.

**Only files on this computer go in.** A playlist belongs to a source, as
`next.md` decided («Playlists separadas, cola mezclada»): a TIDAL track has
no path, and a line that only tidalamp could play would break the file for
every other player. The callers say how many were left out.

Nothing here knows about ``Row`` or Textual: `library` turns these into rows.
Every write goes through `write_atomically`, so a crash halfway leaves the
playlist as it was rather than half of it.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from .config import STATE_DIR, write_atomically
from .i18n import _

PLAYLIST_DIR = STATE_DIR / "playlists"
EXTENSIONS = (".m3u8", ".m3u")
# What the cache key of a playlist's level starts with; the file's name
# follows it, which is unique inside `PLAYLIST_DIR`.
KEY_PREFIX = "local:playlist:"

# What a file name cannot carry on Windows, and `/` on any system. A name
# that needs one keeps it on the `#PLAYLIST:` line, and the file gets `_`.
_UNSAFE = set('<>:"/\\|?*') | {chr(code) for code in range(32)}


class PlaylistExists(ValueError):
    """There is already a playlist by that name."""


class TrackNotInPlaylist(LookupError):
    """The file is no longer in the playlist the browser showed it in."""


@dataclass(slots=True)
class Item:
    """One line of a playlist: the file, and the `#EXTINF` said about it."""

    path: str
    info: str = ""


@dataclass(slots=True)
class Playlist:
    path: Path
    name: str
    items: list[Item] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{KEY_PREFIX}{self.path.name}"

    @property
    def tracks(self) -> list[str]:
        return [item.path for item in self.items]


# ------------------------------------------------------------------ reading


def _resolve(line: str, base: Path) -> str:
    """A playlist line as a path: absolute as it is, a `file://` URI turned
    back into one, and relative to the playlist's folder otherwise."""
    if line.startswith("file://"):
        # url2pathname, not unquote: on Windows `file:///C:/x` is a drive path.
        return url2pathname(urlparse(line).path)
    path = Path(os.path.expandvars(line)).expanduser()
    if not path.is_absolute():
        path = base / path
    return os.path.normpath(path)


def load(path: Path) -> Playlist:
    """One playlist, as its file says. A missing file raises `OSError`."""
    # utf-8-sig: a BOM is what Windows tools put at the head of an `.m3u8`.
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    name = ""
    items: list[Item] = []
    info = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#PLAYLIST:"):
            name = name or line.partition(":")[2].strip()
        elif line.startswith("#EXTINF:"):
            info = line.partition(":")[2]
        elif line.startswith("#"):
            continue
        elif "://" in line and not line.startswith("file://"):
            # A stream URL: not a file on this computer, and nothing this
            # section can show. Kept out rather than shown broken.
            info = ""
        else:
            items.append(Item(_resolve(line, path.parent), info))
            info = ""
    return Playlist(path=path, name=name or path.stem, items=items)


def listing(directory: Path | None = None) -> list[Playlist]:
    """Every playlist in ``directory``, by name. One that cannot be read is
    left out, as a file mutagen cannot read is still listed: there is nothing
    in it to show."""
    folder = PLAYLIST_DIR if directory is None else directory
    try:
        files = [
            entry
            for entry in folder.iterdir()
            if entry.suffix.lower() in EXTENSIONS
            and entry.is_file()
            and not entry.name.startswith(".")
        ]
    except OSError:
        return []
    found = []
    for path in files:
        try:
            found.append(load(path))
        except OSError:
            continue
    found.sort(key=lambda playlist: (playlist.name.casefold(), playlist.path.name))
    return found


def find(key: str, directory: Path | None = None) -> Path:
    """The file behind a playlist row's cache key."""
    name = key.removeprefix(KEY_PREFIX)
    if not name or name != Path(name).name:
        raise ValueError(key)
    return (PLAYLIST_DIR if directory is None else directory) / name


# ------------------------------------------------------------------ writing


def _write(playlist: Playlist) -> None:
    lines = ["#EXTM3U"]
    if playlist.name != playlist.path.stem:
        lines.append(f"#PLAYLIST:{playlist.name}")
    for item in playlist.items:
        if item.info:
            lines.append(f"#EXTINF:{item.info}")
        lines.append(item.path)
    write_atomically(playlist.path, "\n".join(lines) + "\n")


def _clean(name: str) -> str:
    # A newline in the name would end the `#PLAYLIST:` line early.
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValueError(_("una playlist necesita un nombre"))
    return cleaned


def _file_name(name: str) -> str:
    stem = "".join("_" if char in _UNSAFE else char for char in name).strip(" .")
    return f"{stem or '_'}.m3u8"


def _taken(name: str, folder: Path, but: Path | None = None) -> bool:
    """Whether another playlist already goes by ``name``, ignoring case: two
    names that differ only in it are one file on Windows and macOS."""
    wanted = name.casefold()
    return any(
        playlist.name.casefold() == wanted and playlist.path != but
        for playlist in listing(folder)
    )


def _item(entry: Any) -> Item:
    return Item(path=str(entry.url), info=f"{int(entry.duration or 0)},{entry.label}")


def local_only(entries: Iterable[Any]) -> tuple[list[Any], int]:
    """The entries that are files on this computer, and how many were not."""
    kept, skipped = [], 0
    for entry in entries:
        if getattr(entry, "is_local", False) and getattr(entry, "url", ""):
            kept.append(entry)
        else:
            skipped += 1
    return kept, skipped


def create(
    name: str, entries: Iterable[Any] = (), directory: Path | None = None
) -> Playlist:
    """A new playlist called ``name``, with ``entries`` in it, in that order.

    Raises `PlaylistExists` rather than add to one already there: asking
    for a new playlist and getting tracks mixed into an old one is the
    opposite of what was asked.
    """
    folder = PLAYLIST_DIR if directory is None else directory
    name = _clean(name)
    if _taken(name, folder):
        raise PlaylistExists(name)
    path = folder / _file_name(name)
    # Two names can clean to the same file («a/b» and «a_b»): number it.
    count = 2
    while path.exists():
        path = folder / _file_name(f"{name} ({count})")
        count += 1
    playlist = Playlist(path=path, name=name, items=[_item(e) for e in entries])
    _write(playlist)
    return playlist


def add(path: Path, entries: Iterable[Any]) -> int:
    """Append ``entries`` to the end of a playlist. Duplicates go in, as they
    do in TIDAL's: adding the same record twice is a thing someone can mean."""
    playlist = load(path)
    new = [_item(entry) for entry in entries]
    playlist.items.extend(new)
    _write(playlist)
    return len(new)


def remove(path: Path, track: str) -> str:
    """Take one file out of a playlist; returns the playlist's name.

    By path and not by position: the browser may show the playlist sorted,
    and the row's place on screen is then no line of the file. A file that
    is in it twice loses its first appearance, as in TIDAL's.
    """
    playlist = load(path)
    for index, item in enumerate(playlist.items):
        if item.path == track:
            del playlist.items[index]
            _write(playlist)
            return playlist.name
    raise TrackNotInPlaylist(track)


def move(path: Path, index: int, track: str, delta: int) -> str:
    """Move the file at ``index`` ``delta`` places; returns the name.

    The file at ``index`` is checked to be ``track`` first: another program
    may have changed the playlist since the browser read it, and moving by a
    stale position would move a neighbour.
    """
    playlist = load(path)
    items = playlist.items
    if not 0 <= index < len(items) or items[index].path != track:
        raise TrackNotInPlaylist(track)
    target = index + delta
    if 0 <= target < len(items):
        items[index], items[target] = items[target], items[index]
        _write(playlist)
    return playlist.name


def rename(path: Path, name: str) -> Playlist:
    """Give a playlist a new name, and its file the name to go with it."""
    playlist = load(path)
    name = _clean(name)
    if _taken(name, path.parent, but=path):
        raise PlaylistExists(name)
    playlist.name = name
    target = path.parent / _file_name(name)
    if target.exists() and target != path and not _same_file(target, path):
        count = 2
        while target.exists():
            target = path.parent / _file_name(f"{name} ({count})")
            count += 1
    playlist.path = target
    _write(playlist)
    if not _same_file(target, path):
        path.unlink(missing_ok=True)
    return playlist


def _same_file(one: Path, other: Path) -> bool:
    """Whether two paths are one file: only their case differs on a system
    that does not tell them apart."""
    try:
        return one.samefile(other)
    except OSError:
        return False


def delete(path: Path) -> str:
    """Delete a playlist's file; returns its name. The music is not touched."""
    name = load(path).name
    path.unlink()
    return name
