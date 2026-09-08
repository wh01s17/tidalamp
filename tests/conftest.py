"""Shared stubs.

The tests never touch TIDAL or the network: sessions, tracks and manifests are
plain stand-ins that expose only the attributes the code under test reads.
"""

from __future__ import annotations

import pytest

from tidalamp.queue import Entry


class FakeTrack:
    def __init__(self, id: int, name: str = "", artist: str = "", duration: int = 200):
        self.id = id
        self.name = name or f"pista {id}"
        self.artist = type("A", (), {"name": artist or "artista"})()
        self.album = None
        self.duration = duration


@pytest.fixture
def entries():
    return [Entry(id=i, title=f"t{i}", artist="a") for i in range(5)]


@pytest.fixture
def queue_file(tmp_path, monkeypatch):
    """Point the queue's persistence at a temp file."""
    import tidalamp.queue as queue_module

    path = tmp_path / "queue.json"
    monkeypatch.setattr(queue_module, "QUEUE_FILE", path)
    monkeypatch.setattr(queue_module, "ensure_dirs", lambda: None)
    return path
