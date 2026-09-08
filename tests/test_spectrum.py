"""``Cava`` against the fake cava, plus the Analyzer's two modes."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

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


def test_analyzer_reports_which_source_it_is_using():
    analyzer = Analyzer()
    assert analyzer.source == "RMS"
    analyzer.spectrum = [0.5] * Analyzer.BARS
    assert analyzer.source == "FFT"


def test_analyzer_draws_the_spectrum_it_is_given():
    analyzer = Analyzer()
    analyzer.active = True
    analyzer.spectrum = [i / (Analyzer.BARS - 1) for i in range(Analyzer.BARS)]
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
    analyzer = Analyzer()
    analyzer.active = False
    analyzer.spectrum = [1.0] * Analyzer.BARS
    assert analyzer._targets() == [0.0] * Analyzer.BARS
