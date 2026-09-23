"""The audio stack under mpv: what the sink is, and whether it can do hi-res.

A facade (see `tidalamp.backends`): the implementation is PipeWire/PulseAudio
on Linux, in `tidalamp.backends.linux.audio`.
"""

from __future__ import annotations

from .backends.linux.audio import (
    Sink,
    allowed_rates,
    clamped,
    force_rate,
    hardware_rates,
    rate_to_force,
    rates_configured,
    remove_rates,
    restart,
    sink,
    streams_on,
    write_rates,
)

__all__ = [
    "Sink",
    "allowed_rates",
    "clamped",
    "force_rate",
    "hardware_rates",
    "rate_to_force",
    "rates_configured",
    "remove_rates",
    "restart",
    "sink",
    "streams_on",
    "write_rates",
]
