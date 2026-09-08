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
