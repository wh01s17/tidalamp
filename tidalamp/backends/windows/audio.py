"""The audio output on Windows: what mpv says it is playing to.

There is no PipeWire graph to clamp and nothing to force. In **shared mode**,
the normal one, the Windows audio engine resamples everything to the
device's default format (Sound, Properties, Advanced), and nothing inside an
app can avoid it. In **exclusive mode** mpv takes the device and opens it at
the track's own rate: the same result the Linux backend gets by forcing
PipeWire's rate. That is the `exclusive` setting, which mpv applies itself
(`--audio-exclusive`), so this module only has to report.

It asks mpv, the one program that knows which device it opened and at what
rate. The player is handed over once with `use_player`. Everything the Linux
backend does to the audio stack answers with its neutral value here, which
its callers already treat as "nothing to do": no allowed rates, no rate to
force, no drop-in to write.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# The same record on every system: what an output is, as far as it will say.
from ..linux.audio import Sink

# Whether this backend manages the stack's rates. The settings window offers
# PipeWire's rows only where it does, and exclusive mode where it does not.
MANAGES_RATES = False

_player: Any = None


def use_player(player: Any) -> None:
    """The mpv to ask. Kept across its restarts: it is the same object."""
    global _player
    _player = player


def sink() -> Sink:
    """The device mpv plays to and the rate it opened it at."""
    player = _player
    if player is None:
        return Sink()
    device = player.get("audio-device") or ""
    params = player.get("audio-out-params")
    params = params if isinstance(params, dict) else {}
    listing = player.get("audio-device-list")
    description = ""
    for entry in listing if isinstance(listing, list) else []:
        if isinstance(entry, dict) and entry.get("name") == device:
            description = str(entry.get("description") or "")
            break
    try:
        rate = int(params.get("samplerate") or 0)
    except (TypeError, ValueError):
        rate = 0
    return Sink(
        name=str(device),
        description=description,
        rate=rate,
        sample_format=str(params.get("format") or ""),
    )


def streams_on(target: Sink) -> int:
    """Unknown: WASAPI does not say who else is playing."""
    return -1


def allowed_rates() -> tuple[int, ...]:
    """None to manage: the engine or the device decides."""
    return ()


def hardware_rates(sink_name: str = "") -> tuple[int, ...]:
    """Not read. The device's formats are in the registry, and reading them
    there is fragile; exclusive mode asks the device directly instead."""
    return ()


def rate_to_force(
    target: Sink,
    stream_rate: int,
    allowed: tuple[int, ...],
    hardware: tuple[int, ...],
    streams: int,
) -> int:
    """Never: there is no graph rate to force on Windows."""
    return 0


def force_rate(rate: int) -> bool:
    return False


def rates_configured() -> bool:
    return False


def clamped() -> bool:
    return False


def write_rates() -> Path:
    raise NotImplementedError("PipeWire rates do not exist on Windows")


def remove_rates() -> bool:
    raise NotImplementedError("PipeWire rates do not exist on Windows")


def restart() -> str:
    raise NotImplementedError("there is no PipeWire to restart on Windows")
