"""Your mixes in the library: the section lists them and one opens like a
playlist, without the sort or the delete a mix does not have."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app_helpers import FakeMpv, isolate_runtime, open_browser, settle
from conftest import FakeTrack
from test_library import FakeSession

from tidalamp import library
from tidalamp.app import TidalAmp


def a_mix(ident: str, title: str, tracks: list) -> SimpleNamespace:
    calls: list[str] = []

    def items():
        calls.append(ident)
        return tracks

    return SimpleNamespace(
        id=ident,
        title=title,
        sub_title="Deftones, TOOL y más",
        mix_type="DAILY_MIX",
        items=items,
        calls=calls,
    )


def a_session_with_two_mixes():
    session = FakeSession()
    daily = a_mix("m1", "My Daily Discovery", [FakeTrack(1, "Schism"), FakeTrack(2)])
    news = a_mix("m2", "My New Arrivals", [FakeTrack(3, "Parabola")])
    # The page carries other things besides mixes.
    link = SimpleNamespace(title="Ver todo", items=list)
    session.mixes = lambda: [daily, link, news]
    return session, daily


def mixes_row(session):
    return next(row for row in library.root(session) if row.key == "mixes")


def test_the_section_lists_the_mixes_and_opening_one_brings_its_tracks():
    session, daily = a_session_with_two_mixes()

    row = mixes_row(session)
    assert row.label == "Mis mixes"
    mixes = row.loader()
    assert [mix.label for mix in mixes] == ["My Daily Discovery", "My New Arrivals"]
    assert mixes[0].detail == "Deftones, TOOL y más"
    assert daily.calls == [], "cada mix se pide al abrirlo, no al listar"

    tracks = mixes[0].loader()
    assert [track.entry.id for track in tracks] == [1, 2]
    assert all(track.is_playable for track in tracks)
    mixes[0].loader()
    assert daily.calls == ["m1"], "volver a entrar sale de la caché"


def test_a_mix_offers_no_order_and_nothing_to_remove_from():
    session, _daily = a_session_with_two_mixes()
    mix = mixes_row(session).loader()[0]

    assert mix.orders == () and mix.sort is None
    assert mix.key == "mix:m1", "ni fav: ni playlist:, que es lo que d sabe quitar"


def test_a_mix_that_comes_back_empty_is_an_empty_level():
    """tidalapi raises ValueError for a mix with no items in it."""
    session = FakeSession()

    def nothing():
        raise ValueError("Retrieved items missing")

    empty = SimpleNamespace(
        id="m9", title="Vacío", sub_title="", mix_type="X", items=nothing
    )
    session.mixes = lambda: [empty]

    assert mixes_row(session).loader()[0].loader() == []


def test_s_and_d_say_no_inside_a_mix(monkeypatch):
    isolate_runtime(monkeypatch)
    session, _daily = a_session_with_two_mixes()
    mix = mixes_row(session).loader()[0]

    async def scenario() -> None:
        application = TidalAmp(session, FakeMpv())
        async with application.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            open_browser(application, [mix])
            await pilot.pause()
            browser = application.screen
            await pilot.press("enter")
            await settle(pilot, lambda: len(browser._stack) > 1)

            await pilot.press("s")
            await pilot.pause()
            assert application.status == "este nivel no se puede ordenar"
            await pilot.press("d")
            await pilot.pause()
            assert application.status == "aquí no hay de dónde quitar"
            assert application.screen is browser, "ninguna ventana se abrió"

    asyncio.run(scenario())
