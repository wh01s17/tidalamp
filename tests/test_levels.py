"""What every level is made of: pages that hang a «más…» row off a full
one, the cache of levels, the filter's matching and the orders a level is
sorted in and remembers."""

from __future__ import annotations

from library_fakes import FakeSession, favourite_tracks_level, track_row

from tidalamp import levels, library
from tidalamp.levels import PAGE, Row
from tidalamp.queue import Entry


def test_a_short_page_has_no_more_row():
    rows = favourite_tracks_level(FakeSession(total=7))
    assert len(rows) == 7
    assert all(r.more is None for r in rows)


def test_a_full_page_offers_more():
    rows = favourite_tracks_level(FakeSession(total=PAGE + 5))
    assert len(rows) == PAGE + 1
    assert rows[-1].more is not None
    assert rows[-1].entry is None


def test_following_more_fetches_the_next_offset():
    session = FakeSession(total=PAGE + 5)
    rows = favourite_tracks_level(session)
    nxt = rows[-1].more()
    assert session.favorites.calls == [(0, PAGE), (PAGE, PAGE)]
    assert len(nxt) == 5
    assert all(r.more is None for r in nxt)


def test_an_exact_multiple_does_not_offer_an_empty_page_when_the_count_is_known():
    session = FakeSession(total=PAGE)
    rows = favourite_tracks_level(session)
    assert len(rows) == PAGE
    assert all(r.more is None for r in rows)


def test_an_exact_multiple_offers_one_empty_page_without_a_count():
    # With no count we cannot tell a full last page from a truncated one, so we
    # offer "más…" and it resolves to an empty level rather than lying.
    session = FakeSession(total=PAGE, counts=False)
    rows = favourite_tracks_level(session)
    assert rows[-1].more is not None
    assert rows[-1].more() == []


def test_a_short_page_is_not_the_end_when_the_count_says_otherwise():
    """The real bug: 100 favourites asked for, 90 returned, 766 in the account.

    Reading the short page as the end meant the other 676 were unreachable.
    """
    session = FakeSession(total=766, filtered=10)
    rows = favourite_tracks_level(session)

    assert len(rows) == 91  # 90 pistas y la fila «más…»
    assert rows[-1].more is not None
    assert rows[-1].detail == f"siguientes {PAGE} de 766"

    # And it keeps going: the offset advances by the page size, not by how
    # many survived the filter.
    second = rows[-1].more()
    assert session.favorites.calls == [(0, PAGE), (PAGE, PAGE)]
    assert second[-1].more is not None


def test_paging_a_filtered_level_reaches_the_end():
    session = FakeSession(total=250, filtered=10)
    rows = favourite_tracks_level(session)
    pages = 1
    while rows[-1].more is not None:
        rows = rows[-1].more()
        pages += 1
        assert pages < 10, "no debería hacer falta paginar eternamente"

    assert pages == 3  # offsets 0, 100 y 200
    assert session.favorites.calls == [(0, PAGE), (PAGE, PAGE), (2 * PAGE, PAGE)]


# ------------------------------------------------------------------- caching


def test_a_level_is_fetched_once_and_then_remembered():
    calls: list[int] = []

    def loader() -> list[Row]:
        calls.append(1)
        return [Row(label="x")]

    cached = levels.cached("nivel", loader)

    assert cached()[0].label == "x"
    assert cached()[0].label == "x"
    assert calls == [1]

    levels.forget("nivel")
    cached()
    assert calls == [1, 1]


def test_the_cached_level_is_the_same_list_the_browser_extends():
    """Loading another page mutates the level in place; the cache must see it."""
    cached = levels.cached("nivel", lambda: [Row(label="x")])
    rows = cached()
    rows.append(Row(label="y"))

    assert [r.label for r in cached()] == ["x", "y"]


def test_forgetting_everything_clears_every_level():
    levels.cached("a", lambda: [Row(label="a")])()
    levels.cached("b", lambda: [Row(label="b")])()
    levels.forget()
    assert levels._LEVELS == {}


def test_favourite_levels_are_cached_too(monkeypatch):
    session = FakeSession(total=3)
    library.root(session)[1].loader()
    library.root(session)[1].loader()
    assert session.favorites.calls == [(0, PAGE)]


def test_the_filter_reads_label_and_detail():
    row = Row(label="Mis mejores canciones", detail="42 pistas")
    assert levels.matches("mejores", row)
    assert levels.matches("42", row)
    assert not levels.matches("peores", row)


def test_the_filter_ignores_case_and_accents():
    """Typing accents to search is a tax nobody pays, and TIDAL writes the
    same name both ways depending on the release."""
    row = Row(label="Sinfonía nº 9")
    assert levels.matches("sinfonia", row)
    assert levels.matches("SINFONÍA", row)
    assert levels.matches("sinfonía", row)


def test_every_term_has_to_match_somewhere():
    row = track_row("Schism", album="Lateralus")
    assert levels.matches("tool schism", row)
    assert levels.matches("schism tool", row)
    assert not levels.matches("tool sober", row)


def test_a_track_is_found_by_its_album_even_when_no_column_shows_it():
    """The album is what people remember, and it is only on the line if the
    user turned that column on."""
    row = track_row("Schism", album="Lateralus")
    assert levels.matches("lateralus", row)
    assert levels.matches("tool lateralus", row)


def test_a_level_row_without_an_entry_is_matched_by_its_name():
    row = Row(label="Pistas favoritas", key="fav:tracks")
    assert levels.matches("favoritas", row)
    assert not levels.matches("albumes", row)


def test_an_empty_query_matches_everything():
    assert levels.matches("   ", track_row("Schism"))


def test_a_level_tidal_cannot_sort_is_sorted_here_with_more_last():
    """Inside an album or an artist TIDAL takes no order. The rows are sorted
    here, into a new list: the cached level stays as TIDAL gave it."""
    titles = ["Sober", "Aenema", "Schism"]
    albums = ["Undertow", "Aenima", "Lateralus"]
    rows = [
        Row(label=title, entry=Entry(id=i, title=title, artist="TOOL", album=album))
        for i, (title, album) in enumerate(zip(titles, albums, strict=True))
    ]
    rows.append(Row(label="más…", more=list))

    by_name = levels._in_order(rows, levels.Order("name"))
    assert [row.label for row in by_name] == ["Aenema", "Schism", "Sober", "más…"]
    by_album = levels._in_order(rows, levels.Order("album", descending=True))
    assert [row.label for row in by_album] == ["Sober", "Schism", "Aenema", "más…"]
    assert [row.label for row in rows][:3] == titles


def test_the_order_picked_for_a_level_survives_a_restart():
    """Kept on disk by the level's key, and read back as that level's own
    order: a playlist's date is still its creation date the next day."""
    rows = {row.key: row for row in library.root(FakeSession())}
    playlists, tracks = rows["playlists"], rows["fav:tracks"]

    levels.remember(playlists, playlists.orders[1])
    levels.remember(tracks, levels.Order("album", descending=True))
    levels.remember(tracks, levels.Order("name"))

    levels._CHOSEN = None  # what a new process starts with
    assert levels.chosen(tracks) == levels.Order("name")
    back = levels.chosen(playlists)
    assert back is not None and back.created
    assert levels.order_label(back) == "fecha de creación: recientes primero"

    levels.remember(tracks, None)
    levels._CHOSEN = None
    assert levels.chosen(tracks) is None


def test_an_order_that_cannot_be_written_still_holds_and_says_why(tmp_path, monkeypatch):
    """Not written is not forgotten: the order holds for the session, and the
    error goes back to the app, which says so, instead of being swallowed."""

    def refused(*args, **kwargs):
        raise PermissionError("read-only")

    monkeypatch.setattr(levels, "ORDERS_FILE", tmp_path / "library-orders.json")
    monkeypatch.setattr(levels, "write_atomically", refused)
    tracks = {row.key: row for row in library.root(FakeSession())}["fav:tracks"]
    assert isinstance(levels.remember(tracks, levels.Order("name")), OSError)
    assert levels.chosen(tracks) == levels.Order("name")


def test_a_broken_orders_file_is_no_orders_at_all():
    levels.ORDERS_FILE.write_text("{esto no es json", encoding="utf-8")
    tracks = next(row for row in library.root(FakeSession()) if row.key == "fav:tracks")
    assert levels.chosen(tracks) is None
