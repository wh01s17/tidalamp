"""The Jamendo client, the source «Lofi sin copyright» draws from when it can.

Never over the network: every test hands `get_json` a recorded body, which is
the shape the live API answered with on 2026-09-20. Two things here are not
obvious and both were measured rather than assumed — that Jamendo answers
`success` with an empty result set every so often, and that its own licence
filter leaves a handful of rows with no licence at all.
"""

from __future__ import annotations

import pytest

from tidalamp import config, jamendo
from tidalamp.music import FreeMusicUnavailable

# One row, trimmed to the fields the code reads.
ROW = {
    "id": "6581",
    "name": "Arcadia",
    "artist_name": "Tryad",
    "album_name": "Public Domain",
    "duration": 220,
    "releasedate": "2007-03-14",
    "position": 3,
    "license_ccurl": "http://creativecommons.org/licenses/by-sa/3.0/",
    "audio": "https://prod-1.storage.jamendo.com/?trackid=6581&format=mp32",
    "album_image": "https://usercontent.jamendo.com?type=album&id=1003",
    "shareurl": "https://www.jamendo.com/track/6581",
}


def body(*rows, status: str = "success", error: str = "") -> dict:
    return {
        "headers": {
            "status": status,
            "code": 0 if status == "success" else 5,
            "error_message": error,
            "results_count": len(rows),
        },
        "results": list(rows),
    }


@pytest.fixture
def answers(monkeypatch):
    """Queue up what `get_json` hands back, and record what it was asked for."""
    calls: list[tuple[str, dict | None]] = []
    bodies: list[object] = []

    def fake(url, params=None, *, who=""):
        calls.append((url, params))
        return bodies.pop(0)

    monkeypatch.setattr(jamendo, "get_json", fake)
    # No waiting on the empty-answer retry: these tests are not about time.
    monkeypatch.setattr(jamendo, "EMPTY_PAUSE", 0)
    monkeypatch.setattr(config, "JAMENDO_ID", "testing")
    return calls, bodies


# ------------------------------------------------------------- the client id


def test_with_no_client_id_it_says_so_rather_than_asking(monkeypatch):
    """The station reads this as «use the other source», so it has to fail
    rather than send a request that can only be refused."""
    monkeypatch.setattr(config, "JAMENDO_ID", "")
    with pytest.raises(FreeMusicUnavailable, match="client_id"):
        jamendo.tracks()


def test_whitespace_is_not_a_client_id(monkeypatch):
    monkeypatch.setattr(config, "JAMENDO_ID", "   ")
    assert not jamendo.configured()


def test_the_id_rides_along_in_the_query(answers):
    calls, bodies = answers
    bodies.append(body(ROW))
    jamendo.tracks()
    _url, params = calls[0]
    assert params["client_id"] == "testing"


# ---------------------------------------------------------------- the query


def test_the_query_asks_the_server_for_the_permissive_half(answers):
    """`ccnc=0&ccnd=0` is what turns 23 permissive tracks out of 200 into
    192, measured against the live API. Filtering here instead would throw
    away seven eighths of every page."""
    calls, bodies = answers
    bodies.append(body(ROW))
    jamendo.tracks()
    _url, params = calls[0]
    assert params["ccnc"] == 0
    assert params["ccnd"] == 0


def test_the_query_asks_for_instrumental_rather_than_guessing(answers):
    """A field the artist set, not a guess made by reading titles for the
    word «rapper» the way the Archive has to."""
    calls, bodies = answers
    bodies.append(body(ROW))
    jamendo.tracks()
    assert calls[0][1]["vocalinstrumental"] == "instrumental"


def test_the_query_asks_for_a_whole_day_at_once(answers):
    """Jamendo's maximum page is 200 and it carries the audio URLs with it,
    so a day is one request instead of the Archive's two dozen."""
    calls, bodies = answers
    bodies.append(body(ROW))
    jamendo.tracks()
    assert calls[0][1]["limit"] == 200


# ----------------------------------------------------------------- the rows


def test_a_row_becomes_a_track(answers):
    _calls, bodies = answers
    bodies.append(body(ROW))
    track = jamendo.tracks()[0]
    assert (track.title, track.artist, track.album) == (
        "Arcadia",
        "Tryad",
        "Public Domain",
    )
    assert track.licence == "CC BY-SA"
    assert track.duration == 220
    assert track.year == 2007
    assert track.url.startswith("https://prod-1.storage.jamendo.com/")


def test_the_source_is_the_track_page_and_not_the_audio(answers):
    """Attribution asks for where the work lives, and the audio URL is a
    signed link to a file."""
    _calls, bodies = answers
    bodies.append(body(ROW))
    track = jamendo.tracks()[0]
    assert track.source_url == "https://www.jamendo.com/track/6581"
    assert track.source_url != track.url


def test_a_row_with_no_licence_is_dropped_even_though_the_server_filtered(answers):
    """A handful come back with the field empty, and an empty licence is not
    a permissive one — it is an unknown one, and this section may not guess."""
    _calls, bodies = answers
    bodies.append(body({**ROW, "license_ccurl": ""}, ROW))
    assert len(jamendo.tracks()) == 1


def test_a_row_with_no_audio_is_dropped(answers):
    _calls, bodies = answers
    bodies.append(body({**ROW, "audio": ""}, ROW))
    assert len(jamendo.tracks()) == 1


def test_a_page_with_nothing_usable_says_so(answers):
    _calls, bodies = answers
    bodies.append(body({**ROW, "license_ccurl": ""}))
    with pytest.raises(FreeMusicUnavailable, match="permisiva"):
        jamendo.tracks()


# ------------------------------------------------- Jamendo's empty answers


def test_an_empty_answer_is_a_failure_and_not_an_answer(answers):
    """Measured on 2026-09-20: three of twelve identical calls came back
    `success` with no results, no error and no warning. Reading that as «there
    is no lofi today» would have emptied the section at random."""
    _calls, bodies = answers
    bodies.extend([body(), body(), body(ROW)])
    assert len(jamendo.tracks()) == 1


def test_it_gives_up_eventually_rather_than_asking_forever(answers, monkeypatch):
    _calls, bodies = answers
    monkeypatch.setattr(jamendo, "EMPTY_TRIES", 3)
    bodies.extend([body(), body(), body()])
    with pytest.raises(FreeMusicUnavailable, match="sin resultados"):
        jamendo.tracks()


def test_a_refusal_is_reported_at_once_and_not_retried(answers):
    """A suspended application or a bad id will not fix itself, and the
    station has a second source to go to."""
    calls, bodies = answers
    bodies.append(body(status="failed", error="Suspended Application"))
    with pytest.raises(FreeMusicUnavailable, match="Suspended"):
        jamendo.tracks()
    assert len(calls) == 1
