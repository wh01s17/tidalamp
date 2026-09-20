"""The Internet Archive client behind «Lofi sin copyright».

Never over the network: every test hands `_get` a recorded body, which is the
shape the real endpoints answered with on 2026-09-20. What is checked is the
parsing, because that is where the Archive's loose typing bites — a `creator`
that is a list, a `year` that is missing, a `length` that is a string with a
decimal point, and a file listing that holds four derivatives of every
recording.
"""

from __future__ import annotations

from datetime import date

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
    assert freemusic._is_junk(doc), why


@pytest.mark.parametrize(
    "doc",
    [
        {"title": "Popoi - Georgetown Cafe", "subject": ["chillhop", "lofi hiphop"]},
        {"title": "Elephant Funeral - The Mountains", "subject": "chillhop,lofi,sad"},
        {"title": "unVoid - Mintaka", "creator": "unVoid", "subject": ["chillhop"]},
    ],
)
def test_the_junk_filter_keeps_the_music(doc):
    assert not freemusic._is_junk(doc)


def test_the_junk_filter_reads_the_tags_and_not_only_the_title():
    """«Ulises» says nothing; its `screamo` tag says everything."""
    assert not freemusic._is_junk({"title": "Ulises"})
    assert freemusic._is_junk({"title": "Ulises", "subject": ["screamo"]})


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
    assert [album.identifier for album in freemusic.albums()] == ["good"]


def test_the_query_asks_for_the_genre_and_not_for_the_word_lofi():
    """The trap the section was built wrong on first: on the Archive
    `subject:lofi` means both lofi the genre and lo-fi the recording quality,
    and it returned a Playmate calendar and a David Koresh discography among
    the beats."""
    assert '"chillhop"' in freemusic.QUERY
    assert '"lofi hip hop"' in freemusic.QUERY
    assert '"lofi"' not in freemusic.QUERY
    assert '"lo-fi"' not in freemusic.QUERY


# ----------------------------------------------------------------- the station


@pytest.fixture
def no_disk(monkeypatch, tmp_path):
    """The day's cache somewhere harmless, and empty."""
    monkeypatch.setattr(freemusic, "STATION_FILE", tmp_path / "lofi-station.json")


def records(count: int, each: int = 4) -> list[Album]:
    return [Album(f"r{i}", f"disco {i}", f"artista {i}", "CC BY") for i in range(count)]


def songs_of(album: Album, each: int = 4) -> list[Track]:
    return [
        Track(
            url=f"https://archive.org/download/{album.identifier}/{n}.mp3",
            title=f"{album.title} · {n}",
            artist=album.creator,
            album=album.title,
            licence=album.licence,
            duration=180,
        )
        for n in range(each)
    ]


@pytest.fixture
def archive(monkeypatch, no_disk):
    """A pool of thirty records with four tracks each, and no network."""
    pool = records(30)
    monkeypatch.setattr(freemusic, "albums", lambda offset=0, limit=100: list(pool))
    monkeypatch.setattr(freemusic, "tracks", songs_of)
    return pool


def test_the_station_is_the_same_all_day_and_different_tomorrow(archive):
    today, tomorrow = date(2026, 9, 20), date(2026, 9, 21)
    first = freemusic.station(today)
    assert freemusic.station(today) == first
    assert freemusic.station(tomorrow) != first


def test_the_same_day_draws_the_same_tracks_on_every_machine(archive):
    """Seeded with the date and nothing else: no server decides this, and two
    people on the same day hear the same station."""
    day = date(2026, 9, 20)
    drawn = freemusic.station(day)
    freemusic.STATION_FILE.unlink(missing_ok=True)
    assert freemusic.station(day) == drawn


def test_no_record_may_take_over_the_day(archive):
    """Interleaving alone is fair only while every record still has cards:
    once the singles run out the long records take every remaining round, and
    the first day drawn that way was 24 of its 35 tracks from two artists."""
    from collections import Counter

    counts = Counter(song.album for song in freemusic.station(date(2026, 9, 20)))
    assert max(counts.values()) <= freemusic.STATION_PER_RECORD
    assert len(counts) >= 9, "un día no puede ser la tarde de un artista"


def test_the_day_is_capped(archive):
    assert len(freemusic.station(date(2026, 9, 20))) <= freemusic.STATION_TRACKS


def test_an_hour_long_mix_stays_out_of_the_rotation(monkeypatch, no_disk):
    """What this corner of the Archive is full of: «3 HOURS of lofi to study
    to», one file, uploaded as if it were a track. A day of thirty-eight came
    back at seven hours and fifty-one minutes before this."""
    pool = records(12)

    def mixed(album):
        return [
            *songs_of(album, 3),
            Track(
                url=f"https://archive.org/download/{album.identifier}/mix.mp3",
                title=f"3 HOURS of lofi · {album.identifier}",
                artist=album.creator,
                album=album.title,
                licence="CC BY",
                duration=3 * 60 * 60,
            ),
            Track(
                url=f"https://archive.org/download/{album.identifier}/tag.mp3",
                title="jingle",
                artist=album.creator,
                album=album.title,
                licence="CC BY",
                duration=4,
            ),
        ]

    monkeypatch.setattr(freemusic, "albums", lambda offset=0, limit=100: list(pool))
    monkeypatch.setattr(freemusic, "tracks", mixed)

    day = freemusic.station(date(2026, 9, 20))
    assert day, "quitar los mixes no puede dejar el día vacío"
    for song in day:
        assert freemusic.STATION_SHORTEST <= song.duration <= freemusic.STATION_LONGEST


def test_a_track_of_unknown_length_is_kept(monkeypatch, no_disk):
    """An unknown length is the metadata's fault, not the music's, and mpv
    says how long it is the moment it opens it."""
    pool = records(4)
    monkeypatch.setattr(freemusic, "albums", lambda offset=0, limit=100: list(pool))
    monkeypatch.setattr(
        freemusic,
        "tracks",
        lambda album: [
            Track(
                url=f"https://archive.org/download/{album.identifier}/a.mp3",
                title="sin duración",
                artist=album.creator,
                album=album.title,
                licence="CC BY",
                duration=0,
            )
        ],
    )
    assert len(freemusic.station(date(2026, 9, 20))) == 4


def test_one_record_that_will_not_open_does_not_spoil_the_day(monkeypatch, no_disk):
    pool = records(12)
    monkeypatch.setattr(freemusic, "albums", lambda offset=0, limit=100: list(pool))

    def flaky(album):
        if album.identifier in ("r0", "r5"):
            raise FreeMusicUnavailable("sin ficheros")
        return songs_of(album)

    monkeypatch.setattr(freemusic, "tracks", flaky)
    day = freemusic.station(date(2026, 9, 20))
    assert day
    assert not any(song.album in ("disco 0", "disco 5") for song in day)


def test_a_day_where_nothing_opens_says_so(monkeypatch, no_disk):
    monkeypatch.setattr(freemusic, "albums", lambda offset=0, limit=100: records(4))
    monkeypatch.setattr(
        freemusic,
        "tracks",
        lambda album: (_ for _ in ()).throw(FreeMusicUnavailable("x")),
    )
    with pytest.raises(FreeMusicUnavailable):
        freemusic.station(date(2026, 9, 20))


def test_an_empty_pool_says_so(monkeypatch, no_disk):
    monkeypatch.setattr(freemusic, "albums", lambda offset=0, limit=100: [])
    with pytest.raises(FreeMusicUnavailable):
        freemusic.station(date(2026, 9, 20))


def test_the_day_is_read_from_disk_instead_of_fetched_again(archive, monkeypatch):
    day = date(2026, 9, 20)
    drawn = freemusic.station(day)

    def never(*args, **kwargs):
        raise AssertionError("la selección del día ya estaba en disco")

    monkeypatch.setattr(freemusic, "albums", never)
    monkeypatch.setattr(freemusic, "tracks", never)
    assert freemusic.station(day) == drawn


def test_yesterdays_cache_is_redrawn_rather_than_served(archive):
    freemusic.station(date(2026, 9, 20))
    fresh = freemusic.station(date(2026, 9, 21))
    assert fresh == freemusic.station(date(2026, 9, 21))


@pytest.mark.parametrize(
    "broken",
    ['{"day": "2026-09-20", "tracks": [{"nope": 1}]}', "{not json", "[]", '{"day": 3}'],
)
def test_a_broken_cache_is_redrawn_and_not_a_crash(archive, broken):
    """It caches something reproducible, so there is nothing in it worth
    recovering and nothing in it worth failing over."""
    freemusic.STATION_FILE.write_text(broken, encoding="utf-8")
    assert freemusic.station(date(2026, 9, 20))


def test_a_cache_that_cannot_be_written_still_gives_the_day(archive, monkeypatch):
    monkeypatch.setattr(
        freemusic,
        "write_atomically",
        lambda path, text: (_ for _ in ()).throw(OSError("disco lleno")),
    )
    assert freemusic.station(date(2026, 9, 20))


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
    assert freemusic._is_junk(doc), why


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
    assert not freemusic._is_junk(doc)


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
    assert not freemusic._instrumental(guest)
    assert freemusic._instrumental(plain)


def test_a_sung_track_never_reaches_the_rotation(monkeypatch, no_disk):
    """Lofi is music to put behind whatever you are doing, and a voice is the
    one thing that will not stay behind it."""
    pool = records(12)

    def mixed(album):
        return [
            *songs_of(album, 3),
            Track(
                url=f"https://archive.org/download/{album.identifier}/v.mp3",
                title="Interlude (feat. Somebody)",
                artist=album.creator,
                album=album.title,
                licence="CC BY",
                duration=180,
            ),
            Track(
                url=f"https://archive.org/download/{album.identifier}/w.mp3",
                title="Talking",
                artist="A Rapper",
                album=album.title,
                licence="CC BY",
                duration=180,
            ),
        ]

    monkeypatch.setattr(freemusic, "albums", lambda offset=0, limit=100: list(pool))
    monkeypatch.setattr(freemusic, "tracks", mixed)

    day = freemusic.station(date(2026, 9, 20))
    assert day
    for song in day:
        assert "feat" not in song.title.lower()
        assert "Rapper" not in song.artist


def test_whole_words_only():
    """`rap` inside `therapy` and `mc` inside `ambient` would each have
    emptied half the pool."""
    assert not freemusic._says("music therapy ambient soft", freemusic.VOCALS)
    assert freemusic._says("ambient, female_vocals", freemusic.VOCALS)
