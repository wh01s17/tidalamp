"""The audio stack under mpv: what the output is, and whether it can do hi-res.

A facade (see `tidalamp.backends`): PipeWire/PulseAudio on Linux, in
`tidalamp.backends.linux.audio`; on Windows, what mpv reports about the WASAPI
device it opened, in `tidalamp.backends.windows.audio`.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .backends.windows.audio import (
        MANAGES_RATES,
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
        use_player,
        write_rates,
    )
else:
    from .backends.linux.audio import (
        MANAGES_RATES,
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
        use_player,
        write_rates,
    )

__all__ = [
    "MANAGES_RATES",
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
    "use_player",
    "write_rates",
]
