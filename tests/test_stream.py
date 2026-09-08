"""stream.resolve against fixed manifests, so both branches are exercised
without hitting TIDAL."""

from __future__ import annotations

import pytest

from tidalamp import stream
from tidalamp.stream import StreamUnavailable, cleanup_playlists, resolve

from conftest import FakeTrack


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
    playable = resolve(track_with(FakeManifest(urls=["https://cdn/a", "https://cdn/b"]), "HIGH"))
    assert playable.url == "https://cdn/a"
    assert playable.manifest == "BTS"
    assert playable.kbps == "16bit"
    assert playable.khz == "44"


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
