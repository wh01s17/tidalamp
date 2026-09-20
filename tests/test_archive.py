"""The Internet Archive client, the source that needs no client id.

Never over the network: every test hands `get_json` a recorded body, which is
the shape the real endpoints answered with on 2026-09-20. What is checked is
the parsing, because that is where the Archive's loose typing bites — a
`creator` that is a list, a `year` that is missing, a `length` that is a
string with a decimal point, and a file listing that holds four derivatives of
every recording — and the filters, because the Archive's `lofi` tag means both
the genre and «badly recorded».
"""

from __future__ import annotations

import pytest
import requests

from tidalamp import archive, music
from tidalamp.archive import Album
from tidalamp.music import FreeMusicUnavailable, Track

# One page of the search, trimmed to the fields the code reads. `creator` is
# absent on the first doc and a list on the third: both happen in the live
# index, and both used to crash the row builder.
SEARCH = {
    "response": {
        "numFound": 1937,
        "docs": [
            {
                "identifier": "lofi-lion-tame-the-beast",
                "title": "Tame The Beast",
                "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                "downloads": 70268,
            },
            {
                "identifier": "chill-lofi-mix-2",
                "title": "Chill Lofi Mix 2",
                "creator": "Leonardo Gonzalez",
                "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
                "year": "2023",
            },
            {
                "identifier": "gt450FieldExperience",
                "title": "Field Experience",
                "creator": ["Various Artists", "Flavien Gilli"],
                "licenseurl": "http://creativecommons.org/publicdomain/zero/1.0/",
                "year": 2012,
            },
        ],
    }
}

# One item's files: a WAVE original with a FLAC, an Ogg and two MP3s derived
# from it, plus the junk the Archive keeps beside every upload.
FILES = {
    "files": [
        {"name": "01-track.wav", "format": "WAVE", "length": "233.89"},
        {
            "name": "01-track.flac",
            "format": "Flac",
            "original": "01-track.wav",
            "length": "233.89",
            "track": "1",
            "title": "Forest Square",
            "artist": "Flavien Gilli",
        },
        {
            "name": "01-track.ogg",
            "format": "Ogg Vorbis",
            "original": "01-track.wav",
            "length": "233.89",
        },
        {
            "name": "01-track.mp3",
            "format": "VBR MP3",
            "original": "01-track.wav",
            "length": "233.89",
        },
        {
            "name": "02 second track.mp3",
            "format": "VBR MP3",
            "length": "162.17",
            "track": "2",
        },
        {"name": "cover.jpg", "format": "JPEG"},
        {"name": "gt450_meta.xml", "format": "Metadata"},
    ]
}

ITEM = Album(
    identifier="gt450FieldExperience",
    title="Field Experience",
    creator="Various Artists",
    licence="CC0",
    year=2012,
)


@pytest.fixture
def answers(monkeypatch):
    """Queue up what `_get` hands back, and record what it was asked for."""
    calls: list[tuple[str, dict | None]] = []
    bodies: list[object] = []

    def fake_get(url, params=None, *, who=""):
        calls.append((url, params))
        return bodies.pop(0)

    monkeypatch.setattr(archive, "get_json", fake_get)
    return calls, bodies


# ------------------------------------------------------------------ licences


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0"),
        ("https://creativecommons.org/publicdomain/mark/1.0/", "dominio público"),
        ("https://creativecommons.org/licenses/by/4.0/", "CC BY"),
        ("http://creativecommons.org/licenses/by-sa/3.0/", "CC BY-SA"),
    ],
)
def test_licence_names_drop_the_version(url, name):
    assert music.licence_name(url) == name


def test_an_unknown_licence_shows_its_url_rather_than_a_guess():
    unknown = "http://example.invalid/x"
    assert music.licence_name(unknown) == unknown


def test_the_query_only_lets_the_permissive_licences_in():
    """The section's name promises music you can use, not only listen to.

    BY-NC-ND is the Archive's most common lofi licence and the one that would
    break that promise, so the query must not be able to match it.
    """
    assert "publicdomain" in archive.QUERY
    assert "licenses\\/by\\/" in archive.QUERY
    assert "licenses\\/by-sa\\/" in archive.QUERY
    assert "nc" not in archive.QUERY.replace("creativecommons", "")
    assert "by-nd" not in archive.QUERY


# -------------------------------------------------------------------- search


def test_albums_parses_a_page_and_survives_the_loose_typing(answers):
    _calls, bodies = answers
    bodies.append(SEARCH)

    found = archive.albums()

    assert [album.identifier for album in found] == [
        "lofi-lion-tame-the-beast",
        "chill-lofi-mix-2",
        "gt450FieldExperience",
    ]
    # No creator at all, one string, and a list joined rather than repr'd.
    assert [album.creator for album in found] == [
        "",
        "Leonardo Gonzalez",
        "Various Artists, Flavien Gilli",
    ]
    assert [album.year for album in found] == [0, 2023, 2012]
    assert [album.licence for album in found] == ["CC BY", "dominio público", "CC0"]


def test_albums_asks_for_the_page_the_offset_lands_in(answers):
    """`_paged` counts in offsets and the Archive counts in pages."""
    calls, bodies = answers
    bodies.append(SEARCH)

    archive.albums(offset=200, limit=100)

    _url, params = calls[0]
    assert params["page"] == 3
    assert params["rows"] == 100
    assert params["sort[]"] == "downloads desc"


def test_a_doc_with_no_identifier_is_dropped_rather_than_drawn(answers):
    _calls, bodies = answers
    first = SEARCH["response"]["docs"][0]
    bodies.append({"response": {"docs": [{"title": "orphan"}, first]}})

    assert [album.identifier for album in archive.albums()] == [
        "lofi-lion-tame-the-beast"
    ]


def test_an_item_with_no_title_falls_back_to_its_identifier(answers):
    _calls, bodies = answers
    bodies.append({"response": {"docs": [{"identifier": "bare"}]}})

    assert archive.albums()[0].title == "bare"


def test_a_body_that_is_not_a_result_set_is_reported(answers):
    _calls, bodies = answers
    bodies.append({"response": {"docs": "not a list"}})

    with pytest.raises(FreeMusicUnavailable):
        archive.albums()


def test_total_answers_none_rather_than_raising(answers, monkeypatch):
    """The count only decides whether to offer a «más…» row. `_paged`
    already knows how to page without one, so a failure here is not a
    failure of the level."""

    def boom(url, params=None, *, who=""):
        raise FreeMusicUnavailable("down")

    monkeypatch.setattr(archive, "get_json", boom)
    assert archive.total() is None


def test_total_reads_the_count_off_the_search(answers):
    _calls, bodies = answers
    bodies.append(SEARCH)
    assert archive.total() == 1937


# -------------------------------------------------------------------- tracks


def test_tracks_keeps_one_recording_per_upload_and_the_best_encoding(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    found = archive.tracks(ITEM)

    # Four files derived from one WAVE collapse to one recording, and the
    # FLAC wins over the Ogg and the MP3.
    assert len(found) == 2
    assert found[0].codec == "FLAC"
    assert found[0].url.endswith("/gt450FieldExperience/01-track.flac")
    assert found[1].codec == "MP3"


def test_tracks_percent_encodes_the_filename(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    second = archive.tracks(ITEM)[1]
    assert second.url.endswith("/gt450FieldExperience/02%20second%20track.mp3")


def test_a_track_with_no_tags_borrows_the_item_and_its_filename(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    tagged, untagged = archive.tracks(ITEM)
    assert (tagged.title, tagged.artist) == ("Forest Square", "Flavien Gilli")
    # No title tag: the filename with the extension off, and the item's
    # creator, which beats a row reading «02 second track.mp3» by itself.
    assert (untagged.title, untagged.artist) == ("02 second track", "Various Artists")
    assert untagged.album == "Field Experience"


def test_tracks_carry_the_item_licence_year_and_cover(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    for track in archive.tracks(ITEM):
        assert track.licence == "CC0"
        assert track.year == 2012
        assert track.art_url.endswith("/services/img/gt450FieldExperience")


def test_a_length_with_a_decimal_point_becomes_whole_seconds(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    assert archive.tracks(ITEM)[0].duration == 233


def test_an_item_with_no_audio_says_so_rather_than_opening_empty(answers):
    _calls, bodies = answers
    bodies.append({"files": [{"name": "cover.jpg", "format": "JPEG"}]})

    with pytest.raises(FreeMusicUnavailable):
        archive.tracks(ITEM)


def test_an_item_with_no_file_listing_says_so(answers):
    _calls, bodies = answers
    bodies.append({"metadata": {}})

    with pytest.raises(FreeMusicUnavailable):
        archive.tracks(ITEM)


# ------------------------------------------------------------- the junk filter


@pytest.mark.parametrize(
    ("doc", "why"),
    [
        ({"title": "Nujabes - Luv (sic) Hexalogy CD RIP"}, "un rip comercial"),
        ({"title": "JBPWAVE A Jordan Peterson Lofi Hip Hop Mix"}, "voz sobre beats"),
        ({"title": "Byzantine Daily Prayers Lofi"}, "rezos"),
        ({"title": "Ulises", "subject": ["screamo", "lofi hip hop"]}, "mal etiquetado"),
        ({"title": "Classic Background Music", "subject": "royalty free music"}, "stock"),
        ({"title": "X Wife - S/T EP", "subject": ["lofi hiphop", "shitposting"]}, "meme"),
    ],
)
def test_what_passes_both_filters_and_still_is_not_music_to_put_on(doc, why):
    assert archive._is_junk(doc), why


@pytest.mark.parametrize(
    "doc",
    [
        {"title": "Popoi - Georgetown Cafe", "subject": ["chillhop", "lofi hiphop"]},
        {"title": "Elephant Funeral - The Mountains", "subject": "chillhop,lofi,sad"},
        {"title": "unVoid - Mintaka", "creator": "unVoid", "subject": ["chillhop"]},
    ],
)
def test_the_junk_filter_keeps_the_music(doc):
    assert not archive._is_junk(doc)


def test_the_junk_filter_reads_the_tags_and_not_only_the_title():
    """«Ulises» says nothing; its `screamo` tag says everything."""
    assert not archive._is_junk({"title": "Ulises"})
    assert archive._is_junk({"title": "Ulises", "subject": ["screamo"]})


def test_junk_is_dropped_from_a_page_rather_than_shown(answers):
    _calls, bodies = answers
    bodies.append(
        {
            "response": {
                "docs": [
                    {"identifier": "rip", "title": "Nujabes - Luv (sic) CD RIP"},
                    {"identifier": "good", "title": "Popoi - Smoothie"},
                ]
            }
        }
    )
    assert [album.identifier for album in archive.albums()] == ["good"]


def test_the_query_asks_for_the_genre_and_not_for_the_word_lofi():
    """The trap the section was built wrong on first: on the Archive
    `subject:lofi` means both lofi the genre and lo-fi the recording quality,
    and it returned a Playmate calendar and a David Koresh discography among
    the beats."""
    assert '"chillhop"' in archive.QUERY
    assert '"lofi hip hop"' in archive.QUERY
    assert '"lofi"' not in archive.QUERY
    assert '"lo-fi"' not in archive.QUERY


# -------------------------------------------------------- nobody is singing


@pytest.mark.parametrize(
    ("doc", "why"),
    [
        ({"creator": "Kill Bill: The Rapper", "title": "Snow Globe"}, "un rapero"),
        ({"title": "singing in the rain but its lofi"}, "canta"),
        ({"title": "Edgar Cards - In Between", "subject": "acappella"}, "a capella"),
        ({"title": "MAGMA - Freestyle luna", "subject": "poetry"}, "freestyle"),
        ({"title": "x", "subject": ["lofi hiphop", "female_vocals"]}, "voz etiquetada"),
    ],
)
def test_a_record_that_announces_a_voice_stays_out(doc, why):
    assert archive._is_junk(doc), why


@pytest.mark.parametrize(
    "doc",
    [
        # `rap` is deliberately not a vocal marker: on this pool it is almost
        # always `jazz rap` or `instrumental hip hop`, both instrumental.
        {"title": "Free (Instrumental)", "subject": "rap beats, hip hop beats"},
        {"title": "RÏga - Amorphée", "subject": ["instrumental hip hop", "jazz rap"]},
        # And the whole-word matching is what makes the rest safe: `mc` is
        # inside `ambient`, `ft` is inside almost everything.
        {"title": "Itsovah - Balzac by night", "subject": ["ambient", "chillhop"]},
        {"title": "Sevennotes - Soft Drift", "subject": ["chillhop", "soft"]},
    ],
)
def test_the_voice_filter_does_not_eat_the_instrumentals(doc):
    assert not archive._is_junk(doc)


def test_a_guest_spot_is_caught_on_the_track_and_not_only_on_the_record():
    """A record is not its tracks. «Kill Bill: The Rapper ft. Airospace»
    reached a day's rotation as a track on a record whose own creator field
    never said «rapper»."""
    guest = Track(
        url="https://archive.org/download/x/a.mp3",
        title="SPACEMAN",
        artist="Somebody ft. Airospace",
        album="x",
        licence="CC BY",
        duration=180,
    )
    plain = Track(
        url="https://archive.org/download/x/b.mp3",
        title="Georgetown Cafe",
        artist="Popoi",
        album="x",
        licence="CC BY",
        duration=180,
    )
    assert not archive._instrumental(guest)
    assert archive._instrumental(plain)


def test_whole_words_only():
    """`rap` inside `therapy` and `mc` inside `ambient` would each have
    emptied half the pool."""
    assert not archive._says("music therapy ambient soft", archive.VOCALS)
    assert archive._says("ambient, female_vocals", archive.VOCALS)


# ------------------------------------------------------------------ transport


def test_a_network_failure_becomes_a_freemusic_error(monkeypatch):
    """Not a bare `requests` exception: the browser prints what it catches,
    and «ConnectionError()» tells a user nothing."""

    class Boom:
        headers: dict = {}

        def get(self, url, params=None):
            raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(music, "session", lambda: Boom())

    with pytest.raises(FreeMusicUnavailable, match="Internet Archive"):
        archive.albums()


def test_a_body_that_is_not_json_becomes_a_freemusic_error(monkeypatch):
    class Page:
        headers: dict = {}

        def get(self, url, params=None):
            return self

        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("Expecting value")

    monkeypatch.setattr(music, "session", lambda: Page())

    with pytest.raises(FreeMusicUnavailable, match="JSON"):
        archive.albums()


def test_a_sung_track_never_leaves_the_record(answers):
    """Lofi is music to put behind whatever you are doing, and a voice is the
    one thing that will not stay behind it. Caught in `tracks()` and not in
    the station, because this is the only source that has to guess at it."""
    _calls, bodies = answers
    bodies.append(
        {
            "files": [
                {"name": "01 quiet.mp3", "format": "VBR MP3", "length": "180"},
                {
                    "name": "02 interlude.mp3",
                    "format": "VBR MP3",
                    "length": "180",
                    "title": "Interlude (feat. Somebody)",
                },
                {
                    "name": "03 talking.mp3",
                    "format": "VBR MP3",
                    "length": "180",
                    "artist": "A Rapper",
                },
            ]
        }
    )
    found = archive.tracks(ITEM)
    assert [song.title for song in found] == ["01 quiet"]


def test_a_record_that_is_all_voice_says_so(answers):
    _calls, bodies = answers
    bodies.append(
        {
            "files": [
                {
                    "name": "a.mp3",
                    "format": "VBR MP3",
                    "length": "180",
                    "artist": "A Rapper",
                }
            ]
        }
    )
    with pytest.raises(FreeMusicUnavailable, match="voz"):
        archive.tracks(ITEM)
