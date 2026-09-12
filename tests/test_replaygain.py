"""ReplayGain: the gain a mode picks, the peak that caps it, and what TIDAL's
answer brings for it."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tidalamp import stream
from tidalamp.settings import REPLAYGAIN_MODES, replaygain

TRACK = (-7.5, 0.9)
ALBUM = (-9.0, 0.98)


def test_the_three_modes():
    assert REPLAYGAIN_MODES == ("off", "track", "album")
    assert replaygain("off", TRACK, ALBUM) == 0.0
    assert replaygain("track", TRACK, ALBUM) == -7.5
    assert replaygain("album", TRACK, ALBUM) == -9.0


def test_an_unknown_mode_leaves_the_track_alone():
    """The setting comes from a file the user edits by hand."""
    assert replaygain("loud", TRACK, ALBUM) == 0.0


def test_a_raised_track_is_not_pushed_past_full_scale():
    """+6 dB on a track peaking at 0.8 would clip it: the peak marks the
    limit, and 0.8 has 1.94 dB of room."""
    assert replaygain("track", (6.0, 0.8), ALBUM) == 1.94


def test_a_gain_that_lowers_the_level_is_never_cut():
    assert replaygain("track", (-3.0, 1.0), ALBUM) == -3.0


def test_album_mode_falls_back_to_the_track_and_then_to_nothing():
    assert replaygain("album", TRACK, (None, None)) == -7.5
    assert replaygain("album", (None, None), (None, None)) == 0.0
    assert replaygain("track", (None, None), ALBUM) == 0.0


def test_no_peak_means_no_ceiling():
    assert replaygain("track", (4.0, None), ALBUM) == 4.0


# ------------------------------------------------------- from TIDAL's answer


def a_stream(**fields):
    base = {
        "track_replay_gain": -8.25,
        "track_peak_amplitude": 0.97,
        "album_replay_gain": -9.5,
        "album_peak_amplitude": 0.99,
    }
    return SimpleNamespace(**(base | fields))


def test_the_gains_come_with_the_stream_we_already_ask_for():
    """Confirmed against tidalapi 0.8: `Track.get_stream()` parses
    `trackReplayGain`, `trackPeakAmplitude` and the album's two off the same
    `playbackinfopostpaywall` answer that carries the manifest."""
    assert stream._loudness(a_stream(), "track") == (-8.25, 0.97)
    assert stream._loudness(a_stream(), "album") == (-9.5, 0.99)


@pytest.mark.parametrize("which", ["track", "album"])
def test_tidalapis_stand_in_for_a_missing_value_is_not_a_gain(which):
    """tidalapi writes 1.0 for both when TIDAL leaves them out, which would
    otherwise play every such track 1 dB up."""
    fields = {f"{which}_replay_gain": 1.0, f"{which}_peak_amplitude": 1.0}
    assert stream._loudness(a_stream(**fields), which) == (None, None)


def test_a_stream_without_the_fields_has_no_gain():
    assert stream._loudness(SimpleNamespace(), "track") == (None, None)
    assert stream._loudness(a_stream(track_replay_gain="x"), "track") == (None, None)
