"""Shared stubs.

The tests never touch TIDAL or the network: sessions, tracks and manifests are
plain stand-ins that expose only the attributes the code under test reads.
"""

from __future__ import annotations

import os
import sys

# Before importing anything of the package. A handful of strings are built
# when their module is imported — `BINDINGS` lists, the browser's hint bar —
# so by the time a fixture can call `i18n.use()` they are already in whatever
# language the developer's `$LANG` chose. The autouse fixture below still
# handles everything decided at run time; this handles what is decided at
# import time, which is the half that made the suite pass or fail on nothing
# but the terminal it was run from.
os.environ.setdefault("TIDALAMP_LANG", "es")
# Never write a launcher into the developer's own menu from a test.
os.environ.setdefault("TIDALAMP_NO_DESKTOP_ENTRY", "1")

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
    "AUTOPLAY",
    "OFFLINE",
    "DEBUG",
    "KEYS",
    "MPV_PATH",
    "EXCLUSIVE",
    "LOCAL_FOLDERS",
)

# What only one system has. `skipif` and not deleting: when the other system
# grows an implementation, the test comes back for free.
linux_only = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="sólo en Linux"
)
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="sólo en Windows")


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


class NetworkBlocked(RuntimeError):
    """A test reached for a host that is not this machine."""


# What a test may still connect to: this machine. mpv's IPC and D-Bus are
# Unix sockets and never resolve a name; the local HTTP server one test plays
# from listens on 127.0.0.1.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "", None}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Keep the promise at the top of this file: no test touches the network.

    It used to be a promise and not a rule, and it was broken without a word:
    every app test that put a row with `art_url="http://cover/1"` in the queue
    sent the cover worker to resolve `cover`, and `net.with_retries` read the
    DNS failure as a transient one and waited 0.6 s and 1.2 s before giving up.
    That was 1.8 s on the close of each of those tests — most of the suite's
    time — and a test that passed or failed on the machine's network.

    `RuntimeError` and not `OSError` on purpose: nothing in `net` counts it as
    transient, so the caller fails at once, the way an offline machine whose
    resolver answers immediately would.
    """
    import socket

    real = socket.getaddrinfo

    def local_only(host, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else host
        if name not in _LOCAL_HOSTS:
            raise NetworkBlocked(f"los tests no salen a la red: {name}")
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", local_only)


@pytest.fixture(autouse=True)
def clean_library_cache():
    """The browser's level cache is module state; keep it out of other tests."""
    from tidalamp import levels

    levels.forget()
    yield
    levels.forget()


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
    from tidalamp import levels

    monkeypatch.setattr(
        levels, "ORDERS_FILE", tmp_path_factory.mktemp("state") / "library-orders.json"
    )
    monkeypatch.setattr(levels, "_CHOSEN", None)


@pytest.fixture(autouse=True)
def private_local_index(tmp_path_factory, monkeypatch):
    """«Música local» keeps an index and covers in the cache: never the
    developer's own, and no scan carried from one test into the next."""
    from tidalamp import library, local

    folder = tmp_path_factory.mktemp("local-cache")
    monkeypatch.setattr(local, "INDEX_FILE", folder / "local-index.json")
    monkeypatch.setattr(local, "ART_DIR", folder / "local-art")
    monkeypatch.setattr(library, "_LOCAL", None)


@pytest.fixture(autouse=True)
def private_local_playlists(tmp_path_factory, monkeypatch):
    """The playlists of «Música local» are files: never the developer's."""
    from tidalamp import local_playlists

    folder = tmp_path_factory.mktemp("local-playlists")
    monkeypatch.setattr(local_playlists, "PLAYLIST_DIR", folder)


@pytest.fixture(autouse=True)
def private_session(tmp_path_factory, monkeypatch):
    """The session, the app's folders and the menu, never the developer's own.

    A logout that takes the data deletes all of them: a test that reached it
    through the settings window without pointing them somewhere else wiped
    whoever ran the suite, launcher included.
    """
    from tidalamp import auth, config
    from tidalamp.backends.linux import desktop

    folder = tmp_path_factory.mktemp("session")
    monkeypatch.setattr(auth, "SESSION_FILE", folder / "session.json")
    monkeypatch.setattr(desktop, "MARKER", folder / "desktop-entry")
    for name in ("CONFIG_DIR", "STATE_DIR", "CACHE_DIR"):
        monkeypatch.setattr(config, name, folder / name.lower())
    monkeypatch.setenv("XDG_DATA_HOME", str(folder / "data"))
