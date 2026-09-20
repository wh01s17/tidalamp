"""The credit a licence asks for.

CC BY and CC BY-SA do not merely permit attribution, they require it, so this
is the one thing in «Lofi sin copyright» that is not a convenience: without
it the section hands you music you are not, strictly, allowed to use.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from tidalamp.freemusic import Track
from tidalamp.queue import Entry
from tidalamp.screens import TRACK_ACTIONS, CreditsScreen, actions_for, attribution
from tidalamp.screens.credits import DEMANDS
from tidalamp.screens.tracks import FREE_TRACK_ACTIONS, TrackActionsScreen


def free(licence: str = "CC BY", **over) -> Entry:
    fields = {
        "url": "https://archive.org/download/jamendo-300693/a.mp3",
        "title": "Child's play",
        "artist": "Nedim Jahić",
        "album": "Child's play",
        "licence": licence,
        "duration": 85,
        "source_url": "https://archive.org/details/jamendo-300693",
    }
    fields.update(over)
    return Entry.from_free(Track(**fields))


# ------------------------------------------------------------- the credit line


def test_the_credit_carries_all_four_things_the_licence_asks_for():
    """Title, Author, Source, Licence — the order Creative Commons asks for
    them in, which is well enough known to have a name: TASL."""
    line = attribution(free())
    assert "«Child's play»" in line
    assert "Nedim Jahić" in line
    assert "https://archive.org/details/jamendo-300693" in line
    assert "CC BY" in line


def test_the_source_is_the_page_and_not_the_audio_file():
    """Attribution asks for where the work lives. A file URL is not that, and
    it is also the one thing in the entry that may stop resolving."""
    entry = free()
    assert "/details/" in attribution(entry)
    assert entry.url not in attribution(entry)


@pytest.mark.parametrize("missing", [{"source_url": ""}, {"artist": ""}, {"licence": ""}])
def test_what_is_not_known_is_left_out_rather_than_left_blank(missing):
    """A line with a gap in it reads as a bug and credits nobody."""
    line = attribution(free(**missing))
    assert "()" not in line
    assert "  " not in line
    assert not line.endswith("—")
    assert "«Child's play»" in line


def test_every_licence_the_section_lets_in_says_what_it_asks_of_you():
    """The window is where somebody goes when they are about to *use* the
    music, so it has to answer the question they came with."""
    from tidalamp import freemusic

    for url in (
        "https://creativecommons.org/publicdomain/zero/1.0/",
        "https://creativecommons.org/licenses/by/4.0/",
        "https://creativecommons.org/licenses/by-sa/4.0/",
    ):
        assert freemusic.licence_name(url) in DEMANDS


# ----------------------------------------------------------------- the window


def rendered(entry: Entry) -> str:
    class Host(App):
        CSS_PATH: list = []

        def compose(self) -> ComposeResult:
            yield Static("")

    async def scenario() -> str:
        app = Host()
        async with app.run_test(size=(76, 24)) as pilot:
            await app.push_screen(CreditsScreen(entry))
            await pilot.pause()
            return app.screen.query_one("#credits-body", Static).render().plain

    return asyncio.run(scenario())


def test_the_window_shows_the_credit_and_what_the_licence_asks():
    body = rendered(free())
    assert "Nedim Jahić" in body
    assert "https://archive.org/details/jamendo-300693" in body
    assert DEMANDS["CC BY"] in body
    assert attribution(free()) in body


def test_a_share_alike_track_says_the_share_alike_part():
    """The difference between BY and BY-SA is the whole reason to read this."""
    body = rendered(free("CC BY-SA"))
    assert DEMANDS["CC BY-SA"] in body
    assert DEMANDS["CC BY"] not in body


def test_public_domain_says_it_asks_for_nothing():
    assert DEMANDS["CC0"] in rendered(free("CC0"))


def test_a_licence_the_window_does_not_know_still_shows_the_credit():
    """An unknown licence is shown rather than guessed at: what it demands is
    not ours to invent."""
    body = rendered(free("CC BY-NC-ND"))
    assert "CC BY-NC-ND" in body
    assert not any(demand in body for demand in DEMANDS.values())


def test_a_row_with_no_source_draws_no_empty_source_line():
    body = rendered(free(source_url=""))
    assert "Fuente" not in body
    assert "Nedim Jahić" in body


# ------------------------------------------------------------------ the menu


def test_a_free_track_is_offered_its_credits():
    offered = [action for action, *_rest in actions_for(free())]
    assert offered == ["play", "next", "credits"]


def test_a_tidal_track_is_not():
    """Nothing in TIDAL's catalogue is under a licence that asks anything of
    the listener, and the entry has no source page to point at."""
    tidal = Entry(id=1, title="Schism", artist="TOOL")
    assert "credits" not in [action for action, *_rest in actions_for(tidal)]


def test_the_credits_key_actually_does_something_in_the_menu():
    """The menu binds its keys from `TRACK_ACTIONS`, which `credits` is not
    in: without adding the free ones too, `k` was a letter on a row that no
    keypress could reach."""
    keys = {
        binding.key
        for binding in TrackActionsScreen.BINDINGS
        if getattr(binding, "action", "").startswith("pick(")
    }
    for _action, _icon, letter, _label in FREE_TRACK_ACTIONS:
        assert letter in keys


def test_the_credits_letter_collides_with_nothing():
    taken = {letter for _a, _i, letter, _l in TRACK_ACTIONS}
    credits = next(
        letter for action, _i, letter, _l in FREE_TRACK_ACTIONS if action == "credits"
    )
    assert credits not in taken


# -------------------------------------------- `k`, everywhere it should work


def with_queue(monkeypatch):
    from app_helpers import FakeMpv, isolate_runtime

    from tidalamp.app import TidalAmp

    isolate_runtime(monkeypatch)
    monkeypatch.setattr(TidalAmp, "_resolve_worker", lambda self, entry: None)
    mpv = FakeMpv()
    app = TidalAmp(object(), mpv)
    return app, mpv


def free_and_tidal() -> list[Entry]:
    return [free(), Entry(id=7, title="Schism", artist="TOOL", duration=200)]


def test_the_window_can_be_closed(monkeypatch):
    """It could not. The binding named an action that was never written, so
    the credits opened over the player and stayed there: esc did nothing,
    and neither did any other key the window claimed."""
    import asyncio

    async def scenario() -> str:
        app, _mpv = with_queue(monkeypatch)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CreditsScreen(free()))
            await pilot.pause()
            assert isinstance(app.screen, CreditsScreen)
            await pilot.press("escape")
            await pilot.pause()
            return type(app.screen).__name__

    assert asyncio.run(scenario()) != "CreditsScreen"


def test_k_opens_the_credits_of_the_row_under_the_cursor(monkeypatch):
    """`k` reads about what the eye is on, the way `m` acts on it."""
    import asyncio

    async def scenario() -> str:
        app, _mpv = with_queue(monkeypatch)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            app.queue.append(free_and_tidal())
            app._sync_queue()
            app.queue.playing = 0
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()
            return type(app.screen).__name__

    assert asyncio.run(scenario()) == "CreditsScreen"


def test_k_on_a_tidal_row_says_why_there_are_none(monkeypatch):
    """Not a red line: TIDAL's catalogue has no licence that asks anything of
    the listener and no page to point at."""
    import asyncio

    from tidalamp.screens import RowList

    async def scenario() -> tuple[str, str]:
        app, _mpv = with_queue(monkeypatch)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            app.queue.append(free_and_tidal())
            app._sync_queue()
            app.queue.playing = 0
            app.query_one("#playlist", RowList).cursor = 1
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()
            return type(app.screen).__name__, str(app.status)

    screen, status = asyncio.run(scenario())
    assert screen != "CreditsScreen"
    assert "Lofi sin copyright" in status


def test_k_works_in_the_full_screen_view_too(monkeypatch):
    """There the queue is a panel and the cursor is the player's; `k` has to
    reach the same row from both."""
    import asyncio

    async def scenario() -> str:
        app, _mpv = with_queue(monkeypatch)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            app.queue.append(free_and_tidal())
            app._sync_queue()
            app.queue.playing = 0
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()
            return type(app.screen).__name__

    assert asyncio.run(scenario()) == "CreditsScreen"


def test_k_is_listed_in_the_help(monkeypatch):
    """A key nobody is told about is a key nobody presses."""
    from tidalamp import about
    from tidalamp.app import keys_for

    shown = [
        label
        for section in about.shortcuts(keys_for)
        for _key, label in section.rows
        if "crédito" in label
    ]
    assert len(shown) >= 3, "el reproductor, el navegador y pantalla completa"
