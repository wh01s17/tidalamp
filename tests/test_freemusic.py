"""The Internet Archive client behind «Lofi sin copyright».

Never over the network: every test hands `_get` a recorded body, which is the
shape the real endpoints answered with on 2026-09-20. What is checked is the
parsing, because that is where the Archive's loose typing bites — a `creator`
that is a list, a `year` that is missing, a `length` that is a string with a
decimal point, and a file listing that holds four derivatives of every
recording.
"""

from __future__ import annotations

import pytest
import requests

from tidalamp import freemusic
from tidalamp.freemusic import Album, FreeMusicUnavailable, Track

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

    def fake_get(url, params=None):
        calls.append((url, params))
        return bodies.pop(0)

    monkeypatch.setattr(freemusic, "_get", fake_get)
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
    assert freemusic.licence_name(url) == name


def test_an_unknown_licence_shows_its_url_rather_than_a_guess():
    unknown = "http://example.invalid/x"
    assert freemusic.licence_name(unknown) == unknown


def test_the_query_only_lets_the_permissive_licences_in():
    """The section's name promises music you can use, not only listen to.

    BY-NC-ND is the Archive's most common lofi licence and the one that would
    break that promise, so the query must not be able to match it.
    """
    assert "publicdomain" in freemusic.QUERY
    assert "licenses\\/by\\/" in freemusic.QUERY
    assert "licenses\\/by-sa\\/" in freemusic.QUERY
    assert "nc" not in freemusic.QUERY.replace("creativecommons", "")
    assert "by-nd" not in freemusic.QUERY


# -------------------------------------------------------------------- search


def test_albums_parses_a_page_and_survives_the_loose_typing(answers):
    _calls, bodies = answers
    bodies.append(SEARCH)

    found = freemusic.albums()

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

    freemusic.albums(offset=200, limit=100)

    _url, params = calls[0]
    assert params["page"] == 3
    assert params["rows"] == 100
    assert params["sort[]"] == "downloads desc"


def test_a_doc_with_no_identifier_is_dropped_rather_than_drawn(answers):
    _calls, bodies = answers
    first = SEARCH["response"]["docs"][0]
    bodies.append({"response": {"docs": [{"title": "orphan"}, first]}})

    assert [album.identifier for album in freemusic.albums()] == [
        "lofi-lion-tame-the-beast"
    ]


def test_an_item_with_no_title_falls_back_to_its_identifier(answers):
    _calls, bodies = answers
    bodies.append({"response": {"docs": [{"identifier": "bare"}]}})

    assert freemusic.albums()[0].title == "bare"


def test_a_body_that_is_not_a_result_set_is_reported(answers):
    _calls, bodies = answers
    bodies.append({"response": {"docs": "not a list"}})

    with pytest.raises(FreeMusicUnavailable):
        freemusic.albums()


def test_total_answers_none_rather_than_raising(answers, monkeypatch):
    """The count only decides whether to offer a «más…» row. `_paged`
    already knows how to page without one, so a failure here is not a
    failure of the level."""

    def boom(url, params=None):
        raise FreeMusicUnavailable("down")

    monkeypatch.setattr(freemusic, "_get", boom)
    assert freemusic.total() is None


def test_total_reads_the_count_off_the_search(answers):
    _calls, bodies = answers
    bodies.append(SEARCH)
    assert freemusic.total() == 1937


# -------------------------------------------------------------------- tracks


def test_tracks_keeps_one_recording_per_upload_and_the_best_encoding(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    found = freemusic.tracks(ITEM)

    # Four files derived from one WAVE collapse to one recording, and the
    # FLAC wins over the Ogg and the MP3.
    assert len(found) == 2
    assert found[0].codec == "FLAC"
    assert found[0].url.endswith("/gt450FieldExperience/01-track.flac")
    assert found[1].codec == "MP3"


def test_tracks_percent_encodes_the_filename(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    second = freemusic.tracks(ITEM)[1]
    assert second.url.endswith("/gt450FieldExperience/02%20second%20track.mp3")


def test_a_track_with_no_tags_borrows_the_item_and_its_filename(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    tagged, untagged = freemusic.tracks(ITEM)
    assert (tagged.title, tagged.artist) == ("Forest Square", "Flavien Gilli")
    # No title tag: the filename with the extension off, and the item's
    # creator, which beats a row reading «02 second track.mp3» by itself.
    assert (untagged.title, untagged.artist) == ("02 second track", "Various Artists")
    assert untagged.album == "Field Experience"


def test_tracks_carry_the_item_licence_year_and_cover(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    for track in freemusic.tracks(ITEM):
        assert track.licence == "CC0"
        assert track.year == 2012
        assert track.art_url.endswith("/services/img/gt450FieldExperience")


def test_a_length_with_a_decimal_point_becomes_whole_seconds(answers):
    _calls, bodies = answers
    bodies.append(FILES)

    assert freemusic.tracks(ITEM)[0].duration == 233


def test_an_item_with_no_audio_says_so_rather_than_opening_empty(answers):
    _calls, bodies = answers
    bodies.append({"files": [{"name": "cover.jpg", "format": "JPEG"}]})

    with pytest.raises(FreeMusicUnavailable):
        freemusic.tracks(ITEM)


def test_an_item_with_no_file_listing_says_so(answers):
    _calls, bodies = answers
    bodies.append({"metadata": {}})

    with pytest.raises(FreeMusicUnavailable):
        freemusic.tracks(ITEM)


# ------------------------------------------------------------------------ ids


def test_a_track_id_is_negative_so_it_can_never_be_a_tidal_one():
    """The queue keys deduplication, the lyrics cache and restored identity
    off `Entry.id`. TIDAL's are positive; these must never collide."""
    track = Track(
        url="https://archive.org/download/x/a.mp3",
        title="",
        artist="",
        album="",
        licence="",
    )
    assert track.id < 0


def test_the_same_url_is_always_the_same_id():
    def make(url):
        return Track(url=url, title="", artist="", album="", licence="").id

    assert make("https://archive.org/download/x/a.mp3") == make(
        "https://archive.org/download/x/a.mp3"
    )
    assert make("https://archive.org/download/x/a.mp3") != make(
        "https://archive.org/download/x/b.mp3"
    )


# ------------------------------------------------------------------ transport


def test_a_network_failure_becomes_a_freemusic_error(monkeypatch):
    """Not a bare `requests` exception: the browser prints what it catches,
    and «ConnectionError()» tells a user nothing."""

    class Boom:
        headers: dict = {}

        def get(self, url, params=None):
            raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(freemusic, "_session", lambda: Boom())

    with pytest.raises(FreeMusicUnavailable, match="Internet Archive"):
        freemusic.albums()


def test_a_body_that_is_not_json_becomes_a_freemusic_error(monkeypatch):
    class Page:
        headers: dict = {}

        def get(self, url, params=None):
            return self

        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("Expecting value")

    monkeypatch.setattr(freemusic, "_session", lambda: Page())

    with pytest.raises(FreeMusicUnavailable, match="JSON"):
        freemusic.albums()


# ---------------------------------------------- the verbs a free row offers


def test_a_free_track_is_offered_only_what_can_actually_be_done():
    """The other five verbs all end at TIDAL: its radio grows from a track in
    its catalogue, and its favourites, playlists, artists and albums are its
    own. Offering them would be five rows that answer with an error."""
    from tidalamp.queue import Entry
    from tidalamp.screens.tracks import TRACK_ACTIONS, actions_for

    free = Entry.from_free(
        Track(
            url="https://archive.org/download/x/a.mp3",
            title="a",
            artist="b",
            album="c",
            licence="CC0",
        )
    )
    offered = [action for action, *_rest in actions_for(free)]
    assert offered == ["play", "next"]

    tidal = Entry(id=1, title="Schism", artist="TOOL")
    assert [action for action, *_rest in actions_for(tidal)] == [
        action for action, *_rest in TRACK_ACTIONS
    ]


def test_a_free_record_is_offered_only_what_can_actually_be_done():
    from tidalamp.library import Row
    from tidalamp.queue import FREE
    from tidalamp.screens.tracks import CONTAINER_ACTIONS, container_actions_for

    free = Row("Field Experience", key="free:gt450", source=FREE)
    assert [action for action, *_rest in container_actions_for(free)] == ["play", "next"]

    album = Row("TOOL - Lateralus", key="album:1")
    assert [action for action, *_rest in container_actions_for(album)] == [
        action for action, *_rest in CONTAINER_ACTIONS
    ]


def test_the_free_letters_are_the_ones_the_full_menu_already_uses():
    """`a` and `c` keep meaning what they mean everywhere else, so muscle
    memory carries over instead of being retrained per section."""
    from tidalamp.screens.tracks import FREE_TRACK_ACTIONS, TRACK_ACTIONS

    full = {action: letter for action, _icon, letter, _label in TRACK_ACTIONS}
    for action, _icon, letter, _label in FREE_TRACK_ACTIONS:
        assert full[action] == letter
