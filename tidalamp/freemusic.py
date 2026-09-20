"""Copyright-free lofi from the Internet Archive.

The Archive's search and metadata endpoints need no account and no API key,
which is the same reason the rest of the project talks to TIDAL through the
device flow: registering an app is a dependency on somebody's goodwill, and
this one would buy nothing.

Only permissive licences get in — CC0, the public domain mark, CC BY and
CC BY-SA. Every Creative Commons licence allows *listening*, so filtering is
not what makes playback lawful; it is what makes the section's name true.
«Lofi sin copyright» promises music you can actually use, and BY-NC-ND (the
Archive's most common licence by far: 6009 of the 10421 lofi items) does not
deliver that. See `LICENCES` below for the shape of the filter.

Nothing here knows about ``Row``, tidalapi or Textual: it answers with the two
dataclasses below and `library` turns them into rows. That keeps the module
testable against a recorded JSON body and keeps TIDAL out of it.
"""

from __future__ import annotations

import logging
import zlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

from .i18n import _
from .net import TimeoutSession, with_retries

log = logging.getLogger("tidalamp.freemusic")

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata"
DOWNLOAD_URL = "https://archive.org/download"
# The Archive renders a square thumbnail for any item at this path, whatever
# the item actually holds, so a record with no cover still answers 200.
IMAGE_URL = "https://archive.org/services/img"

# Who we say we are. The Archive asks for a real user agent and throttles the
# ones that do not identify themselves.
USER_AGENT = "tidalamp (+https://github.com/wh01s17/tidalamp)"

# What the section is: lofi audio, and nothing that is only a video with a
# soundtrack. `subject` is the Archive's tag field.
SUBJECT = '(subject:("lofi" OR "lo-fi") AND mediatype:audio)'

# The permissive half of Creative Commons, as substrings of `licenseurl`.
# Measured against the live index on 2026-09-20: 754 items in the public
# domain or CC0, 753 CC BY, 367 CC BY-SA, 1937 together.
LICENCES = (
    "*publicdomain*",
    "*licenses\\/by\\/*",
    "*licenses\\/by-sa\\/*",
)
QUERY = f"{SUBJECT} AND ({' OR '.join(f'licenseurl:{lic}' for lic in LICENCES)})"

# The fields the search has to bring back for a row to be drawable without a
# second request per item.
FIELDS = ("identifier", "title", "creator", "licenseurl", "year", "downloads")

# The Archive derives several encodings of every upload. These are the ones
# mpv opens, best first: the original lossless when it is there, then the
# variable-rate MP3 the Archive makes for everything, then the rest.
FORMATS = ("Flac", "Ogg Vorbis", "VBR MP3", "MP3", "128Kbps MP3", "64Kbps MP3")

# What the SRC badge says instead of a TIDAL quality tier.
CODECS = {
    "Flac": "FLAC",
    "Ogg Vorbis": "VORBIS",
    "VBR MP3": "MP3",
    "MP3": "MP3",
    "128Kbps MP3": "MP3",
    "64Kbps MP3": "MP3",
}

# How the licence reads on screen. The Archive writes the URL, not the name,
# and the version at the end of it is noise in a row that has 24 cells.
_LICENCE_NAMES = (
    ("publicdomain/zero", "CC0"),
    ("publicdomain/mark", _("dominio público")),
    ("publicdomain", _("dominio público")),
    ("licenses/by-sa", "CC BY-SA"),
    ("licenses/by", "CC BY"),
)


class FreeMusicUnavailable(RuntimeError):
    """The Archive did not answer, or answered with nothing usable."""


def licence_name(url: str) -> str:
    """«CC BY-SA» out of a licenseurl, or the URL when it is not one we know."""
    lowered = url.lower()
    for fragment, name in _LICENCE_NAMES:
        if fragment in lowered:
            return name
    return url


@dataclass(frozen=True, slots=True)
class Album:
    """One Archive item: a record, an EP or a single upload of several tracks."""

    identifier: str
    title: str
    creator: str
    licence: str
    year: int = 0

    @property
    def art_url(self) -> str:
        return f"{IMAGE_URL}/{self.identifier}"


@dataclass(frozen=True, slots=True)
class Track:
    """One playable file inside an item."""

    url: str
    title: str
    artist: str
    album: str
    licence: str
    duration: int = 0
    year: int = 0
    track_num: int = 0
    codec: str = ""
    art_url: str = ""

    @property
    def id(self) -> int:
        """A stable negative id, unique to this URL.

        Negative on purpose: TIDAL's track ids are positive, and the queue
        keys deduplication, the lyrics cache and the restored-entry identity
        off ``Entry.id``. A number no TIDAL track can ever hold keeps those
        three working untouched, and deriving it from the URL means the same
        file restores from disk as the same track.
        """
        return -(zlib.crc32(self.url.encode("utf-8")) or 1)


def _session() -> requests.Session:
    session = TimeoutSession()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _get(url: str, params: dict[str, Any] | None = None) -> Any:
    """One GET against the Archive, retried and parsed.

    ``raise_for_status`` before the parse so `with_retries` sees the HTTPError
    for a 5xx and gives it another go; a body that is not JSON is the Archive
    serving an error page, which is not worth retrying.
    """

    def call() -> Any:
        response = _session().get(url, params=params)
        response.raise_for_status()
        return response.json()

    try:
        return with_retries(call)
    except ValueError as exc:
        raise FreeMusicUnavailable(
            _("el Internet Archive contestó algo que no es JSON")
        ) from exc
    except requests.RequestException as exc:
        raise FreeMusicUnavailable(
            _("no se pudo hablar con el Internet Archive: {error}").format(error=exc)
        ) from exc


def _int(value: Any) -> int:
    """The Archive types loosely: a year may arrive as int, str or a list."""
    if isinstance(value, list):
        value = value[0] if value else 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    """Likewise for text: `creator` is a list when an item has several."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value) if value is not None else ""


def albums(offset: int = 0, limit: int = 100, query: str = "") -> list[Album]:
    """One page of lofi items, most downloaded first.

    ``query`` narrows the search inside the section; empty is the whole of it.
    Sorted by downloads rather than by date because an index of 1937 items
    opened at random is a worse first screen than its most listened records.
    """
    terms = QUERY if not query else f"{QUERY} AND ({query})"
    raw = _get(
        SEARCH_URL,
        {
            "q": terms,
            "fl[]": list(FIELDS),
            "sort[]": "downloads desc",
            # The Archive pages by 1-based page number, not by offset.
            "rows": limit,
            "page": offset // limit + 1,
            "output": "json",
        },
    )
    docs = raw.get("response", {}).get("docs", [])
    if not isinstance(docs, list):
        raise FreeMusicUnavailable(_("el Internet Archive no devolvió resultados"))
    found = []
    for doc in docs:
        identifier = _text(doc.get("identifier"))
        if not identifier:
            continue
        found.append(
            Album(
                identifier=identifier,
                title=_text(doc.get("title")) or identifier,
                creator=_text(doc.get("creator")),
                licence=licence_name(_text(doc.get("licenseurl"))),
                year=_int(doc.get("year")),
            )
        )
    return found


def total() -> int | None:
    """How many items the section holds, for the «más…» row. None when the
    Archive does not say, which `_paged` already knows how to live with."""
    try:
        raw = _get(
            SEARCH_URL,
            {"q": QUERY, "fl[]": ["identifier"], "rows": 0, "output": "json"},
        )
    except FreeMusicUnavailable:
        return None
    found = raw.get("response", {}).get("numFound")
    return _int(found) if found is not None else None


def _best(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The best encoding of each recording, keyed by what it is a copy of.

    The Archive keeps every derivative beside the original: one upload is a
    FLAC, a VBR MP3 and two more. They share an ``original`` field pointing at
    the file they came from, so grouping by it and keeping the best format
    lists each recording once instead of four times.
    """
    best: dict[str, dict[str, Any]] = {}
    for item in files:
        fmt = _text(item.get("format"))
        if fmt not in FORMATS:
            continue
        # A derivative names its source; an original names itself.
        source = _text(item.get("original")) or _text(item.get("name"))
        current = best.get(source)
        if current is None or FORMATS.index(fmt) < FORMATS.index(
            _text(current["format"])
        ):
            best[source] = item
    return best


def _title_of(item: dict[str, Any], album: Album) -> str:
    """The track's name: its tag, or its filename with the extension off.

    Half the lofi uploads carry no ID3 title at all, and a row reading
    «01-1505152-....mp3» is worse than no row, so the filename is cleaned up
    rather than shown raw.
    """
    tagged = _text(item.get("title"))
    if tagged:
        return tagged
    name = _text(item.get("name")).rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    return stem or album.title


def tracks(album: Album) -> list[Track]:
    """Every playable recording inside an item, in track order.

    One request. The Archive's metadata endpoint answers with the item's tags
    and the whole file listing at once, so a record costs the same as a row.
    """
    raw = _get(f"{METADATA_URL}/{album.identifier}")
    files = raw.get("files")
    if not isinstance(files, list):
        raise FreeMusicUnavailable(
            _("«{name}» no trae ficheros").format(name=album.title)
        )
    found = []
    for item in _best(files).values():
        name = _text(item.get("name"))
        if not name:
            continue
        fmt = _text(item.get("format"))
        found.append(
            Track(
                # Percent-encoded, because a name with a space or a «#» in it
                # is the rule and not the exception here. The slashes stay:
                # a file inside the item may sit in a folder of its own.
                url=f"{DOWNLOAD_URL}/{album.identifier}/{quote(name, safe='/')}",
                title=_title_of(item, album),
                artist=_text(item.get("artist")) or album.creator,
                album=_text(item.get("album")) or album.title,
                licence=album.licence,
                duration=_int(item.get("length")),
                year=album.year,
                track_num=_int(item.get("track")),
                codec=CODECS.get(fmt, fmt),
                art_url=album.art_url,
            )
        )
    if not found:
        raise FreeMusicUnavailable(
            _("«{name}» no trae audio que mpv pueda abrir").format(name=album.title)
        )
    # By track number when the tags have one, and by name for the uploads
    # that do not: the Archive lists files in upload order, which is nobody's.
    found.sort(key=lambda track: (track.track_num or 10_000, track.title))
    return found
