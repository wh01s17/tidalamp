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
