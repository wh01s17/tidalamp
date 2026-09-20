"""The Internet Archive: where «Lofi sin copyright» goes without a client id.

The fallback, not the first choice. Its search and metadata endpoints need no
account and no API key, which is what makes it the right thing to fall back
*to*; what it costs is everything `jamendo` gives cheaply — a search plus a
metadata call per record, some twenty seconds for a day, no field that says
whether anybody is singing, and a tag soup that has to be filtered by hand.

**Three filters decide what may be in it**, and the order matters:

*Licence.* Only the permissive half, as everywhere in this section: see
`music.PERMISSIVE`.

*Genre.* Not `subject:lofi`, which is the trap: on the Archive that tag means
both lofi the genre and lo-fi the recording quality, and searching it returned
«PLAYMATE CALENDAR 1991», a David Koresh discography and «China 2006 Sound
Clips» among the beats. `GENRES` names the genre instead — chillhop, lofi hip
hop, jazzhop — which cut 1937 items to 133 and made almost all of them right.

*Junk and voices.* What still slips through is a short, specific list: a
commercial rip with a CC licence typed over it, speech mixes, prayers, memes,
stock «royalty free background music», and anything that announces singing.
`JUNK` and `music.VOCALS` name those by word, and they are blocklists of
words rather than of items on purpose — the Archive grows, and a list of
identifiers would only ever describe the day it was written.

Measured against the live index on 2026-09-20: 133 items pass the licence and
genre filters, 121 survive the junk list, 115 the voices, by 62 artists.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from .i18n import _
from .music import (
    FreeMusicUnavailable,
    Track,
    as_int,
    as_text,
    get_json,
    licence_name,
)

log = logging.getLogger("tidalamp.archive")

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata"
DOWNLOAD_URL = "https://archive.org/download"
# The page a credit points at. The audio URL is a file; attribution asks
# for where the work lives, which is the item's own page.
DETAILS_URL = "https://archive.org/details"
# The Archive renders a square thumbnail for any item at this path, whatever
# the item actually holds, so a record with no cover still answers 200.
IMAGE_URL = "https://archive.org/services/img"

# How this source names itself when something goes wrong.
WHO = "el Internet Archive"

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
# The whole pool in one request. 115 items pass every filter on
# 2026-09-20 and the Archive serves 200 happily, so this is one round
# trip with room to grow into.
POOL = 200

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

    @property
    def source_url(self) -> str:
        """Where the work lives, for the credit CC BY and CC BY-SA ask for."""
        return f"{DETAILS_URL}/{self.identifier}"


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
        as_text(doc.get(field)) for field in ("title", "creator", "subject")
    ).lower()


def _instrumental(song: Track) -> bool:
    """Whether a track looks like it has nobody singing on it.

    Checked on the track as well as on the record, because a record is not
    its tracks: a mostly instrumental album carries the guest spot that is
    not, and «Kill Bill: The Rapper ft. Airospace» reached a day's rotation
    as a track on a record whose own creator field never said «rapper».

    Best effort, and only that. Nothing in the Archive's metadata means «no
    singing»; this drops what announces itself. `jamendo` needs none of it:
    there the artist ticked a box, and guessing over that would throw away
    instrumentals whose titles happen to say «feat.».
    """
    return not _says(f"{song.title} {song.artist}".lower(), VOCALS)


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
    raw = get_json(
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
        who=WHO,
    )
    docs = raw.get("response", {}).get("docs", [])
    if not isinstance(docs, list):
        raise FreeMusicUnavailable(_("el Internet Archive no devolvió resultados"))
    found = []
    for doc in docs:
        identifier = as_text(doc.get("identifier"))
        if not identifier or _is_junk(doc):
            continue
        found.append(
            Album(
                identifier=identifier,
                title=as_text(doc.get("title")) or identifier,
                creator=as_text(doc.get("creator")),
                licence=licence_name(as_text(doc.get("licenseurl"))),
                year=as_int(doc.get("year")),
            )
        )
    return found


def total() -> int | None:
    """How many items the section holds, for the «más…» row. None when the
    Archive does not say, which `_paged` already knows how to live with."""
    try:
        raw = get_json(
            SEARCH_URL,
            {"q": QUERY, "fl[]": ["identifier"], "rows": 0, "output": "json"},
            who=WHO,
        )
    except FreeMusicUnavailable:
        return None
    found = raw.get("response", {}).get("numFound")
    return as_int(found) if found is not None else None


def _best(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The best encoding of each recording, keyed by what it is a copy of.

    The Archive keeps every derivative beside the original: one upload is a
    FLAC, a VBR MP3 and two more. They share an ``original`` field pointing at
    the file they came from, so grouping by it and keeping the best format
    lists each recording once instead of four times.
    """
    best: dict[str, dict[str, Any]] = {}
    for item in files:
        fmt = as_text(item.get("format"))
        if fmt not in FORMATS:
            continue
        # A derivative names its source; an original names itself.
        source = as_text(item.get("original")) or as_text(item.get("name"))
        current = best.get(source)
        if current is None or FORMATS.index(fmt) < FORMATS.index(
            as_text(current["format"])
        ):
            best[source] = item
    return best


def _title_of(item: dict[str, Any], album: Album) -> str:
    """The track's name: its tag, or its filename with the extension off.

    Half the lofi uploads carry no ID3 title at all, and a row reading
    «01-1505152-....mp3» is worse than no row, so the filename is cleaned up
    rather than shown raw.
    """
    tagged = as_text(item.get("title"))
    if tagged:
        return tagged
    name = as_text(item.get("name")).rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    return stem or album.title


def tracks(album: Album) -> list[Track]:
    """Every playable recording inside an item, in track order.

    One request. The Archive's metadata endpoint answers with the item's tags
    and the whole file listing at once, so a record costs the same as a row.
    """
    raw = get_json(f"{METADATA_URL}/{album.identifier}", who=WHO)
    files = raw.get("files")
    if not isinstance(files, list):
        raise FreeMusicUnavailable(
            _("«{name}» no trae ficheros").format(name=album.title)
        )
    found = []
    for item in _best(files).values():
        name = as_text(item.get("name"))
        if not name:
            continue
        fmt = as_text(item.get("format"))
        found.append(
            Track(
                # Percent-encoded, because a name with a space or a «#» in it
                # is the rule and not the exception here. The slashes stay:
                # a file inside the item may sit in a folder of its own.
                url=f"{DOWNLOAD_URL}/{album.identifier}/{quote(name, safe='/')}",
                title=_title_of(item, album),
                artist=as_text(item.get("artist")) or album.creator,
                album=as_text(item.get("album")) or album.title,
                licence=album.licence,
                duration=as_int(item.get("length")),
                year=album.year,
                track_num=as_int(item.get("track")),
                codec=CODECS.get(fmt, fmt),
                art_url=album.art_url,
                source_url=album.source_url,
            )
        )
    if not found:
        raise FreeMusicUnavailable(
            _("«{name}» no trae audio que mpv pueda abrir").format(name=album.title)
        )
    # Whoever is singing goes here and not in the station: this is the only
    # source that has to guess at it.
    found = [song for song in found if _instrumental(song)]
    if not found:
        raise FreeMusicUnavailable(_("«{name}» es todo con voz").format(name=album.title))
    # By track number when the tags have one, and by name for the uploads
    # that do not: the Archive lists files in upload order, which is nobody's.
    found.sort(key=lambda track: (track.track_num or 10_000, track.title))
    return found
