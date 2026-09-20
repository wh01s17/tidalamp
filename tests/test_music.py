"""The types and the licence names both sources answer with.

`music` is the seam that lets `freemusic` treat Jamendo and the Internet
Archive as the same thing. What is checked here is the part that has to hold
whichever source a track came from.
"""

from __future__ import annotations

import pytest

from tidalamp import music
from tidalamp.music import Track


def track(url: str = "https://archive.org/download/x/a.mp3", **over) -> Track:
    return Track(url=url, title="", artist="", album="", licence="", **over)


# ------------------------------------------------------------------ licences


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0"),
        ("https://creativecommons.org/publicdomain/mark/1.0/", "dominio público"),
        ("https://creativecommons.org/licenses/by/4.0/", "CC BY"),
        ("http://creativecommons.org/licenses/by-sa/3.0/", "CC BY-SA"),
        ("http://creativecommons.org/licenses/by-nc/3.0/", "CC BY-NC"),
        ("http://creativecommons.org/licenses/by-nd/2.0/fr/", "CC BY-ND"),
        ("http://creativecommons.org/licenses/by-nc-sa/3.0/", "CC BY-NC-SA"),
        ("http://creativecommons.org/licenses/by-nc-nd/2.5/", "CC BY-NC-ND"),
    ],
)
def test_licence_names_drop_the_version(url, name):
    assert music.licence_name(url) == name


def test_share_alike_is_not_read_as_plain_attribution():
    """`licenses/by-sa` contains `licenses/by`, so the order of the table
    decides: the wrong one labelled every share-alike track «CC BY» and
    quietly dropped the condition that matters most to whoever reuses it."""
    assert music.licence_name("http://creativecommons.org/licenses/by-sa/3.0/") != "CC BY"


def test_an_unknown_licence_shows_its_url_rather_than_a_guess():
    unknown = "http://example.invalid/x"
    assert music.licence_name(unknown) == unknown


@pytest.mark.parametrize("licence", ["CC0", "dominio público", "CC BY", "CC BY-SA"])
def test_the_permissive_licences_are_the_ones_you_may_actually_use(licence):
    assert music.is_permissive(licence)


@pytest.mark.parametrize(
    "licence",
    ["CC BY-NC", "CC BY-ND", "CC BY-NC-SA", "CC BY-NC-ND", "", "http://example/x"],
)
def test_everything_else_is_kept_out(licence):
    """Every Creative Commons licence allows listening, so this is not what
    makes playback lawful; it is what makes the section's name true. An empty
    licence is not permissive either: it is unknown, and we may not guess."""
    assert not music.is_permissive(licence)


# ------------------------------------------------------------------------ ids


def test_a_track_id_is_negative_so_it_can_never_be_a_tidal_one():
    """The queue keys deduplication, the lyrics cache and restored identity
    off `Entry.id`. TIDAL's are positive; these must never collide."""
    assert track().id < 0


def test_the_same_url_is_always_the_same_id():
    assert track().id == track().id
    assert track().id != track("https://archive.org/download/x/b.mp3").id


def test_two_sources_never_collide_on_one_id():
    """The station may hand back either source's tracks, and the queue tells
    rows apart by this number alone."""
    assert track("https://www.jamendo.com/a").id != track("https://archive.org/a").id


# ------------------------------------------------------------------ the wire


def test_a_network_failure_becomes_a_named_error(monkeypatch):
    """Not a bare `requests` exception: the browser prints what it catches,
    and «ConnectionError()» tells a user nothing about which source broke."""
    import requests

    class Boom:
        headers: dict = {}

        def get(self, url, params=None):
            raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(music, "session", lambda: Boom())
    with pytest.raises(music.FreeMusicUnavailable, match="Jamendo"):
        music.get_json("https://x", who="Jamendo")


def test_a_body_that_is_not_json_becomes_a_named_error(monkeypatch):
    class Page:
        headers: dict = {}

        def get(self, url, params=None):
            return self

        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("Expecting value")

    monkeypatch.setattr(music, "session", lambda: Page())
    with pytest.raises(music.FreeMusicUnavailable, match="JSON"):
        music.get_json("https://x", who="Jamendo")


@pytest.mark.parametrize(
    ("raw", "want"),
    [(["2012"], 2012), ("2012-03-01", 0), (None, 0), ([], 0), ("175.57", 175)],
)
def test_numbers_survive_loose_typing(raw, want):
    """These APIs type loosely: a year may arrive as int, str or a list."""
    assert music.as_int(raw) == want


@pytest.mark.parametrize(
    ("raw", "want"),
    [(["a", "b"], "a, b"), (["a", None], "a"), (None, ""), ("a", "a"), ([], "")],
)
def test_text_survives_loose_typing(raw, want):
    assert music.as_text(raw) == want
