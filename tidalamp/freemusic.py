"""Copyright-free lofi from the Internet Archive, as a station.

The Archive's search and metadata endpoints need no account and no API key,
which is the same reason the rest of the project talks to TIDAL through the
device flow: registering an app is a dependency on somebody's goodwill, and
this one would buy nothing.

**It is a station and not a catalogue.** A browsable index of thousands is the
wrong shape for this: nobody opens a music player to audition strangers one
record at a time. `station()` answers with a day's worth of tracks, already
shuffled and ready to play, and the whole catalogue stays behind one row for
whoever wants it. The selection is drawn with the date as the seed, so it
holds still all day, is the same on every machine, and turns over at midnight
without a server anywhere.

**Three filters decide what may be in it**, and the order matters:

*Licence.* Only CC0, the public domain mark, CC BY and CC BY-SA. Every
Creative Commons licence allows listening, so this is not what makes playback
lawful; it is what makes the section's name true. «Lofi sin copyright»
promises music you can actually use, and BY-NC-ND does not deliver that.

*Genre.* Not `subject:lofi`, which is the trap: on the Archive that tag means
both lofi the genre and lo-fi the recording quality, and searching it returned
«PLAYMATE CALENDAR 1991», a David Koresh discography and «China 2006 Sound
Clips» among the beats. `GENRES` names the genre instead — chillhop, lofi hip
hop, jazzhop — which cut 1937 items to 133 and made almost all of them right.

*Junk.* What still slips through is a short, specific list: a commercial rip
with a CC licence typed over it, speech mixes, prayers, memes, and stock
«royalty free background music». `JUNK` names those by word, and it is a
blocklist of words rather than of items on purpose — the Archive grows, and a
list of identifiers would only ever describe the day it was written.

Measured against the live index on 2026-09-20: 133 items pass the licence and
genre filters, 12 are junk, 121 remain, by 66 artists.

Nothing here knows about ``Row``, tidalapi or Textual: it answers with the two
dataclasses below and `library` turns them into rows. That keeps the module
testable against a recorded JSON body and keeps TIDAL out of it.
"""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any
from urllib.parse import quote

import requests

from .config import STATE_DIR, write_atomically
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

# The genre, named as the genre. `subject:lofi` alone is the trap described
# at the top of the module: it catches every badly recorded thing on the
# Archive. These tags are what the people who make this music actually write.
GENRES = (
    "chillhop",
    "chill hop",
    "lofi hip hop",
    "lo-fi hip hop",
    "lofi hiphop",
    "jazzhop",
    "jazz hop",
    "lofi beats",
    "lo fi beats",
)
SUBJECT = (
    f"(subject:({' OR '.join(chr(34) + tag + chr(34) for tag in GENRES)})"
    " AND mediatype:audio)"
)

# The permissive half of Creative Commons, as substrings of `licenseurl`.
LICENCES = (
    "*publicdomain*",
    "*licenses\\/by\\/*",
    "*licenses\\/by-sa\\/*",
)
QUERY = f"{SUBJECT} AND ({' OR '.join(f'licenseurl:{lic}' for lic in LICENCES)})"

# What passes both filters and still is not music to put on. Matched against
# the title, the creator and the tags, lower-cased. Each one was seen in the
# live pool on 2026-09-20; the comment says which record it was there for.
JUNK = (
    "nujabes",  # a commercial rip with a CC licence typed over it
    "cd rip",  # and the others like it
    "jordan peterson",  # a speech mixed over beats
    "podcast",
    "audiobook",
    "sermon",
    "prayer",  # «Byzantine Daily Prayers Lofi»
    "catholic",
    "byzantine",
    "bardcore",  # medieval covers: a joke genre, not this one
    "screamo",  # mistagged: «Viva Belgrado - Ulises»
    "shitposting",
    "asmr",
    "royalty free music",  # stock beds, all of them interchangeable
    "no copyright music",
    "background music",
    "colonialism",
)

# Lofi is music to put behind whatever you are doing, and a voice is the one
# thing that will not stay behind it. These are the words that give a vocal
# away in metadata that never says «instrumental» outright.
#
# What is deliberately **not** here is `rap`: on this pool it is almost always
# `jazz rap` or `instrumental hip hop`, both instrumental genres, and
# excluding it took «Free (Instrumental)» and «Amorphée» out with it. The
# whole-word matching in `_says` is what lets the rest of these be safe —
# `mc` as a substring matches `ambient`, and `ft` matches almost anything.
#
# This is best effort and cannot be more: the Archive's metadata does not
# have a field for «has singing in it», so what is caught is what says so.
VOCALS = (
    "rapper",
    "vocal",
    "vocals",
    "vocalist",
    "female_vocals",
    "male_vocals",
    "singer",
    "singing",
    "sung",
    "acappella",
    "a cappella",
    "spoken",
    "spoken word",
    "freestyle",
    "choir",
    "feat",
    "ft",
    "featuring",
    "lyrics",
    "poetry",
    "mc",
)

# The fields the search has to bring back for a row to be drawable without a
# second request per item.
FIELDS = (
    "identifier",
    "title",
    "creator",
    "licenseurl",
    "year",
    "downloads",
    # Read only by the junk filter, which needs the tags as well as the
    # title: «Ulises» says nothing, and its `screamo` tag says everything.
    "subject",
)

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


# One session per thread. `requests.Session` is not safe to share between
# threads, and a new one per request throws away the connection with it, so
# every call paid for its own TLS handshake. Measured, that handshake is not
# what makes the Archive slow — the latency is the Archive's — but a
# connection per request is still a connection per request, and `tracks()`
# and `albums()` are called far more often than the station builds.
_LOCAL = threading.local()


def _session() -> requests.Session:
    session = getattr(_LOCAL, "session", None)
    if session is None:
        session = TimeoutSession()
        session.headers["User-Agent"] = USER_AGENT
        _LOCAL.session = session
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


def _says(text: str, words: tuple[str, ...]) -> bool:
    """Whether ``text`` contains any of ``words`` as whole words.

    Whole words and not substrings, which matters more than it looks: `rap`
    inside `therapy` and `mc` inside `ambient` would each have emptied half
    the pool, and `ft` matches nearly everything as a substring.
    """
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text) for word in words
    )


def _describes(doc: dict[str, Any]) -> str:
    """Title, creator and tags as one lower-cased line to match against.

    All three, because no one of them is enough: a screamo record mistagged
    `lofi hip hop` gives itself away only in its other tags, and a stock
    backing bed only in its title.
    """
    return " ".join(
        _text(doc.get(field)) for field in ("title", "creator", "subject")
    ).lower()


def _is_junk(doc: dict[str, Any]) -> bool:
    """Whether a record that passed both filters is still not music to put on."""
    said = _describes(doc)
    return _says(said, JUNK) or _says(said, VOCALS)


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
        if not identifier or _is_junk(doc):
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


# ------------------------------------------------------------------- station

# How many records the day is drawn from, the most any one of them may put
# in it, and the most tracks it holds. Twenty-four records for forty tracks
# looks like far too many until you look at the pool: most of it is singles,
# and twelve records at four each came back with eighteen tracks and 58
# minutes. They are fetched at once, so more records cost no more waiting.
#
# The cap is what makes the day listenable. Interleaving alone is fair only
# while every record still has cards: once the singles run out the long
# records take every remaining round, and the first day drawn that way was 24
# of its 35 tracks from two artists.
STATION_RECORDS = 24
STATION_PER_RECORD = 4
STATION_TRACKS = 40

# In parallel, and eight is deliberate. Measured against the live Archive on
# 2026-09-20: a metadata call takes 2.2 seconds at the median whatever it is
# asked for, so the day's two dozen cost 63 seconds one after another and
# some 19 through twelve workers. Firing all twenty-four at once did **not**
# help — three runs in a row came back at 20, 25 and 28 seconds, each slower
# than the last, which is what being throttled looks like. The latency is the
# Archive's and there is no beating it from here, so this asks politely and
# the day is built once, behind a spinner, and then read from a file.
STATION_WORKERS = 8

# How long a track may be to belong on a station. The floor drops interludes
# and jingles; the ceiling drops what this corner of the Archive is full of —
# «3 HOURS of lofi to study to», one file, uploaded as if it were a track. A
# day of thirty-eight came back at seven hours and fifty-one minutes before
# this, which is not a station, it is four mixes with a playlist over them.
# The catalogue still shows them: an hour-long mix is a real thing to put on,
# just not a thing to shuffle into a rotation.
STATION_SHORTEST = 45
STATION_LONGEST = 10 * 60
# The whole pool in one request. 121 items on 2026-09-20 and the Archive
# serves 200 happily, so this is one round trip with room to grow into.
POOL = 200

# Today's selection, so opening the row twice is a file read and not eleven
# requests. Keyed by the day it was drawn for: a stale one is simply redrawn.
STATION_FILE = STATE_DIR / "lofi-station.json"


def _seed(day: date) -> random.Random:
    """The day's shuffle.

    Seeded with the date and nothing else, so the selection holds still all
    day, is the same on every machine, and turns over at midnight without a
    server anywhere deciding anything.
    """
    return random.Random(day.isoformat())


def _read_station(day: date) -> list[Track] | None:
    """The day's selection off the disk, or None to draw it again.

    Anything wrong with the file — missing, truncated, from yesterday, written
    by a version that shaped a Track differently — means None. It is a cache
    of something reproducible, so there is nothing here worth recovering.
    """
    try:
        raw = json.loads(STATION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("day") != day.isoformat():
        return None
    try:
        return [Track(**item) for item in raw.get("tracks", [])]
    except TypeError:
        return None


def _write_station(day: date, songs: list[Track]) -> None:
    """Keep the day's selection. Failing to is not worth reporting: the next
    open draws the same tracks again, off the network instead of the disk."""
    try:
        STATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(
            STATION_FILE,
            json.dumps(
                {"day": day.isoformat(), "tracks": [asdict(song) for song in songs]},
                ensure_ascii=False,
            ),
        )
    except OSError as exc:
        log.debug("no se pudo guardar la selección del día: %s", exc)


def station(day: date | None = None) -> list[Track]:
    """The day's tracks, shuffled and ready to play.

    Eleven requests the first time each day and a file read after that. One
    record that will not open does not spoil the day: it is dropped and the
    other nine play, which is why the loop swallows `FreeMusicUnavailable`
    here and nowhere else in this module.
    """
    day = day or date.today()
    cached = _read_station(day)
    if cached is not None:
        return cached

    pool = albums(limit=POOL)
    if not pool:
        raise FreeMusicUnavailable(_("el Internet Archive no devolvió resultados"))
    rng = _seed(day)
    rng.shuffle(pool)
    chosen = pool[:STATION_RECORDS]

    # In parallel. Ten metadata requests one after another took 75 seconds
    # against the live Archive — a minute and a quarter of spinner before a
    # note is heard — and they wait on the network, not on us.
    with ThreadPoolExecutor(
        max_workers=min(STATION_WORKERS, len(chosen))
    ) as pool_of_threads:
        fetched = list(pool_of_threads.map(_tracks_or_none, chosen))

    # One record that will not open does not spoil the day: it is dropped and
    # the others play.
    records = [found for found in fetched if found]
    if not records:
        raise FreeMusicUnavailable(
            _("ninguno de los discos de hoy trae audio que mpv pueda abrir")
        )
    songs = _interleave(records, rng)[:STATION_TRACKS]
    if not songs:
        raise FreeMusicUnavailable(
            _("ninguno de los discos de hoy trae audio que mpv pueda abrir")
        )
    _write_station(day, songs)
    return songs


def _tracks_or_none(record: Album) -> list[Track]:
    try:
        return tracks(record)
    except FreeMusicUnavailable as exc:
        log.debug("«%s» fuera de la selección: %s", record.identifier, exc)
        return []


def _station_length(song: Track) -> bool:
    """Whether a track is the length of a track. See `STATION_LONGEST`.

    A track the Archive gave no duration for is kept: an unknown length is
    the metadata's fault, not the music's, and mpv will say how long it is
    the moment it opens it.
    """
    return not song.duration or STATION_SHORTEST <= song.duration <= STATION_LONGEST


def _instrumental(song: Track) -> bool:
    """Whether a track looks like it has nobody singing on it.

    Checked here as well as on the record, because a record is not its
    tracks: a mostly instrumental album carries the guest spot that is not,
    and «Kill Bill: The Rapper ft. Airospace» reached a day's rotation as a
    track on a record whose own creator field never said «rapper».

    Best effort, and only that. Nothing in the Archive's metadata means «no
    singing»; this drops what announces itself.
    """
    return not _says(f"{song.title} {song.artist}".lower(), VOCALS)


def _interleave(records: list[list[Track]], rng: random.Random) -> list[Track]:
    """One track from each record in turn, each record shuffled within itself.

    A flat shuffle of everything looks fair and is not: a record with twenty
    tracks drowns nine records with one each, and the first day drawn that way
    was two artists out of twelve for half of it. Round-robin plus the cap
    gives every record the same voice however much it brought, and the order
    of the records is shuffled too so it is not the same artist opening every
    day.

    What each record offers is filtered first, by length and by whether
    anybody is singing on it: both are properties of a track, not of the
    record it came on.
    """
    decks = []
    for record in records:
        deck = [song for song in record if _station_length(song) and _instrumental(song)]
        if not deck:
            continue
        rng.shuffle(deck)
        decks.append(deck[:STATION_PER_RECORD])
    if not decks:
        return []
    rng.shuffle(decks)
    out: list[Track] = []
    for round_ in range(max(len(deck) for deck in decks)):
        for deck in decks:
            if round_ < len(deck):
                out.append(deck[round_])
    return out
