"""The station: a day of music out of whichever source can serve it.

Never over the network and never over a real source: both providers are
stubbed, because what is under test here is what `freemusic` decides and the
sources cannot — how long a track may be, how much of a day one record may
take, in what order, and what happens when a source will not answer.
"""

from __future__ import annotations

from datetime import date

import pytest

from tidalamp import archive, freemusic
from tidalamp import config as config_module
from tidalamp.archive import Album
from tidalamp.music import FreeMusicUnavailable, Track

# ----------------------------------------------------------------- the station


@pytest.fixture
def no_disk(monkeypatch, tmp_path):
    """The day's cache somewhere harmless and empty, and Jamendo switched off.

    Off by emptying the client id, which is what a machine that never
    configured one looks like: the station falls to the Archive, and these
    tests stub that.
    """
    monkeypatch.setattr(freemusic, "STATION_FILE", tmp_path / "lofi-station.json")
    monkeypatch.setattr(config_module, "JAMENDO_ID", "")


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
def sources(monkeypatch, no_disk):
    """A pool of thirty records with four tracks each, and no network.

    Jamendo is switched off by emptying the client id, which is the same
    thing that happens on a machine that never configured one: the station
    then falls to the Archive, and these tests are about what the station
    does with whatever it is given.
    """
    monkeypatch.setattr(config_module, "JAMENDO_ID", "")
    pool = records(30)
    monkeypatch.setattr(archive, "albums", lambda offset=0, limit=100: list(pool))
    monkeypatch.setattr(archive, "tracks", songs_of)
    return pool


def test_the_station_is_the_same_all_day_and_different_tomorrow(sources):
    today, tomorrow = date(2026, 9, 20), date(2026, 9, 21)
    first = freemusic.station(today)
    assert freemusic.station(today) == first
    assert freemusic.station(tomorrow) != first


def test_the_same_day_draws_the_same_tracks_on_every_machine(sources):
    """Seeded with the date and nothing else: no server decides this, and two
    people on the same day hear the same station."""
    day = date(2026, 9, 20)
    drawn = freemusic.station(day)
    freemusic.STATION_FILE.unlink(missing_ok=True)
    assert freemusic.station(day) == drawn


def test_no_record_may_take_over_the_day(sources):
    """Interleaving alone is fair only while every record still has cards:
    once the singles run out the long records take every remaining round, and
    the first day drawn that way was 24 of its 35 tracks from two artists."""
    from collections import Counter

    counts = Counter(song.album for song in freemusic.station(date(2026, 9, 20)))
    assert max(counts.values()) <= freemusic.STATION_PER_RECORD
    assert len(counts) >= 9, "un día no puede ser la tarde de un artista"


def test_the_day_is_capped(sources):
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

    monkeypatch.setattr(archive, "albums", lambda offset=0, limit=100: list(pool))
    monkeypatch.setattr(archive, "tracks", mixed)

    day = freemusic.station(date(2026, 9, 20))
    assert day, "quitar los mixes no puede dejar el día vacío"
    for song in day:
        assert freemusic.STATION_SHORTEST <= song.duration <= freemusic.STATION_LONGEST


def test_a_track_of_unknown_length_is_kept(monkeypatch, no_disk):
    """An unknown length is the metadata's fault, not the music's, and mpv
    says how long it is the moment it opens it."""
    pool = records(4)
    monkeypatch.setattr(archive, "albums", lambda offset=0, limit=100: list(pool))
    monkeypatch.setattr(
        archive,
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
    monkeypatch.setattr(archive, "albums", lambda offset=0, limit=100: list(pool))

    def flaky(album):
        if album.identifier in ("r0", "r5"):
            raise FreeMusicUnavailable("sin ficheros")
        return songs_of(album)

    monkeypatch.setattr(archive, "tracks", flaky)
    day = freemusic.station(date(2026, 9, 20))
    assert day
    assert not any(song.album in ("disco 0", "disco 5") for song in day)


def test_a_day_where_nothing_opens_says_so(monkeypatch, no_disk):
    monkeypatch.setattr(archive, "albums", lambda offset=0, limit=100: records(4))
    monkeypatch.setattr(
        archive,
        "tracks",
        lambda album: (_ for _ in ()).throw(FreeMusicUnavailable("x")),
    )
    with pytest.raises(FreeMusicUnavailable):
        freemusic.station(date(2026, 9, 20))


def test_an_empty_pool_says_so(monkeypatch, no_disk):
    monkeypatch.setattr(archive, "albums", lambda offset=0, limit=100: [])
    with pytest.raises(FreeMusicUnavailable):
        freemusic.station(date(2026, 9, 20))


def test_the_day_is_read_from_disk_instead_of_fetched_again(sources, monkeypatch):
    day = date(2026, 9, 20)
    drawn = freemusic.station(day)

    def never(*args, **kwargs):
        raise AssertionError("la selección del día ya estaba en disco")

    monkeypatch.setattr(archive, "albums", never)
    monkeypatch.setattr(archive, "tracks", never)
    assert freemusic.station(day) == drawn


def test_yesterdays_cache_is_redrawn_rather_than_served(sources):
    freemusic.station(date(2026, 9, 20))
    fresh = freemusic.station(date(2026, 9, 21))
    assert fresh == freemusic.station(date(2026, 9, 21))


@pytest.mark.parametrize(
    "broken",
    ['{"day": "2026-09-20", "tracks": [{"nope": 1}]}', "{not json", "[]", '{"day": 3}'],
)
def test_a_broken_cache_is_redrawn_and_not_a_crash(sources, broken):
    """It caches something reproducible, so there is nothing in it worth
    recovering and nothing in it worth failing over."""
    freemusic.STATION_FILE.write_text(broken, encoding="utf-8")
    assert freemusic.station(date(2026, 9, 20))


def test_a_cache_that_cannot_be_written_still_gives_the_day(sources, monkeypatch):
    monkeypatch.setattr(
        freemusic,
        "write_atomically",
        lambda path, text: (_ for _ in ()).throw(OSError("disco lleno")),
    )
    assert freemusic.station(date(2026, 9, 20))


# ------------------------------------------------- which source serves a day


@pytest.fixture
def both(monkeypatch, tmp_path):
    """Both sources stubbed, and a cache nobody else is using."""
    from tidalamp import jamendo

    monkeypatch.setattr(freemusic, "STATION_FILE", tmp_path / "lofi-station.json")
    monkeypatch.setattr(config_module, "JAMENDO_ID", "testing")
    asked: list[str] = []

    def from_jamendo(offset=0):
        asked.append("jamendo")
        return [
            Track(
                url=f"https://www.jamendo.com/{n}.mp3",
                title=f"jamendo {n}",
                artist=f"artista {n}",
                album="j",
                licence="CC BY",
                duration=180,
            )
            for n in range(30)
        ]

    def archive_albums(offset=0, limit=100):
        asked.append("archive")
        return records(12)

    monkeypatch.setattr(jamendo, "tracks", from_jamendo)
    monkeypatch.setattr(archive, "albums", archive_albums)
    monkeypatch.setattr(archive, "tracks", songs_of)
    return asked


def test_jamendo_serves_the_day_when_there_is_a_client_id(both):
    day = freemusic.station(date(2026, 9, 20))
    assert both == ["jamendo"], "el Archive no se toca si Jamendo contesta"
    assert all(song.url.startswith("https://www.jamendo.com/") for song in day)


def test_the_archive_catches_the_day_when_jamendo_will_not(both, monkeypatch):
    """A day is never lost to one source being down: they answer with the
    same `Track`, and the only thing that changes is how long the first open
    takes and how good the filtering was."""
    from tidalamp import jamendo

    def refuse(offset=0):
        both.append("jamendo")
        raise FreeMusicUnavailable("suspendida")

    monkeypatch.setattr(jamendo, "tracks", refuse)
    day = freemusic.station(date(2026, 9, 20))
    assert both == ["jamendo", "archive"]
    assert day


def test_with_no_client_id_jamendo_is_not_even_asked(both, monkeypatch):
    monkeypatch.setattr(config_module, "JAMENDO_ID", "")
    freemusic.station(date(2026, 9, 20))
    assert both == ["archive"]


def test_the_row_says_which_source_a_day_would_come_from(monkeypatch):
    monkeypatch.setattr(config_module, "JAMENDO_ID", "testing")
    assert freemusic.source_name() == "Jamendo"
    monkeypatch.setattr(config_module, "JAMENDO_ID", "")
    assert "Archive" in freemusic.source_name()


def test_a_jamendo_day_spreads_itself_across_artists(both):
    """Jamendo orders by popularity and we want a day, not a chart."""
    from collections import Counter

    day = freemusic.station(date(2026, 9, 20))
    assert max(Counter(song.artist for song in day).values()) <= (
        freemusic.STATION_PER_RECORD
    )


def test_a_jamendo_day_is_capped_and_length_filtered(both, monkeypatch):
    from tidalamp import jamendo

    def mixed(offset=0):
        return [
            Track(
                url=f"https://www.jamendo.com/{n}.mp3",
                title=f"pista {n}",
                artist=f"artista {n}",
                album="j",
                licence="CC BY",
                # One of every three is an hour-long mix.
                duration=180 if n % 3 else 3 * 60 * 60,
            )
            for n in range(60)
        ]

    monkeypatch.setattr(jamendo, "tracks", mixed)
    day = freemusic.station(date(2026, 9, 20))
    assert len(day) <= freemusic.STATION_TRACKS
    assert all(song.duration <= freemusic.STATION_LONGEST for song in day)
