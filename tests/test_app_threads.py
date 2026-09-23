"""call_from_thread for a thread worker that finishes after the app has: the
call is dropped instead of raising in the thread, running against widgets
that are gone, or waiting forever on a loop that stopped."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from app_helpers import FakeMpv, isolate_runtime

from tidalamp import audio
from tidalamp.app import TidalAmp

# Taken before any test can patch it: isolate_runtime switches it off.
SINK_WORKER = TidalAmp._refresh_sink_worker


def _from_thread(application: TidalAmp, callback, *args) -> dict:
    """Call ``callback`` through the app from a thread of its own; what came back."""
    out: dict = {}

    def run() -> None:
        try:
            out["result"] = application.call_from_thread(callback, *args)
        except BaseException as error:
            out["error"] = error

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=5)
    out["hung"] = thread.is_alive()
    return out


def test_a_running_app_runs_the_callback_and_hands_back_its_result(monkeypatch):
    isolate_runtime(monkeypatch)
    seen: dict = {}

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            seen.update(
                await asyncio.to_thread(_from_thread, application, lambda x: x * 2, 21)
            )

    asyncio.run(scenario())
    assert seen == {"result": 42, "hung": False}


def test_a_running_app_still_raises_what_the_callback_raises(monkeypatch):
    isolate_runtime(monkeypatch)
    seen: dict = {}

    def broken() -> None:
        raise ValueError("a real bug")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            seen.update(await asyncio.to_thread(_from_thread, application, broken))

    asyncio.run(scenario())
    assert isinstance(seen["error"], ValueError)


def test_a_call_after_the_app_closed_is_dropped(monkeypatch):
    isolate_runtime(monkeypatch)
    ran: list[bool] = []
    seen: dict = {}

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
        # The loop is still running, as it is while asyncio.run() waits on the
        # worker threads; the app on it is not.
        seen.update(
            await asyncio.to_thread(_from_thread, application, lambda: ran.append(True))
        )

    asyncio.run(scenario())
    assert seen == {"result": None, "hung": False}
    assert ran == []


def test_a_loop_that_stopped_before_the_callback_does_not_hold_the_thread():
    application = TidalAmp(object(), FakeMpv())
    stopped = asyncio.new_event_loop()
    # As the app sees it at the worst moment: still marked running, its loop
    # already stopped and never going to run what is handed to it.
    application._loop = stopped
    application._running = True
    ran: list[bool] = []
    try:
        started = time.monotonic()
        seen = _from_thread(application, lambda: ran.append(True))
        elapsed = time.monotonic() - started
    finally:
        application._running = False
        stopped.close()
    assert seen == {"result": None, "hung": False}
    assert ran == []
    assert elapsed < 1


def test_the_apps_own_thread_is_still_refused(monkeypatch):
    isolate_runtime(monkeypatch)
    seen: list[BaseException] = []

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            with pytest.raises(RuntimeError) as caught:
                application.call_from_thread(lambda: None)
            seen.append(caught.value)

    asyncio.run(scenario())
    assert len(seen) == 1


def test_the_sink_worker_finishing_after_the_app_touches_nothing(monkeypatch):
    """The race isolate_runtime used to dodge for every app test, made certain:
    the app closes while the audio worker is halfway through reading the sink,
    past its last look at `is_cancelled`, and the reading brings a new rate,
    which is what makes the worker call back."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_refresh_sink_worker", SINK_WORKER)
    reading = threading.Event()
    closed = threading.Event()
    readings = iter([48000, 96000])

    def sink() -> audio.Sink:
        rate = next(readings, 96000)
        if rate == 96000:
            reading.set()
            closed.wait(5)
        return audio.Sink(name="a", rate=rate)

    monkeypatch.setattr(audio, "sink", sink)
    landed: list[tuple[int, bool]] = []
    set_sink = TidalAmp._set_sink

    def spy(self, sink, stream_rate=0):
        landed.append((sink.rate, self.is_running))
        set_sink(self, sink, stream_rate)

    monkeypatch.setattr(TidalAmp, "_set_sink", spy)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert await asyncio.to_thread(reading.wait, 5)
        closed.set()
        # What asyncio.run() does next: wait for the worker threads.
        await asyncio.sleep(0.5)

    asyncio.run(scenario())
    assert landed == [(48000, True)]
