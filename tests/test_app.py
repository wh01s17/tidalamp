"""Focused Textual workflow regressions."""

from __future__ import annotations

import asyncio
import threading

from textual.screen import Screen
from textual.widgets import Static

from tidalamp import about, artwork, library
from tidalamp import app as app_module
from tidalamp.app import BrowserScreen, HelpScreen, TidalAmp
from tidalamp.artwork import Cover, Protocol
from tidalamp.library import Row
from tidalamp.player import Mpv
from tidalamp.queue import Entry, Queue
from tidalamp.settings import Settings
from tidalamp.theme import DEFAULT_COLORS, ThemePalette
from tidalamp.widgets import Artwork, Slider, Spinner


async def settle(pilot, done, tries: int = 100) -> None:
    """Pump the event loop until a worker's result has landed."""
    for _ in range(tries):
        await pilot.pause()
        if done():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("el worker no terminó")


class FakeMpv:
    alive = True
    position = 0.0
    duration = 0.0
    paused = False
    idle = True

    def __init__(self) -> None:
        self.filter_calls: list[tuple[str, str | None]] = []
        self.loaded: str | None = None
        self._volume = 100

    @property
    def volume(self) -> int:
        return self._volume

    @volume.setter
    def volume(self, value: int) -> None:
        # Same ceiling as the real player: the app relies on it to clamp.
        self._volume = max(0, min(Mpv.VOLUME_MAX, value))

    def load(self, url: str) -> None:
        self.loaded = url

    def set_filter(self, label: str, graph: str | None) -> None:
        self.filter_calls.append((label, graph))

    def rms(self) -> float:
        return -91.0

    def close(self) -> None:
        pass


def isolate_runtime(monkeypatch) -> None:
    async def no_mpris(self) -> None:
        return None

    monkeypatch.setattr(Queue, "load", lambda self: False)
    monkeypatch.setattr(Queue, "save", lambda self: None)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings()))
    monkeypatch.setattr(TidalAmp, "_start_spectrum", lambda self: None)
    monkeypatch.setattr(TidalAmp, "_start_mpris", no_mpris)


def test_slow_tick_does_not_reapply_audio_filters(monkeypatch):
    """Changing filters may create an audible gap; polling must stay read-only."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        mpv = FakeMpv()
        application = TidalAmp(object(), mpv)
        async with application.run_test() as pilot:
            await pilot.pause()
            initial = list(mpv.filter_calls)
            application._tick_slow()
            assert initial == [("balance", None), ("eq", None)]
            assert mpv.filter_calls == initial

    asyncio.run(scenario())


def test_shuffle_and_repeat_have_persistent_indicators(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            modes = application.query_one("#modes", Static)
            assert modes.content.plain == "   SHUF OFF     REP OFF "

            await pilot.press("s")
            assert modes.content.plain == "   SHUF ON     REP OFF "

            await pilot.press("r")
            assert modes.content.plain == "   SHUF ON     REP ALL "

            application.mpris_set_loop_status("Track")
            application.mpris_set_shuffle(False)
            assert modes.content.plain == "   SHUF OFF     REP 1 "

    asyncio.run(scenario())


def test_running_app_follows_an_omarchy_theme_change(monkeypatch):
    isolate_runtime(monkeypatch)
    initial = ThemePalette(dict(DEFAULT_COLORS), source="omarchy")
    changed_colors = dict(DEFAULT_COLORS)
    changed_colors["accent"] = "#7aa2f7"
    changed_colors["panel"] = "#1a1b26"
    changed = ThemePalette(changed_colors, source="omarchy")
    palettes = iter((initial, changed))
    monkeypatch.setattr("tidalamp.app.load_palette", lambda: next(palettes))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.press("s")
            application._refresh_theme()

            modes = application.query_one("#modes", Static)
            assert application.tidalamp_palette is changed
            assert application.get_theme_variable_defaults()["tidalamp-accent"] == (
                "#7aa2f7"
            )
            assert application.query_one("#main").styles.background.hex == "#1A1B26"
            assert any("#7aa2f7" in str(span.style) for span in modes.content.spans)

    asyncio.run(scenario())


# ---------------------------------------------------------------------- artwork


def a_cover(protocol=Protocol.BLOCKS, escape=""):
    pixels = (((255, 0, 0), (0, 255, 0)), ((0, 0, 255), (255, 255, 0)))
    return Cover(
        cols=2,
        rows=1,
        protocol=protocol,
        pixels=pixels if protocol is Protocol.BLOCKS else None,
        escape=escape,
    )


def test_the_cover_takes_no_room_until_there_is_one(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            art = application.query_one(Artwork)
            assert art.cover is None
            assert art.styles.display == "none"

            art.show(a_cover())
            await pilot.pause()
            assert art.styles.display == "block"

    asyncio.run(scenario())


def test_the_cover_box_grows_with_the_terminal_but_leaves_the_row_alone(monkeypatch):
    """18x9 was fixed, which made the cover a stamp on a big terminal.

    Two ceilings have to hold: the display band must not eat the playlist,
    and the box shares its row with the clock and the readout.
    """
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        for size, expected in ((76, 20), 9), ((120, 50), 12), ((180, 100), 20):
            application = TidalAmp(object(), FakeMpv())
            async with application.run_test(size=size) as pilot:
                await pilot.pause()
                art = application.query_one(Artwork)
                assert (art.rows, art.cols) == (expected, expected * 2), size

                # A square box on screen, and room left for the rest of the row.
                art.show(a_cover())
                await pilot.pause()
                clock = application.query_one("#clock")
                readout = application.query_one("#readout")
                assert art.region.right <= clock.region.x
                assert readout.region.right <= size[0]
                assert application.query_one("#playlist").size.height > 0

    asyncio.run(scenario())


def test_a_narrow_but_tall_terminal_keeps_the_small_box(monkeypatch):
    """Height alone must not grow it: the readout shares the row and would go."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(76, 200)) as pilot:
            await pilot.pause()
            assert application.query_one(Artwork).rows == Artwork.MIN_ROWS

    asyncio.run(scenario())


def test_resizing_asks_for_the_cover_again_at_the_new_size(monkeypatch):
    """resize() drops the old cover, so something has to redraw it."""
    isolate_runtime(monkeypatch)
    asked: list[str] = []
    monkeypatch.setattr(TidalAmp, "_art_worker", lambda self, url: asked.append(url))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            application._art_url = "http://example/cover.jpg"
            asked.clear()
            application.query_one(Artwork).show(a_cover())

            await pilot.resize_terminal(180, 100)
            await pilot.pause()
            assert application.query_one(Artwork).rows == 20
            assert asked == ["http://example/cover.jpg"]

    asyncio.run(scenario())


def test_half_blocks_paint_two_pixels_per_cell(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            art = application.query_one(Artwork)
            art.show(a_cover())
            await pilot.pause()

            segments = list(art.render_line(0))
            assert segments[0].text == "▀"
            # Upper half is the first pixel row, lower half the second.
            assert segments[0].style.color.triplet == (255, 0, 0)
            assert segments[0].style.bgcolor.triplet == (0, 0, 255)
            assert segments[1].style.color.triplet == (0, 255, 0)
            assert segments[1].style.bgcolor.triplet == (255, 255, 0)

    asyncio.run(scenario())


def test_a_pixel_protocol_goes_out_as_a_zero_width_control_segment(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            art = application.query_one(Artwork)
            art.show(a_cover(Protocol.KITTY, escape="\033_Ga=T;AAAA\033\\"))
            await pilot.pause()

            strip = art.render_line(0)
            control = [segment for segment in strip if segment.is_control]
            assert control and control[0].text.startswith("\033_G")
            # The escape must not eat cells, or the compositor would shift the
            # rest of the row to the left.
            assert strip.cell_length == art.size.width
            # One anchor draws the whole image; the other rows stay empty.
            assert not any(segment.is_control for segment in art.render_line(1))

    asyncio.run(scenario())


def test_a_modal_takes_the_cover_down_and_the_tick_puts_it_back(monkeypatch):
    """kitty images float above the text, so a modal would open under them."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            art = application.query_one(Artwork)
            cover = a_cover()
            art.show(cover)
            await pilot.pause()

            application.push_screen(Screen())
            await pilot.pause()
            assert art.cover is None
            assert application._art_hidden

            application.pop_screen()
            await pilot.pause()
            application._tick_slow()
            assert art.cover is cover
            assert not application._art_hidden

    asyncio.run(scenario())


def test_the_same_cover_is_not_fetched_twice(monkeypatch):
    isolate_runtime(monkeypatch)
    asked: list[str] = []
    monkeypatch.setattr(TidalAmp, "_art_worker", lambda self, url: asked.append(url))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            entry = Entry(id=1, title="t", artist="a", art_url="https://c/1.jpg")
            application._load_art(entry)
            application._load_art(entry)
            assert asked == ["https://c/1.jpg"]

            # A track with no cover hides whatever was on screen.
            application.query_one(Artwork).show(a_cover())
            application._load_art(Entry(id=2, title="t2", artist="a"))
            assert application.query_one(Artwork).cover is None

    asyncio.run(scenario())


def test_artwork_off_never_asks_for_a_cover(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(
        "tidalamp.artwork.detect_protocol",
        lambda env=None, configured="": Protocol.NONE,
    )
    asked: list[str] = []
    monkeypatch.setattr(TidalAmp, "_art_worker", lambda self, url: asked.append(url))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            application._load_art(
                Entry(id=1, title="t", artist="a", art_url="https://c/1.jpg")
            )
            assert asked == []

    asyncio.run(scenario())


def test_pushing_a_screen_before_the_ui_exists_is_harmless(monkeypatch):
    """Textual pushes the default screen while compose has not run yet."""
    isolate_runtime(monkeypatch)
    application = TidalAmp(object(), FakeMpv())
    application._hide_art()
    application._restore_art()
    assert application._artwork() is None


# -------------------------------------------------------------- MPRIS TrackList


def test_the_track_list_is_the_queue_with_one_id_per_row(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            # The same song twice: the ids still have to differ, or a client
            # could not tell the two rows apart.
            application.queue.append(
                [
                    Entry(id=7, title="Schism", artist="TOOL"),
                    Entry(id=7, title="Schism", artist="TOOL"),
                ]
            )

            tracks = application.mpris_tracks()
            ids = [t["trackid"] for t in tracks]
            assert len(set(ids)) == 2
            assert all(t["title"] == "Schism" for t in tracks)

    asyncio.run(scenario())


def test_go_to_plays_the_row_with_that_id(monkeypatch):
    isolate_runtime(monkeypatch)
    played: list[int] = []
    monkeypatch.setattr(TidalAmp, "_play_index", lambda self, index: played.append(index))

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            await pilot.pause()
            application.queue.append(
                [Entry(id=i, title=f"t{i}", artist="a") for i in range(3)]
            )

            application.mpris_go_to(application.mpris_tracks()[2]["trackid"])
            # An id we never handed out is ignored, not an index error.
            application.mpris_go_to("/org/mpris/MediaPlayer2/tidalamp/track/999999")

            assert played == [2]

    asyncio.run(scenario())


# ---------------------------------------------------------------- loading state


def test_the_spinner_is_silent_until_there_is_something_to_wait_for():
    spinner = Spinner()
    assert spinner.busy is False
    assert spinner.render().plain == ""

    # Idle must not animate: a frame change would repaint the screen forever.
    spinner._advance()
    assert spinner._frame == 0

    spinner.start("cargando playlists…")
    spinner._advance()
    assert spinner.busy is True
    assert spinner._frame == 1
    assert spinner.render().plain == f"{Spinner.FRAMES[1]} cargando playlists…"

    spinner.stop()
    assert spinner.render().plain == ""


def test_the_browser_says_what_it_is_loading_and_stops_when_it_lands(monkeypatch):
    """The complaint this fixes: pressing `l` sat silent while the API answered."""
    isolate_runtime(monkeypatch)
    release = threading.Event()

    def slow_root():
        release.wait(5)
        return [Row(label="Mi playlist", loader=list)]

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            application.push_screen(BrowserScreen("MI BIBLIOTECA", slow_root))
            await pilot.pause()

            spinner = application.screen.query_one(Spinner)
            assert spinner.busy
            assert "biblioteca" in spinner.label

            release.set()
            await settle(pilot, lambda: not spinner.busy)
            assert not spinner.busy

    asyncio.run(scenario())


def test_a_title_with_brackets_survives_the_browser_header(monkeypatch):
    """TIDAL names square-bracket things all the time: «[Deluxe Edition]».

    `Static.update` reads a str as Rich markup, so the header used to swallow
    everything from the first bracket on, and a name carrying a closing tag
    («[/]») raised MarkupError instead of drawing.
    """
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            for name in ("Lateralus [Deluxe Edition]", "Song [/] end", "[red]hot[/red]"):
                application.push_screen(BrowserScreen(name, lambda: [Row(label="x")]))
                await pilot.pause()
                drawn = application.screen.query_one("#browser-title").render_line(0)
                assert name[:20] in drawn.text
                application.pop_screen()
                await pilot.pause()

    asyncio.run(scenario())


# ------------------------------------------------------------------------ volume


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


# ------------------------------------------------------------------------- help


def test_the_help_key_opens_the_help_and_closes_it_again(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            assert len(application.screen_stack) == 1

            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(application.screen, HelpScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert len(application.screen_stack) == 1

            # `h` is the second binding on the same action.
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(application.screen, HelpScreen)

    asyncio.run(scenario())


def test_the_help_lists_the_rebound_key_not_the_shipped_one(monkeypatch):
    """A help screen that showed DEFAULT_KEYS would be wrong for anyone who
    edited config.toml — which is the only reason the file exists."""
    isolate_runtime(monkeypatch)
    monkeypatch.setitem(app_module.config.KEYS, "play", "ctrl+j")

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            application.push_screen(HelpScreen(app_module.keys_for))
            await pilot.pause()
            drawn = "\n".join(
                application.screen.query_one("#help-body").render_line(y).text
                for y in range(application.screen.query_one("#help-body").size.height)
            )
            assert "ctrl+j" in drawn
            assert "\n  x " not in drawn

    asyncio.run(scenario())


def test_the_help_credits_the_author_the_repo_the_licence_and_the_changes(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            screen = HelpScreen(app_module.keys_for)
            application.push_screen(screen)
            await pilot.pause()
            document = "\n".join(text for _kind, text in screen._lines)

            assert about.AUTHOR in document
            assert about.REPO_URL in document
            assert about.LICENSE in document
            assert about.LICENSE_URL in document
            assert about.version() in document
            for release in about.releases():
                assert release.version in document
                for change in release.changes:
                    assert change in document

    asyncio.run(scenario())


def test_the_help_scrolls_and_stops_at_both_ends(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            screen = HelpScreen(app_module.keys_for)
            application.push_screen(screen)
            await pilot.pause()
            assert screen._offset == 0

            await pilot.press("up")
            await pilot.pause()
            assert screen._offset == 0, "no debe pasar del principio"

            await pilot.press("end")
            await pilot.pause()
            bottom = screen._offset
            assert bottom > 0
            assert bottom == len(screen._lines) - screen._height()

            await pilot.press("down")
            await pilot.pause()
            assert screen._offset == bottom, "no debe pasar del final"

            await pilot.press("home")
            await pilot.pause()
            assert screen._offset == 0

    asyncio.run(scenario())


def test_the_help_hides_a_kitty_cover_like_the_other_modals(monkeypatch):
    """An image drawn by the terminal floats over the text: a modal opened
    under it would be unreadable. push_screen already handles it."""
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            application.query_one(Artwork).show(a_cover(Protocol.KITTY, escape="\x1b_G"))
            await pilot.pause()

            await pilot.press("question_mark")
            await pilot.pause()
            assert application._art_hidden
            assert application.query_one(Artwork).cover is None

    asyncio.run(scenario())


def test_opening_a_playlist_names_the_playlist_while_it_loads(monkeypatch):
    isolate_runtime(monkeypatch)
    release = threading.Event()

    def slow_level():
        release.wait(5)
        return []

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:
            screen = BrowserScreen(
                "MI BIBLIOTECA",
                lambda: [Row(label="Mi playlist", loader=slow_level)],
            )
            application.push_screen(screen)
            await pilot.pause()
            spinner = application.screen.query_one(Spinner)
            await settle(pilot, lambda: not spinner.busy)

            await pilot.press("enter")
            await pilot.pause()
            assert spinner.busy
            assert spinner.label == "abriendo Mi playlist…"
            # The title is what tells the user where they are; it stays put.
            title = application.screen.query_one("#browser-title", Static).content
            assert str(title) == "MI BIBLIOTECA"

            release.set()
            await settle(pilot, lambda: not spinner.busy)

    asyncio.run(scenario())


def test_going_back_stops_a_spinner_for_a_level_nobody_is_waiting_for(monkeypatch):
    isolate_runtime(monkeypatch)
    release = threading.Event()

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test() as pilot:

            def blocked():
                release.wait(5)
                return []

            screen = BrowserScreen(
                "MI BIBLIOTECA",
                lambda: [Row(label="A", loader=lambda: [Row(label="B", loader=blocked)])],
            )
            application.push_screen(screen)
            await pilot.pause()
            spinner = application.screen.query_one(Spinner)
            await settle(pilot, lambda: not spinner.busy)

            await pilot.press("enter")
            await settle(pilot, lambda: not spinner.busy)
            await pilot.press("enter")
            await pilot.pause()
            assert spinner.busy

            await pilot.press("backspace")
            await pilot.pause()
            assert not spinner.busy
            release.set()

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


def test_a_missing_pillow_is_announced_instead_of_leaving_an_empty_corner(monkeypatch):
    """Without Pillow the cover widget simply never becomes visible.

    That used to be a `log.info` to a file nobody reads, so a fresh clone
    looked broken. The status line now names the extra that fixes it.
    """
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(artwork, "have_decoder", lambda: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert "Pillow" in application.status

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


def test_a_present_pillow_says_nothing(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(artwork, "have_decoder", lambda: True)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert "Pillow" not in application.status

    asyncio.run(scenario())


def test_resolving_a_track_says_so_and_stops_saying_it(monkeypatch):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)

    class Playable:
        url = "https://cdn/a"
        kbps = "1411"
        khz = "44.1"
        quality = "LOSSLESS"

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


def test_reload_drops_the_cached_level_and_asks_again(monkeypatch):
    """The cache lasts the session; `R` is the way to see a new playlist."""
    isolate_runtime(monkeypatch)
    calls: list[int] = []

    def loader():
        calls.append(1)
        return [Row(label="Mi playlist", loader=list)]

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            screen = BrowserScreen(
                "MI BIBLIOTECA", library.cached("playlists", loader), "playlists"
            )
            application.push_screen(screen)
            await pilot.pause()
            spinner = application.screen.query_one(Spinner)
            await settle(pilot, lambda: not spinner.busy)
            assert calls == [1]

            await pilot.press("R")
            await settle(pilot, lambda: not spinner.busy and len(calls) == 2)

            assert calls == [1, 1]
            # One level on the stack, not two: reloading replaces, it does not
            # drill in.
            assert len(screen._stack) == 1
            title = application.screen.query_one("#browser-title", Static).content
            assert str(title) == "MI BIBLIOTECA"

    asyncio.run(scenario())


def test_a_quality_downgrade_reaches_the_status_line(monkeypatch):
    isolate_runtime(monkeypatch)

    class Downgraded:
        url = "https://cdn/a"
        kbps = "320"
        khz = "44"
        quality = "HIGH"
        requested = "LOSSLESS"
        downgraded = True

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            entry = Entry(id=1, title="Schism", artist="TOOL")
            application._start(entry, Downgraded())

            assert "TIDAL entregó HIGH, no LOSSLESS" in application.status
            badges = application.query_one("#badges", Static)
            assert "320" in str(badges.content) and "HIGH" in str(badges.content)

    asyncio.run(scenario())


# ------------------------------------------------------------- terminal size


def test_a_small_terminal_gets_an_explanation_not_a_broken_layout(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            notice = application.query_one("#too-small", Static)
            assert notice.display is True
            text = str(notice.content)
            assert "60×18" in text
            assert f"{TidalAmp.MIN_WIDTH}×{TidalAmp.MIN_HEIGHT}" in text

    asyncio.run(scenario())


def test_a_terminal_big_enough_shows_nothing_extra(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert application.query_one("#too-small", Static).display is False

    asyncio.run(scenario())


def test_the_notice_appears_and_clears_as_the_window_is_resized(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            notice = application.query_one("#too-small", Static)
            assert notice.display is False

            await pilot.resize_terminal(70, 40)
            await pilot.pause()
            assert notice.display is True

            await pilot.resize_terminal(100, 40)
            await pilot.pause()
            assert notice.display is False

    asyncio.run(scenario())


# ---------------------------------------------------------------- favoritos


def test_f_favourites_the_selected_track_and_says_so(monkeypatch):
    isolate_runtime(monkeypatch)
    calls: list[tuple[int, bool]] = []

    def fake_favourite(session, row, add=True):
        calls.append((row.entry.id, add))
        return row.entry.label

    monkeypatch.setattr("tidalamp.library.favourite", fake_favourite)
    monkeypatch.setattr("tidalamp.screens.ensure_fresh", lambda session: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.queue.append([Entry(id=42, title="Schism", artist="TOOL")])
            application._sync_queue()
            await pilot.pause()

            await pilot.press("f")
            await settle(pilot, lambda: "favoritos" in application.status)
            assert calls == [(42, True)]
            assert application.status == "«TOOL - Schism» añadido a favoritos"

            await pilot.press("F")
            await settle(pilot, lambda: "quitado" in application.status)
            assert calls == [(42, True), (42, False)]

    asyncio.run(scenario())


def test_favouriting_nothing_says_so_instead_of_failing(monkeypatch):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("f")
            assert application.status == "no hay ninguna pista seleccionada"

    asyncio.run(scenario())


def test_a_favourite_that_fails_reaches_the_status_line(monkeypatch):
    isolate_runtime(monkeypatch)

    def boom(session, row, add=True):
        raise RuntimeError("sin red")

    monkeypatch.setattr("tidalamp.library.favourite", boom)
    monkeypatch.setattr("tidalamp.screens.ensure_fresh", lambda session: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            application.queue.append([Entry(id=1, title="t", artist="a")])
            application._sync_queue()
            await pilot.pause()

            await pilot.press("f")
            await settle(pilot, lambda: "favoritos" in application.status)
            assert application.status == "favoritos: sin red"
            assert not application.query_one("#busy", Spinner).busy

    asyncio.run(scenario())


def test_favouriting_drops_the_cached_favourites_levels(monkeypatch):
    """The level on disk is now a lie; the next visit must ask again."""
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(
        "tidalamp.library.favourite", lambda s, r, add=True: r.entry.label
    )
    monkeypatch.setattr("tidalamp.screens.ensure_fresh", lambda session: False)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            library.cached("fav:tracks", lambda: [Row(label="vieja")])()
            assert "fav:tracks" in library._LEVELS

            application.queue.append([Entry(id=1, title="t", artist="a")])
            application._sync_queue()
            await pilot.pause()
            await pilot.press("f")
            await settle(pilot, lambda: "favoritos" in application.status)

            assert "fav:tracks" not in library._LEVELS

    asyncio.run(scenario())
