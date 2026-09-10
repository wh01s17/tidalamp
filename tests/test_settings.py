"""Balance and equaliser: clamping, the filter graphs, and persistence."""

from __future__ import annotations

import pytest

from tidalamp import settings as settings_module
from tidalamp.settings import BANDS, GAIN_LIMIT, Settings


@pytest.fixture(autouse=True)
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", path)
    monkeypatch.setattr(settings_module, "ensure_dirs", lambda: None)
    return path


def test_defaults_are_neutral_and_install_no_filters():
    s = Settings()
    assert s.balance == 0.0
    assert s.gains == [0.0] * len(BANDS)
    # Neutral means *no* filter, so the chain is not reinitialised for nothing.
    assert s.balance_graph() is None
    assert s.eq_graph() is None
    assert s.eq_active is False


def test_balance_is_clamped():
    s = Settings()
    assert s.set_balance(5.0) == 1.0
    assert s.set_balance(-5.0) == -1.0


def test_balance_left_attenuates_the_right_channel():
    s = Settings()
    s.set_balance(-0.5)
    graph = s.balance_graph()
    assert "c0=1.00*c0" in graph
    assert "c1=0.50*c1" in graph


def test_balance_right_attenuates_the_left_channel():
    s = Settings()
    s.set_balance(0.5)
    graph = s.balance_graph()
    assert "c0=0.50*c0" in graph
    assert "c1=1.00*c1" in graph


def test_gains_are_clamped_to_the_winamp_range():
    s = Settings()
    assert s.set_gain(0, 99) == GAIN_LIMIT
    assert s.set_gain(1, -99) == -GAIN_LIMIT
    # Out of range bands are ignored rather than raising.
    assert s.set_gain(99, 3) == 0.0
    assert len(s.gains) == len(BANDS)


def test_eq_graph_only_lists_bands_that_are_not_flat():
    s = Settings()
    s.set_gain(0, 6)
    s.set_gain(4, -3)
    graph = s.eq_graph()
    assert graph.count("equalizer=") == 2
    assert f"f={BANDS[0]}" in graph and "g=6" in graph
    assert f"f={BANDS[4]}" in graph and "g=-3" in graph
    assert s.eq_active is True


def test_reset_makes_the_eq_disappear_again():
    s = Settings()
    s.set_gain(2, 9)
    s.reset_eq()
    assert s.eq_graph() is None


def test_roundtrip_through_disk():
    s = Settings()
    s.set_balance(-0.3)
    s.set_gain(3, 7.5)
    s.save()

    restored = Settings.load()
    assert restored.balance == -0.3
    assert restored.gains[3] == 7.5
    assert restored.eq_graph() == s.eq_graph()


def test_missing_file_gives_neutral_settings():
    assert Settings.load().balance == 0.0


def test_a_junk_file_gives_neutral_settings(settings_file):
    settings_file.write_text('{"balance": "mucho", "gains": [1, 2]}', encoding="utf-8")
    s = Settings.load()
    assert s.balance == 0.0
    assert s.gains == [0.0] * len(BANDS)


def test_saved_values_are_clamped_on_load(settings_file):
    settings_file.write_text('{"balance": 9, "gains": [99]}', encoding="utf-8")
    s = Settings.load()
    assert s.balance == 1.0
    assert s.gains[0] == GAIN_LIMIT


# ------------------------------------------------------------------- presets


def test_a_preset_puts_its_curve_on_the_bands():
    from tidalamp.settings import PRESETS, Settings

    settings = Settings()
    settings.apply_preset("rock")

    assert settings.gains == [float(g) for g in dict(PRESETS)["rock"]]
    assert settings.preset == "rock"


def test_a_preset_written_past_the_limit_is_clamped_when_applied():
    """The catalogue reads as what each curve meant, not as what survived."""
    from tidalamp.settings import GAIN_LIMIT, Settings

    settings = Settings()
    for name, _gains in __import__("tidalamp.settings", fromlist=["x"]).PRESETS:
        settings.apply_preset(name)
        assert all(abs(gain) <= GAIN_LIMIT for gain in settings.gains), name


def test_moving_a_band_stops_it_being_that_preset():
    """Worked out from the gains, not remembered: a stored name would go on
    lying until something reset it."""
    from tidalamp.settings import MANUAL, Settings

    settings = Settings()
    settings.apply_preset("jazz")
    settings.set_gain(0, settings.gains[0] + 1)

    assert settings.preset == MANUAL


def test_flat_bands_are_the_flat_preset_and_not_manual():
    from tidalamp.settings import Settings

    assert Settings().preset == "flat"
