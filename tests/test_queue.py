from tidalamp.queue import Entry, Queue, Repeat


def make(entries, **kwargs):
    q = Queue()
    q.replace(entries, start=kwargs.get("start", -1))
    return q


def test_next_walks_forward_and_stops(entries):
    q = make(entries)
    q.playing = 0
    assert q.next_index() == 1
    q.playing = len(entries) - 1
    assert q.next_index() is None


def test_repeat_queue_wraps(entries):
    q = make(entries)
    q.repeat = Repeat.QUEUE
    q.playing = len(entries) - 1
    assert q.next_index() == 0
    q.playing = 0
    assert q.prev_index() == len(entries) - 1


def test_repeat_track_stays(entries):
    q = make(entries)
    q.repeat = Repeat.TRACK
    q.playing = 2
    assert q.next_index() == 2


def test_shuffle_keeps_current_first_and_visits_everything(entries):
    q = make(entries)
    q.playing = 3
    q.shuffle = True
    seen = [3]
    while (nxt := q.next_index()) is not None:
        seen.append(nxt)
        q.playing = nxt
    assert sorted(seen) == list(range(len(entries)))


def test_shuffle_off_restores_order(entries):
    q = make(entries)
    q.shuffle = True
    q.shuffle = False
    assert [e.id for e in q] == [0, 1, 2, 3, 4]
    q.playing = 1
    assert q.next_index() == 2


def test_remove_shifts_the_cursor(entries):
    q = make(entries)
    q.playing = 3
    q.remove(1)
    assert q.playing == 2
    assert [e.id for e in q] == [0, 2, 3, 4]


def test_remove_of_the_playing_track_clears_the_cursor(entries):
    q = make(entries)
    q.playing = 2
    q.remove(2)
    assert q.playing == -1


def test_move_swaps_and_follows_the_cursor(entries):
    q = make(entries)
    q.playing = 1
    assert q.move(1, 1) == 2
    assert [e.id for e in q] == [0, 2, 1, 3, 4]
    assert q.playing == 2


def test_move_at_the_edges_is_a_no_op(entries):
    q = make(entries)
    assert q.move(0, -1) == 0
    assert q.move(len(entries) - 1, 1) == len(entries) - 1
    assert [e.id for e in q] == [0, 1, 2, 3, 4]


def test_move_does_not_reshuffle(entries):
    q = make(entries)
    q.shuffle = True
    order_before = [q.entries[i].id for i in q._order]
    q.move(0, 1)
    # The same songs in the same playback order, whatever their new indices.
    assert [q.entries[i].id for i in q._order] == order_before


def test_persistence_roundtrip(entries, queue_file):
    q = make(entries)
    q.playing = 2
    q.repeat = Repeat.TRACK
    q.shuffle = True
    q.save()

    restored = Queue()
    assert restored.load() is True
    assert [e.id for e in restored] == [e.id for e in entries]
    assert restored.repeat is Repeat.TRACK
    assert restored.shuffle is True
    # Nothing is playing after a restart, but we remember where we were.
    assert restored.playing == -1
    assert restored.resume_at == 2


def test_load_without_a_file_is_false(queue_file):
    assert Queue().load() is False


def test_load_of_corrupt_json_is_false(queue_file):
    queue_file.write_text("{not json", encoding="utf-8")
    assert Queue().load() is False


def test_entry_dict_roundtrip():
    entry = Entry(id=7, title="x", artist="y", album="z", duration=125, art_url="u")
    clone = Entry.from_dict(entry.to_dict())
    assert clone == entry
    assert clone.length == "2:05"


# --------------------------------------------------------------------- row ids


def test_every_row_gets_its_own_id_even_for_the_same_song():
    q = Queue()
    q.append([Entry(id=7, title="x", artist="y"), Entry(id=7, title="x", artist="y")])
    assert q[0].uid != q[1].uid


def test_a_row_id_survives_a_reorder():
    q = Queue()
    q.append([Entry(id=i, title=f"t{i}", artist="a") for i in range(3)])
    uids = [e.uid for e in q]

    q.move(0, 1)

    assert [e.uid for e in q] == [uids[1], uids[0], uids[2]]


def test_row_ids_survive_a_save_and_never_collide_afterwards(queue_file, entries):
    q = Queue()
    q.append(entries)
    saved = [e.uid for e in q]
    q.save()

    restored = Queue()
    assert restored.load() is True
    assert [e.uid for e in restored] == saved

    # The counter has to come back ahead of what was on disk, or the next row
    # added would reuse an id that MPRIS clients still hold.
    fresh = Entry(id=99, title="new", artist="a")
    assert fresh.uid not in saved


def test_a_queue_written_before_row_ids_still_loads(queue_file):
    queue_file.write_text(
        '{"entries": [{"id": 1, "title": "x", "artist": "y"}], "playing": 0}',
        encoding="utf-8",
    )
    restored = Queue()
    assert restored.load() is True
    assert restored[0].uid > 0


# --------------------------------------------------------------- insert_next


def play_order(q, limit=20):
    """The titles the queue would visit from here, in order."""
    seen = []
    while (index := q.next_index()) is not None and len(seen) < limit:
        q.playing = index
        seen.append(q[index].title)
    return seen


def test_insert_next_lands_right_after_the_current_track(entries):
    q = make(entries)
    q.playing = 1
    extra = [Entry(id=90, title="x", artist="a"), Entry(id=91, title="y", artist="a")]

    assert q.insert_next(extra) == 2
    assert [e.title for e in q] == ["t0", "t1", "x", "y", "t2", "t3", "t4"]
    # The cursor still points at the same song, which is now further along.
    assert q.current.title == "t1"
    assert play_order(q) == ["x", "y", "t2", "t3", "t4"]


def test_insert_next_plays_next_under_shuffle_too(entries):
    """The whole point is play order, and under shuffle that is not the list."""
    q = make(entries)
    q.playing = 2
    q.shuffle = True

    q.insert_next([Entry(id=90, title="x", artist="a")])
    order = play_order(q)
    assert order[0] == "x"
    assert sorted(order) == sorted(["x", "t0", "t1", "t3", "t4"])


def test_insert_next_with_nothing_playing_goes_to_the_end(entries):
    """There is no "after this" without a this; the end is what comes next."""
    q = make(entries)
    assert q.playing == -1
    q.insert_next([Entry(id=90, title="x", artist="a")])
    assert [e.title for e in q][-1] == "x"


def test_insert_next_into_an_empty_queue_just_adds(entries):
    q = Queue()
    assert q.insert_next([Entry(id=90, title="x", artist="a")]) == 1
    assert [e.title for e in q] == ["x"]


def test_insert_next_of_nothing_changes_nothing(entries):
    q = make(entries)
    q.playing = 1
    assert q.insert_next([]) == 0
    assert len(q) == len(entries)
