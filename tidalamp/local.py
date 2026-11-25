"""«Música local»: the audio files in the folders the user points at.

**mpv does the playing, this module does the knowing.** mpv already opens a
FLAC at 24/192, a DSF or a WavPack the way it opens anything else, at the
file's own rate, so what a local track needs from tidalamp is what mpv does
not say before it plays: its tags, its length, its rate and its depth, and a
cover. `mutagen` reads all of that without decoding a sample.

**Scanned once, then stat'ed.** Reading the tags of a few thousand files
takes a while; checking that they have not changed takes very little. Every
file read goes into `INDEX_FILE` with its size and modification time, and the
next scan reads again only what is new or touched since.

Nothing here knows about ``Row`` or Textual: `library` turns these into
rows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from . import config
from .config import CACHE_DIR, write_atomically
from .i18n import _

log = logging.getLogger("tidalamp.local")

# What a folder of music holds that mpv plays: lossless first, because that
# is what this section is for, then the lossy formats people still keep.
LOSSLESS = frozenset(
    {".flac", ".wav", ".aif", ".aiff", ".aifc", ".ape", ".wv", ".dsf", ".dff", ".tta"}
)
LOSSY = frozenset({".mp3", ".ogg", ".oga", ".opus", ".m4a", ".mp4", ".aac", ".mpc"})
EXTENSIONS = LOSSLESS | LOSSY

# The names a cover goes by in a record's folder, most deliberate first.
_COVER_NAMES = ("cover", "folder", "front", "album", "albumart")
_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

# Every file read so far, so the next scan reads only what changed. Keyed by
# path; bump the version whenever `Track` changes shape, or an old index
# loads quietly wrong.
INDEX_FILE = CACHE_DIR / "local-index.json"
INDEX_VERSION = 1
# Covers that only exist inside a file, written out once so the artwork code
# can read them like any other.
ART_DIR = CACHE_DIR / "local-art"


class LocalUnavailable(RuntimeError):
    """No folders configured, or none of them can be read."""


@dataclass(frozen=True, slots=True)
class Track:
    """One audio file, as much of it as the tags and the header say."""

    path: str
    title: str
    artist: str
    album: str
    album_artist: str = ""
    year: int = 0
    track_num: int = 0
    disc: int = 0
    duration: int = 0
    codec: str = ""
    sample_rate: int = 0
    bit_depth: int = 0
    bitrate: int = 0
    # When the file arrived, as the filesystem says: what «recientes primero»
    # sorts by, the way a favourite sorts by when it was added.
    added: float = 0.0
    art_url: str = ""

    @property
    def id(self) -> int:
        """A stable negative id, unique to this file.

        Negative so that it can never be taken for a TIDAL track's id, which
        is always positive. The `local:` prefix is part of the hash, and
        changing it would orphan every local row in a saved queue.
        """
        return -(zlib.crc32(f"local:{self.path}".encode()) or 1)

    @property
    def lossless(self) -> bool:
        return Path(self.path).suffix.lower() in LOSSLESS or self.codec == "ALAC"

    @property
    def quality(self) -> str:
        """What the queue's quality column and the badge say: «FLAC 24/96»."""
        parts = [self.codec]
        if self.lossless and self.sample_rate:
            rate = f"{self.sample_rate / 1000:g}"
            parts.append(f"{self.bit_depth}/{rate}" if self.bit_depth else f"{rate} kHz")
        elif self.bitrate:
            parts.append(f"{self.bitrate // 1000} kbps")
        return " ".join(part for part in parts if part)

    @property
    def hires(self) -> bool:
        """More than a CD holds: over 16 bits or over 48 kHz."""
        return self.lossless and (self.bit_depth > 16 or self.sample_rate > 48000)

    @property
    def album_key(self) -> str:
        """What makes two files the same record: its artist and its name, or
        its folder when the tags say neither."""
        artist = (self.album_artist or self.artist).casefold()
        if self.album:
            return f"{artist}\x00{self.album.casefold()}"
        return f"\x00{Path(self.path).parent}"


# ------------------------------------------------------------------ folders


def folders(raw: Iterable[str] | None = None) -> list[Path]:
    """The folders configured, expanded, in the order they were added."""
    value = config.LOCAL_FOLDERS if raw is None else raw
    return [Path(os.path.expandvars(item)).expanduser() for item in value]


def audio_files(roots: Iterable[Path]) -> Iterator[Path]:
    """Every audio file under ``roots``, each one once, hidden folders skipped."""
    seen: set[str] = set()
    for root in roots:
        for directory, subdirs, names in os.walk(root, followlinks=True):
            subdirs[:] = sorted(name for name in subdirs if not name.startswith("."))
            for name in sorted(names):
                if Path(name).suffix.lower() not in EXTENSIONS or name.startswith("."):
                    continue
                path = os.path.realpath(os.path.join(directory, name))
                if path not in seen:
                    seen.add(path)
                    yield Path(path)


# -------------------------------------------------------------------- tags

# The same field under every tag format mutagen hands back: the "easy" names
# (FLAC, Ogg, easy ID3 and MP4), APEv2's capitalised ones, and the raw ID3
# frames a DSF carries.
_FIELDS: dict[str, tuple[str, ...]] = {
    "title": ("title", "TIT2"),
    "artist": ("artist", "TPE1"),
    "album": ("album", "TALB"),
    "album_artist": ("albumartist", "album artist", "album_artist", "TPE2"),
    "date": ("date", "year", "originaldate", "TDRC", "TYER"),
    "track": ("tracknumber", "track", "TRCK"),
    "disc": ("discnumber", "disc", "TPOS"),
}


def _first(value: Any) -> str:
    """One tag value as text: ID3 frames, lists and APE values all unwrap."""
    value = getattr(value, "text", value)
    if isinstance(value, list | tuple):
        value = value[0] if value else ""
    return str(value).strip()


def _tag(tags: Any, field: str) -> str:
    if not tags:
        return ""
    try:
        # `.keys()` on purpose: a Vorbis comment iterates as (key, value).
        lowered = {str(key).casefold(): key for key in tags.keys()}  # noqa: SIM118
    except Exception:
        return ""
    for name in _FIELDS[field]:
        key = lowered.get(name.casefold())
        if key is not None:
            text = _first(tags[key])
            if text:
                return text
    return ""


def _number(text: str) -> int:
    """`3`, `3/12` or `2009-05-01`: the leading number, or 0."""
    digits = ""
    for char in text:
        if not char.isdigit():
            break
        digits += char
    return int(digits) if digits else 0


def _codec(path: Path, audio: Any) -> str:
    suffix = path.suffix.lower()
    if suffix in (".m4a", ".mp4"):
        codec = str(getattr(audio.info, "codec", "") or "").lower()
        return "ALAC" if codec.startswith("alac") else "AAC"
    return {
        ".flac": "FLAC",
        ".wav": "WAV",
        ".aif": "AIFF",
        ".aiff": "AIFF",
        ".aifc": "AIFF",
        ".ape": "APE",
        ".wv": "WavPack",
        ".dsf": "DSD",
        ".dff": "DSD",
        ".tta": "TTA",
        ".mp3": "MP3",
        ".ogg": "Vorbis",
        ".oga": "Vorbis",
        ".opus": "Opus",
        ".aac": "AAC",
        ".mpc": "Musepack",
    }.get(suffix, suffix.lstrip(".").upper())


def _open(path: Path) -> Any:
    import mutagen

    try:
        return mutagen.File(path, easy=True)
    except Exception as exc:
        log.debug("no se pudo leer %s: %s", path, exc)
        return None


def read(path: Path, *, stat: os.stat_result | None = None) -> Track:
    """One file's tags and header. A file mutagen cannot read is still a
    track: its name is the title, its folder the album, and mpv decides."""
    stat = stat or path.stat()
    audio = _open(path)
    tags = getattr(audio, "tags", None)
    info = getattr(audio, "info", None)
    return Track(
        path=str(path),
        title=_tag(tags, "title") or path.stem,
        artist=_tag(tags, "artist"),
        album=_tag(tags, "album") or path.parent.name,
        album_artist=_tag(tags, "album_artist"),
        year=_number(_tag(tags, "date")),
        track_num=_number(_tag(tags, "track")),
        disc=_number(_tag(tags, "disc")),
        duration=int(getattr(info, "length", 0) or 0),
        codec=_codec(path, audio) if audio is not None else _codec(path, None),
        sample_rate=int(getattr(info, "sample_rate", 0) or 0),
        bit_depth=int(getattr(info, "bits_per_sample", 0) or 0),
        bitrate=int(getattr(info, "bitrate", 0) or 0),
        added=stat.st_mtime,
    )


def header(path: str) -> tuple[int, int]:
    """The rate and depth of one file, for the badge of what is playing."""
    info = getattr(_open(Path(path)), "info", None)
    return (
        int(getattr(info, "sample_rate", 0) or 0),
        int(getattr(info, "bits_per_sample", 0) or 0),
    )


# ------------------------------------------------------------------- covers


def _folder_cover(directory: Path) -> Path | None:
    try:
        images = sorted(
            entry
            for entry in directory.iterdir()
            if entry.suffix.lower() in _IMAGE_EXTENSIONS and entry.is_file()
        )
    except OSError:
        return None
    for name in _COVER_NAMES:
        for image in images:
            if image.stem.casefold() == name:
                return image
    return images[0] if images else None


def _embedded_cover(path: Path) -> bytes:
    """The picture inside a file, if it carries one: FLAC's pictures, an ID3
    APIC frame, MP4's `covr`."""
    import mutagen

    try:
        audio = mutagen.File(path)
    except Exception:
        return b""
    if audio is None:
        return b""
    pictures = getattr(audio, "pictures", None)
    if pictures:
        return bytes(pictures[0].data)
    tags = getattr(audio, "tags", None) or {}
    try:
        for key in tags.keys():  # noqa: SIM118
            if str(key).startswith("APIC"):
                return bytes(tags[key].data)
            if key == "covr" and tags[key]:
                return bytes(tags[key][0])
    except Exception:
        return b""
    return b""


def _cover_for(directory: Path, tracks: list[Track]) -> str:
    """A file URI for a record's cover: the image in its folder, or the one
    inside its first file that has one, written out to `ART_DIR`."""
    found = _folder_cover(directory)
    if found is not None:
        return found.as_uri()
    for track in tracks:
        data = _embedded_cover(Path(track.path))
        if data:
            name = hashlib.sha256(str(directory).encode()).hexdigest()[:32]
            target = ART_DIR / f"{name}.img"
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            except OSError as exc:
                log.warning("no se pudo guardar la carátula de %s: %s", directory, exc)
                return ""
            return target.as_uri()
    return ""


# -------------------------------------------------------------------- scan


def _load_index() -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or raw.get("version") != INDEX_VERSION:
        return {}
    files = raw.get("files")
    return files if isinstance(files, dict) else {}


_NAMES = tuple(field.name for field in fields(Track))


def _from_index(raw: dict[str, Any]) -> Track | None:
    try:
        return Track(**{name: raw[name] for name in _NAMES})
    except (KeyError, TypeError):
        return None


def scan(roots: Iterable[Path] | None = None) -> list[Track]:
    """Every track under the configured folders, newest first.

    Raises `LocalUnavailable` when there is nothing to scan: no folder set,
    or none of them there. A folder that is there and holds no audio is an
    empty list, which the browser shows as an empty level.
    """
    wanted = folders() if roots is None else list(roots)
    if not wanted:
        raise LocalUnavailable(
            _("no hay carpetas de música: añádelas en la configuración (o)")
        )
    present = [root for root in wanted if root.is_dir()]
    if not present:
        raise LocalUnavailable(
            _("no se encontró ninguna de las carpetas de música configuradas")
        )

    index = _load_index()
    kept: dict[str, dict[str, Any]] = {}
    tracks: list[Track] = []
    fresh: dict[Path, list[Track]] = {}
    for path in audio_files(present):
        try:
            stat = path.stat()
        except OSError:
            continue
        key = str(path)
        cached = index.get(key)
        track = None
        if (
            cached is not None
            and cached.get("mtime") == stat.st_mtime
            and cached.get("size") == stat.st_size
        ):
            track = _from_index(cached)
        if track is None:
            track = read(path, stat=stat)
            fresh.setdefault(path.parent, []).append(track)
        tracks.append(track)
        kept[key] = {**asdict(track), "mtime": stat.st_mtime, "size": stat.st_size}

    # A cover per folder that has new files, shared by every track in it.
    covers = {directory: _cover_for(directory, new) for directory, new in fresh.items()}
    if covers:
        for at, track in enumerate(tracks):
            directory = Path(track.path).parent
            if directory in covers and not track.art_url:
                art = covers[directory]
                if art:
                    track = _replace(track, art_url=art)
                    tracks[at] = track
                    kept[track.path]["art_url"] = art
    if kept != index:
        try:
            write_atomically(
                INDEX_FILE, json.dumps({"version": INDEX_VERSION, "files": kept})
            )
        except OSError as exc:
            log.warning("no se pudo guardar el índice de música local: %s", exc)
    tracks.sort(key=lambda track: track.added, reverse=True)
    return tracks


def _replace(track: Track, **changes: Any) -> Track:
    return Track(**{**asdict(track), **changes})


# ------------------------------------------------------------------ grouping


@dataclass(slots=True)
class Album:
    """A record: the tracks sharing an album and its artist."""

    title: str
    artist: str
    year: int
    tracks: list[Track]

    @property
    def added(self) -> float:
        """When its newest file arrived: a record grows when a disc is added."""
        return max((track.added for track in self.tracks), default=0.0)

    @property
    def art_url(self) -> str:
        return next((track.art_url for track in self.tracks if track.art_url), "")

    @property
    def quality(self) -> str:
        """The best of its tracks, which is what a record is bought as."""
        best = max(
            self.tracks,
            key=lambda track: (track.bit_depth, track.sample_rate),
            default=None,
        )
        return best.quality if best is not None else ""


def albums(tracks: Iterable[Track]) -> list[Album]:
    """The records ``tracks`` make, each one's tracks in disc and track order,
    the records newest first."""
    grouped: dict[str, list[Track]] = {}
    for track in tracks:
        grouped.setdefault(track.album_key, []).append(track)
    records = []
    for members in grouped.values():
        members.sort(key=lambda track: (track.disc, track.track_num, track.path))
        first = members[0]
        artists = {track.album_artist or track.artist for track in members}
        records.append(
            Album(
                title=first.album,
                artist=(
                    first.album_artist
                    or (first.artist if len(artists) == 1 else _("Varios artistas"))
                ),
                year=max(track.year for track in members),
                tracks=members,
            )
        )
    records.sort(key=lambda album: album.added, reverse=True)
    return records


def artists(records: Iterable[Album]) -> dict[str, list[Album]]:
    """Each record artist and their records, by name as it is first written."""
    found: dict[str, list[Album]] = {}
    names: dict[str, str] = {}
    for album in records:
        name = names.setdefault(album.artist.casefold(), album.artist)
        found.setdefault(name, []).append(album)
    return found
