"""stream.resolve against fixed manifests, so both branches are exercised
without hitting TIDAL."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FakeTrack

from tidalamp import stream
from tidalamp.stream import StreamUnavailable, cleanup_playlists, resolve


class FakeManifest:
    def __init__(self, *, is_mpd=False, is_encrypted=False, urls=None, hls=""):
        self.is_mpd = is_mpd
        self.is_encrypted = is_encrypted
        self._urls = urls if urls is not None else ["https://cdn/audio.flac"]
        self._hls = hls

    def get_urls(self):
        return self._urls

    def get_hls(self):
        return self._hls

    def get_codecs(self):
        return "flac"


class FakeStream:
    def __init__(self, manifest, quality="LOSSLESS"):
        self._manifest = manifest
        self.audio_quality = quality
        self.sample_rate = 44100
        self.bit_depth = 16

    def get_stream_manifest(self):
        return self._manifest


def track_with(manifest, quality="LOSSLESS"):
    track = FakeTrack(1, name="Schism")
    track.get_stream = lambda: FakeStream(manifest, quality)
    return track


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(stream, "ensure_dirs", lambda: None)
    return tmp_path


def test_bts_manifest_uses_the_first_url():
    playable = resolve(
        track_with(FakeManifest(urls=["https://cdn/a", "https://cdn/b"]), "HIGH")
    )
    assert playable.url == "https://cdn/a"
    assert playable.manifest == "BTS"
    assert playable.khz == "44"


def test_a_lossy_stream_shows_its_bitrate_and_not_a_bit_depth():
    """TIDAL reports 16 bits for 320 kbps AAC too: that is what it decodes to."""
    playable = resolve(track_with(FakeManifest(urls=["https://cdn/a"]), "HIGH"))
    assert playable.bit_depth == 16
    assert playable.kbps == "320"

    low = resolve(track_with(FakeManifest(urls=["https://cdn/a"]), "LOW"))
    assert low.kbps == "96"


def test_a_lossless_stream_shows_its_bit_depth():
    playable = resolve(track_with(FakeManifest(urls=["https://cdn/a"]), "LOSSLESS"))
    assert playable.kbps == "16bit"


def test_a_downgrade_is_visible_instead_of_silent(monkeypatch):
    """Measured against TIDAL: the device-flow client gets HIGH for LOSSLESS."""
    monkeypatch.setattr(stream.config, "DEFAULT_QUALITY", "HI_RES_LOSSLESS")
    playable = resolve(track_with(FakeManifest(urls=["https://cdn/a"]), "HIGH"))

    assert playable.requested == "HI_RES_LOSSLESS"
    assert playable.quality == "HIGH"
    assert playable.downgraded is True


def test_getting_what_we_asked_for_is_not_a_downgrade(monkeypatch):
    monkeypatch.setattr(stream.config, "DEFAULT_QUALITY", "HIGH")
    playable = resolve(track_with(FakeManifest(urls=["https://cdn/a"]), "HIGH"))
    assert playable.downgraded is False


def test_mpd_manifest_is_written_as_a_local_playlist(cache_dir):
    playlist = "#EXTM3U\n#EXT-X-VERSION:3\nseg1.mp4\n"
    playable = resolve(track_with(FakeManifest(is_mpd=True, hls=playlist)))
    assert playable.manifest == "MPD"
    assert playable.url.startswith(str(cache_dir))
    assert playable.url.endswith(".m3u8")
    with open(playable.url, encoding="utf-8") as handle:
        assert handle.read() == playlist


def test_encrypted_manifest_explains_the_drm():
    with pytest.raises(StreamUnavailable, match="DRM"):
        resolve(track_with(FakeManifest(is_encrypted=True)))


def test_empty_manifest_is_reported():
    with pytest.raises(StreamUnavailable, match="Manifiesto vacío"):
        resolve(track_with(FakeManifest(urls=[])))


def test_api_failure_is_wrapped():
    track = FakeTrack(1)
    track.get_stream = lambda: (_ for _ in ()).throw(RuntimeError("500"))
    with pytest.raises(StreamUnavailable, match="no devolvió stream"):
        resolve(track)


def test_cleanup_removes_only_our_playlists(cache_dir, monkeypatch):
    resolve(track_with(FakeManifest(is_mpd=True, hls="x")))
    keep = cache_dir / "mpv.sock"
    keep.write_text("")
    cleanup_playlists()
    assert list(cache_dir.glob("*.m3u8")) == []
    assert keep.exists()


def test_manifest_branch_is_logged(caplog):
    with caplog.at_level("DEBUG", logger="tidalamp.stream"):
        resolve(track_with(FakeManifest(is_mpd=True, hls="x")))
    assert "manifiesto=MPD" in caplog.text


def _config_with_env(monkeypatch, value: str | None):
    """Load a private copy of config.py, so reloading cannot leak elsewhere."""
    import importlib.util
    from pathlib import Path

    from tidalamp import config

    if value is None:
        monkeypatch.delenv("TIDALAMP_QUALITY", raising=False)
    else:
        monkeypatch.setenv("TIDALAMP_QUALITY", value)
    spec = importlib.util.spec_from_file_location("config_probe", Path(config.__file__))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_default_quality_is_the_one_that_actually_yields_lossless(monkeypatch):
    """LOSSLESS is answered with HIGH by the device-flow client; HI_RES is not."""
    assert _config_with_env(monkeypatch, None).DEFAULT_QUALITY == "HI_RES_LOSSLESS"


def test_the_quality_can_still_be_forced_from_the_environment(monkeypatch):
    assert _config_with_env(monkeypatch, "HIGH").DEFAULT_QUALITY == "HIGH"


# --------------------------------------------------- the fMP4 playlist rewrite

TIDALAPI_HLS = (
    "#EXTM3U\n"
    "#EXT-X-TARGETDURATION:266\n"
    "#EXT-X-VERSION:3\n"
    "#EXTINF:3.968,\n"
    "https://cdn/track/0.mp4?token=x\n"
    "#EXTINF:3.968,\n"
    "https://cdn/track/1.mp4?token=x\n"
    "#EXTINF:1.234,\n"
    "https://cdn/track/2.mp4?token=x\n"
    "#EXT-X-ENDLIST\n"
)


def test_the_init_segment_becomes_a_map_instead_of_audio():
    """Segment 0 is ftyp+moov; listed as audio, ffmpeg cannot read any header."""
    fixed = stream._to_fmp4_hls(TIDALAPI_HLS).splitlines()

    assert '#EXT-X-MAP:URI="https://cdn/track/0.mp4?token=x"' in fixed
    # fMP4 in HLS needs version 7; tidalapi declares 3.
    assert "#EXT-X-VERSION:7" in fixed
    assert "#EXT-X-VERSION:3" not in fixed
    # It must appear only in the map, never as a media segment of its own.
    assert "https://cdn/track/0.mp4?token=x" not in fixed
    assert sum("track/0.mp4" in line for line in fixed) == 1
    assert "#EXT-X-TARGETDURATION:266" in fixed
    assert fixed[-1] == "#EXT-X-ENDLIST"


def test_the_media_segments_keep_their_order_and_durations():
    fixed = stream._to_fmp4_hls(TIDALAPI_HLS).splitlines()
    pairs = [
        (fixed[i], fixed[i + 1])
        for i, line in enumerate(fixed)
        if line.startswith("#EXTINF")
    ]
    assert pairs == [
        ("#EXTINF:3.968,", "https://cdn/track/1.mp4?token=x"),
        ("#EXTINF:1.234,", "https://cdn/track/2.mp4?token=x"),
    ]


def test_a_playlist_that_already_has_a_map_is_left_alone():
    already = (
        '#EXTM3U\n#EXT-X-MAP:URI="https://cdn/0.mp4"\n#EXTINF:1,\nhttps://cdn/1.mp4\n'
    )
    assert stream._to_fmp4_hls(already) == already


def test_a_playlist_too_short_to_split_is_left_alone():
    single = "#EXTM3U\n#EXTINF:1,\nhttps://cdn/0.mp4\n"
    assert stream._to_fmp4_hls(single) == single


def test_the_mpd_branch_writes_the_rewritten_playlist(cache_dir):
    playable = resolve(track_with(FakeManifest(is_mpd=True, hls=TIDALAPI_HLS)))
    written = Path(playable.url).read_text(encoding="utf-8")
    assert "#EXT-X-MAP:" in written
