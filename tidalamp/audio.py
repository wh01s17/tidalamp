"""The audio stack under mpv: what the sink is, and whether it can do hi-res.

tidalamp asks TIDAL for 24/96 and hands mpv a FLAC that really is 24/96, and
then PipeWire resamples it to whatever single rate its graph is clamped to.
The badge says HI_RES_LOSSLESS and it is telling the truth about the stream;
the DAC still receives 48 kHz. Nothing in the player can see that, so this
module goes and looks.

Everything here shells out to tools that may not be installed and to a daemon
that may not be running. Every function answers with what it found rather than
raising, because none of it is on the path that plays music.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import _xdg
from .i18n import _

log = logging.getLogger("tidalamp.audio")

# PipeWire reads every file in this directory on top of its own defaults, so a
# drop-in adds a setting without touching a file the distribution owns.
CONF_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "pipewire/pipewire.conf.d"
RATES_FILE = CONF_DIR / "10-tidalamp-rates.conf"

# The rates worth allowing: the two families (44.1 and 48 kHz) doubled up to
# what USB DACs commonly reach. PipeWire only switches to one a device claims
# to support, so listing a rate no hardware has is harmless.
RATES = (44100, 48000, 88200, 96000, 176400, 192000, 352800, 384000)

SERVICES = ("pipewire", "pipewire-pulse", "wireplumber")

_TIMEOUT = 5


def _run(command: list[str], timeout: int = _TIMEOUT) -> str | None:
    """Stdout, or None when the tool is missing, fails or hangs."""
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("%s no se pudo ejecutar: %s", command[0], exc)
        return None
    if done.returncode != 0:
        log.debug("%s salió con %s: %s", command[0], done.returncode, done.stderr.strip())
        return None
    return done.stdout


@dataclass(frozen=True)
class Sink:
    """The output PipeWire is sending audio to, as far as it will say."""

    name: str = ""
    description: str = ""
    rate: int = 0
    sample_format: str = ""

    @property
    def known(self) -> bool:
        return bool(self.name)

    @property
    def bluetooth(self) -> bool:
        """Bluetooth cannot carry lossless: worth saying before hi-res is asked for."""
        return self.name.startswith("bluez_")


def sink() -> Sink:
    """The default sink and the rate it is running at right now."""
    name = (_run(["pactl", "get-default-sink"]) or "").strip()
    if not name:
        return Sink()
    listing = _run(["pactl", "list", "sinks"]) or ""
    description, rate, fmt = "", 0, ""
    for block in listing.split("\nSink #"):
        if f"Name: {name}" not in block:
            continue
        found = re.search(r"^\s*Description:\s*(.+)$", block, re.MULTILINE)
        description = found.group(1).strip() if found else ""
        spec = re.search(
            r"^\s*Sample Specification:\s*(\S+)\s+\S+\s+(\d+)Hz", block, re.MULTILINE
        )
        if spec:
            fmt, rate = spec.group(1), int(spec.group(2))
        break
    return Sink(name=name, description=description, rate=rate, sample_format=fmt)


def allowed_rates() -> tuple[int, ...]:
    """The rates PipeWire's graph may switch to. Empty when it will not say."""
    output = _run(["pw-metadata", "-n", "settings"])
    if output is None:
        return ()
    found = re.search(r"key:'clock\.allowed-rates'\s+value:'\[([^\]]*)\]'", output)
    if not found:
        return ()
    return tuple(int(value) for value in re.findall(r"\d+", found.group(1)))


def hardware_rates(sink_name: str = "") -> tuple[int, ...]:
    """What the card itself accepts, read from ALSA rather than from PipeWire.

    A USB DAC's rates live in `/proc/asound/cardN/stream0`. Matching the card
    to the sink by name is best-effort: the sink name carries the USB product
    string, which is what ALSA names the card directory after.
    """
    cards = Path("/proc/asound")
    if not cards.is_dir():
        return ()
    for stream in sorted(cards.glob("card*/stream*")):
        try:
            text = stream.read_text(errors="replace")
        except OSError:
            continue
        first = text.split("\n", 1)[0]
        if sink_name and not _same_device(first, sink_name):
            continue
        rates: set[int] = set()
        for line in text.splitlines():
            if line.strip().startswith("Rates:"):
                rates.update(int(value) for value in re.findall(r"\d+", line))
        if rates:
            return tuple(sorted(rates))
    return ()


def _same_device(alsa_line: str, sink_name: str) -> bool:
    """Do an ALSA stream header and a PipeWire sink name describe one device?

    Both carry the USB product string, spelled differently: ALSA keeps the
    spaces and commas, PipeWire turns them into underscores. Comparing the
    letters and digits alone is crude and gets it right.
    """
    alsa = re.sub(r"[^a-z0-9]", "", alsa_line.split(" at ")[0].lower())
    sink = re.sub(r"[^a-z0-9]", "", sink_name.lower())
    return bool(alsa) and (alsa in sink or sink in alsa)


def rates_configured() -> bool:
    """Whether our drop-in is in place."""
    return RATES_FILE.is_file()


def clamped() -> bool:
    """Whether the graph is stuck on a single rate, which is the whole problem."""
    return len(allowed_rates()) == 1


def write_rates() -> Path:
    """Drop in the allowed-rates setting. Returns the file it wrote."""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    listed = " ".join(str(rate) for rate in RATES)
    RATES_FILE.write_text(
        "# Written by tidalamp. Delete this file to undo it.\n"
        "#\n"
        "# Without it PipeWire runs its graph at one rate and resamples\n"
        "# everything into it, so a 24/96 stream reaches the DAC at 48 kHz.\n"
        "# PipeWire only switches rate while the device is idle: if another\n"
        "# application is holding the sink open, the change waits for it.\n"
        "context.properties = {\n"
        "    default.clock.rate          = 48000\n"
        f"    default.clock.allowed-rates = [ {listed} ]\n"
        "}\n",
        encoding="utf-8",
    )
    return RATES_FILE


def remove_rates() -> bool:
    """Take the drop-in away again. True if there was one."""
    if not RATES_FILE.is_file():
        return False
    RATES_FILE.unlink()
    return True


def restart() -> str:
    """Restart the user's PipeWire services. Returns a line for the status bar.

    This cuts audio for a moment and mpv loses its output; the caller stops
    playback first. It is a `systemctl --user` restart and nothing more — no
    privileges, no system units.
    """
    if os.environ.get("TIDALAMP_NO_RESTART"):
        # For the tests, and for anyone who would rather do it themselves.
        return _("reinicio de PipeWire desactivado por el entorno")
    output = _run(["systemctl", "--user", "restart", *SERVICES], timeout=30)
    if output is None:
        return _(
            "no se pudo reiniciar PipeWire; hazlo tú: systemctl --user restart {services}"
        ).format(services=" ".join(SERVICES))
    return _("PipeWire reiniciado")
