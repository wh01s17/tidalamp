"""Turn a TIDAL track into something mpv can open.

TIDAL hands back two shapes of manifest:

``BTS``
    A plain list of progressive URLs (HIGH / LOW, and often LOSSLESS). mpv
    plays the first URL directly.

``MPD``
    A segmented DASH manifest (typical for LOSSLESS / HI_RES_LOSSLESS).
    tidalapi already parses the segment templates for us, so we render the
    segments as a local HLS playlist and point mpv at that file.

Asking for a quality is not the same as getting it. Measured against a real
account on 2026-09-08: with the device-flow client, TIDAL answers ``HIGH`` to
both ``LOSSLESS`` and ``HI_RES_LOSSLESS`` even on a subscription whose own
endpoint reports ``HI_RES`` as available. ``Playable.downgraded`` says so
rather than letting the display imply we got what we asked for.

Tracks whose manifest is encrypted are DRM-protected: mpv cannot decrypt them
and we say so instead of failing with a codec error.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import tidalapi

from .config import CACHE_DIR, DEFAULT_QUALITY, ensure_dirs
from .i18n import _
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
    # What we asked TIDAL for, which is not always what it sends.
    requested: str = ""

    @property
    def khz(self) -> str:
        return (
            f"{round((self.sample_rate or 44100) / 1000)}" if self.sample_rate else "44"
        )

    @property
    def kbps(self) -> str:
        """The bitrate for lossy streams, the bit depth for lossless ones.

        Quality decides, not ``bit_depth``: TIDAL reports 16 bits for a 320
        kbps AAC stream too — that is the depth it decodes to, not what was
        encoded — so trusting it printed "16bit" over lossy audio.
        """
        lossy = {"LOW": "96", "HIGH": "320"}
        if self.quality in lossy:
            return lossy[self.quality]
        if self.bit_depth:
            return f"{self.bit_depth}bit"
        return "---"

    @property
    def downgraded(self) -> bool:
        """True when TIDAL sent a lower quality than the one we asked for."""
        return bool(self.requested) and self.requested != self.quality


def _to_fmp4_hls(playlist: str) -> str:
    """Fix tidalapi's HLS so ffmpeg can actually open it.

    A DASH manifest's first segment is the initialisation segment: ``ftyp`` and
    ``moov``, the header that describes the track. The ones after it are
    ``moof``/``mdat`` — audio with no header of its own. tidalapi's
    ``get_hls()`` lists the init segment as if it were audio and never emits
    ``#EXT-X-MAP``, so ffmpeg opens each segment on its own, finds no ``trex``
    for the fragments, and gives up with "error reading header". Verified
    against a real hi-res track: 69 segments, segment 0 is ``ftyp+moov`` and
    the rest are ``moof+mdat``.

    So we hoist the first segment into ``#EXT-X-MAP`` and declare version 7,
    which is what fragmented MP4 in HLS requires. A playlist that already has
    a map is passed through untouched.
    """
    lines = playlist.splitlines()
    if any(line.startswith("#EXT-X-MAP") for line in lines):
        return playlist

    target = next(
        (line for line in lines if line.startswith("#EXT-X-TARGETDURATION")),
        "#EXT-X-TARGETDURATION:10",
    )
    # (duration, url) in order; tidalapi writes one #EXTINF per segment.
    segments: list[tuple[str, str]] = []
    duration = "#EXTINF:10.000,"
    for line in lines:
        if line.startswith("#EXTINF"):
            duration = line
        elif line and not line.startswith("#"):
            segments.append((duration, line))
    if len(segments) < 2:
        return playlist

    init = segments[0][1]
    out = ["#EXTM3U", "#EXT-X-VERSION:7", target, "#EXT-X-PLAYLIST-TYPE:VOD"]
    out.append(f'#EXT-X-MAP:URI="{init}"')
    for extinf, url in segments[1:]:
        out.append(extinf)
        out.append(url)
    out.append("#EXT-X-ENDLIST")
    return "\n".join(out) + "\n"


def _write_hls(playlist: str, track_id: int) -> str:
    ensure_dirs()
    path = Path(
        tempfile.mkstemp(dir=CACHE_DIR, prefix=f"track-{track_id}-", suffix=".m3u8")[1]
    )
    path.write_text(playlist, encoding="utf-8")
    return str(path)


def resolve(track: tidalapi.Track) -> Playable:
    """Resolve ``track`` to a playable URL or local playlist path."""
    try:
        stream = with_retries(track.get_stream)
    except Exception as exc:  # tidalapi raises a grab-bag of API errors here
        raise StreamUnavailable(
            _("TIDAL no devolvió stream para «{name}»: {error}").format(
                name=track.name, error=exc
            )
        ) from exc

    manifest = stream.get_stream_manifest()

    if manifest.is_encrypted:
        raise StreamUnavailable(
            _(
                "«{name}» viene con DRM (Widevine); mpv no puede reproducirla. "
                "Prueba con TIDALAMP_QUALITY=HIGH."
            ).format(name=track.name)
        )

    if manifest.is_mpd:
        kind = "MPD"
        url = _write_hls(_to_fmp4_hls(manifest.get_hls()), track.id)
    else:
        kind = "BTS"
        urls = manifest.get_urls()
        if not urls:
            raise StreamUnavailable(
                _("Manifiesto vacío para «{name}»").format(name=track.name)
            )
        url = urls[0]

    log.debug(
        "«%s» pedida=%s entregada=%s manifiesto=%s códec=%s %s/%sbit",
        track.name,
        DEFAULT_QUALITY,
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
        requested=DEFAULT_QUALITY,
    )


def cleanup_playlists() -> None:
    """Drop the temporary HLS playlists written during this run."""
    if not CACHE_DIR.exists():
        return
    for stale in CACHE_DIR.glob("track-*.m3u8"):
        stale.unlink(missing_ok=True)
