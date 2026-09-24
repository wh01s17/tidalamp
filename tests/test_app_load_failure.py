"""A URL mpv cannot open, told apart from a track that ended.

Both look the same from the player: mpv goes idle. Until this, they *were*
the same — a URL that answered 500 put «reproduciendo X» in the status line,
said nothing, and slid to the next track a second and a half later, so a run
of them raced through the queue in silence. Measured against the real
Internet Archive: five of thirty tracks answered 500 under load and every one
of them came back 206 on the next try, which is why a retry is worth more
here than a skip.
"""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime
from test_app_gapless import Playable, three

from tidalamp import app as app_module
from tidalamp.app import TidalAmp


def player(monkeypatch) -> tuple[TidalAmp, FakeMpv]:
    isolate_runtime(monkeypatch)
    # The resolve is not what is under test: every track here resolves fine
    # and it is mpv that cannot open what it was handed.
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)
    monkeypatch.setattr(app_module, "ensure_fresh", lambda session: False)
    mpv = FakeMpv()
    return TidalAmp(object(), mpv), mpv


async def loaded(application, mpv, pilot, entries, index: int = 0) -> None:
    """Start a track the way `_start` does, without asking mpv to succeed."""
    application.queue.append(entries)
    application._sync_queue()
    application.queue.playing = index
    application._start(entries[index], Playable(f"https://cdn/{index}"))
    mpv.idle = False
    await pilot.pause()


def test_a_track_that_never_sounded_is_tried_again(monkeypatch):
    """The failure this exists for is momentary: a CDN answering 500 under
    load, and the very same URL coming back a second later."""

    async def scenario() -> tuple[str, int]:
        application, mpv = player(monkeypatch)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await loaded(application, mpv, pilot, three())
            mpv.loaded = None

            # mpv gives up on the URL without a sample ever coming out.
            mpv.idle = True
            application._tick_slow()
            await pilot.pause()
            return str(application.status), application.queue.playing

    status, playing = asyncio.run(scenario())
    assert "reintentando" in status
    assert playing == 0, "reintentar es la misma pista, no la siguiente"


def test_the_retry_asks_for_the_same_url(monkeypatch):
    async def scenario() -> str | None:
        application, mpv = player(monkeypatch)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await loaded(application, mpv, pilot, three())
            mpv.loaded = None
            mpv.idle = True
            application._tick_slow()
            await pilot.pause()
            return mpv.loaded

    assert asyncio.run(scenario()) == "https://cdn/0"


def test_a_track_that_will_not_open_is_named_and_skipped(monkeypatch):
    """And named. Sliding on in silence is what made this look like tracks
    «not resolving» rather than tracks being dropped."""

    async def scenario() -> tuple[str, int]:
        application, mpv = player(monkeypatch)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await loaded(application, mpv, pilot, three())
            for _ in range(application.LOAD_RETRIES + 1):
                mpv.idle = True
                application._tick_slow()
                await pilot.pause()
                application._was_idle = False
            return str(application.status), application.queue.playing

    status, playing = asyncio.run(scenario())
    assert "no se pudo abrir" in status
    assert "Schism" in status, "la pista se nombra"
    assert playing == 1, "y se pasa a la siguiente"


def test_a_track_that_sounded_and_then_ended_is_not_a_failure(monkeypatch):
    """The ordinary end of a track: no retry, no message, just the next one.
    This is the behaviour everything else in the player is built on."""

    async def scenario() -> tuple[str, int, str | None]:
        application, mpv = player(monkeypatch)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await loaded(application, mpv, pilot, three())
            # It played.
            mpv.position, mpv.duration = 30.0, 200.0
            application._tick_slow()
            await pilot.pause()
            mpv.loaded = None
            # And then it ended.
            mpv.position, mpv.duration, mpv.idle = 0.0, 0.0, True
            application._tick_slow()
            await pilot.pause()
            return str(application.status), application.queue.playing, mpv.loaded

    status, playing, reloaded = asyncio.run(scenario())
    assert "reintentando" not in status
    assert "no se pudo abrir" not in status
    assert playing == 1
    assert reloaded is None, "una pista que acabó no se vuelve a cargar"


def test_every_new_track_is_judged_on_its_own(monkeypatch):
    """A track that failed twice must not hand its two strikes to the next."""

    async def scenario() -> int:
        application, mpv = player(monkeypatch)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            await loaded(application, mpv, pilot, entries)
            for _ in range(application.LOAD_RETRIES):
                mpv.idle = True
                application._tick_slow()
                await pilot.pause()
                application._was_idle = False
            assert application._retries == application.LOAD_RETRIES
            application._start(entries[1], Playable("https://cdn/1"))
            return application._retries

    assert asyncio.run(scenario()) == 0


def test_a_track_slid_into_with_no_gap_is_judged_on_its_own_too(monkeypatch):
    """It never goes through `_start`, which is why the counter is cleared in
    `_now_playing` and not there: a prepared track that will not open used to
    inherit «already heard» from the track before it and be skipped as if it
    had ended."""

    async def scenario() -> tuple[bool, int]:
        application, mpv = player(monkeypatch)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            await loaded(application, mpv, pilot, entries)
            mpv.position, mpv.duration = 30.0, 200.0
            application._tick_slow()
            await pilot.pause()
            assert application._opened, "la primera abrió"
            application._now_playing(entries[1], Playable("https://cdn/1"))
            return application._opened, application._retries

    heard, retries = asyncio.run(scenario())
    assert not heard
    assert retries == 0


def test_unplugging_the_chosen_device_goes_on_through_the_default(monkeypatch):
    """Unplugging a FiiO BTR15 mid-track skipped the whole queue: mpv ended
    the track («audio output initialization failed») and could open none
    after it. Now it moves to the system's default and picks the same track
    up where it was."""
    from tidalamp import audio

    async def scenario() -> tuple[FakeMpv, str, int]:
        application, mpv = player(monkeypatch)
        mpv.device = "wasapi/{fiio}"
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await loaded(application, mpv, pilot, three())
            mpv.position, mpv.duration = 42.0, 200.0
            application._tick_slow()
            await pilot.pause()
            mpv.loaded = None
            monkeypatch.setattr(audio, "connected", lambda name: False)
            mpv.position, mpv.duration, mpv.idle = 0.0, 0.0, True
            application._tick_slow()
            await pilot.pause()
            return mpv, str(application.status), application.queue.playing

    mpv, status, playing = asyncio.run(scenario())
    assert mpv.devices == ["auto"]
    assert (mpv.loaded, mpv.started_at) == ("https://cdn/0", 42.0)
    assert playing == 0, "la misma pista, no la siguiente"
    assert "se desconectó el dispositivo" in status


def test_on_auto_a_track_that_ends_is_just_the_end_of_it(monkeypatch):
    """mpv follows the default output by itself: nothing to move."""
    from tidalamp import audio

    async def scenario() -> tuple[FakeMpv, int]:
        application, mpv = player(monkeypatch)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await loaded(application, mpv, pilot, three())
            mpv.position, mpv.duration = 30.0, 200.0
            application._tick_slow()
            await pilot.pause()
            monkeypatch.setattr(audio, "connected", lambda name: False)
            mpv.position, mpv.duration, mpv.idle = 0.0, 0.0, True
            application._tick_slow()
            await pilot.pause()
            return mpv, application.queue.playing

    mpv, playing = asyncio.run(scenario())
    assert mpv.devices == []
    assert playing == 1
