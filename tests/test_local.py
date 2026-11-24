"""«Música local»: scanning folders, reading hi-res headers, and the levels."""

from __future__ import annotations

import os
import struct
import wave
from pathlib import Path

import pytest
from mutagen.flac import FLAC

from tidalamp import config, levels, library, local, stream
from tidalamp.queue import LOCAL, Entry
from tidalamp.screens.tracks import LOCAL_TRACK_ACTIONS, actions_for


def _streaminfo(rate: int, depth: int, channels: int = 2, samples: int = 0) -> bytes:
    """FLAC's STREAMINFO block: enough of a FLAC for mutagen to read it."""
    packed = (rate << 44) | ((channels - 1) << 41) | ((depth - 1) << 36) | samples
    return (
        struct.pack(">HH", 4096, 4096)
        + (0).to_bytes(3, "big")
        + (0).to_bytes(3, "big")
        + packed.to_bytes(8, "big")
        + bytes(16)
    )


def make_flac(path: Path, *, rate=96000, depth=24, seconds=0, mtime=None, **tags) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = _streaminfo(rate, depth, samples=rate * seconds)
    # The last-block flag on the only block, then no frames: a header only.
    path.write_bytes(b"fLaC" + bytes([0x80]) + len(info).to_bytes(3, "big") + info)
    if tags:
        audio = FLAC(path)
        for key, value in tags.items():
            audio[key] = str(value)
        audio.save()
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def make_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(44100)
        out.writeframes(bytes(4 * 441))
    return path


def test_a_flac_is_read_with_its_tags_its_rate_and_its_depth(tmp_path):
    make_flac(
        tmp_path / "Tool" / "Lateralus" / "01.flac",
        seconds=3,
        title="The Grudge",
        artist="TOOL",
        album="Lateralus",
        date="2001-05-15",
        tracknumber="1/13",
    )
    (track,) = local.scan([tmp_path])
    assert (track.title, track.artist, track.album) == ("The Grudge", "TOOL", "Lateralus")
    assert (track.year, track.track_num, track.duration) == (2001, 1, 3)
    assert (track.sample_rate, track.bit_depth) == (96000, 24)
    assert track.quality == "FLAC 24/96"
    assert track.hires and track.id < 0


def test_a_file_without_tags_is_named_after_itself_and_its_folder(tmp_path):
    make_wav(tmp_path / "Demos" / "toma 3.wav")
    (track,) = local.scan([tmp_path])
    assert (track.title, track.album, track.codec) == ("toma 3", "Demos", "WAV")
    assert track.quality == "WAV 16/44.1"
    assert not track.hires


def test_what_is_not_audio_and_what_is_hidden_is_left_out(tmp_path):
    make_flac(tmp_path / "a.flac")
    (tmp_path / "notas.txt").write_text("x")
    make_flac(tmp_path / ".oculta" / "b.flac")
    assert [Path(t.path).name for t in local.scan([tmp_path])] == ["a.flac"]


def test_the_second_scan_reads_only_what_changed(tmp_path, monkeypatch):
    make_flac(tmp_path / "a.flac", title="A")
    local.scan([tmp_path])

    def unwanted(*args, **kwargs):
        raise AssertionError("read again")

    monkeypatch.setattr(local, "read", unwanted)
    assert [t.title for t in local.scan([tmp_path])] == ["A"]


def test_no_folder_is_said_as_such(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_FOLDERS", ())
    with pytest.raises(local.LocalUnavailable, match="configuración"):
        local.scan()
    with pytest.raises(local.LocalUnavailable):
        local.scan([tmp_path / "no-existe"])


def test_records_group_their_tracks_in_order_and_find_their_cover(tmp_path):
    record = tmp_path / "Lateralus"
    make_flac(record / "b.flac", album="Lateralus", artist="TOOL", tracknumber="2")
    make_flac(record / "a.flac", album="Lateralus", artist="TOOL", tracknumber="1")
    (record / "cover.jpg").write_bytes(b"\xff\xd8")
    (album,) = local.albums(local.scan([tmp_path]))
    assert [t.track_num for t in album.tracks] == [1, 2]
    assert album.art_url == (record / "cover.jpg").as_uri()
    assert album.quality == "FLAC 24/96"


def test_the_section_opens_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_FOLDERS", (str(tmp_path),))
    make_flac(tmp_path / "old.flac", title="Vieja", album="X", mtime=1_000_000)
    make_flac(tmp_path / "new.flac", title="Nueva", album="Y", mtime=2_000_000)

    section = next(row for row in library.root(FakeSession()) if row.key == "local")
    albums, artists, tracks, _folders = section.loader()
    assert "2 pistas · 2 hi-res" in tracks.detail

    for row in (albums, artists, tracks):
        order = levels.chosen(row)
        assert order is not None and order.by == "date" and order.descending
    _key, load = tracks.sort(levels.chosen(tracks))
    assert [row.entry.title for row in load()] == ["Nueva", "Vieja"]
    _key, load = tracks.sort(levels.Order("date"))
    assert [row.entry.title for row in load()] == ["Vieja", "Nueva"]
    _key, load = albums.sort(levels.Order("name"))
    assert [row.caption for row in load()] == ["X", "Y"]


def test_the_folders_row_shows_the_disk_as_it_is(tmp_path, monkeypatch):
    """Subfolders first, then files, each by name; only folders with audio;
    `m` on a folder plays everything under it."""
    monkeypatch.setattr(config, "LOCAL_FOLDERS", (str(tmp_path),))
    make_flac(tmp_path / "Tool" / "Lateralus" / "02.flac", title="Eon Blue")
    make_flac(tmp_path / "Tool" / "Lateralus" / "01.flac", title="The Grudge")
    make_flac(tmp_path / "Tool" / "Aenima" / "01.flac", title="Stinkfist")
    make_flac(tmp_path / "suelta.flac", title="Suelta")
    (tmp_path / "escaneos").mkdir()
    (tmp_path / "escaneos" / "libreto.jpg").write_bytes(b"x")

    section = next(row for row in library.root(FakeSession()) if row.key == "local")
    folders = next(row for row in section.loader() if row.key == "local:folders")
    (root,) = folders.loader()
    assert root.detail == "4 pistas"

    top = root.loader()
    assert [row.label for row in top] == ["Tool/", "Suelta"]
    tool = top[0].loader()
    assert [row.label for row in tool] == ["Aenima/", "Lateralus/"]
    assert [row.entry.title for row in tool[1].loader()] == ["The Grudge", "Eon Blue"]
    assert [row.entry.title for row in top[0].tracks()] == [
        "Stinkfist",
        "The Grudge",
        "Eon Blue",
    ]


def test_a_local_row_plays_its_file_at_its_own_rate(tmp_path):
    path = make_flac(tmp_path / "a.flac", rate=192000, depth=24, title="A")
    entry = Entry.from_local(local.read(path))
    playable = stream.playable_for(entry, session=None)
    assert playable.url == str(path)
    assert (playable.sample_rate, playable.bit_depth) == (192000, 24)
    assert (playable.codec, playable.manifest, playable.khz) == ("FLAC", "LOCAL", "192")
    assert actions_for(entry) == LOCAL_TRACK_ACTIONS

    path.unlink()
    with pytest.raises(stream.StreamUnavailable):
        stream.playable_for(entry, session=None)


def test_a_local_row_survives_a_restart_of_the_queue(tmp_path):
    entry = Entry.from_local(local.read(make_flac(tmp_path / "a.flac", title="A")))
    back = Entry.from_dict(entry.to_dict())
    assert back.source == LOCAL and back.url == entry.url and back.is_local
    assert not back.is_tidal


def test_the_folders_are_written_as_a_list_and_read_back():
    config.set_option("local_folders", ["~/Música", "/mnt/nas/flac"])
    assert config.LOCAL_FOLDERS == ("~/Música", "/mnt/nas/flac")
    assert local.folders()[0] == Path.home() / "Música"


def test_the_environment_lists_folders_like_path(monkeypatch):
    monkeypatch.setenv("TIDALAMP_LOCAL_FOLDERS", os.pathsep.join(["/a", "/b", "/a"]))
    assert config.local_folders() == ("/a", "/b")


class FakeSession:
    """Only what `library.root` touches before a level is opened."""

    class user:  # noqa: N801
        class favorites:  # noqa: N801
            get_tracks_count = get_albums_count = get_artists_count = None
