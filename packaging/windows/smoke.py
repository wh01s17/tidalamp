"""Check a frozen build before it ships: python packaging/windows/smoke.py DIR

PyInstaller does not fail to build when a module or a stylesheet is missing;
the program fails when it reaches it. So this runs the program as far as it
goes without a TIDAL account, and looks for what it will read later.

`tidalamp tui` imports the whole player before it finds there is no session,
and says so with exit status 1. An import the build missed ends in a
traceback instead.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main(folder: str) -> int:
    root = Path(folder)
    exe = root / ("tidalamp.exe" if sys.platform == "win32" else "tidalamp")
    failures: list[str] = []

    version = subprocess.run([exe, "--version"], capture_output=True, text=True)
    if version.returncode != 0 or "tidalamp" not in version.stdout:
        failures.append(
            f"--version: {version.returncode} {version.stdout}{version.stderr}"
        )

    with tempfile.TemporaryDirectory() as home:
        env = {
            **os.environ,
            # A home of its own, so no real session is found on any system.
            "APPDATA": home,
            "LOCALAPPDATA": home,
            "XDG_CONFIG_HOME": home,
            "XDG_CACHE_HOME": home,
            "XDG_STATE_HOME": home,
            "TIDALAMP_LANG": "en",
            "TIDALAMP_NO_DESKTOP_ENTRY": "1",
        }
        tui = subprocess.run([exe, "tui"], capture_output=True, text=True, env=env)
    said = tui.stdout + tui.stderr
    if tui.returncode != 1 or "Traceback" in said or "login" not in said:
        failures.append(f"tui without a session: {tui.returncode}\n{said}")

    for sheet in ("base", "player", "compact", "looks", "themed"):
        if not any(root.rglob(f"tidalamp/styles/{sheet}.tcss")):
            failures.append(f"missing stylesheet: {sheet}.tcss")
    if not any(root.rglob("tidalamp/emblems/*.png")):
        failures.append("missing emblems")

    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if not failures:
        print(f"ok: {exe}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
