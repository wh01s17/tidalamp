"""Shared stubs.

The tests never touch TIDAL or the network: sessions, tracks and manifests are
plain stand-ins that expose only the attributes the code under test reads.
"""

from __future__ import annotations

import os

# Before importing anything of the package. A handful of strings are built
# when their module is imported — `BINDINGS` lists, the browser's hint bar —
# so by the time a fixture can call `i18n.use()` they are already in whatever
# language the developer's `$LANG` chose. The autouse fixture below still
# handles everything decided at run time; this handles what is decided at
# import time, which is the half that made the suite pass or fail on nothing
# but the terminal it was run from.
os.environ.setdefault("TIDALAMP_LANG", "es")

import pytest

from tidalamp.queue import Entry

# Everything `config.reload()` rebinds, which is everything a test can move.
_CONFIG_GLOBALS = (
    "FILE",
    "DEFAULT_QUALITY",
    "ARTWORK",
    "LANGUAGE",
    "THEME",
    "PALETTE",
    "ARRANGEMENT",
    "BACKDROP",
    "COVER_SHAPE",
    "DEBUG",
    "KEYS",
)


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


@pytest.fixture(autouse=True)
def clean_library_cache():
    """The browser's level cache is module state; keep it out of other tests."""
    from tidalamp import library

    library.forget()
    yield
    library.forget()


@pytest.fixture(autouse=True)
def spanish_interface():
    """The tests assert the strings as they are written in the source.

    Which language the interface picks depends on the developer's locale, and
    a suite that passes or fails on $LANG is no suite at all.
    """
    from tidalamp import i18n

    i18n.use("es")
    yield
    # refresh(), not _language(): the language is a setting now, and the
    # locale is only consulted when that setting says «auto».
    i18n.refresh()


@pytest.fixture(autouse=True)
def pristine_config(tmp_path_factory, monkeypatch):
    """Start every test from the shipped defaults, never the developer's own.

    Two separate traps, and both bit. The settings are module globals, so a
    test that switched the theme left every later test rendering the other
    one. And `config.FILE` is read at import time from
    `~/.config/tidalamp/config.toml`: a suite that does not point that
    somewhere empty passes or fails on whatever the developer last chose in
    the running app — which is how a green suite turned red halfway through
    an afternoon, with nothing but the config file having changed.
    """
    from tidalamp import config

    saved = {name: getattr(config, name) for name in _CONFIG_GLOBALS}
    for variable in config.ENV_VARS.values():
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(
        config, "CONFIG_FILE", tmp_path_factory.mktemp("config") / "config.toml"
    )
    config.reload()
    yield
    for name, value in saved.items():
        setattr(config, name, value)


@pytest.fixture(autouse=True)
def private_library_orders(tmp_path_factory, monkeypatch):
    """The browser remembers sort orders on disk; never in the developer's own
    state directory, and never from one test into the next."""
    from tidalamp import library

    monkeypatch.setattr(
        library, "ORDERS_FILE", tmp_path_factory.mktemp("state") / "library-orders.json"
    )
    monkeypatch.setattr(library, "_CHOSEN", None)
