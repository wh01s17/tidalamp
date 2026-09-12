"""The player around mpv: the next track queued ahead so it starts with no
gap, an mpv that stops answering or dies, and the normalised volume."""

from __future__ import annotations

import asyncio

from app_helpers import FakeMpv, isolate_runtime, settle

from tidalamp import app as app_module
from tidalamp import artwork
from tidalamp.app import TidalAmp
from tidalamp.queue import Entry, Repeat
from tidalamp.widgets import Glide, Marquee


class Playable:
    kbps = "16-bit"
    khz = "44.1"
    quality = "LOSSLESS"
    codec = "flac"

    def __init__(self, url: str, gain: float | None = None, peak: float | None = None):
        self.url = url
        self.track_gain = gain
        self.track_peak = peak
        self.album_gain = None
        self.album_peak = None


def three() -> list[Entry]:
    return [
        Entry(id=i, title=title, artist="TOOL", duration=200)
        for i, title in enumerate(("Schism", "Parabol", "Parabola"), start=1)
    ]


def isolate(monkeypatch) -> tuple[list[Entry], list[Entry]]:
    """No resolve ever reaches TIDAL: both workers only say what they were
    asked for, and the test answers for them."""
    isolate_runtime(monkeypatch)
    resolves: list[Entry] = []
    prefetches: list[Entry] = []
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, e: resolves.append(e))
    monkeypatch.setattr(
        TidalAmp, "_prefetch_worker", lambda self, e, *rest: prefetches.append(e)
    )
    return resolves, prefetches


async def playing_first(application, mpv, pilot, entries) -> None:
    application.queue.append(entries)
    application._sync_queue()
    application._play_index(0)
    application._start(entries[0], Playable("https://cdn/1"))
    mpv.idle = False
    mpv.duration = 200.0
    mpv.position = 10.0
    await pilot.pause(0.3)


def test_the_next_track_is_queued_ahead_and_starts_without_resolving(monkeypatch):
    resolves, prefetches = isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            await playing_first(application, mpv, pilot, entries)
            assert prefetches == [], "no con tanta antelación: la URL caduca"

            mpv.position = 190.0
            await settle(pilot, lambda: bool(prefetches))
            assert prefetches == [entries[1]]
            application._prefetched(entries[1], Playable("https://cdn/2"))
            assert mpv.queued == [("https://cdn/2", 0.0)]

            resolves.clear()
            # The track ends and mpv goes on to the queued one by itself,
            # without ever going idle in between.
            mpv.playlist_pos = 1
            await settle(pilot, lambda: application.queue.playing == 1)

            assert resolves == [], "la siguiente no se volvió a pedir"
            assert mpv.loaded == "https://cdn/1", "ni se volvió a cargar"
            assert mpv.playlist_pos == 0, "lo que suena vuelve a ser la primera"
            assert application.query_one(Marquee).text == "2. Parabol"
            assert application._playable.url == "https://cdn/2"
            assert application.status == "reproduciendo TOOL - Parabol"

    asyncio.run(scenario())


def test_a_queue_changed_meanwhile_resolves_the_right_track(monkeypatch):
    _resolves, prefetches = isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            await playing_first(application, mpv, pilot, entries)
            mpv.position = 190.0
            await settle(pilot, lambda: bool(prefetches))
            application._prefetched(entries[1], Playable("https://cdn/2"))
            assert mpv.queued

            # The prepared track leaves the queue before its turn.
            application.queue.remove(1)
            application._sync_queue()
            assert mpv.queued == [], "lo preparado para otra pista no suena"
            assert application._prepared is None

            # The tick prepares the one that is next now.
            await settle(pilot, lambda: len(prefetches) == 2)
            assert prefetches[-1] is entries[2]

    asyncio.run(scenario())


def test_a_result_for_a_track_no_longer_next_is_dropped(monkeypatch):
    """The prefetch was on its way when repeat changed which track is next."""
    _resolves, prefetches = isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            await playing_first(application, mpv, pilot, entries)
            mpv.position = 190.0
            await settle(pilot, lambda: bool(prefetches))

            while application.queue.repeat is not Repeat.TRACK:
                application.action_repeat()
            application._prefetched(entries[1], Playable("https://cdn/2"))

            assert mpv.queued == []
            assert application._prepared is None

    asyncio.run(scenario())


def test_stop_and_a_jump_elsewhere_take_the_queued_track_out(monkeypatch):
    _resolves, prefetches = isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            await playing_first(application, mpv, pilot, entries)
            application._prepared = None
            application._prefetching = entries[1]
            application._prefetched(entries[1], Playable("https://cdn/2"))
            assert mpv.queued

            # A jump: the old track plays on while the new one resolves, and
            # must not run into the queued one if it ends meanwhile.
            application._play_index(2)
            assert mpv.queued == [] and application._prepared is None

            application._prefetching = entries[1]
            application.action_stop()
            application._prefetched(entries[1], Playable("https://cdn/2"))
            assert mpv.queued == [], "detenido no prepara nada"
            del prefetches[:]

    asyncio.run(scenario())


def test_a_prepared_track_that_waited_too_long_is_resolved_again(monkeypatch):
    """Paused near the end for longer than a TIDAL URL lives."""
    _resolves, prefetches = isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            await playing_first(application, mpv, pilot, entries)
            mpv.position = 190.0
            await settle(pilot, lambda: bool(prefetches))
            application._prefetched(entries[1], Playable("https://cdn/2"))
            stale = application._prepared
            application._prepared = stale._replace(
                at=stale.at - TidalAmp.PREPARED_TTL - 1
            )

            await settle(pilot, lambda: len(prefetches) == 2)
            assert prefetches == [entries[1], entries[1]]
            assert mpv.queued == [], "la caducada salió de mpv"

    asyncio.run(scenario())


# ----------------------------------------------------------- a stuck mpv


def test_an_mpv_that_stops_answering_says_so_and_is_asked_off_the_ui(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            mpv.stalled = True
            await settle(pilot, lambda: mpv.probes > 0)
            assert application.status == "mpv no contesta; esperando a que vuelva…"
            assert mpv.restarts == 0, "atascado un momento no es muerto"

            # A stall clears the way it does in `Mpv`: a probe gets an answer.
            def answers_again(self) -> bool:
                self.probes += 1
                self.stalled = False
                return True

            monkeypatch.setattr(FakeMpv, "probe", answers_again)
            await settle(pilot, lambda: application.status == "mpv vuelve a contestar")
            assert not mpv.stalled

    asyncio.run(scenario())


def test_a_dead_mpv_is_restarted_in_a_worker_and_the_track_reloaded(monkeypatch):
    isolate_runtime(monkeypatch)
    started: list[int] = []

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.queue.append(three())
            application._sync_queue()
            application.queue.playing = 1
            monkeypatch.setattr(
                TidalAmp, "_play_index", lambda self, i: started.append(i)
            )

            mpv.alive = False
            await settle(pilot, lambda: bool(started))
            assert mpv.restarts == 1
            assert started == [1]
            assert application._recovering is False

    asyncio.run(scenario())


def test_a_restart_that_fails_waits_before_trying_again(monkeypatch):
    isolate_runtime(monkeypatch)

    def broken(self) -> None:
        self.restarts += 1
        raise OSError("sin mpv")

    monkeypatch.setattr(FakeMpv, "restart", broken)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            mpv.alive = False
            await settle(pilot, lambda: mpv.restarts > 0 and not application._recovering)
            await pilot.pause(0.6)
            assert mpv.restarts == 1, "no cuatro veces por segundo"
            assert "no se pudo reiniciar" in application.status

    asyncio.run(scenario())


# ------------------------------------------------------------- ReplayGain


def test_the_gain_reaching_mpv_follows_the_mode_and_goes_when_off(monkeypatch):
    _resolves, prefetches = isolate(monkeypatch)
    monkeypatch.setattr(app_module.config, "REPLAYGAIN", "track")

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            application.queue.append(entries)
            application._sync_queue()
            application._play_index(0)
            application._start(entries[0], Playable("https://cdn/1", -7.5, 0.9))
            assert mpv.gain == -7.5

            # A quiet track is raised only as far as its peak allows.
            application._play_index(1)
            application._start(entries[1], Playable("https://cdn/2", 6.0, 0.8))
            assert mpv.gain == 1.94

            # And the queued one carries its own, from its first sample.
            mpv.idle, mpv.duration, mpv.position = False, 200.0, 190.0
            await settle(pilot, lambda: bool(prefetches))
            application._prefetched(entries[2], Playable("https://cdn/3", -3.0, 1.0))
            assert mpv.queued == [("https://cdn/3", -3.0)]

            monkeypatch.setattr(app_module.config, "REPLAYGAIN", "off")
            application._setting_changed("replaygain")
            assert mpv.gain == 0.0, "apagado, la pista vuelve a como vino"
            assert mpv.queued == [], "la preparada llevaba la ganancia vieja"
            assert application.status == "volumen normalizado: off"

    asyncio.run(scenario())


def test_the_badge_line_says_the_gain_being_applied(monkeypatch):
    """Normalised, a track can sound quieter than the one before with
    nothing on screen saying why. It is also how the maintainer reads the
    values TIDAL really sends."""
    isolate(monkeypatch)
    monkeypatch.setattr(app_module.config, "REPLAYGAIN", "track")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            application.queue.append(entries)
            application._sync_queue()
            badges = application.query_one("#badges", Glide)

            application._play_index(0)
            application._start(entries[0], Playable("https://cdn/1", -7.5, 0.9))
            assert "RG -7.5 dB" in str(badges.content)

            application._play_index(1)
            application._start(entries[1], Playable("https://cdn/2", 6.0, 0.8))
            assert "RG +1.9 dB" in str(badges.content), "la aplicada, con el tope"

            application._play_index(2)
            application._start(entries[2], Playable("https://cdn/3"))
            assert "RG —" in str(badges.content), "sin datos no es 0 dB"

            monkeypatch.setattr(app_module.config, "REPLAYGAIN", "off")
            application._setting_changed("replaygain")
            assert "RG" not in str(badges.content)

    asyncio.run(scenario())


def test_the_next_cover_and_lyrics_are_fetched_with_its_stream(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, e: None)
    fetched: list[str] = []
    lyrics_for: list[str] = []
    monkeypatch.setattr(app_module, "ensure_fresh", lambda session: False)
    monkeypatch.setattr(Entry, "resolve", lambda self, session: f"track-{self.id}")
    monkeypatch.setattr(
        app_module, "resolve", lambda track: Playable(f"https://cdn/{track}")
    )
    monkeypatch.setattr(
        app_module.artwork, "fetch", lambda url: fetched.append(url) or b""
    )
    monkeypatch.setattr(
        app_module, "load_lyrics", lambda track: lyrics_for.append(track) or "letra"
    )

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.art_protocol = artwork.Protocol.BLOCKS
            entries = [
                Entry(id=1, title="Schism", artist="TOOL", duration=200),
                Entry(
                    id=2,
                    title="Parabol",
                    artist="TOOL",
                    duration=200,
                    art_url="https://img/2.jpg",
                ),
            ]
            await playing_first(application, mpv, pilot, entries)

            application._prefetching = entries[1]
            application._prefetch_worker(entries[1], True)
            await settle(pilot, lambda: bool(lyrics_for))

            assert mpv.queued == [("https://cdn/track-2", 0.0)], "el audio, primero"
            assert fetched == ["https://img/2.jpg"]
            assert lyrics_for == ["track-2"]
            assert application._lyrics_cache[2] == "letra"

            # Without anything on screen following the lyrics, not asked for.
            application._warm(entries[1], "track-2", False)
            del application._lyrics_cache[2]
            application._warm(entries[1], "track-2", False)
            assert lyrics_for == ["track-2"]

    asyncio.run(scenario())


def test_a_restarted_mpv_picks_the_track_up_where_it_was(monkeypatch):
    """It went back to 0:00: the maintainer killed mpv at the middle of a
    song and heard it start over."""
    resolves, _prefetches = isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            await playing_first(application, mpv, pilot, entries)
            mpv.position = 95.0
            await pilot.pause(0.3)
            resolves.clear()

            mpv.alive = False
            await settle(pilot, lambda: bool(resolves))
            assert resolves == [entries[0]], "la misma pista, otra vez"
            application._start(entries[0], Playable("https://cdn/1b"))
            assert mpv.loaded == "https://cdn/1b"
            assert mpv.started_at == 95.0

            # Only that reload: playing the track again starts at the top.
            application._play_index(0)
            application._start(entries[0], Playable("https://cdn/1c"))
            assert mpv.started_at == 0.0

    asyncio.run(scenario())


def test_next_pressed_during_the_reload_starts_the_next_at_the_top(monkeypatch):
    resolves, _prefetches = isolate(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entries = three()
            await playing_first(application, mpv, pilot, entries)
            mpv.position = 95.0
            await pilot.pause(0.3)
            resolves.clear()

            mpv.alive = False
            await settle(pilot, lambda: bool(resolves))
            application._play_index(1)
            application._start(entries[1], Playable("https://cdn/2"))
            assert mpv.started_at == 0.0

    asyncio.run(scenario())
