"""The playlists of «Música local»: `.m3u8` files, their levels, and the keys."""

from __future__ import annotations

import asyncio

import pytest
from app_helpers import FakeMpv, isolate_runtime, settle
from test_local import FakeSession, make_flac
from textual.widgets import Input

from tidalamp import auth, config, library, local, local_playlists
from tidalamp.app import BrowserScreen, RowList, TidalAmp
from tidalamp.queue import Entry
from tidalamp.screens import PlaylistNameScreen, PlaylistPickerScreen
from tidalamp.screens.tracks import (
    LOCAL_PLAYLIST_ACTIONS,
    LOCAL_TRACK_ACTIONS,
    container_actions_for,
)


def a_file(tmp_path, name: str, **tags) -> Entry:
    path = make_flac(tmp_path / f"{name}.flac", title=name, **tags)
    return Entry.from_local(local.read(path))


# ------------------------------------------------------------------- the files


def test_a_playlist_is_an_m3u8_any_player_opens(tmp_path):
    one, two = a_file(tmp_path, "Uno", artist="TOOL"), a_file(tmp_path, "Dos")
    playlist = local_playlists.create("Viaje", [one, two])

    text = playlist.path.read_text(encoding="utf-8")
    assert playlist.path.name == "Viaje.m3u8"
    assert text.splitlines() == [
        "#EXTM3U",
        f"#EXTINF:0,{one.label}",
        one.url,
        f"#EXTINF:0,{two.label}",
        two.url,
    ]
    assert local_playlists.load(playlist.path).tracks == [one.url, two.url]


def test_a_name_no_file_can_carry_is_kept_inside_the_file(tmp_path):
    playlist = local_playlists.create("AC/DC: lo mejor")
    assert playlist.path.name == "AC_DC_ lo mejor.m3u8"
    assert local_playlists.load(playlist.path).name == "AC/DC: lo mejor"


def test_a_second_playlist_by_the_same_name_is_refused(tmp_path):
    local_playlists.create("Viaje")
    with pytest.raises(local_playlists.PlaylistExists):
        local_playlists.create("viaje")
    with pytest.raises(ValueError):
        local_playlists.create("   ")


def test_a_playlist_from_elsewhere_is_read_with_its_relative_lines(tmp_path):
    """A BOM, relative paths, a `file://` URI and a stream: what other
    players write. The stream is left out, it is not a file here."""
    music = tmp_path / "music"
    make_flac(music / "a.flac", title="A")
    written = tmp_path / "listas" / "ajena.m3u"
    written.parent.mkdir()
    written.write_text(
        "﻿#EXTM3U\n#EXTINF:10,X - A\n../music/a.flac\n"
        f"{(music / 'a.flac').as_uri()}\nhttp://radio.example/stream\n",
        encoding="utf-8",
    )
    found = local_playlists.load(written)
    assert found.name == "ajena"
    assert found.tracks == [str(music / "a.flac")] * 2
    assert found.items[0].info == "10,X - A"


def test_add_remove_move_rename_and_delete(tmp_path):
    one, two, three = (a_file(tmp_path, name) for name in ("Uno", "Dos", "Tres"))
    path = local_playlists.create("Viaje", [one]).path

    assert local_playlists.add(path, [two, three, one]) == 3
    assert local_playlists.load(path).tracks == [one.url, two.url, three.url, one.url]

    # A file in it twice loses its first appearance.
    assert local_playlists.remove(path, one.url) == "Viaje"
    assert local_playlists.load(path).tracks == [two.url, three.url, one.url]
    with pytest.raises(local_playlists.TrackNotInPlaylist):
        local_playlists.remove(path, "/no/está.flac")

    local_playlists.move(path, 0, two.url, 1)
    assert local_playlists.load(path).tracks == [three.url, two.url, one.url]
    # A stale position moves nothing rather than the neighbour.
    with pytest.raises(local_playlists.TrackNotInPlaylist):
        local_playlists.move(path, 0, two.url, 1)

    renamed = local_playlists.rename(path, "Ruta")
    assert not path.exists() and renamed.path.name == "Ruta.m3u8"
    assert local_playlists.load(renamed.path).tracks == [three.url, two.url, one.url]

    assert local_playlists.delete(renamed.path) == "Ruta"
    assert local_playlists.listing() == []
    # The music is not touched.
    assert all(make.exists() for make in tmp_path.glob("*.flac"))


def test_only_files_go_in(tmp_path):
    kept, skipped = local_playlists.local_only(
        [a_file(tmp_path, "Uno"), Entry(id=1, title="Schism", artist="TOOL")]
    )
    assert [entry.title for entry in kept] == ["Uno"] and skipped == 1


# ------------------------------------------------------------------ the levels


def _playlists_row():
    section = next(row for row in library.root(FakeSession()) if row.key == "local")
    return next(row for row in section.loader() if row.key == "local:playlists")


def test_playlists_live_inside_local_music(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_FOLDERS", (str(tmp_path),))
    one, two = a_file(tmp_path, "Uno"), a_file(tmp_path, "Dos")
    local_playlists.create("Viaje", [two, one])
    gone = local_playlists.create("Rota")
    local_playlists.add(
        gone.path, [Entry.from_local(local.Track("/x/y.flac", "y", "", ""))]
    )

    new, rota, viaje = _playlists_row().loader()
    assert new.key == library.NEW_LOCAL_PLAYLIST and new.loader is None
    assert (rota.label, viaje.label) == ("Rota", "Viaje")
    assert viaje.editable and not viaje.is_tidal and viaje.detail == "2 pistas"
    assert container_actions_for(viaje) == LOCAL_PLAYLIST_ACTIONS

    # In its own order, the one it was made in.
    assert [row.entry.title for row in viaje.loader()] == ["Dos", "Uno"]
    (missing,) = rota.loader()
    assert missing.detail == "el fichero no está" and missing.entry.title == "y"


def test_a_local_track_offers_adding_to_a_playlist(tmp_path):
    assert "playlist" in [action for action, *_rest in LOCAL_TRACK_ACTIONS]
    assert "radio" not in [action for action, *_rest in LOCAL_TRACK_ACTIONS]


def test_a_forgotten_playlist_level_reads_its_file_again(tmp_path, monkeypatch):
    """The level reads the file when it loads, so forgetting it after a write
    is enough: a snapshot of the list would come back as it was."""
    monkeypatch.setattr(config, "LOCAL_FOLDERS", (str(tmp_path),))
    one, two = a_file(tmp_path, "Uno"), a_file(tmp_path, "Dos")
    playlist = local_playlists.create("Viaje", [one])
    (_new, row) = _playlists_row().loader()
    assert len(row.loader()) == 1

    local_playlists.add(playlist.path, [two])
    library.forget_local_playlists(row.key)
    assert [r.entry.title for r in row.loader()] == ["Uno", "Dos"]


def test_reloading_a_local_level_sees_new_files(tmp_path, monkeypatch):
    """`R` drops the scan: a file copied into a record shows up in the
    record's own level, not only in the section's."""
    monkeypatch.setattr(config, "LOCAL_FOLDERS", (str(tmp_path),))
    make_flac(tmp_path / "Lateralus" / "01.flac", album="Lateralus", tracknumber="1")
    section = next(row for row in library.root(FakeSession()) if row.key == "local")
    albums = next(row for row in section.loader() if row.key == "local:albums")
    (record,) = albums.loader()
    assert len(record.loader()) == 1

    make_flac(tmp_path / "Lateralus" / "02.flac", album="Lateralus", tracknumber="2")
    library.forget_local()
    assert len(record.loader()) == 2


# --------------------------------------------------------------------- the app


def offline_app() -> TidalAmp:
    return TidalAmp(auth.OfflineSession(), FakeMpv())  # type: ignore[arg-type]


def _rows(application) -> list:
    return application.screen.query_one(RowList).rows


async def _open(pilot, application, label: str) -> None:
    rows = _rows(application)
    application.screen.query_one(RowList).cursor = [r.label for r in rows].index(label)
    await pilot.press("enter")
    await settle(
        pilot, lambda: [r.label for r in _rows(application)] != [r.label for r in rows]
    )


def test_a_playlist_is_made_and_filled_from_the_browser(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(config, "LOCAL_FOLDERS", (str(tmp_path),))
    make_flac(tmp_path / "a.flac", title="Schism", artist="TOOL")

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            await pilot.press("l")
            await settle(
                pilot,
                lambda: (
                    isinstance(application.screen, BrowserScreen)
                    and bool(_rows(application))
                ),
            )
            await _open(pilot, application, "Playlists")
            assert [r.label for r in _rows(application)] == ["+ nueva playlist…"]

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(application.screen, PlaylistNameScreen)
            application.screen.query_one(Input).value = "Viaje"
            await pilot.press("enter")
            await settle(pilot, lambda: len(_rows(application)) == 2)
            assert _rows(application)[1].label == "Viaje"

            await pilot.press("backspace")
            await pilot.pause()
            await _open(pilot, application, "Todas las pistas")
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("l")
            await settle(
                pilot,
                lambda: (
                    isinstance(application.screen, PlaylistPickerScreen)
                    and len(application.screen.query_one(RowList).rows) == 2
                ),
            )
            await pilot.press("down", "enter")
            await pilot.pause()

            (playlist,) = local_playlists.listing()
            assert playlist.tracks == [str(tmp_path / "a.flac")]
            assert application.status == "1 pistas añadidas a «Viaje»"

    asyncio.run(scenario())


def test_p_saves_a_queue_of_files_as_a_local_playlist(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            application.queue.replace(
                [a_file(tmp_path, "Uno"), Entry(id=7, title="Schism", artist="TOOL")],
                start=-1,
            )
            application.queue_view.sync()
            await pilot.press("p")
            await pilot.pause()
            application.screen.query_one(Input).value = "Cola"
            await pilot.press("enter")
            await pilot.pause()

            (playlist,) = local_playlists.listing()
            assert playlist.name == "Cola" and len(playlist.tracks) == 1
            assert application.status == (
                "playlist local «Cola» creada con 1 pistas (1 de TIDAL fuera)"
            )

    asyncio.run(scenario())


async def _library(pilot, application) -> None:
    await pilot.press("l")
    await settle(
        pilot,
        lambda: (
            isinstance(application.screen, BrowserScreen) and bool(_rows(application))
        ),
    )


def test_r_in_the_library_picks_up_files_copied_in_since(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(config, "LOCAL_FOLDERS", (str(tmp_path),))
    make_flac(tmp_path / "a.flac", title="Uno")

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            await _library(pilot, application)
            await _open(pilot, application, "Todas las pistas")
            assert len(_rows(application)) == 1

            make_flac(tmp_path / "b.flac", title="Dos")
            await pilot.press("R")
            await settle(pilot, lambda: len(_rows(application)) == 2)

    asyncio.run(scenario())


def test_a_track_is_moved_and_taken_out_of_a_local_playlist(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    monkeypatch.setattr(config, "LOCAL_FOLDERS", (str(tmp_path),))
    one, two = a_file(tmp_path, "Uno"), a_file(tmp_path, "Dos")
    path = local_playlists.create("Viaje", [one, two]).path

    async def scenario() -> None:
        application = offline_app()
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            await _library(pilot, application)
            await _open(pilot, application, "Playlists")
            await _open(pilot, application, "Viaje")

            await pilot.press("alt+down")
            await pilot.pause()
            assert local_playlists.load(path).tracks == [two.url, one.url]
            assert [r.entry.title for r in _rows(application)] == ["Dos", "Uno"]

            await pilot.press("d")
            await pilot.pause()
            await pilot.press("up", "enter")
            await pilot.pause()
            assert local_playlists.load(path).tracks == [two.url]
            assert application.status == "«Uno» quitada de «Viaje»"

    asyncio.run(scenario())


# ------------------------------------------------- `p` with a mixed queue


def _mixed_save(monkeypatch, tmp_path, answer: str):
    """Save a queue of two TIDAL tracks and one file, answering ``answer``
    to the question; returns what TIDAL was sent, and the app's status."""
    from tidalamp import playlists
    from tidalamp.library_tasks import LibraryTasks
    from tidalamp.screens import ChoiceScreen

    isolate_runtime(monkeypatch)
    sent: list[list[int]] = []
    monkeypatch.setattr(auth, "ensure_fresh", lambda session: False)
    monkeypatch.setattr(
        playlists,
        "save_queue_playlist",
        lambda session, title, entries: (
            sent.append([e.id for e in entries]) or len(entries)
        ),
    )
    status: list[str] = []
    asked: list[list[str]] = []

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())  # type: ignore[arg-type]
        async with application.run_test(size=(100, 34)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(
                application, "call_from_thread", lambda callback, *a: callback(*a)
            )
            monkeypatch.setattr(
                application.tasks,
                "save_worker",
                lambda *args: LibraryTasks.save_worker.__wrapped__(
                    application.tasks, *args
                ),
            )
            application.queue.replace(
                [
                    Entry(id=1, title="Schism", artist="TOOL"),
                    a_file(tmp_path, "Uno"),
                    Entry(id=2, title="Sober", artist="TOOL"),
                ],
                start=-1,
            )
            application.queue_view.sync()
            await pilot.press("p")
            await pilot.pause()
            application.screen.query_one(Input).value = "Mezcla"
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(application.screen, ChoiceScreen)
            asked.append([label for _value, label in application.screen._options])
            application.screen.dismiss(answer)
            await pilot.pause()
            status.append(application.status)

    asyncio.run(scenario())
    return sent, status[0], asked[0]


def test_a_mixed_queue_asks_where_and_says_what_stays_out(monkeypatch, tmp_path):
    sent, status, asked = _mixed_save(monkeypatch, tmp_path, "tidal")
    assert asked == [
        "en TIDAL: 2 pistas (1 locales fuera)",
        "como playlist local: 1 pistas (2 de TIDAL fuera)",
        "cancelar",
    ]
    # Never a file's negative id: TIDAL gets its own tracks only.
    assert sent == [[1, 2]]
    assert status == "playlist «Mezcla» creada con 2 pistas (1 locales fuera)"
    assert local_playlists.listing() == []


def test_a_mixed_queue_can_go_to_a_local_playlist(monkeypatch, tmp_path):
    sent, status, _asked = _mixed_save(monkeypatch, tmp_path, "local")
    assert sent == []
    (playlist,) = local_playlists.listing()
    assert playlist.name == "Mezcla" and len(playlist.tracks) == 1
    assert status == "playlist local «Mezcla» creada con 1 pistas (2 de TIDAL fuera)"


def test_cancelling_a_mixed_queue_saves_nothing(monkeypatch, tmp_path):
    sent, _status, _asked = _mixed_save(monkeypatch, tmp_path, "cancel")
    assert sent == [] and local_playlists.listing() == []


def test_tidal_is_never_sent_a_files_id():
    """The guard under the UI: a local entry that reaches the write is left
    out of the request, not sent as a negative id."""
    from tidalamp import playlists

    class FakePlaylist:
        def __init__(self):
            self.items = []

        def add(self, items, **kwargs):
            self.items.extend(items)
            return items

    made = FakePlaylist()

    class FakeUser:
        def create_playlist(self, title, description):
            return made

    session = type("S", (), {"user": FakeUser()})()
    entries = [
        Entry(id=5, title="Schism", artist="TOOL"),
        Entry.from_local(local.Track("/m/a.flac", "a", "", "")),
    ]
    assert playlists.save_queue_playlist(session, "X", entries) == 1
    assert made.items == ["5"]
