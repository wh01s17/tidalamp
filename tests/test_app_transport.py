"""The transport row, the keys, the sliders and the status line."""

from __future__ import annotations

import asyncio

import pytest
from app_helpers import (
    LABEL_ROW,
    FakeMpv,
    a_deftones_track,
    isolate_runtime,
    open_menu_on_b,
    settle,
    track_rows,
    transport,
)

from tidalamp import app as app_module
from tidalamp import artwork
from tidalamp import audio as audio_module
from tidalamp.app import TidalAmp
from tidalamp.player import Mpv
from tidalamp.queue import Entry
from tidalamp.screens import (
    TRACK_ACTIONS,
    TrackActionsScreen,
)
from tidalamp.settings import Settings
from tidalamp.widgets import (
    Glide,
    Marquee,
    SeekBar,
    Slider,
    Spinner,
)


def test_the_transport_buttons_are_clickable_without_changing_keyboard_controls(
    monkeypatch,
):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            start, end, _action = next(
                hit for hit in application._transport_hits if hit[2] == "shuffle"
            )
            clicked = await pilot.click(
                "#transport-play", offset=((start + end) // 2, LABEL_ROW)
            )
            await pilot.pause()

            assert clicked is True
            assert application.queue.shuffle is True
            assert "⇄●" in transport(application)

    asyncio.run(scenario())


def test_the_transport_runs_z_x_c_v_across_the_keyboard(monkeypatch):
    """Four adjacent keys in the order the buttons sit on screen. Winamp's
    fifth (`b`) went with the separate pause button, and came back for the
    speed window: never a second pause."""
    isolate_runtime(monkeypatch)
    keys = app_module.DEFAULT_KEYS

    faces = [keys[action].split(",")[0] for action in ("prev", "play", "stop", "next")]
    assert faces == list("zxcv")
    assert {
        binding.action for binding in TidalAmp.BINDINGS if "b" in binding.key.split(",")
    } == {"speed"}

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 26)) as pilot:
            await pilot.pause()
            drawn = transport(application)
            for key, glyph in (("z", "◀◀"), ("x", "▶"), ("c", "■"), ("v", "▶▶")):
                assert f"{key} {glyph}" in drawn

    asyncio.run(scenario())


def test_the_buttons_show_the_rebound_key_not_the_shipped_one(monkeypatch):
    """A button with the wrong letter on it is worse than one with none."""
    isolate_runtime(monkeypatch)
    monkeypatch.setitem(app_module.config.KEYS, "stop", "k")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 26)) as pilot:
            await pilot.pause()
            drawn = transport(application)
            assert "k ■" in drawn
            assert "c ■" not in drawn

    asyncio.run(scenario())


def test_play_and_pause_are_one_button_showing_what_it_will_do(monkeypatch):
    """There used to be «x ▶» and «c ‖» side by side, and only one of them
    ever made sense at a given moment."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 30)) as pilot:
            await pilot.pause()
            # Stopped: the button offers to play, and there is no second one.
            drawn = transport(application)
            assert "x ▶" in drawn
            assert drawn.count("‖") == 0

            application.queue.replace(
                [Entry(id=1, title="t", artist="a", duration=9)], start=0
            )
            mpv.idle = False
            await pilot.pause(0.3)
            drawn = transport(application)
            assert "x ‖" in drawn
            assert drawn.count("▶") == 2, "los dos del ▶▶ de «siguiente», y ninguno más"

            mpv.paused = True
            await pilot.pause(0.3)
            assert "x ▶" in transport(application)

    asyncio.run(scenario())


def test_a_track_ending_on_its_own_still_advances(monkeypatch):
    """The guard must not cost the auto-advance it sits next to."""
    isolate_runtime(monkeypatch)
    started: list[int] = []
    monkeypatch.setattr(TidalAmp, "_play_index", lambda self, i: started.append(i))

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 26)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=i, title=f"t{i}", artist="a", duration=9) for i in range(3)],
                start=0,
            )
            application._sync_queue()
            mpv.idle = False
            await pilot.pause(0.3)
            started.clear()

            # mpv falls idle by itself: the song finished.
            mpv.idle = True
            await settle(pilot, lambda: bool(started))
            assert started == [1]

    asyncio.run(scenario())


def test_there_is_no_second_key_that_pauses(monkeypatch):
    """«c» used to pause as well as «x», which after merging the two buttons
    was just a second shortcut for the same thing. It is the stop key now."""
    isolate_runtime(monkeypatch)

    assert "pause" not in app_module.DEFAULT_KEYS
    assert app_module.DEFAULT_KEYS["stop"] == "c"

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 24)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [Entry(id=1, title="t", artist="a", duration=9)], start=0
            )
            mpv.idle = False

            await pilot.press("c")
            await pilot.pause()
            assert mpv.paused is False, "«c» para, no pausa"
            assert mpv.idle is True

    asyncio.run(scenario())


def test_mpris_play_pause_still_toggles(monkeypatch):
    """The key went; the D-Bus verb did not, and it has to keep working."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 24)) as pilot:
            await pilot.pause()
            mpv.idle = False

            application.mpris_play_pause()
            assert mpv.paused is True
            application.mpris_play_pause()
            assert mpv.paused is False

    asyncio.run(scenario())


def test_enter_on_a_track_offers_the_four_things_worth_doing(monkeypatch):
    """It used to queue the whole level and start playing, with no way to say
    «just this one next» or «play the radio»."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            open_menu_on_b(application, track_rows())
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(application.screen, TrackActionsScreen)
            drawn = application.screen.query_one("#actions-list").render_line
            lines = [drawn(y).text for y in range(len(TRACK_ACTIONS))]
            for (_action, icon, letter, label), line in zip(
                TRACK_ACTIONS, lines, strict=True
            ):
                assert icon in line
                assert label in line
                assert f"[{letter}]" in line

            # And it names the track it is about.
            title = application.screen.query_one("#actions-title")
            assert "A" in title.render_line(0).text

    asyncio.run(scenario())


def test_play_next_adds_only_that_track_after_the_current_one(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [
                    Entry(id=8, title="sonando", artist="x"),
                    Entry(id=9, title="luego", artist="x"),
                ],
                start=0,
            )
            open_menu_on_b(application, track_rows())
            await pilot.pause()
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert [e.title for e in application.queue] == ["sonando", "B", "luego"]
            assert application.queue.playing == 0
            assert "B" in application.status

    asyncio.run(scenario())


def test_the_marquee_carries_the_number_and_the_title_and_nothing_else(monkeypatch):
    """The artist, the album and the length moved under the clock. One line is
    all the marquee has, and it spends it on the title."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace([a_deftones_track()], start=-1)
            application._sync_queue()
            application._play_index(0)
            await pilot.pause()

            text = application.query_one(Marquee).text
            assert text == "1. Entombed"
            assert "Deftones" not in text and "4:59" not in text

    asyncio.run(scenario())


def test_a_track_with_no_year_does_not_leave_a_stray_separator(monkeypatch):
    """A restored queue from before the year column carries `year = 0`."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [
                    Entry(
                        id=1,
                        title="Entombed",
                        artist="Deftones",
                        album="Around the Fur",
                        duration=299,
                    )
                ],
                start=-1,
            )
            application._sync_queue()
            application._play_index(0)
            await pilot.pause()

            lines = [
                line.rstrip()
                for line in application.query_one("#trackmeta", Glide)
                .render()
                .plain.split("\n")
            ]
            assert lines[:3] == ["Deftones", "Around the Fur", "4:59"]

    asyncio.run(scenario())


def test_space_plays_and_pauses_like_x(monkeypatch):
    """What every other player uses, and nothing in the main window wanted."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(120, 32)) as pilot:
            await pilot.pause()
            application.queue.replace([a_deftones_track()], start=0)
            mpv.idle = False

            await pilot.press("space")
            await pilot.pause()
            assert mpv.paused is True

            await pilot.press("space")
            await pilot.pause()
            assert mpv.paused is False

    asyncio.run(scenario())


# ------------------------------------------------------------------------ volume


def test_clicking_the_middle_of_seek_jumps_to_the_middle(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        mpv.duration = 200.0
        mpv.idle = False
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            seek = application.query_one("#seek", SeekBar)
            seek.total = mpv.duration
            middle = seek.content_offset.x + (seek.size.width - 1) // 2

            assert await pilot.click("#seek", offset=(middle, 0))
            await pilot.pause()

            assert len(mpv.seek_calls) == 1
            seconds, mode = mpv.seek_calls[0]
            assert mode == "absolute"
            assert seconds == pytest.approx(100.0, abs=200 / (seek.size.width - 1))

    asyncio.run(scenario())


def test_clicking_seek_without_a_loaded_track_does_nothing(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            seek = application.query_one("#seek", SeekBar)
            middle = seek.content_offset.x + (seek.size.width - 1) // 2

            assert await pilot.click("#seek", offset=(middle, 0))
            await pilot.pause()

            assert mpv.seek_calls == []

    asyncio.run(scenario())


def test_clicking_volume_sets_the_players_volume(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        mpv.volume = 0
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            slider = application.query_one("#volume", Slider)
            start, track = slider._track()
            right = slider.content_offset.x + start + track - 1

            assert await pilot.click("#volume", offset=(right, 0))
            await pilot.pause()

            assert mpv.volume == Mpv.VOLUME_MAX
            assert slider.value == Mpv.VOLUME_MAX

    asyncio.run(scenario())


def test_clicking_the_balance_centre_sets_exactly_zero(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(Settings, "save", lambda self: None)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            application.settings.set_balance(0.7)
            slider = application.query_one("#balance", Slider)
            slider.value = 70
            start, track = slider._track()
            centre = slider.content_offset.x + start + track // 2

            assert await pilot.click("#balance", offset=(centre, 0))
            await pilot.pause()

            assert application.settings.balance == 0.0
            assert slider.value == 0
            assert mpv.filter_calls[-1] == ("eq", None)
            assert application.status == "balance: centro"

    asyncio.run(scenario())


def test_the_volume_slider_scales_to_the_players_ceiling(monkeypatch):
    """A full bar has to mean the loudest the player will actually go."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            slider = application.query_one("#volume", Slider)
            assert slider.maximum == Mpv.VOLUME_MAX

            slider.value = Mpv.VOLUME_MAX
            await pilot.pause()
            assert "░" not in slider.render_line(0).text

    asyncio.run(scenario())


def test_turning_the_volume_up_stops_at_the_ceiling(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            for _ in range(30):
                await pilot.press("plus")
            await pilot.pause()
            assert mpv.volume == Mpv.VOLUME_MAX

            for _ in range(40):
                await pilot.press("minus")
            await pilot.pause()
            assert mpv.volume == 0

    asyncio.run(scenario())


def test_mpris_cannot_push_the_volume_past_the_ceiling(monkeypatch):
    """The bus used to accept 1.3 and hand the player 130, which is the same
    boost the keyboard could no longer ask for."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            application.mpris_set_volume(1.3)
            assert mpv.volume == Mpv.VOLUME_MAX
            assert application.mpris_volume() == 1.0

            application.mpris_set_volume(-2.0)
            assert mpv.volume == 0

            application.mpris_set_volume(0.45)
            assert mpv.volume == 45

    asyncio.run(scenario())


def test_the_status_bar_is_actually_on_screen(monkeypatch):
    """It was not: an auto-height playlist pushed it past the bottom edge.

    Everything the app has to say — errors, «resolviendo…», a restored queue —
    is written there, so off-screen meant silent.
    """
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            bar = application.query_one("#statusbar")
            assert bar.region.bottom <= application.size.height
            assert bar.region.height == 1

    asyncio.run(scenario())


def test_a_status_with_square_brackets_reaches_the_screen_intact(monkeypatch):
    """`Static.update` reads a str as markup, and ate the `[art]` in the advice."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(artwork, "have_decoder", lambda: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.3)
            drawn = application.query_one("#status").render_line(0).text
            assert "tidalamp[art]" in drawn

    asyncio.run(scenario())


def test_resolving_a_track_says_so_and_stops_saying_it(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    class Playable:
        url = "https://cdn/a"
        kbps = "16-bit"
        khz = "44.1"
        quality = "LOSSLESS"
        codec = "flac"

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entry = Entry(id=1, title="Schism", artist="TOOL")
            application.queue.append([entry])
            application._sync_queue()

            application._play_index(0)
            busy = application.query_one("#busy", Spinner)
            assert busy.busy
            assert busy.label == "resolviendo «Schism»…"

            application._start(entry, Playable())
            assert not busy.busy

            # A failure has to clear it too, or the app looks stuck forever.
            application._play_index(0)
            application._resolve_failed("error: sin red")
            assert not busy.busy
            assert application.status == "error: sin red"

    asyncio.run(scenario())


def test_a_quality_downgrade_reaches_the_status_line(monkeypatch):
    isolate_runtime(monkeypatch)

    class Downgraded:
        url = "https://cdn/a"
        kbps = "320 kbps"
        khz = "44.1"
        quality = "HIGH"
        codec = "aac"
        requested = "LOSSLESS"
        downgraded = True

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entry = Entry(id=1, title="Schism", artist="TOOL")
            application._start(entry, Downgraded())

            assert "TIDAL entregó HIGH, no LOSSLESS" in application.status
            badges = application.query_one("#badges", Glide)
            assert "320" in str(badges.content) and "HIGH" in str(badges.content)

    asyncio.run(scenario())


def test_source_output_and_pause_are_separate_truthful_readouts(monkeypatch):
    isolate_runtime(monkeypatch)

    class HiRes:
        url = "https://cdn/a"
        kbps = "24-bit"
        khz = "176.4"
        quality = "HI_RES_LOSSLESS"
        codec = "flac"
        requested = "HI_RES_LOSSLESS"
        downgraded = False

    async def scenario() -> None:
        mpv = FakeMpv()
        mpv.idle = False
        mpv.paused = True
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(120, 36)) as pilot:
            entry = Entry(id=1, title="Thriller", artist="Michael Jackson")
            application.queue.replace([entry], start=0)
            application._sync_queue()
            application._start(entry, HiRes())
            application._set_sink(
                audio_module.Sink(
                    name="alsa_output.usb",
                    description="FIIO BTR15",
                    rate=176400,
                    sample_format="s32le",
                )
            )
            await pilot.pause()

            source = str(application.query_one("#badges", Glide).content)
            output = str(application.query_one("#output", Glide).content)
            assert "SRC  FLAC" in source
            assert "24-bit" in source and "176.4 kHz" in source
            assert "HI-RES" in source and "PAUSA" in source
            assert output == "OUT  FIIO BTR15 · PCM S32LE · 176.4 kHz"
            assert application.query_one("#volume", Slider).label == "VOL/mpv"

    asyncio.run(scenario())


def test_the_speed_window_offers_a_quarter_to_double_and_applies_on_enter(monkeypatch):
    """Eight speeds in quarters with 1 as recorded; ↵ applies, esc leaves the
    speed alone, and the button says the speed and lights up off 1×."""
    from tidalamp.player import Mpv
    from tidalamp.screens import SpeedScreen

    assert Mpv.SPEEDS == (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 26)) as pilot:
            await pilot.pause()
            assert "b 1×" in transport(application)

            await pilot.press("b")
            await pilot.pause()
            assert isinstance(application.screen, SpeedScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert mpv.speed == 1.0

            await pilot.press("b")
            await pilot.press("up", "up")
            await pilot.press("enter")
            await pilot.pause()
            assert not isinstance(application.screen, SpeedScreen)
            assert mpv.speed == 0.5
            assert "b 0.5×" in transport(application)
            assert "0.5×" in application.status

            await pilot.press("b")
            for _step in range(10):
                await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            assert mpv.speed == 2.0

    asyncio.run(scenario())


def test_a_desktop_s_rate_lands_on_the_nearest_quarter(monkeypatch):
    """Any number a desktop sends is rounded to one of the window's eight, so
    the button still says one of them; 0 and below are not a speed."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(150, 26)) as pilot:
            await pilot.pause()
            application.mpris_set_rate(0.6)
            assert mpv.speed == 0.5
            assert application.mpris_rate() == 0.5
            application.mpris_set_rate(0)
            application.mpris_set_rate(-1.0)
            assert mpv.speed == 0.5
            application.mpris_set_rate(3.0)
            assert mpv.speed == 2.0
            await pilot.pause()
            assert "b 2×" in transport(application)

    asyncio.run(scenario())


def test_q_asks_before_quitting_and_ctrl_c_does_not(monkeypatch):
    """`q` sits next to `w`: it asks, on «cancel», and `q` again confirms.
    ctrl+c is the way out that does not ask."""
    from tidalamp.screens import ChoiceScreen

    isolate_runtime(monkeypatch)
    closed: list[str] = []

    async def close_player(self) -> None:
        closed.append("closed")

    # Not Textual's `_shutdown`: stubbing that one left the test waiting on
    # an app that never finished closing.
    monkeypatch.setattr(TidalAmp, "_close_player", close_player)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(150, 26)) as pilot:
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            assert isinstance(application.screen, ChoiceScreen)
            await pilot.press("enter")  # «cancel»
            await pilot.pause()
            assert closed == []
            assert len(application.screen_stack) == 1

            await pilot.press("q", "q")
            await settle(pilot, lambda: closed == ["closed"])

            await pilot.press("ctrl+c")
            await settle(pilot, lambda: closed == ["closed", "closed"])
            assert len(application.screen_stack) == 1

            # With a window open too: ctrl+c is checked before any window.
            await pilot.press("q")
            await pilot.pause()
            assert isinstance(application.screen, ChoiceScreen)
            await pilot.press("ctrl+c")
            await settle(pilot, lambda: closed == ["closed", "closed", "closed"])

    asyncio.run(scenario())


def test_a_tick_after_teardown_finds_no_screen_quietly():
    """CI caught `_tick_slow` asking for `app.screen` once the stack was empty.

    After exit that is nothing to report; while running it is a real fault.
    """
    import pytest
    from textual.app import ScreenStackError

    from tidalamp.app import _quiet_after_teardown

    class Stub:
        _running = False

        @_quiet_after_teardown
        def tick(self):
            raise ScreenStackError("No screens on stack")

    stub = Stub()
    assert stub.tick() is None

    stub._running = True
    with pytest.raises(ScreenStackError):
        stub.tick()


def test_a_resolve_that_comes_back_late_does_not_start_an_older_track(monkeypatch):
    """A worker's thread is not cancelled with it: «next» pressed twice quickly
    could see the first track's resolve land after the second was asked for."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    class Playable:
        kbps = "16-bit"
        khz = "44.1"
        quality = "LOSSLESS"
        codec = "flac"

        def __init__(self, url: str) -> None:
            self.url = url

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            first = Entry(id=1, title="Schism", artist="TOOL")
            second = Entry(id=2, title="Parabola", artist="TOOL")
            application.queue.append([first, second])
            application._sync_queue()
            busy = application.query_one("#busy", Spinner)

            application._play_index(0)
            application._play_index(1)

            application._start(first, Playable("https://cdn/schism"))
            assert mpv.loaded is None, "la vieja no se pone a sonar"
            assert busy.busy, "la nueva sigue resolviéndose"
            application._resolve_failed("error: sin red", first)
            assert busy.busy and application.status != "error: sin red"

            application._start(second, Playable("https://cdn/parabola"))
            assert mpv.loaded == "https://cdn/parabola"
            assert not busy.busy

    asyncio.run(scenario())
