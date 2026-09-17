"""Lyrics parsing and loading without contacting TIDAL."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from tidalamp.lyrics import LyricsUnavailable, load_lyrics, parse_lyrics


def test_lrc_is_parsed_and_sorted_by_timestamp():
    document = parse_lyrics(
        text="fallback",
        subtitles="[00:12.50]dos\n[ar:artista]\n[00:01.250]uno",
        provider="Musixmatch",
    )

    assert document.synced is True
    assert [line.text for line in document.lines] == ["uno", "dos"]
    assert [line.at for line in document.lines] == [1.25, 12.5]
    assert document.provider == "Musixmatch"


def test_multiple_timestamps_create_multiple_lines():
    document = parse_lyrics(subtitles="[00:01.00][00:03.50]estribillo")
    assert [(line.at, line.text) for line in document.lines] == [
        (1.0, "estribillo"),
        (3.5, "estribillo"),
    ]


def test_plain_text_is_used_when_subtitles_are_missing():
    document = parse_lyrics(text="primera\n\nsegunda")
    assert document.synced is False
    assert [line.text for line in document.lines] == ["primera", "", "segunda"]
    assert document.active_index(20) is None


def test_unknown_subtitle_format_falls_back_to_plain_text():
    document = parse_lyrics(text="texto seguro", subtitles="WEBVTT\n00:00 --> 00:01")
    assert [line.text for line in document.lines] == ["texto seguro"]


def test_active_line_and_window_follow_playback_position():
    document = parse_lyrics(
        subtitles="\n".join(f"[00:{second:02d}.00]línea {second}" for second in range(10))
    )
    start, lines, active = document.window(6.2, height=5)
    assert active == 6
    assert start == 4
    assert [line.text for line in lines] == [
        "línea 4",
        "línea 5",
        "línea 6",
        "línea 7",
        "línea 8",
    ]


def test_no_line_is_active_before_the_first_timestamp():
    document = parse_lyrics(subtitles="[00:05.00]primera\n[00:10.00]segunda")
    start, lines, active = document.window(2.0, height=5)
    assert active is None
    assert start == 0
    assert [line.text for line in lines] == ["primera", "segunda"]


def test_load_lyrics_maps_the_tidal_object():
    raw = SimpleNamespace(text="texto", subtitles="", provider="TIDAL")
    track = SimpleNamespace(name="Schism", lyrics=lambda: raw)
    document = load_lyrics(track)
    assert document.provider == "TIDAL"
    assert document.lines[0].text == "texto"


def test_load_lyrics_retries_transient_failures(monkeypatch):
    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)
    calls = []
    raw = SimpleNamespace(text="letra", subtitles="", provider="")

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise requests.ConnectionError("caída")
        return raw

    document = load_lyrics(SimpleNamespace(name="Schism", lyrics=flaky))
    assert document.lines[0].text == "letra"
    assert len(calls) == 3


def test_empty_and_failed_lyrics_are_actionable():
    empty = SimpleNamespace(
        name="Schism",
        lyrics=lambda: SimpleNamespace(text="", subtitles="", provider=""),
    )
    with pytest.raises(LyricsUnavailable, match="Schism"):
        load_lyrics(empty)

    failed = SimpleNamespace(
        name="Schism",
        lyrics=lambda: (_ for _ in ()).throw(RuntimeError("sin licencia")),
    )
    with pytest.raises(LyricsUnavailable, match="sin licencia"):
        load_lyrics(failed)


def test_fit_centres_the_anchor_by_rows_not_by_lines():
    from tidalamp.lyrics import fit

    # Ten lines of two rows in a window of seven: three lines, the anchor
    # in the middle one, and never more rows than the window has.
    start, end = fit([2] * 10, 5, 7)

    assert start <= 5 < end
    assert sum([2] * (end - start)) <= 7
    assert (start, end) == (4, 7)


def test_fit_fills_from_the_other_side_at_either_end():
    from tidalamp.lyrics import fit

    assert fit([1, 3, 1, 1, 1], 0, 5) == (0, 3)
    assert fit([1, 1, 1, 3, 1], 4, 5) == (2, 5)


def test_an_anchor_taller_than_the_window_is_still_shown():
    from tidalamp.lyrics import fit

    assert fit([1, 9, 1], 1, 4) == (1, 2)
    assert fit([], 0, 4) == (0, 0)


def test_scrolling_stops_where_the_last_screenful_starts():
    from tidalamp.lyrics import last_start

    assert last_start([1, 1, 2, 2, 2], 4) == 3
    assert last_start([1, 1], 10) == 0
