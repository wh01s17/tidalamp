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
