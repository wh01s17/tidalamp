"""Turn a TIDAL track into something mpv can open.

TIDAL hands back two shapes of manifest:

``BTS``
    A plain list of progressive URLs (HIGH / LOW, and often LOSSLESS). mpv
    plays the first URL directly.

``MPD``
    A segmented DASH manifest (typical for LOSSLESS / HI_RES_LOSSLESS).
    tidalapi already parses the segment templates for us, so we render the
    segments as a local HLS playlist and point mpv at that file.

Tracks whose manifest is encrypted are DRM-protected: mpv cannot decrypt them
and we say so instead of failing with a codec error.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import tidalapi

from .config import CACHE_DIR, ensure_dirs
from .net import with_retries

log = logging.getLogger("tidalamp.stream")


class StreamUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class Playable:
    """What we hand to mpv, plus the badges the Winamp display shows."""

    url: str
    quality: str
    sample_rate: int | None
    bit_depth: int | None
    codec: str | None
    # Which branch of the manifest we took: "BTS" (progressive URL) or
    # "MPD" (segmented DASH rendered to a local HLS playlist).
    manifest: str = "BTS"

    @property
    def khz(self) -> str:
        return f"{round((self.sample_rate or 44100) / 1000)}" if self.sample_rate else "44"

    @property
    def kbps(self) -> str:
        # Lossless has no fixed bitrate; show the bit depth instead, which is
        # what the classic display has room for anyway.
        if self.bit_depth:
            return f"{self.bit_depth}bit"
        return {"HIGH": "320", "LOW": "96"}.get(self.quality, "---")


def _write_hls(playlist: str, track_id: int) -> str:
    ensure_dirs()
    path = Path(tempfile.mkstemp(dir=CACHE_DIR, prefix=f"track-{track_id}-", suffix=".m3u8")[1])
    path.write_text(playlist, encoding="utf-8")
    return str(path)


def resolve(track: tidalapi.Track) -> Playable:
    """Resolve ``track`` to a playable URL or local playlist path."""
    try:
        stream = with_retries(track.get_stream)
    except Exception as exc:  # tidalapi raises a grab-bag of API errors here
        raise StreamUnavailable(f"TIDAL no devolvió stream para «{track.name}»: {exc}") from exc

    manifest = stream.get_stream_manifest()

    if manifest.is_encrypted:
        raise StreamUnavailable(
            f"«{track.name}» viene con DRM (Widevine); mpv no puede reproducirla. "
            "Prueba con TIDALAMP_QUALITY=HIGH."
        )

    if manifest.is_mpd:
        kind = "MPD"
        url = _write_hls(manifest.get_hls(), track.id)
    else:
        kind = "BTS"
        urls = manifest.get_urls()
        if not urls:
            raise StreamUnavailable(f"Manifiesto vacío para «{track.name}»")
        url = urls[0]

    log.debug(
        "«%s» calidad=%s manifiesto=%s códec=%s %s/%sbit",
        track.name,
        stream.audio_quality,
        kind,
        manifest.get_codecs(),
        stream.sample_rate,
        stream.bit_depth,
    )

    return Playable(
        url=url,
        quality=stream.audio_quality,
        sample_rate=stream.sample_rate,
        bit_depth=stream.bit_depth,
        codec=manifest.get_codecs(),
        manifest=kind,
    )


def cleanup_playlists() -> None:
    """Drop the temporary HLS playlists written during this run."""
    if not CACHE_DIR.exists():
        return
    for stale in CACHE_DIR.glob("track-*.m3u8"):
        stale.unlink(missing_ok=True)
