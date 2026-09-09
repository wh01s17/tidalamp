"""Reading the audio stack: what the sink is, and whether it can do hi-res.

Every function here shells out, so the tests hand it fixed output instead of
whatever the machine running them happens to have plugged in.
"""

from __future__ import annotations

import pytest

from tidalamp import audio

PACTL_SINKS = """Sink #3367
\tState: RUNNING
\tName: alsa_output.usb-GuangZhou_FIIO_Electronics_Co._Ltd_FIIO_BTR15-00.analog-stereo
\tDescription: FIIO BTR15 Analog Stereo
\tSample Specification: s32le 2ch 48000Hz

Sink #57
\tState: SUSPENDED
\tName: alsa_output.pci-0000_00_1f.3.analog-stereo
\tDescription: Altavoces
\tSample Specification: s32le 2ch 44100Hz
"""

BTR15 = "alsa_output.usb-GuangZhou_FIIO_Electronics_Co._Ltd_FIIO_BTR15-00.analog-stereo"

STREAM0 = """GuangZhou FIIO Electronics Co.,Ltd FIIO BTR15 at usb-0000:00:14 : USB Audio

Playback:
  Interface 1
    Altset 1
    Format: S32_LE
    Rates: 44100, 48000, 88200, 96000, 176400, 192000, 352800, 384000
    Bits: 32
"""


@pytest.fixture
def pactl(monkeypatch):
    """Answer `pactl` with the two-sink listing above, BTR15 as the default."""

    def fake_run(command, timeout=5):
        if command[:2] == ["pactl", "get-default-sink"]:
            return BTR15 + "\n"
        return PACTL_SINKS

    monkeypatch.setattr(audio, "_run", fake_run)


# --------------------------------------------------------------------- sink


def test_the_default_sink_is_read_with_its_rate(pactl):
    found = audio.sink()

    assert found.known
    assert found.description == "FIIO BTR15 Analog Stereo"
    assert found.rate == 48000
    assert found.sample_format == "s32le"
    assert found.bluetooth is False


def test_no_pactl_is_an_answer_not_a_crash(monkeypatch):
    monkeypatch.setattr(audio, "_run", lambda command, timeout=5: None)
    found = audio.sink()
    assert found.known is False
    assert found.rate == 0


def test_a_bluetooth_sink_says_so():
    assert audio.Sink(name="bluez_output.B8_D5_0B.1").bluetooth is True
    assert audio.Sink(name=BTR15).bluetooth is False


# ---------------------------------------------------------------- the graph


def test_allowed_rates_are_read_from_the_metadata(monkeypatch):
    output = (
        "update: id:0 key:'clock.rate' value:'48000' type:''\n"
        "update: id:0 key:'clock.allowed-rates' value:'[ 44100 48000 96000 ]' type:''\n"
    )
    monkeypatch.setattr(audio, "_run", lambda command, timeout=5: output)
    assert audio.allowed_rates() == (44100, 48000, 96000)
    assert audio.clamped() is False


def test_a_single_allowed_rate_is_the_whole_problem(monkeypatch):
    output = "update: id:0 key:'clock.allowed-rates' value:'[ 48000 ]' type:''\n"
    monkeypatch.setattr(audio, "_run", lambda command, timeout=5: output)
    assert audio.allowed_rates() == (48000,)
    assert audio.clamped() is True


def test_metadata_we_cannot_read_reports_nothing_rather_than_guessing(monkeypatch):
    monkeypatch.setattr(audio, "_run", lambda command, timeout=5: None)
    assert audio.allowed_rates() == ()
    # And "not clamped", because an empty answer is not evidence of a problem.
    assert audio.clamped() is False


# ------------------------------------------------------------- the hardware


def test_the_cards_rates_are_read_from_alsa(monkeypatch, tmp_path):
    stream = tmp_path / "card2" / "stream0"
    stream.parent.mkdir(parents=True)
    stream.write_text(STREAM0)
    monkeypatch.setattr(audio, "Path", lambda _path: tmp_path)

    assert audio.hardware_rates(BTR15) == (
        44100,
        48000,
        88200,
        96000,
        176400,
        192000,
        352800,
        384000,
    )


def test_a_card_that_is_not_the_sink_is_skipped(monkeypatch, tmp_path):
    stream = tmp_path / "card2" / "stream0"
    stream.parent.mkdir(parents=True)
    stream.write_text(STREAM0)
    monkeypatch.setattr(audio, "Path", lambda _path: tmp_path)

    assert audio.hardware_rates("alsa_output.pci-0000_00_1f.3.analog-stereo") == ()


def test_a_machine_without_proc_asound_answers_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "Path", lambda _path: tmp_path / "nada")
    assert audio.hardware_rates() == ()


@pytest.mark.parametrize(
    "alsa, sink, same",
    [
        ("GuangZhou FIIO Electronics Co.,Ltd FIIO BTR15 at usb-1", BTR15, True),
        ("HDA Intel PCH at 0xdc528000", BTR15, False),
        ("", BTR15, False),
    ],
)
def test_alsa_and_pipewire_names_are_matched_on_their_letters(alsa, sink, same):
    """One spells the product with spaces and commas, the other with
    underscores; only the letters and digits are common to both."""
    assert audio._same_device(alsa, sink) is same


# ------------------------------------------------------------ the drop-in


def test_the_drop_in_is_written_and_taken_away_again(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "CONF_DIR", tmp_path / "pipewire.conf.d")
    monkeypatch.setattr(audio, "RATES_FILE", tmp_path / "pipewire.conf.d" / "r.conf")

    assert audio.rates_configured() is False
    written = audio.write_rates()

    assert audio.rates_configured() is True
    text = written.read_text()
    assert "allowed-rates" in text
    for rate in (44100, 96000, 192000):
        assert str(rate) in text
    # It says how to undo it without this program.
    assert "Delete this file" in text

    assert audio.remove_rates() is True
    assert audio.rates_configured() is False
    assert audio.remove_rates() is False


def test_the_restart_can_be_switched_off_by_the_environment(monkeypatch):
    monkeypatch.setenv("TIDALAMP_NO_RESTART", "1")
    called: list[list[str]] = []
    monkeypatch.setattr(audio, "_run", lambda command, timeout=5: called.append(command))

    message = audio.restart()

    assert called == [], "no debe tocar los servicios"
    assert "PipeWire" in message


def test_a_restart_that_fails_says_what_to_run_by_hand(monkeypatch):
    monkeypatch.delenv("TIDALAMP_NO_RESTART", raising=False)
    monkeypatch.setattr(audio, "_run", lambda command, timeout=5: None)

    message = audio.restart()

    assert "systemctl --user restart" in message
    for service in audio.SERVICES:
        assert service in message
