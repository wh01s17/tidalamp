"""Writing to the playlists this account made: creating one from the queue,
adding to one, taking a track out, and never sending a write twice."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tidalamp import levels, playlists
from tidalamp.levels import PAGE, Row
from tidalamp.queue import Entry

# ------------------------------------------------------- playlist creation


class WritablePlaylist:
    def __init__(self, fail_on: int | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[tuple[list[str], bool, int, int]] = []

    def add(self, media_ids, allow_duplicates=False, position=-1, limit=100):
        batch = list(media_ids)
        self.calls.append((batch, allow_duplicates, position, limit))
        if self.fail_on == len(self.calls):
            raise RuntimeError("sin red")
        return batch


class PlaylistOwner:
    def __init__(self, playlist: WritablePlaylist) -> None:
        self.playlist = playlist
        self.calls: list[tuple[str, str]] = []

    def create_playlist(self, title: str, description: str):
        self.calls.append((title, description))
        return self.playlist


def queue_entries(count: int) -> list[Entry]:
    return [Entry(id=i, title=f"pista {i}", artist="artista") for i in range(count)]


def test_saving_a_queue_creates_and_fills_the_playlist_in_order_and_batches():
    playlist = WritablePlaylist()
    owner = PlaylistOwner(playlist)
    session = SimpleNamespace(user=owner)
    entries = queue_entries(700)
    levels.cached("playlists", lambda: [Row(label="vieja")])()

    added = playlists.save_queue_playlist(session, "Viaje", entries)

    assert owner.calls == [("Viaje", "")]
    assert [len(call[0]) for call in playlist.calls] == [100] * 7
    assert [ident for batch, *_ in playlist.calls for ident in batch] == [
        str(entry.id) for entry in entries
    ]
    assert all(
        call[1:] == (True, -1, playlists.PLAYLIST_BATCH) for call in playlist.calls
    )
    assert added == 700
    assert "playlists" not in levels._LEVELS


def test_a_failed_batch_reports_the_completed_count_and_keeps_the_source_queue():
    playlist = WritablePlaylist(fail_on=3)
    owner = PlaylistOwner(playlist)
    session = SimpleNamespace(user=owner)
    entries = queue_entries(205)
    before = [entry.id for entry in entries]

    with pytest.raises(playlists.PlaylistSaveFailed) as raised:
        playlists.save_queue_playlist(session, "Viaje", entries)

    assert raised.value.title == "Viaje"
    assert raised.value.added == 200
    assert raised.value.total == 205
    assert str(raised.value) == "sin red"
    assert [entry.id for entry in entries] == before
    assert len(playlist.calls) == 3


# ------------------------------------------- añadir a una playlist existente


class FakeUserPlaylist:
    def __init__(self, name="Mi playlist", fail_after=None):
        self.name = name
        self.batches: list[list[str]] = []
        self._fail_after = fail_after

    def add(self, items, allow_duplicates=False, position=-1, limit=100):
        if self._fail_after is not None and len(self.batches) >= self._fail_after:
            raise RuntimeError("TIDAL dijo que no")
        self.batches.append(list(items))
        return list(range(len(items)))


class FakeReadOnlyPlaylist:
    """What a playlist someone else owns parses into: no `add`."""

    name = "De otra persona"


class FakePlaylistSession:
    def __init__(self, playlist):
        self._playlist = playlist

    def playlist(self, playlist_id):
        return self._playlist


def entries(count):
    return [Entry(id=i, title=f"t{i}", artist="a") for i in range(count)]


def test_adding_to_a_playlist_sends_every_track_in_batches():
    playlist = FakeUserPlaylist()
    added = playlists.add_to_playlist(
        FakePlaylistSession(playlist), "7", entries(250), batch_size=100
    )

    assert added == 250
    assert [len(b) for b in playlist.batches] == [100, 100, 50]
    assert [b[0] for b in playlist.batches] == ["0", "100", "200"], "en orden"


def test_a_batch_that_fails_keeps_what_already_went_in():
    playlist = FakeUserPlaylist(fail_after=2)

    with pytest.raises(playlists.PlaylistSaveFailed) as caught:
        playlists.add_to_playlist(
            FakePlaylistSession(playlist), "7", entries(250), batch_size=100
        )

    assert caught.value.added == 200
    assert caught.value.total == 250
    assert len(playlist.batches) == 2, "no se deshace lo que sí entró"


def test_a_playlist_this_account_cannot_write_to_is_reported():
    with pytest.raises(playlists.PlaylistNotWritable):
        playlists.add_to_playlist(
            FakePlaylistSession(FakeReadOnlyPlaylist()), "7", entries(1)
        )


def test_adding_forgets_the_listing_and_that_playlist_level():
    """Otherwise opening it afterwards shows it as it was."""
    levels._LEVELS["playlists"] = ["viejo"]
    levels._LEVELS["playlist:7"] = ["viejo"]

    playlists.add_to_playlist(FakePlaylistSession(FakeUserPlaylist()), "7", entries(1))

    assert "playlists" not in levels._LEVELS
    assert "playlist:7" not in levels._LEVELS


class FakeOwnedPlaylist:
    """A playlist the account owns: it lists its tracks and removes by index."""

    def __init__(self, ids, name="Mía"):
        self.name = name
        self.ids = list(ids)
        self.num_tracks = len(self.ids)
        self.pages: list[int] = []
        self.removed: list[int] = []

    def tracks(self, limit=None, offset=0, **order):
        self.pages.append(offset)
        return [SimpleNamespace(id=i) for i in self.ids[offset : offset + limit]]

    def remove_by_index(self, index):
        self.removed.append(index)
        del self.ids[index]
        return True


def test_removing_from_a_playlist_finds_the_track_past_the_first_page(monkeypatch):
    """tidalapi's own lookup reads one page and calls a later track absent."""
    monkeypatch.setattr(
        levels,
        "_LEVELS",
        {"playlist:7": [], "playlist:7|name-asc": [], "playlists": [], "fav:tracks": []},
    )
    playlist = FakeOwnedPlaylist(range(250))

    name = playlists.remove_from_playlist(
        FakePlaylistSession(playlist), "7", Entry(id=230, title="t", artist="a")
    )

    assert name == "Mía"
    assert playlist.removed == [230]
    # Three pages to find it, then one track read to confirm the position.
    assert playlist.pages == [0, PAGE, 2 * PAGE, 230]
    # The playlist in every order, and the list of playlists with its count.
    assert set(levels._LEVELS) == {"fav:tracks"}


def test_a_playlist_someone_else_owns_is_left_alone():
    with pytest.raises(playlists.PlaylistNotWritable):
        playlists.remove_from_playlist(
            FakePlaylistSession(FakeReadOnlyPlaylist()),
            "7",
            Entry(id=1, title="t", artist="a"),
        )


def test_a_track_already_gone_says_so_and_removes_nothing():
    playlist = FakeOwnedPlaylist([1, 2])
    with pytest.raises(playlists.TrackNotInPlaylist):
        playlists.remove_from_playlist(
            FakePlaylistSession(playlist), "7", Entry(id=9, title="t", artist="a")
        )
    assert playlist.removed == []


class FakeGappyPlaylist(FakeOwnedPlaylist):
    """A playlist TIDAL hands back with gaps: a track it cannot serve is left
    out of a page after the limit is applied, so positions after it shift."""

    def __init__(self, ids, hidden):
        super().__init__(ids)
        self.hidden = set(hidden)

    def tracks(self, limit=None, offset=0, **order):
        self.pages.append(offset)
        window = self.ids[offset : offset + limit]
        return [SimpleNamespace(id=i) for i in window if i not in self.hidden]


def test_a_gap_in_the_page_does_not_delete_the_neighbour():
    """Counting the page put track 7 at position 6, behind the hidden 3; the
    position is checked before deleting, and the real one is 7."""
    playlist = FakeGappyPlaylist(range(10), hidden={3})

    playlists.remove_from_playlist(
        FakePlaylistSession(playlist), "7", Entry(id=7, title="t", artist="a")
    )

    assert playlist.removed == [7]
    assert 7 not in playlist.ids and 6 in playlist.ids


def test_a_playlist_whose_creation_answer_is_lost_is_not_created_twice(monkeypatch):
    import requests

    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)

    class LostAnswer(PlaylistOwner):
        def create_playlist(self, title, description):
            super().create_playlist(title, description)
            raise requests.ReadTimeout()

    owner = LostAnswer(WritablePlaylist())
    with pytest.raises(requests.ReadTimeout):
        playlists.save_queue_playlist(
            SimpleNamespace(user=owner), "Viaje", queue_entries(3)
        )

    assert len(owner.calls) == 1, "un reintento sería una segunda playlist"


def test_a_batch_whose_answer_is_lost_is_not_sent_twice(monkeypatch):
    import requests

    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)

    class LostBatch(FakeUserPlaylist):
        def add(self, items, **kwargs):
            self.batches.append(list(items))
            raise requests.ReadTimeout()

    playlist = LostBatch()
    with pytest.raises(playlists.PlaylistSaveFailed) as caught:
        playlists.add_to_playlist(FakePlaylistSession(playlist), "7", entries(50))

    assert len(playlist.batches) == 1, "un reintento duplicaría el lote"
    assert caught.value.added == 0
