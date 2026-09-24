"""mpv goes when tidalamp goes, on Windows too.

Closing the terminal tidalamp ran in left mpv playing: Python is ended
without any cleanup, and mpv, with a hidden console of its own, never hears
the terminal close. Here the app is a child process running `Mpv` against the
fake, which lingers like a real mpv once its client is gone, and the app is
killed the way closing its console kills it: no `close()`, no `atexit`,
nothing of ours runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from conftest import windows_only

pytestmark = windows_only

FAKE = Path(__file__).parent / "fake_mpv.py"

APP = """
import sys, time
from tidalamp import config, player
config.IPC_PIPE = sys.argv[1]
player.ensure_dirs = lambda: None
mpv = player.Mpv(command=[sys.executable, sys.argv[2]])
if sys.argv[3] == "restart":
    mpv.restart()
print(mpv._proc.pid, flush=True)
time.sleep(60)
"""


def _ends_within(pid: int, seconds: float, *, kill: bool = False) -> bool:
    """Whether ``pid`` exits within ``seconds``. With ``kill``, one that does
    not is ended here, so a failing test leaves no fake mpv playing on."""
    import _winapi

    synchronize, terminate = 0x00100000, 0x0001
    try:
        handle = _winapi.OpenProcess(synchronize | terminate, False, pid)
    except OSError:
        return True  # already gone, handle and all
    try:
        waited = _winapi.WaitForSingleObject(handle, int(seconds * 1000))
        if waited == _winapi.WAIT_OBJECT_0:
            return True
        if kill:
            _winapi.TerminateProcess(handle, 1)
        return False
    finally:
        _winapi.CloseHandle(handle)


@pytest.mark.parametrize("when", ["start", "restart"])
def test_killing_the_app_takes_mpv_with_it(when):
    """Also the mpv a restart brings back, which is a new process."""
    pipe = rf"\\.\pipe\tidalamp-test-{uuid.uuid4().hex}"
    app = subprocess.Popen(
        [sys.executable, "-c", APP, pipe, str(FAKE), when],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "FAKE_MPV_LINGER": "1"},
    )
    try:
        assert app.stdout is not None
        mpv_pid = int(app.stdout.readline())
        assert not _ends_within(mpv_pid, 0.2)  # it is up while the app is
    finally:
        app.kill()
        app.wait(timeout=5)
    assert _ends_within(mpv_pid, 5, kill=True), "mpv outlived the app"
