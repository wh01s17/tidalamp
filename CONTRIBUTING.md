# Contributing

## First, two lines that are not crossed

1. **No DRM.** `stream.py` rejects encrypted manifests rather than decrypting them, and
   no audio is downloaded to disk. Patches that add decryption or download to a file are
   not accepted. This is not an aesthetic preference: it is what keeps the project clear
   of anti-circumvention law.
2. **No embedded credentials.** No API keys, no tokens, no client secrets of our own in
   the repository.

## Setting up

### Linux

```sh
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

You need `mpv` on the system. `cava` is optional (a real spectrum) and so is
`dbus-daemon` — without it the MPRIS integration skips itself rather than failing.

### Windows

In PowerShell, from Windows 10 or 11. Python 3.11 or newer, Git and mpv, once:

```powershell
winget install Python.Python.3.13 Git.Git shinchiro.mpv
winget install karlstav.cava          # optional: the real spectrum
```

Open a new terminal afterwards, so the PATH includes what was just installed.
winget's mpv installer leaves it off the PATH (in `Program Files\MPV Player`);
tidalamp finds it there on its own.

```powershell
git clone https://github.com/wh01s17/tidalamp.git
cd tidalamp
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
```

If PowerShell refuses to run scripts, nothing here needs it: every command above
calls `python.exe` directly and never `Activate.ps1`. On Windows some 50 tests are
skipped, the ones marked `@linux_only` (PipeWire, D-Bus, file modes, the `.desktop`
launcher); none should fail. The suite takes a few minutes, a little longer than on
Linux. It needs no mpv: it runs a fake one over a named pipe.

To run the player from the checkout:

```powershell
.venv\Scripts\tidalamp login
.venv\Scripts\tidalamp
$env:TIDALAMP_DEBUG = "1"; .venv\Scripts\tidalamp     # with the debug log
```

Where things live on Windows (on Linux, the XDG directories):

| | Path |
| --- | --- |
| Settings and session | `%APPDATA%\tidalamp\` (`config.toml`, `session.json`) |
| Queue, state, debug log | `%LOCALAPPDATA%\tidalamp\state\` (`tidalamp.log`) |
| Cache (covers, playlists for mpv) | `%LOCALAPPDATA%\tidalamp\cache\` |
| The Start menu shortcut | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\TidalAmp.lnk` |

Line endings are LF everywhere, Windows included: `.gitattributes` makes Git check
files out that way, so do not set `core.autocrlf`. If a test fails with a
`FileNotFoundError` that makes no sense, suspect the 260-character path limit and
enable long paths, or clone to a shorter directory such as `C:\src`.

The agent skills under `.agents/skills/` are not in the repository (`.gitignore`);
a fresh clone on Windows does not have them. `windows.md` and this file say what
they said.

## What has to pass before a commit

```sh
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/mypy --platform linux
.venv/bin/mypy --platform win32
.venv/bin/python -m pytest -q --cov
```

On Windows the same five, as `.venv\Scripts\ruff`, `.venv\Scripts\mypy` and
`.venv\Scripts\python -m pytest`. mypy checks both systems from either one.

All of it runs in CI, the suite on Linux and on Windows. mypy runs once per system
because each pass drops the other's branches: without the second, the Windows code
is never checked from Linux. That is also why platform code tests `sys.platform`
literally and never through a constant of our own, which mypy cannot see through. Coverage has a floor of 70%, which is a floor and not a target: it
exists so that a change which empties the tests fails instead of passing quietly.

`tidalamp/backends/linux/mpris.py` is excluded from mypy on purpose: its annotations are D-Bus
signatures (`"b"`, `"a{sv}"`), not Python types, and no checker can read them. In
exchange, that module has contract tests against a real bus in `tests/test_mpris.py`.

## Linux and Windows

What differs between the two lives in `tidalamp/backends/<system>/`, behind a facade
(`audio`, `mpris`, `desktop`, `distro`) that picks the backend and re-exports its
public names. `tests/test_backend_parity.py` checks that both backends offer the
same names with the same signatures. Patch a backend's internals on the backend
module: the facade only holds references. The plan, with its phases and traps, is
`windows.md`.

A test that only makes sense on one system is marked `@linux_only` or
`@windows_only` (from `conftest.py`) rather than deleted, so that it comes back the
day the other system has it. Do not simulate a write failure with `chmod`: it
protects nothing on Windows or from root. Make the write raise instead.

## How the tests are written here

They do not touch the network, TIDAL, or the user's session bus. There are doubles for
everything needed: `tests/fake_mpv.py` speaks the real IPC, `tests/fake_cava.py` emits
binary frames, and the MPRIS integration starts its own temporary `dbus-daemon`.

When you fix a bug, the test should say **what was breaking**, not only what the
function does. Plenty of the ones in this repository carry the symptom in the name or in
the docstring, and that is deliberate.

## Documentation

The split is by audience, not by preference: what a stranger reads is in English, and
what the maintainer reads is in Spanish.

- `README.md` and `CHANGELOG.md` are the public documentation, in English. So are the
  GitHub release notes.
- `plan.md` is the handover document, in Spanish: what exists, what has been verified
  and **the reasoning behind each decision**. If you make an architectural decision, it
  goes there, with the why. If you lose an afternoon to a trap, it goes in §7, so nobody
  repeats it.
- `next.md` is the queue of committed work for the next version, in Spanish: what goes
  in, why, the traps already known and how it gets checked. **When something there is
  done it is deleted from there**, and its trace goes to `CHANGELOG.md` as the user-
  facing line and to `plan.md` as the detail. A list that collects struck-out entries
  stops saying what is missing.
- `publish.md` is the release procedure, in Spanish: from the version to the tag and the
  AUR. `packaging/README.md` is its summary plus the packaging-specific decisions, also
  in Spanish: it is a companion to `publish.md`, not a door a stranger comes in through.
- This file is in English. Whoever reads it is deciding whether to contribute, and that
  is a stranger by definition.
- `CHANGELOG.md` is updated in the same commit as the change.

## Commit messages

Imperative, and explaining **why**, not only what. If the change comes out of a
measurement, the number goes in the message: that is what lets it be argued with later.
