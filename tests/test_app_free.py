"""Playing a row that never went through TIDAL.

The whole point of «Lofi sin copyright» is that the audio is reachable with
no subscription and no session, so what these tests watch for is the absence
of TIDAL: no token refresh, no `session.track()`, no lyrics request. Everything
after that — mpv, the queue, the prefetch, the cover — is the same code the
rest of the player runs, which is why there is no second playback path.
"""

from __future__ import annotations

import asyncio

import pytest
from app_helpers import FakeMpv, isolate_runtime, settle
from test_app_gapless import playing_first

from tidalamp import app as app_module
from tidalamp import stream
from tidalamp.app import TidalAmp
from tidalamp.freemusic import Track
from tidalamp.lyrics import LyricsUnavailable
from tidalamp.queue import Entry


def free_entry(n: int = 1) -> Entry:
    return Entry.from_free(
        Track(
            url=f"https://archive.org/download/x/{n}.mp3",
            title=f"pista {n}",
            artist="Lofi Lion",
            album="Tame The Beast",
            licence="CC BY",
            duration=174,
            codec="MP3",
            art_url="https://archive.org/services/img/x",
        )
    )


class Exploding:
    """A session that fails the test if anything asks it for anything."""

    def __getattr__(self, name):
        raise AssertionError(f"«Lofi sin copyright» no debe pedirle «{name}» a TIDAL")


# ------------------------------------------------------------------- resolve


def test_a_free_row_resolves_to_its_own_url_without_a_session():
    playable = stream.playable_for(free_entry(), Exploding())
    assert playable.url == "https://archive.org/download/x/1.mp3"
    assert playable.manifest == "FREE"
    assert playable.licence == "CC BY"
    assert playable.codec == "MP3"


def test_a_free_row_with_no_url_says_so_rather_than_handing_mpv_nothing():
    entry = free_entry()
    entry.url = ""
    with pytest.raises(stream.StreamUnavailable):
        stream.playable_for(entry, Exploding())


def test_a_free_playable_claims_no_tidal_tier_and_is_never_a_downgrade():
    """`downgraded` is about TIDAL sending less than we asked for. A free
    track was never asked of TIDAL, so the badge must not imply it was."""
    playable = stream.direct(free_entry())
    assert playable.quality == ""
    assert not playable.downgraded


def test_the_badge_shows_the_licence_and_leaves_out_what_it_cannot_know():
    """The Archive publishes neither the sample rate nor the bit depth, and
    «— · — kHz» spends eleven cells saying nothing."""
    playable = stream.direct(free_entry())
    assert playable.kbps == "—"
    assert playable.khz == "—"
    assert playable.licence == "CC BY"


# ---------------------------------------------------------------- the player


def test_playing_a_free_row_never_refreshes_the_tidal_token(monkeypatch):
    """A token refresh per track, for music that is not TIDAL's, would be a
    request bought with nothing."""
    isolate_runtime(monkeypatch)
    refreshed: list[object] = []
    monkeypatch.setattr(
        app_module, "ensure_fresh", lambda session: refreshed.append(session) or False
    )
    started: list[tuple[Entry, object]] = []
    monkeypatch.setattr(
        TidalAmp,
        "_start",
        lambda self, entry, playable: started.append((entry, playable)),
    )

    async def scenario() -> None:
        application = TidalAmp(Exploding(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entry = free_entry()
            application._resolving = entry
            application._resolve_worker(entry)
            await settle(pilot, lambda: bool(started))

    asyncio.run(scenario())
    assert refreshed == []
    assert started[0][0].url == "https://archive.org/download/x/1.mp3"
    assert started[0][1].licence == "CC BY"


def test_prefetching_a_free_row_queues_its_url_and_skips_the_lyrics(monkeypatch):
    """The cover still arrives ahead of the sound; the lyrics cannot, because
    TIDAL is the only provider and it has never heard of this track."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, e: None)
    fetched: list[str] = []
    asked_for_lyrics: list[object] = []
    monkeypatch.setattr(app_module, "ensure_fresh", lambda session: False)
    monkeypatch.setattr(
        app_module.artwork, "fetch", lambda url: fetched.append(url) or b""
    )
    monkeypatch.setattr(
        app_module,
        "load_lyrics",
        lambda track: asked_for_lyrics.append(track) or "letra",
    )

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(Exploding(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.art_protocol = app_module.artwork.Protocol.BLOCKS
            entries = [
                Entry(id=1, title="Schism", artist="TOOL", duration=200),
                free_entry(2),
            ]
            # The first row is a TIDAL one, started by hand the way the
            # gapless tests do it, so only the prefetch is under test.
            await playing_first(application, mpv, pilot, entries)

            application._prefetching = entries[1]
            application._prefetch_worker(entries[1], True)
            await settle(pilot, lambda: bool(fetched))

    asyncio.run(scenario())
    assert fetched == ["https://archive.org/services/img/x"]
    assert asked_for_lyrics == [], "TIDAL no sabe nada de una pista que no es suya"


def test_the_lyrics_of_a_free_row_say_why_there_are_none(monkeypatch):
    """Every lyrics view — `y`, the split pane, the full-screen panel — goes
    through `_lyrics_for`, so the guard belongs there and nowhere else."""
    isolate_runtime(monkeypatch)

    async def scenario() -> str:
        application = TidalAmp(Exploding(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            with pytest.raises(LyricsUnavailable) as caught:
                application._lyrics_for(free_entry())
            return str(caught.value)

    assert "TIDAL" in asyncio.run(scenario())


def test_mpris_publishes_the_real_url_of_a_free_row():
    """`tidal://track/-1234567` names nothing: the id is a hash, and no TIDAL
    client could open it. The audio has a URL of its own, so it is the one
    that goes out."""
    entry = free_entry()
    assert app_module._entry_metadata(entry)["url"] == entry.url
    tidal = Entry(id=42, title="Schism", artist="TOOL")
    assert app_module._entry_metadata(tidal)["url"] == "tidal://track/42"


def test_a_free_row_still_gets_a_valid_mpris_track_path():
    """The path is built from `uid`, a positive counter, not from the id.
    A negative number in a D-Bus object path would be rejected outright."""
    path = app_module._track_path(free_entry())
    assert path.startswith("/org/mpris/MediaPlayer2/tidalamp/track/")
    assert "-" not in path.rsplit("/", 1)[-1]
