"""«Lofi sin copyright»: a day's worth of instrumental lofi, as a station.

**It is a station and not a catalogue.** A browsable index of thousands is
the wrong shape for this: nobody opens a music player to audition strangers
one record at a time. `station()` answers with a day's tracks, already
shuffled and ready to play, drawn with the date as the seed — so it holds
still all day, is the same on every machine, and turns over at midnight
without a server anywhere deciding anything.

**Two sources, one shape.** `jamendo` when there is a client id, which is a
single request for a whole day and knows for itself which of its tracks are
instrumental; `archive` when there is not, or when Jamendo will not answer,
which costs a search plus a metadata call per record and has to have its tag
soup filtered by hand. Both hand back `music.Track`, so everything below this
line — and every line of the player above it — is the same either way.

**What this module decides** is what the sources cannot: how long a track may
be to belong on a station, how much of a day one record may take, and in what
order. See `STATION_LONGEST` and `_interleave`, which exist because the first
days drawn without them were four hour-long mixes and two artists.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import asdict
from datetime import date

from . import archive, jamendo
from .config import STATE_DIR, write_atomically
from .i18n import _
from .music import FreeMusicUnavailable, Track, licence_name
from .net import with_retries

log = logging.getLogger("tidalamp.freemusic")

__all__ = [
    "FreeMusicUnavailable",
    "Track",
    "licence_name",
    "source_name",
    "station",
]

# How many records the Archive's day is drawn from, the most any one source
# record may put in it, and the most tracks a day holds. Jamendo needs no
# record count: one request already brings two hundred tracks.
ARCHIVE_RECORDS = 24
STATION_PER_RECORD = 4
STATION_TRACKS = 40

# At once, but not all at once: the Archive is a public read-only endpoint
# doing us a favour. Measured on 2026-09-20, a metadata call takes 2.2
# seconds at the median whatever it is asked for, so a day costs 63 seconds
# in series and some 19 through eight workers. Firing all twenty-four at once
# did **not** help — three runs came back at 20, 25 and 28 seconds, each
# slower than the last, which is what being throttled looks like.
ARCHIVE_WORKERS = 8

# How long a track may be to belong on a station. The floor drops interludes
# and jingles; the ceiling drops what these catalogues are full of — «3 HOURS
# of lofi to study to», one file, uploaded as if it were a track. A day of
# thirty-eight came back at seven hours and fifty-one minutes before this,
# which is not a station, it is four mixes with a playlist over them.
STATION_SHORTEST = 45
STATION_LONGEST = 10 * 60

# Today's selection, so opening the row twice is a file read and not a day's
# worth of requests. Keyed by the day it was drawn for.
STATION_FILE = STATE_DIR / "lofi-station.json"
# And by the shape of a `Track`, which is the part that is easy to get wrong.
# A field added with a default does not make an old cache fail to load — it
# makes it load *quietly wrong*, every track missing the new value until the
# day turns over. Adding `source_url` did exactly that: the credits came up
# blank and nothing anywhere said why. Bump this whenever `Track` changes.
STATION_VERSION = 3


def source_name() -> str:
    """Which source a day would be drawn from, for the row's own line."""
    return jamendo.WHO if jamendo.configured() else archive.WHO


def _seed(day: date) -> random.Random:
    """The day's shuffle.

    Seeded with the date and nothing else, so the selection holds still all
    day, is the same on every machine, and turns over at midnight without a
    server anywhere deciding anything.
    """
    return random.Random(day.isoformat())


def _read_station(day: date) -> list[Track] | None:
    """The day's selection off the disk, or None to draw it again.

    Anything wrong with the file — missing, truncated, from yesterday, or
    written when a `Track` held different fields — means None. It is a cache
    of something reproducible, so there is nothing here worth recovering.
    """
    try:
        raw = json.loads(STATION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("day") != day.isoformat():
        return None
    if raw.get("version") != STATION_VERSION:
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
                {
                    "day": day.isoformat(),
                    "version": STATION_VERSION,
                    "tracks": [asdict(song) for song in songs],
                },
                ensure_ascii=False,
            ),
        )
    except OSError as exc:
        log.debug("no se pudo guardar la selección del día: %s", exc)


def _belongs(song: Track) -> bool:
    """Whether a track is the length of a track. See `STATION_LONGEST`.

    A track the source gave no duration for is kept: an unknown length is
    the metadata's fault, not the music's, and mpv will say how long it is
    the moment it opens it.
    """
    return not song.duration or STATION_SHORTEST <= song.duration <= STATION_LONGEST


def _interleave(records: list[list[Track]], rng: random.Random) -> list[Track]:
    """One track from each record in turn, each record shuffled within itself.

    A flat shuffle of everything looks fair and is not: a record with twenty
    tracks drowns nine records with one each, and the first day drawn that way
    was two artists out of twelve for half of it. Round-robin plus the cap
    gives every record the same voice however much it brought, and the order
    of the records is shuffled too so it is not the same artist opening every
    day.

    What each record offers is filtered first, by length: that is a property
    of a track, not of the record it came on.
    """
    decks = []
    for record in records:
        deck = [song for song in record if _belongs(song)]
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


def _from_jamendo(rng: random.Random) -> list[Track]:
    """A day out of Jamendo: one request, then grouped by artist.

    Jamendo orders by popularity and we want a day, not a chart, so the two
    hundred it sends are shuffled and then dealt out one artist at a time —
    the same round-robin the Archive's records get, with the artist standing
    in for the record.
    """
    songs = with_retries(jamendo.tracks)
    by_artist: dict[str, list[Track]] = {}
    for song in songs:
        by_artist.setdefault(song.artist.lower(), []).append(song)
    return _interleave(list(by_artist.values()), rng)


def _from_archive(rng: random.Random) -> list[Track]:
    """A day out of the Internet Archive: a search, then a record at a time.

    In parallel, because these wait on the network and not on us, and one
    record that will not open does not spoil the day — it is dropped and the
    others play.
    """
    from concurrent.futures import ThreadPoolExecutor

    pool = archive.albums(limit=archive.POOL)
    if not pool:
        raise FreeMusicUnavailable(_("no se encontró música con licencia libre"))
    rng.shuffle(pool)
    chosen = pool[:ARCHIVE_RECORDS]

    def opened(record: archive.Album) -> list[Track]:
        try:
            return archive.tracks(record)
        except FreeMusicUnavailable as exc:
            log.debug("«%s» fuera de la selección: %s", record.identifier, exc)
            return []

    with ThreadPoolExecutor(max_workers=min(ARCHIVE_WORKERS, len(chosen))) as threads:
        fetched = [found for found in threads.map(opened, chosen) if found]
    return _interleave(fetched, rng)


def station(day: date | None = None) -> list[Track]:
    """The day's tracks, shuffled and ready to play.

    Jamendo first and the Archive when it cannot be reached, so a day is
    never lost to one source being down: they answer with the same `Track`,
    and the only thing that changes is how long the first open of the day
    takes and how good the filtering was.
    """
    day = day or date.today()
    cached = _read_station(day)
    if cached is not None:
        return cached

    rng = _seed(day)
    songs: list[Track] = []
    if jamendo.configured():
        try:
            songs = _from_jamendo(rng)
        except Exception as exc:
            # Not fatal and not silent: the Archive is right there, and a day
            # that quietly changed source would be a day nobody could explain.
            log.warning("Jamendo no sirvió la selección (%s); se usa el Archive", exc)
    if not songs:
        songs = _from_archive(_seed(day))

    songs = songs[:STATION_TRACKS]
    if not songs:
        raise FreeMusicUnavailable(
            _("ninguno de los discos de hoy trae audio que mpv pueda abrir")
        )
    _write_station(day, songs)
    return songs
