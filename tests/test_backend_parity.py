"""Each facade's backends offer the same names with the same signatures.

"The same API" is what lets a facade pick a backend without the app noticing;
this turns it from a promise into a check. It runs on Linux against both, so
the Windows backends must import anywhere (see backends/windows/__init__.py).
"""

from __future__ import annotations

import inspect

import pytest

from tidalamp import desktop, distro, mpris
from tidalamp.backends.linux import desktop as linux_desktop
from tidalamp.backends.linux import distro as linux_distro
from tidalamp.backends.linux import mpris as linux_mpris
from tidalamp.backends.windows import desktop as windows_desktop
from tidalamp.backends.windows import distro as windows_distro
from tidalamp.backends.windows import media as windows_media

PAIRS = [
    (distro, linux_distro, windows_distro),
    (desktop, linux_desktop, windows_desktop),
]


@pytest.mark.parametrize(
    ("facade", "linux", "windows", "name"),
    [
        (facade, linux, windows, name)
        for facade, linux, windows in PAIRS
        for name in facade.__all__
    ],
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_windows_offers_every_name_the_facade_exports(facade, linux, windows, name):
    ours, theirs = getattr(linux, name), getattr(windows, name)
    assert inspect.signature(theirs) == inspect.signature(ours)


def _public(cls) -> dict[str, object]:
    return {
        name: member
        for name, member in inspect.getmembers(cls)
        if not name.startswith("_")
    }


def test_the_media_backends_have_the_same_public_face():
    linux, windows = (
        _public(linux_mpris.MprisService),
        _public(windows_media.MprisService),
    )
    assert set(windows) == set(linux)
    for name, member in windows.items():
        if callable(member):
            assert inspect.signature(member) == inspect.signature(linux[name]), name


def test_the_facade_exports_the_contract():
    assert {"MediaService", "MprisService", "PlayerBackend"} <= set(mpris.__all__)
