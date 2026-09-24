"""The audio output on Windows: what mpv says it is playing to.

There is no PipeWire graph to clamp and nothing to force. In **shared mode**,
the normal one, the Windows audio engine resamples everything to the
device's default format (Sound, Properties, Advanced), and nothing inside an
app can avoid it. In **exclusive mode** mpv takes the device and opens it at
the track's own rate: the same result the Linux backend gets by forcing
PipeWire's rate. That is the `exclusive` setting, which mpv applies itself
(`--audio-exclusive`), so this module only has to report.

The device is the `audio_device` setting: `auto`, mpv's own default, follows
the one Windows has as its default output, and anything else is one of the
names mpv lists (`wasapi/{guid}`). With exclusive mode the device matters
more than ever, since tidalamp takes all of it, so what `auto` stands for is
asked of Windows (`system_default`) rather than left as mpv's «Autoselect
device».

It asks mpv, the one program that knows which device it opened and at what
rate. The player is handed over once with `use_player`. Everything the Linux
backend does to the audio stack answers with its neutral value here, which
its callers already treat as "nothing to do": no allowed rates, no rate to
force, no drop-in to write.
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from typing import Any

# The same record on every system: what an output is, as far as it will say.
from ..linux.audio import Sink

# Whether this backend manages the stack's rates. The settings window offers
# PipeWire's rows only where it does, and exclusive mode where it does not.
MANAGES_RATES = False

log = logging.getLogger("tidalamp.audio")

_player: Any = None

# The COM names for the list of audio endpoints (mmdeviceapi.h).
_CLSID_ENUMERATOR = uuid.UUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
_IID_ENUMERATOR = uuid.UUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
_RENDER = 0  # eRender: outputs, not microphones
_MULTIMEDIA = 1  # eMultimedia: the role music plays under
_ACTIVE = 0x1  # DEVICE_STATE_ACTIVE: plugged in and enabled
_CLSCTX_ALL = 0x17


def use_player(player: Any) -> None:
    """The mpv to ask. Kept across its restarts: it is the same object."""
    global _player
    _player = player


def sink() -> Sink:
    """The device mpv plays to and the rate it opened it at.

    Under `auto`, the device is the system's default, by its own name: mpv's
    «Autoselect device» did not say which of the outputs was playing.
    """
    player = _player
    if player is None:
        return Sink()
    device = player.get("audio-device") or ""
    params = player.get("audio-out-params")
    params = params if isinstance(params, dict) else {}
    names = dict(_listed(player))
    shown = system_default() if device == "auto" else device
    description = names.get(shown, "")
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


def devices() -> list[tuple[str, str]]:
    """The outputs worth choosing, as mpv names and describes them.

    Only WASAPI's: exclusive mode is a WASAPI thing, and the other outputs
    mpv lists (openal, say) are another way to reach the same devices.
    """
    if _player is None:
        return []
    return [
        (name, description)
        for name, description in _listed(_player)
        if name.startswith("wasapi/")
    ]


def system_default() -> str:
    """The output Windows plays music to, by mpv's name for it; "" unknown."""
    found = _endpoints()
    return f"wasapi/{found[0]}" if found is not None and found[0] else ""


def connected(name: str) -> bool:
    """Whether ``name`` is an output that can be opened right now.

    A speaker switched off is still in the settings, and mpv asked for it
    opens nothing: no sound, and no error the user sees. Unknown counts as
    connected, so a failure to ask never takes the user's choice away.
    """
    found = _endpoints()
    if found is None or not name.startswith("wasapi/"):
        return True
    return name.removeprefix("wasapi/").lower() in found[1]


def _listed(player: Any) -> list[tuple[str, str]]:
    listing = player.get("audio-device-list")
    return [
        (str(entry.get("name") or ""), str(entry.get("description") or ""))
        for entry in (listing if isinstance(listing, list) else [])
        if isinstance(entry, dict)
    ]


def _endpoints() -> tuple[str, list[str]] | None:
    """The default output and every active one, as the `{guid}` mpv puts
    after ``wasapi/``. None when Windows could not be asked.

    Straight from the Core Audio API over ctypes, which is what mpv itself
    reads: an endpoint id is ``{0.0.0.00000000}.{guid}``, and the guid is the
    part mpv names the device by.
    """
    if sys.platform != "win32":
        return None
    import ctypes

    ole32 = ctypes.windll.ole32
    initialised = ole32.CoInitializeEx(None, 0) in (0, 1)  # S_OK, S_FALSE
    enumerator = ctypes.c_void_p()
    try:
        failed = ole32.CoCreateInstance(
            ctypes.create_string_buffer(_CLSID_ENUMERATOR.bytes_le, 16),
            None,
            _CLSCTX_ALL,
            ctypes.create_string_buffer(_IID_ENUMERATOR.bytes_le, 16),
            ctypes.byref(enumerator),
        )
        if failed or not enumerator:
            log.warning("no se pudo preguntar a Windows por las salidas (%#x)", failed)
            return None
        default = ""
        device = ctypes.c_void_p()
        # IMMDeviceEnumerator::GetDefaultAudioEndpoint, fourth in its table.
        if not _call(enumerator, 4, _RENDER, _MULTIMEDIA, ctypes.byref(device)):
            default = _endpoint_guid(device)
            _release(device)
        active: list[str] = []
        collection = ctypes.c_void_p()
        # EnumAudioEndpoints, third.
        if not _call(enumerator, 3, _RENDER, _ACTIVE, ctypes.byref(collection)):
            count = ctypes.c_uint()
            _call(collection, 3, ctypes.byref(count))  # IMMDeviceCollection::GetCount
            for index in range(count.value):
                item = ctypes.c_void_p()
                if not _call(collection, 4, index, ctypes.byref(item)):  # ::Item
                    active.append(_endpoint_guid(item))
                    _release(item)
            _release(collection)
        return default, [guid for guid in active if guid]
    except OSError as exc:
        log.warning("no se pudo preguntar a Windows por las salidas: %s", exc)
        return None
    finally:
        if enumerator:
            _release(enumerator)
        if initialised:
            ole32.CoUninitialize()


def _call(interface: Any, slot: int, *args: Any) -> int:
    """Call method ``slot`` of a COM interface's table; its HRESULT.

    Integers go as 32-bit values, which is what every method called here
    takes; anything else (a `byref`) as a pointer.
    """
    if sys.platform != "win32":
        raise OSError("COM only exists on Windows")
    import ctypes

    table = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    kinds = [ctypes.c_void_p] + [
        ctypes.c_uint if isinstance(arg, int) else ctypes.c_void_p for arg in args
    ]
    method = ctypes.WINFUNCTYPE(ctypes.c_long, *kinds)(table.contents[slot])
    return int(method(interface, *args))


def _release(interface: Any) -> None:
    _call(interface, 2)  # IUnknown::Release


def _endpoint_guid(device: Any) -> str:
    """The `{guid}` of an IMMDevice's id, lower-cased; "" if it has none."""
    if sys.platform != "win32":
        return ""
    import ctypes

    text = ctypes.c_void_p()
    if _call(device, 5, ctypes.byref(text)) or not text.value:  # IMMDevice::GetId
        return ""
    try:
        whole = ctypes.wstring_at(text.value)
    finally:
        free = ctypes.windll.ole32.CoTaskMemFree
        free.argtypes = [ctypes.c_void_p]
        free(text)
    _head, _dot, guid = whole.rpartition(".")
    return guid.lower() if guid.startswith("{") else ""


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
