"""``Cava`` against the fake cava, plus the Analyzer's sources and shapes."""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import pytest
from textual.geometry import Size

from tidalamp import spectrum
from tidalamp.spectrum import Cava, SpectrumUnavailable
from tidalamp.widgets import Analyzer

FAKE = Path(__file__).parent / "fake_cava.py"


@pytest.fixture
def cava_env(tmp_path, monkeypatch):
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "cava").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    (shim / "cava").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}:{__import__('os').environ['PATH']}")
    monkeypatch.setattr(spectrum, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(spectrum, "ensure_dirs", lambda: None)
    return tmp_path


def wait_for_a_frame(cava, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        frame = cava.frame()
        if any(frame):
            return frame
        time.sleep(0.02)
    raise AssertionError("cava no envió ningún frame")


def test_missing_cava_is_reported_not_raised_blindly(monkeypatch):
    monkeypatch.setattr(spectrum.shutil, "which", lambda _: None)
    with pytest.raises(SpectrumUnavailable, match="no está instalado"):
        Cava()


def test_frames_arrive_normalised(cava_env):
    cava = Cava(bars=19)
    try:
        frame = wait_for_a_frame(cava)
        assert len(frame) == 19
        assert all(0.0 <= v <= 1.0 for v in frame)
        # The fake sends a ramp; the last band must be the loudest.
        assert frame[-1] > frame[0]
    finally:
        cava.close()


def test_the_config_we_write_carries_our_bar_count(cava_env):
    cava = Cava(bars=7)
    try:
        config = (cava_env / "cava.conf").read_text(encoding="utf-8")
        assert "bars = 7" in config
        assert "data_format = binary" in config
        assert len(wait_for_a_frame(cava)) == 7
    finally:
        cava.close()


def test_close_stops_the_process(cava_env):
    cava = Cava(bars=19)
    wait_for_a_frame(cava)
    cava.close()
    assert cava.alive is False


def test_alive_turns_false_when_cava_exits(cava_env, monkeypatch):
    monkeypatch.setenv("FAKE_CAVA_FRAMES", "3")
    cava = Cava(bars=19)
    try:
        deadline = time.monotonic() + 5
        while cava.alive and time.monotonic() < deadline:
            time.sleep(0.05)
        assert cava.alive is False
    finally:
        cava.close()


# ------------------------------------------------------------------ analyzer


class Sized(Analyzer):
    """An Analyzer that believes it has been laid out, without an app.

    The shapes read their band count off the widget's size, and a widget that
    was never mounted reports 0x0.
    """

    def __init__(self, mode: str, width: int, height: int) -> None:
        super().__init__()
        self._laid_out = Size(width, height)
        self.mode = mode

    @property
    def size(self) -> Size:
        return self._laid_out

    def resize(self, width: int, height: int) -> None:
        self._laid_out = Size(width, height)


def sized(mode: str, width: int, height: int) -> Sized:
    analyzer = Sized(mode, width, height)
    analyzer._resize(analyzer.count)
    return analyzer


def drawn(analyzer: Analyzer) -> list[str]:
    return analyzer.render().plain.split("\n")


def test_analyzer_reports_which_source_it_is_using():
    analyzer = Analyzer()
    assert analyzer.source == "RMS"
    analyzer.spectrum = [0.5] * Analyzer.BANDS
    assert analyzer.source == "FFT"


def test_analyzer_draws_the_spectrum_it_is_given():
    # A curve draws one band per column, so at this width there is one band
    # per measured one and what comes out can be compared with what went in.
    analyzer = sized("curve", Analyzer.BANDS, 5)
    analyzer.active = True
    analyzer.spectrum = [i / (Analyzer.BANDS - 1) for i in range(Analyzer.BANDS)]
    targets = analyzer._targets()
    assert targets == analyzer.spectrum
    # Rising bands stay rising; nothing reweights them behind our back.
    assert targets == sorted(targets)


def test_analyzer_falls_back_to_the_rms_envelope():
    analyzer = Analyzer()
    analyzer.active = True
    analyzer.level = -6.0
    targets = analyzer._targets()
    assert analyzer.source == "RMS"
    assert all(0.0 <= v <= 1.0 for v in targets)
    assert any(v > 0.0 for v in targets)


def test_silence_flattens_both_modes():
    analyzer = sized("bars", 80, 5)
    analyzer.active = False
    analyzer.spectrum = [1.0] * Analyzer.BANDS
    assert analyzer._targets() == [0.0] * analyzer.count


# ------------------------------------------------------------------- shapes


def test_the_shapes_are_the_ones_the_setting_offers():
    """The config screen renders MODES straight, so a shape missing from it
    is a shape nobody can pick."""
    assert Analyzer.MODES == ("bars", "mirror", "curve", "fine")


@pytest.mark.parametrize("mode", ["bars", "mirror", "curve", "fine"])
def test_every_shape_uses_every_column_it_is_given(mode):
    """A cap on the band count left the bars stopping short of the right edge
    on a wide terminal, which is the one thing these shapes are for."""
    for width in (80, 200):
        analyzer = sized(mode, width, 5)
        analyzer.active = True
        analyzer.spectrum = [0.9] * Analyzer.BANDS
        analyzer.tick()

        lines = drawn(analyzer)
        assert len(lines) == 5
        # Within one band's width of the full column: what is left over is
        # the remainder of dividing the columns among whole bands.
        assert all(width - 2 <= len(line) <= width for line in lines), (mode, width)


def test_the_bars_take_one_column_each_plus_a_gap():
    """The shape is the classic one; what changed is that it no longer stops
    at nineteen bands and leaves two thirds of the column empty."""
    analyzer = sized("bars", 80, 5)
    assert analyzer.count == 40
    assert len(drawn(analyzer)[0]) == 80


def test_the_mirror_grows_both_ways_from_a_centre_line():
    analyzer = sized("mirror", 40, 5)
    analyzer.active = True
    analyzer.spectrum = [1.0] * Analyzer.BANDS
    for _ in range(20):
        analyzer.tick()

    lines = drawn(analyzer)
    assert set(lines[2].replace(" ", "")) == {"─"}, "la línea central"
    assert "█" in lines[1] and "█" in lines[3], "las filas de dentro se llenan"
    # The outermost row of each half is the one the bar only reaches into, and
    # it is drawn as a half block hanging from the centre — mirrored, so the
    # two halves are the same shape and not one of them eight times finer.
    assert set(lines[0].replace(" ", "")) == {"▄"}
    assert set(lines[4].replace(" ", "")) == {"▀"}
    assert len(lines[0]) == len(lines[4]), "simétrica"


def test_the_curve_draws_a_contour_and_not_a_filled_bar():
    """One glyph per column and nothing under it: that is what makes it a
    line instead of a second bar shape."""
    analyzer = sized("curve", 40, 5)
    analyzer.active = True
    analyzer.spectrum = [0.5] * Analyzer.BANDS
    for _ in range(20):
        analyzer.tick()

    columns = [[line[x] for line in drawn(analyzer)] for x in range(40)]
    assert all(sum(cell != " " for cell in column) == 1 for column in columns)


@pytest.mark.parametrize("mode", ["bars", "mirror", "curve", "fine"])
def test_a_4k_wide_analyser_stays_cheap_to_send_to_the_terminal(mode):
    """Rich turns every span into its own escape sequence. Uncapped bands and
    a span per cell cost 950 of them a frame at this width, which took the app
    from 8% of a core to 55% at ten frames a second.

    Measured against a spectrum shaped like music's — a hump and a tail, not a
    sawtooth — because that is what the neighbouring cells sharing a colour,
    and therefore the merging, depend on.
    """
    analyzer = sized(mode, 380, 5)
    analyzer.active = True
    analyzer.spectrum = [
        math.exp(-((i - 30) ** 2) / 400) + 0.3 * math.exp(-i / 20)
        for i in range(Analyzer.BANDS)
    ]
    for _ in range(10):
        analyzer.tick()

    assert len(analyzer.render().spans) < 120, mode
    # And it still covers the whole width.
    assert all(len(line) == 380 for line in drawn(analyzer))


@pytest.mark.parametrize("mode", ["bars", "mirror"])
def test_the_bars_have_a_worst_case_and_the_width_does_not_change_it(mode):
    """Even against a spectrum built to defeat the merging, the cap holds the
    count down: one span per band per row and no more."""
    analyzer = sized(mode, 380, 5)
    analyzer.active = True
    analyzer.spectrum = [(i % 5) / 4 for i in range(Analyzer.BANDS)]
    for _ in range(10):
        analyzer.tick()

    assert len(analyzer.render().spans) <= 5 * Analyzer.MAX_BARS


def test_the_bars_are_capped_but_still_reach_the_edge():
    """Fewer, wider bars rather than more, thinner ones: the cap is what keeps
    a 4K terminal cheap, and `_slots` is what keeps it full."""
    analyzer = sized("bars", 380, 5)
    assert analyzer.count == Analyzer.MAX_BARS
    assert sum(analyzer._slots()) == 380


def test_the_fine_trace_is_drawn_with_braille_and_nothing_else():
    analyzer = sized("fine", 60, 5)
    analyzer.active = True
    analyzer.spectrum = [0.5] * Analyzer.BANDS
    for _ in range(20):
        analyzer.tick()

    glyphs = set(analyzer.render().plain) - {"\n"}
    assert glyphs, "algo tiene que dibujar"
    assert all(glyph == " " or 0x2800 <= ord(glyph) <= 0x28FF for glyph in glyphs)


def test_the_fine_trace_is_joined_up_and_not_a_row_of_marks():
    """Each sample meets its neighbours halfway, so the line passes through
    every column instead of breaking into dots down a steep edge."""
    analyzer = sized("fine", 60, 5)
    analyzer.active = True
    # A ramp: every column sits at a different height, which is what a row of
    # unjoined marks would show up on.
    analyzer.spectrum = [i / (Analyzer.BANDS - 1) for i in range(Analyzer.BANDS)]
    for _ in range(30):
        analyzer.tick()

    lines = drawn(analyzer)
    for column in range(60):
        assert any(line[column] != " " for line in lines), f"hueco en {column}"


def test_the_fine_trace_is_a_line_and_not_a_filled_area():
    """A loud band lights the dots the trace passes through, not everything
    under it: that is the difference from the bars."""
    analyzer = sized("fine", 60, 5)
    analyzer.active = True
    analyzer.spectrum = [1.0] * Analyzer.BANDS
    for _ in range(30):
        analyzer.tick()

    lines = drawn(analyzer)
    assert lines[0].strip(), "el trazo va arriba del todo"
    assert not lines[-1].strip(), "y no rellena hasta el suelo"


def test_the_fine_trace_puts_two_bands_in_every_column():
    analyzer = sized("fine", 60, 5)
    assert analyzer.count == 120
    assert len(drawn(analyzer)) == 5


def test_a_frame_is_averaged_down_and_interpolated_up():
    frame = [0.0, 1.0]
    assert Analyzer._resample(frame, 2) == frame
    # Down: the two halves are averaged into one value.
    assert Analyzer._resample([0.0, 0.0, 1.0, 1.0], 2) == [0.0, 1.0]
    # Up: a straight line between the measured points, not a staircase.
    assert Analyzer._resample(frame, 3) == [0.0, 0.5, 1.0]


def test_a_mirror_with_no_room_for_a_centre_line_draws_plain_bars():
    """One row is what the compact layout leaves the analyser, and a third of
    a mirror is not a shape."""
    analyzer = sized("mirror", 40, 1)
    analyzer.active = True
    analyzer.spectrum = [0.9] * Analyzer.BANDS
    for _ in range(20):
        analyzer.tick()

    assert "─" not in analyzer.render().plain


def test_every_shape_reads_the_same_frame_cava_sends():
    """cava is asked for BANDS bands once and never restarted: each shape
    resamples that one frame to whatever it draws."""
    frame = [i / (Analyzer.BANDS - 1) for i in range(Analyzer.BANDS)]
    for mode in Analyzer.MODES:
        analyzer = sized(mode, 80, 5)
        analyzer.active = True
        analyzer.spectrum = frame
        targets = analyzer._targets()
        assert len(targets) == analyzer.count
        assert all(0.0 <= value <= 1.0 for value in targets)
        assert targets == sorted(targets), mode
